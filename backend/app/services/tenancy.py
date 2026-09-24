"""One immutable tenant boundary per request/session, including background jobs.

Unscoped SQLAlchemy Sessions are reserved for migrations and provisioning. HTTP
always binds a scope before authentication; scope cannot be supplied by a client.
"""
from fastapi import HTTPException, Request
from sqlalchemy import event, inspect, select
from sqlalchemy.orm import Session, with_loader_criteria

from app.core.config import get_settings
from app.models.organization import Organization, OrganizationMembership, TenantOwned


def bind_scope(db: Session, scope: str, organization_id: int | None = None) -> None:
    if "access_scope" in db.info:
        if (db.info["access_scope"], db.info.get("organization_id")) != (scope, organization_id):
            raise RuntimeError("A session cannot switch access contexts")
        return
    if db.identity_map:
        raise RuntimeError("Bind scope before loading identities")
    db.info.update(access_scope=scope, organization_id=organization_id)


def resolve_request(db: Session, request: Request) -> None:
    settings = get_settings()
    # Deliberately do not trust X-Forwarded-Host, Origin or a tenant header.
    host = request.url.hostname
    if not host:
        raise HTTPException(404, "Contexto no disponible")
    host = host.lower().rstrip(".")
    if host in settings.platform_hosts:
        bind_scope(db, "platform")
        return
    slug = settings.tenant_hosts.get(host)
    if not slug:
        raise HTTPException(404, "Contexto no disponible")
    row = db.execute(select(Organization.id).where(Organization.slug == slug, Organization.is_active.is_(True))).first()
    if row is None:
        raise HTTPException(404, "Contexto no disponible")
    bind_scope(db, "tenant", row.id)


def context_claims(db: Session) -> dict:
    if "access_scope" not in db.info:
        return {}  # Unit/legacy maintenance callers; never reached by HTTP get_db.
    return {"scope": db.info["access_scope"], "org": db.info.get("organization_id")}


def validate_context(db: Session, payload: dict) -> None:
    if context_claims(db) and any(payload.get(key) != value for key, value in context_claims(db).items()):
        raise HTTPException(401, "Sesión inválida para este contexto")


@event.listens_for(Session, "do_orm_execute")
def scope_queries(state):
    db = state.session
    if "access_scope" not in db.info:
        return
    from app.models.identity import User
    org_id = db.info.get("organization_id") or -1
    if state.is_select or state.is_update or state.is_delete:
        state.statement = state.statement.options(
            with_loader_criteria(TenantOwned, lambda cls: cls.organization_id == org_id, include_aliases=True),
        )
        if db.info["access_scope"] == "tenant":
            state.statement = state.statement.options(with_loader_criteria(
                User, lambda cls: cls.memberships.any(OrganizationMembership.organization_id == org_id), include_aliases=True,
            ))
            state.statement = state.statement.options(with_loader_criteria(
                Organization, lambda cls: cls.id == org_id, include_aliases=True,
            ))
    # Core secondary tables do not receive ORM loader criteria. Their ownership
    # comes from a tenant-owned endpoint, not from the global user's id.
    from app.models.center import user_centers
    from app.models import CareCenter
    statement = state.statement
    if state.is_select and not state.is_relationship_load:
        froms = statement.get_final_froms()
        if user_centers in froms:
            state.statement = statement.where(user_centers.c.center_id.in_(
                select(CareCenter.id).where(CareCenter.organization_id == org_id)))
    if (state.is_update or state.is_delete) and getattr(statement, "table", None) is not None:
        if statement.table.name == "user_centers":
            state.statement = statement.where(user_centers.c.center_id.in_(
                select(CareCenter.id).where(CareCenter.organization_id == org_id)))


def _not_found():
    raise HTTPException(404, "Recurso no disponible en este contexto")


@event.listens_for(Session, "before_flush")
def scope_writes(db, _context, _instances):
    if "access_scope" not in db.info:
        return
    from app.models.identity import User, Role, Permission
    org_id = db.info.get("organization_id")
    # Provision new users inside this organization without retaining global roles.
    for obj in list(db.new):
        if isinstance(obj, User):
            if not org_id:
                _not_found()
            membership = OrganizationMembership(organization_id=org_id, state="active",
                roles=list(obj.legacy_roles), denied_permissions=list(obj.legacy_denied_permissions or []))
            obj.legacy_roles = []
            obj.memberships.append(membership)
    for obj in list(db.new) + list(db.dirty) + list(db.deleted):
        if isinstance(obj, (Role, Permission, Organization)) and (obj in db.new or obj in db.deleted or db.is_modified(obj, include_collections=False)):
            _not_found()  # Catalog authority/provisioning has no tenant HTTP write path.
        if isinstance(obj, TenantOwned):
            if not org_id:
                _not_found()
            if obj in db.new and obj.organization_id is None:
                obj.organization_id = org_id
            if obj.organization_id != org_id:
                _not_found()
            attr = inspect(obj).attrs.organization_id
            if obj not in db.new and attr.history.has_changes():
                _not_found()
            # Validate every FK, including input ids that bypass relationship setters.
            for column in inspect(obj).mapper.columns:
                value = getattr(obj, column.key)
                if value is None:
                    continue
                for fk in column.foreign_keys:
                    table = fk.column.table
                    if table.name == "organizations":
                        continue
                    if "organization_id" in table.c:
                        exists = db.connection().execute(select(fk.column).where(
                            fk.column == value, table.c.organization_id == org_id)).first()
                        if exists is None:
                            _not_found()
                    elif table.name == "users" and not isinstance(obj, OrganizationMembership):
                        exists = db.scalar(select(OrganizationMembership.id).where(
                            OrganizationMembership.user_id == value, OrganizationMembership.organization_id == org_id))
                        if exists is None:
                            _not_found()
        # Relationship changes can write association rows without scalar FK history.
        for rel in inspect(obj).mapper.relationships:
            for related in inspect(obj).attrs[rel.key].history.added:
                if isinstance(related, TenantOwned) and related.organization_id not in (None, org_id):
                    _not_found()
                if isinstance(related, User) and related not in db.new:
                    if not db.scalar(select(OrganizationMembership.id).where(OrganizationMembership.user_id == related.id)):
                        _not_found()


def protect_shared_identity(db: Session, user) -> None:
    """A tenant admin cannot change credentials/profile used in another tenant."""
    if db.info.get("access_scope") != "tenant":
        return
    table = OrganizationMembership.__table__
    other = db.connection().execute(select(table.c.id).where(
        table.c.user_id == user.id, table.c.organization_id != db.info["organization_id"])).first()
    if other or user.is_platform_admin:
        raise HTTPException(409, "Esta identidad requiere gestión de cuenta fuera del contexto de organización")
