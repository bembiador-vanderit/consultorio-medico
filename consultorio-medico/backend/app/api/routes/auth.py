from datetime import datetime, timedelta, timezone

import jwt
from fastapi import APIRouter, Cookie, Depends, HTTPException, Response, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import current_user
from app.core.config import get_settings
from app.core.security import create_access_token, verify_password
from app.db import get_db
from app.models import User
from app.schemas.auth import LoginRequest, TokenResponse, UserResponse

router = APIRouter(prefix="/auth", tags=["Autenticación"])

REFRESH_COOKIE = "consultorio_refresh"
REFRESH_DAYS = 7


def serialize(user: User) -> UserResponse:
    return UserResponse(id=user.id, email=user.email, full_name=user.full_name, is_active=user.is_active, roles=[r.code for r in user.roles])


def create_refresh_token(subject: str) -> str:
    settings = get_settings()
    expires = datetime.now(timezone.utc) + timedelta(days=REFRESH_DAYS)
    return jwt.encode({"sub": subject, "type": "refresh", "exp": expires}, settings.secret_key, algorithm="HS256")


def set_refresh_cookie(response: Response, token: str) -> None:
    settings = get_settings()
    response.set_cookie(
        key=REFRESH_COOKIE,
        value=token,
        httponly=True,
        secure=settings.environment == "production",
        samesite="lax",
        max_age=REFRESH_DAYS * 24 * 60 * 60,
        path="/api/v1/auth",
    )


@router.post("/login", response_model=TokenResponse)
def login(payload: LoginRequest, response: Response, db: Session = Depends(get_db)):
    user = db.scalar(select(User).where(User.email == str(payload.email).lower()))
    if not user or not user.is_active or not verify_password(payload.password, user.password_hash):
        raise HTTPException(status_code=401, detail="Credenciales inválidas")
    set_refresh_cookie(response, create_refresh_token(user.email))
    return TokenResponse(access_token=create_access_token(user.email))


@router.post("/refresh", response_model=TokenResponse)
def refresh(refresh_token: str | None = Cookie(default=None, alias=REFRESH_COOKIE), db: Session = Depends(get_db)):
    if not refresh_token:
        raise HTTPException(status_code=401, detail="Sesión expirada")
    try:
        payload = jwt.decode(refresh_token, get_settings().secret_key, algorithms=["HS256"])
        if payload.get("type") != "refresh":
            raise jwt.InvalidTokenError()
        email = payload["sub"]
    except (jwt.InvalidTokenError, KeyError, TypeError):
        raise HTTPException(status_code=401, detail="Sesión expirada")
    user = db.scalar(select(User).where(User.email == email))
    if not user or not user.is_active:
        raise HTTPException(status_code=401, detail="Usuario no disponible")
    return TokenResponse(access_token=create_access_token(user.email))


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(response: Response):
    response.delete_cookie(REFRESH_COOKIE, path="/api/v1/auth")


@router.get("/me", response_model=UserResponse)
def me(user: User = Depends(current_user)): return serialize(user)
