from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import delete, func, insert, select
from sqlalchemy.orm import Session

from app.api.deps import require_permission
from app.core.security import hash_password
from app.db import get_db
from app.models import CareCenter, Role, User
from app.models.center import user_centers
from app.schemas.auth import UserCreate
from app.schemas.user import (
    UserAdminResponse,
    UserCentersUpdate,
    UserPasswordUpdate,
    UserProfileUpdate,
    UserRolesUpdate,
    UserStatusUpdate,
)

router = APIRouter(prefix="/users", tags=["Usuarios"])
manage = require_permission("users:manage")


def is_role(user: User, code: str) -> bool:
    return any(role.code == code for role in user.roles)


def require_user(db: Session, user_id: int) -> User:
    user = db.get(User, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="Usuario no encontrado")
    return user


def validate_password_strength(password: str) -> None:
    if not any(character.isalpha() for character in password) or not any(character.isdigit() for character in password):
        raise HTTPException(status_code=422, detail="La contraseña debe contener al menos una letra y un número")


def active_admin_count(db: Session) -> int:
    return db.scalar(
        select(func.count(User.id))
        .join(User.roles)
        .where(User.is_active.is_(True), Role.code == "admin")
    ) or 0


def serialize(user: User, db: Session) -> UserAdminResponse:
    assignments = db.execute(
        select(user_centers.c.center_id, user_centers.c.is_primary)
        .where(user_centers.c.user_id == user.id)
        .order_by(user_centers.c.center_id)
    ).all()
    return UserAdminResponse(
        id=user.id,
        email=user.email,
        full_name=user.full_name,
        is_active=user.is_active,
        roles=[role.code for role in user.roles],
        center_ids=[row.center_id for row in assignments],
        primary_center_id=next((row.center_id for row in assignments if row.is_primary), None),
    )


def validate_roles(db: Session, role_codes: list[str]) -> list[Role]:
    unique_codes = set(role_codes)
    roles = list(db.scalars(select(Role).where(Role.code.in_(unique_codes))).all())
    if len(roles) != len(unique_codes):
        raise HTTPException(status_code=422, detail="Rol inválido")
    return roles


@router.get("", response_model=list[UserAdminResponse])
def list_users(_: User = Depends(manage), db: Session = Depends(get_db)):
    return [serialize(user, db) for user in db.scalars(select(User).order_by(User.full_name)).all()]


@router.post("", response_model=UserAdminResponse, status_code=status.HTTP_201_CREATED)
def create_user(payload: UserCreate, _: User = Depends(manage), db: Session = Depends(get_db)):
    email = str(payload.email).strip().lower()
    full_name = payload.full_name.strip()
    if len(full_name) < 2:
        raise HTTPException(status_code=422, detail="El nombre completo es obligatorio")
    if db.scalar(select(User).where(func.lower(User.email) == email)):
        raise HTTPException(status_code=409, detail="El correo ya está registrado")
    roles = validate_roles(db, payload.role_codes)
    validate_password_strength(payload.password)
    user = User(
        email=email,
        full_name=full_name,
        password_hash=hash_password(payload.password),
        roles=roles,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return serialize(user, db)


@router.patch("/{user_id}/profile", response_model=UserAdminResponse)
def update_user_profile(user_id: int, payload: UserProfileUpdate, admin: User = Depends(manage), db: Session = Depends(get_db)):
    user = require_user(db, user_id)
    email = str(payload.email).strip().lower()
    full_name = payload.full_name.strip()
    if len(full_name) < 2:
        raise HTTPException(status_code=422, detail="El nombre completo es obligatorio")
    if user.id == admin.id and email != user.email:
        raise HTTPException(status_code=422, detail="Otro administrador debe cambiar su correo electrónico")
    duplicate = db.scalar(select(User).where(func.lower(User.email) == email, User.id != user.id))
    if duplicate:
        raise HTTPException(status_code=409, detail="El correo ya está registrado")
    user.full_name = full_name
    user.email = email
    db.commit()
    db.refresh(user)
    return serialize(user, db)


@router.put("/{user_id}/password", response_model=UserAdminResponse)
def update_user_password(user_id: int, payload: UserPasswordUpdate, _: User = Depends(manage), db: Session = Depends(get_db)):
    user = require_user(db, user_id)
    validate_password_strength(payload.new_password)
    user.password_hash = hash_password(payload.new_password)
    db.commit()
    db.refresh(user)
    return serialize(user, db)


@router.put("/{user_id}/status", response_model=UserAdminResponse)
def update_user_status(user_id: int, payload: UserStatusUpdate, admin: User = Depends(manage), db: Session = Depends(get_db)):
    user = require_user(db, user_id)
    if not payload.is_active and user.is_active and is_role(user, "admin") and active_admin_count(db) <= 1:
        raise HTTPException(status_code=409, detail="No se puede desactivar al último administrador activo")
    if not payload.is_active and user.id == admin.id:
        raise HTTPException(status_code=422, detail="Un administrador no puede desactivar su propia cuenta")
    user.is_active = payload.is_active
    db.commit()
    db.refresh(user)
    return serialize(user, db)


@router.put("/{user_id}/roles", response_model=UserAdminResponse)
def update_user_roles(user_id: int, payload: UserRolesUpdate, admin: User = Depends(manage), db: Session = Depends(get_db)):
    user = require_user(db, user_id)
    roles = validate_roles(db, payload.role_codes)
    removing_admin = is_role(user, "admin") and not any(role.code == "admin" for role in roles)
    if removing_admin and user.is_active and active_admin_count(db) <= 1:
        raise HTTPException(status_code=409, detail="No se puede quitar el rol al último administrador activo")
    if removing_admin and user.id == admin.id:
        raise HTTPException(status_code=422, detail="Un administrador no puede retirar su propio rol admin")
    user.roles = roles
    db.commit()
    db.refresh(user)
    return serialize(user, db)


@router.put("/{user_id}/centers", response_model=UserAdminResponse)
def update_user_centers(user_id: int, payload: UserCentersUpdate, _: User = Depends(manage), db: Session = Depends(get_db)):
    user = require_user(db, user_id)
    center_ids = set(payload.center_ids)
    if len(center_ids) != len(payload.center_ids):
        raise HTTPException(status_code=422, detail="Los centros no pueden repetirse")
    if payload.primary_center_id is not None and payload.primary_center_id not in center_ids:
        raise HTTPException(status_code=422, detail="El centro principal debe estar asignado al usuario")

    current_ids = set(db.scalars(select(user_centers.c.center_id).where(user_centers.c.user_id == user.id)).all())
    centers = list(db.scalars(select(CareCenter).where(CareCenter.id.in_(center_ids))).all()) if center_ids else []
    if len(centers) != len(center_ids):
        raise HTTPException(status_code=422, detail="Centro de atención inválido")
    if any(not center.is_active for center in centers if center.id not in current_ids):
        raise HTTPException(status_code=422, detail="No se puede asignar un centro inactivo")
    if not user.is_active and not center_ids.issubset(current_ids):
        raise HTTPException(status_code=422, detail="No se pueden agregar centros a un usuario inactivo")

    db.execute(delete(user_centers).where(user_centers.c.user_id == user.id))
    if center_ids:
        db.execute(insert(user_centers), [
            {"user_id": user.id, "center_id": center_id, "is_primary": center_id == payload.primary_center_id}
            for center_id in sorted(center_ids)
        ])
    db.commit()
    return serialize(user, db)
