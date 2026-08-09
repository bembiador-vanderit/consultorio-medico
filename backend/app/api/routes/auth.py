from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session
from app.api.deps import current_user
from app.core.security import create_access_token, verify_password
from app.db import get_db
from app.models import User
from app.schemas.auth import LoginRequest, TokenResponse, UserResponse

router = APIRouter(prefix="/auth", tags=["Autenticación"])
def serialize(user: User) -> UserResponse: return UserResponse(id=user.id, email=user.email, full_name=user.full_name, is_active=user.is_active, roles=[r.code for r in user.roles])
@router.post("/login", response_model=TokenResponse)
def login(payload: LoginRequest, db: Session = Depends(get_db)):
    user = db.scalar(select(User).where(User.email == str(payload.email).lower()))
    if not user or not user.is_active or not verify_password(payload.password, user.password_hash): raise HTTPException(status_code=401, detail="Credenciales inválidas")
    return TokenResponse(access_token=create_access_token(user.email))
@router.get("/me", response_model=UserResponse)
def me(user: User = Depends(current_user)): return serialize(user)
