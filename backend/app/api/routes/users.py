from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session
from app.api.deps import require_permission
from app.core.security import hash_password
from app.db import get_db
from app.models import Role, User
from app.schemas.auth import UserCreate, UserResponse

router = APIRouter(prefix="/users", tags=["Usuarios"])
def serialize(user: User) -> UserResponse: return UserResponse(id=user.id, email=user.email, full_name=user.full_name, is_active=user.is_active, roles=[r.code for r in user.roles])
@router.get("", response_model=list[UserResponse])
def list_users(_: User = Depends(require_permission("users:manage")), db: Session = Depends(get_db)): return [serialize(user) for user in db.scalars(select(User)).all()]
@router.post("", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
def create_user(payload: UserCreate, _: User = Depends(require_permission("users:manage")), db: Session = Depends(get_db)):
    if db.scalar(select(User).where(User.email == str(payload.email).lower())): raise HTTPException(status_code=409, detail="El correo ya está registrado")
    roles = db.scalars(select(Role).where(Role.code.in_(payload.role_codes))).all()
    if len(roles) != len(set(payload.role_codes)): raise HTTPException(status_code=422, detail="Rol inválido")
    user = User(email=str(payload.email).lower(), full_name=payload.full_name, password_hash=hash_password(payload.password), roles=list(roles))
    db.add(user); db.commit(); db.refresh(user); return serialize(user)
