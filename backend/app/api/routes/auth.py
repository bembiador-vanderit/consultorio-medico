from datetime import datetime, timedelta, timezone
import jwt
from fastapi import APIRouter, Cookie, Depends, HTTPException, Response, status
from sqlalchemy import select
from sqlalchemy.orm import Session, object_session
from app.services.tenancy import context_claims, validate_context
from app.api.deps import current_user
from app.services.administration import effective_permissions
from app.core.config import get_settings
from app.core.security import create_access_token, verify_password
from app.db import get_db
from app.models import User
from app.schemas.auth import LoginRequest, TokenResponse, UserResponse
router = APIRouter(prefix="/auth", tags=["Autenticación"])
REFRESH_COOKIE = "consultorio_refresh"
REFRESH_DAYS = 7

def serialize(user: User) -> UserResponse:
    db = object_session(user)
    context = context_claims(db) if db else {}
    membership = user.tenant_membership()
    profile = user.doctor_profile
    specialties = sorted(user.specialties, key=lambda item: (item.name.lower(), item.id))
    return UserResponse(
        access_scope=context.get("scope", "tenant"),
        organization={"id": membership.organization.id, "name": membership.organization.name} if membership else None,
        membership_state=membership.state if membership else None,
        id=user.id, email=user.email, full_name=user.full_name, is_active=user.is_active,
        roles=[r.code for r in user.roles],
        permissions=sorted(effective_permissions(user)),
        denied_permissions=user.denied_permissions or [],
        primary_specialty_id=profile.specialty_id if profile else None,
        specialty_ids=[specialty.id for specialty in specialties],
        specialty_names=[specialty.name for specialty in specialties],
    )

def create_refresh_token(subject: str, session_version: int = 0, user_id: int | None = None, context: dict | None = None) -> str:
    settings = get_settings()
    expires = datetime.now(timezone.utc) + timedelta(days=REFRESH_DAYS)
    return jwt.encode({"sub": subject, "type": "refresh", "uid": user_id, "sv": session_version, "exp": expires, **(context or {})}, settings.secret_key, algorithm="HS256")

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

def check_membership(db, user):
    if db.info.get("access_scope") == "platform" and not user.is_platform_admin:
        raise HTTPException(401, "Credenciales inválidas")
    if db.info.get("access_scope") == "tenant":
        membership = user.tenant_membership()
        if membership is None or membership.state != "active":
            raise HTTPException(401, "Credenciales inválidas")

@router.post("/login", response_model=TokenResponse)
def login(payload: LoginRequest, response: Response, db: Session = Depends(get_db)):
    user = db.scalar(select(User).where(User.email == str(payload.email).lower()))
    if not user or not user.is_active or not verify_password(payload.password, user.password_hash):
        raise HTTPException(status_code=401, detail="Credenciales inválidas")
    check_membership(db, user)
    set_refresh_cookie(response, create_refresh_token(user.email, user.session_version, user.id, context_claims(db)))
    check_membership(db, user)
    return TokenResponse(access_token=create_access_token(user.email, user.session_version, user.id, context_claims(db)))

@router.post("/refresh", response_model=TokenResponse)
def refresh(refresh_token: str | None = Cookie(default=None, alias=REFRESH_COOKIE), db: Session = Depends(get_db)):
    if not refresh_token:
        raise HTTPException(status_code=401, detail="Sesión expirada")
    try:
        payload = jwt.decode(refresh_token, get_settings().secret_key, algorithms=["HS256"], options={"require": ["sub", "exp", "type", "sv", "uid"]})
        if payload.get("type") != "refresh":
            raise jwt.InvalidTokenError()
        email = payload["sub"]
    except (jwt.InvalidTokenError, KeyError, TypeError):
        raise HTTPException(status_code=401, detail="Sesión expirada")
    validate_context(db, payload)
    user = db.scalar(select(User).where(User.email == email, User.id == payload["uid"]))
    if not user or not user.is_active or payload.get("sv") != user.session_version:
        raise HTTPException(status_code=401, detail="Usuario no disponible")
    check_membership(db, user)
    return TokenResponse(access_token=create_access_token(user.email, user.session_version, user.id, context_claims(db)))

@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(response: Response):
    response.delete_cookie(REFRESH_COOKIE, path="/api/v1/auth")

@router.get("/me", response_model=UserResponse)
def me(user: User = Depends(current_user)): return serialize(user)
