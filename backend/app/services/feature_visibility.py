"""FEATURE != VISIBILITY != PERMISSION != ENTITLEMENT.

This resolver returns presentation decisions, never clinical access grants.
No process cache: every resolution observes current PostgreSQL configuration.
"""
from datetime import datetime, timezone
from fastapi import HTTPException
from sqlalchemy import inspect, select
from app.models import CareCenter, Organization
from app.models.feature_visibility import FeatureVisibilitySetting
from app.models.clinical_audit import ClinicalAuditLog
from app.services.administration import effective_permissions
from app.services.appointment_scope import assigned_center_ids, is_role

FEATURES = ("clinical_safety_full", "clinical_safety_critical_alert")
AUDIENCES = ("doctor", "secretary")
CONTEXTS = ("ambulatory",)


def available(db):
    return inspect(db.connection()).has_table("feature_visibility_settings")


def audience_for(user):
    # User.roles already resolves the active organization membership. In a
    # mixed admin/doctor account the clinical presentation is the doctor one.
    for role, audience in (("doctor", "doctor"), ("secretary", "secretary"), ("admin", "administrator")):
        if is_role(user, role):
            return audience
    return "other_clinical"


def ensure_tenant(db):
    if db.info.get("access_scope") != "tenant" or not db.info.get("organization_id"):
        raise HTTPException(403, "La configuración requiere una organización activa")


def authorize_admin(db, user):
    ensure_tenant(db)
    membership = user.tenant_membership()
    if not user.is_active or not membership or membership.state != "active" or not is_role(user, "admin") or "users:manage" not in effective_permissions(user):
        raise HTTPException(403, "No tiene permiso para configurar visibilidad")


def validate_center(db, user, center_id, *, administrative=False):
    if center_id is None:
        return
    center = db.get(CareCenter, center_id)
    if not center or center.organization_id != db.info["organization_id"] or not center.is_active:
        raise HTTPException(404, "Centro no disponible")
    if not administrative and not is_role(user, "admin") and center_id not in assigned_center_ids(user):
        raise HTTPException(403, "Centro fuera de su alcance")


def resolve(db, *, center_id, context_code, audience, feature_code):
    ensure_tenant(db)
    # V1 registry is intentionally limited. Future codes require an explicit
    # integration, not automatic navigation or a commercial entitlement.
    if feature_code not in FEATURES or context_code not in CONTEXTS:
        return {"visible": False, "source": "system_default"}
    if available(db):
        query = select(FeatureVisibilitySetting).where(
            FeatureVisibilitySetting.feature_code == feature_code,
            FeatureVisibilitySetting.context_code == context_code,
            FeatureVisibilitySetting.audience == audience)
        if center_id is not None:
            row = db.scalar(query.where(FeatureVisibilitySetting.center_id == center_id))
            if row:
                return {"visible": row.visibility_mode == "visible", "source": "center"}
        row = db.scalar(query.where(FeatureVisibilitySetting.center_id.is_(None)))
        if row:
            return {"visible": row.visibility_mode == "visible", "source": "organization"}
    return {"visible": False, "source": "system_default"}


def settings_view(db, center_id):
    enabled = available(db)
    rows = list(db.scalars(select(FeatureVisibilitySetting).where(
        FeatureVisibilitySetting.center_id == center_id if center_id is not None else FeatureVisibilitySetting.center_id.is_(None)))) if enabled else []
    keyed = {(r.feature_code, r.context_code, r.audience): r for r in rows}
    items = []
    for feature in FEATURES:
        for audience in AUDIENCES:
            row = keyed.get((feature, "ambulatory", audience))
            items.append({"feature_code": feature, "context_code": "ambulatory", "audience": audience,
                "visibility_mode": row.visibility_mode if row else None, "revision": row.revision if row else 0,
                **resolve(db, center_id=center_id, context_code="ambulatory", audience=audience, feature_code=feature)})
    return {"enabled": enabled, "center_id": center_id, "items": items,
            "centers": [{"id": c.id, "name": c.name} for c in db.scalars(select(CareCenter).where(CareCenter.is_active.is_(True)).order_by(CareCenter.name))]}


def update(db, user, center_id, payload):
    authorize_admin(db, user)
    validate_center(db, user, center_id, administrative=True)
    if not available(db):
        raise HTTPException(503, "Visibilidad pendiente de activación de la base")
    # Stable organization lock serializes first insert, updates and inheritance.
    org_id = db.info["organization_id"]
    db.scalar(select(Organization).where(Organization.id == org_id).with_for_update())
    for change in payload.changes:
        row = db.scalar(select(FeatureVisibilitySetting).where(
            FeatureVisibilitySetting.center_id == center_id if center_id is not None else FeatureVisibilitySetting.center_id.is_(None),
            FeatureVisibilitySetting.feature_code == change.feature_code,
            FeatureVisibilitySetting.context_code == change.context_code,
            FeatureVisibilitySetting.audience == change.audience))
        previous_revision = row.revision if row else 0
        if change.revision != previous_revision:
            raise HTTPException(409, "La visibilidad cambió; vuelva a cargarla")
        before = row.visibility_mode if row else None
        if before == change.visibility_mode:
            continue
        if change.visibility_mode is None:
            db.delete(row)
        else:
            if row is None:
                row = FeatureVisibilitySetting(organization_id=org_id, center_id=center_id,
                    feature_code=change.feature_code, context_code=change.context_code, audience=change.audience)
                db.add(row)
            else:
                row.revision += 1
            row.visibility_mode = change.visibility_mode
            row.updated_by_user_id = user.id
            row.reason = payload.reason
            row.updated_at = datetime.now(timezone.utc)
            db.flush()
        # Snapshot the resulting LOCAL setting revision in this transaction.
        # Removing an override resumes inheritance: local revision is then 0,
        # exactly as settings_view exposes it. Keep the removed revision too.
        revision = 0 if change.visibility_mode is None else row.revision
        db.add(ClinicalAuditLog(organization_id=org_id, center_id=center_id, user_id=user.id,
            action="feature_visibility.updated", resource_type="feature_visibility_setting", resource_id=row.id,
            outcome="success", context={"feature_code": change.feature_code, "context_code": change.context_code,
                "audience": change.audience, "before": before, "after": change.visibility_mode,
                "previous_revision": previous_revision, "revision": revision, "reason": payload.reason}))
    db.commit()
    return settings_view(db, center_id)
