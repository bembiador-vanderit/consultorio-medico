from datetime import datetime
from hashlib import sha256
from fastapi import HTTPException
from sqlalchemy import event, inspect, select
from sqlalchemy.orm import Session
from app.models import Role, User
from app.models.administration import ReauthenticationGrant, SecurityAudit

RESTRICTABLE = {"patients:access", "clinical:access"}

def effective_permissions(user: User) -> set[str]:
    permissions = {p.code for role in user.roles for p in role.permissions}
    if not any(role.code == "doctor" for role in user.roles):
        permissions.discard("clinical:access")
    return permissions - set(user.denied_permissions or [])

def lock_administration(db: Session) -> None:
    # One database lock shared by all administrative writers.
    db.execute(select(Role.id).where(Role.code == "admin").with_for_update()).all()

def audit(db: Session, actor: User, action: str, outcome: str = "success") -> None:
    db.add(SecurityAudit(actor_id=actor.id, action=action, outcome=outcome))

def authorize_sensitive_write(db: Session, user: User, action: str, grant_id: str | None) -> None:
    version = user.session_version
    lock_administration(db)
    db.refresh(user)
    db.expire(user, ["roles"])
    if not user.is_active or version != user.session_version:
        raise HTTPException(401, "La sesión cambió; vuelva a iniciar sesión")
    grant = db.scalar(select(ReauthenticationGrant).where(
        ReauthenticationGrant.id == sha256(grant_id.encode()).hexdigest(),
    ).with_for_update()) if grant_id else None
    if (not grant or grant.user_id != user.id or grant.session_version != user.session_version
            or grant.action != action or grant.consumed or grant.expires_at <= datetime.utcnow()):
        raise HTTPException(428, "Confirme su contraseña para esta operación")
    grant.consumed = True
    # Audit and consumption commit atomically with the protected mutation.
    audit(db, user, action)

@event.listens_for(Session, "before_flush")
def revoke_changed_identities(db: Session, _flush_context, _instances) -> None:
    for user in list(db.dirty):
        if not isinstance(user, User):
            continue
        state = inspect(user)
        if any(state.attrs[name].history.has_changes() for name in (
            "password_hash", "email", "is_active", "roles", "denied_permissions", "centers",
        )):
            user.session_version = (user.session_version or 0) + 1
