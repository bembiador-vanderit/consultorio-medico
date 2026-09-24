import jwt
from fastapi import Depends, HTTPException, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.orm import Session
from app.core.config import get_settings
from app.db import get_db
from app.models import User
from app.services.administration import authorize_sensitive_write, effective_permissions
bearer = HTTPBearer()
def current_user(request: Request, credentials: HTTPAuthorizationCredentials = Depends(bearer), db: Session = Depends(get_db)) -> User:
    try:
        payload = jwt.decode(credentials.credentials, get_settings().secret_key, algorithms=["HS256"], options={"require": ["sub", "exp", "type", "sv", "uid"]})
        if payload["type"] != "access":
            raise jwt.InvalidTokenError()
    except (jwt.InvalidTokenError, KeyError, TypeError):
        raise HTTPException(status_code=401, detail="Sesión inválida")
    from app.services.tenancy import validate_context
    validate_context(db, payload)
    if db.info.get("access_scope") == "platform" and request.url.path not in {"/api/v1/auth/me", "/api/v1/platform/organizations"}:
        raise HTTPException(403, "Operación exclusiva del contexto de organización")
    user = db.scalar(select(User).where(User.email == payload["sub"], User.id == payload["uid"]))
    if not user or not user.is_active or user.session_version != payload["sv"]:
        raise HTTPException(status_code=401, detail="Usuario o sesión no disponible")
    if db.info.get("access_scope") == "platform" and not user.is_platform_admin:
        raise HTTPException(403, "Contexto no autorizado")
    membership = user.tenant_membership()
    if db.info.get("access_scope") == "tenant" and (membership is None or membership.state != "active"):
        raise HTTPException(401, "Membresía no disponible")
    return user
def require_permission(code: str):
    def dependency(request: Request, user: User = Depends(current_user), db: Session = Depends(get_db)) -> User:
        if code not in effective_permissions(user):
            raise HTTPException(status_code=403, detail="No tiene permiso para esta operación")
        if code in {"users:manage", "centers:manage"} and request.method not in {"GET", "HEAD", "OPTIONS"}:
            authorize_sensitive_write(db, user, f"{request.method} {request.url.path}", request.headers.get("X-Reauthentication"))
            if code not in effective_permissions(user):
                raise HTTPException(403, "Sus permisos cambiaron")
        return user
    return dependency
