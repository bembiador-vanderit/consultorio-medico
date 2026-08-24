from sqlalchemy import select
from sqlalchemy.orm import Session
from app.core.config import get_settings
from app.core.security import hash_password
from app.models import Permission, Role, User

ROLE_PERMISSIONS = {"admin": ("Administrador", ["users:manage", "patients:access"]), "doctor": ("Doctor", ["patients:access"]), "secretary": ("Secretaria", ["patients:access"])}
def seed_identity(db: Session) -> None:
    permissions = {}
    for code in {item for _, values in ROLE_PERMISSIONS.items() for item in values[1]}:
        permission = db.scalar(select(Permission).where(Permission.code == code))
        if permission is None: permission = Permission(code=code, description=code)
        db.add(permission); permissions[code] = permission
    db.flush(); roles = {}
    for code, (name, codes) in ROLE_PERMISSIONS.items():
        role = db.scalar(select(Role).where(Role.code == code)) or Role(code=code, name=name)
        role.permissions = [permissions[item] for item in codes]; db.add(role); roles[code] = role
    db.flush(); settings = get_settings()
    if settings.initial_admin_email and settings.initial_admin_password and db.scalar(select(User).where(User.email == settings.initial_admin_email.lower())) is None:
        db.add(User(email=settings.initial_admin_email.lower(), full_name=settings.initial_admin_name, password_hash=hash_password(settings.initial_admin_password), roles=[roles["admin"]]))
    db.commit()
