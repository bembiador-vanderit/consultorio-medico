import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.orm import Session
from app.core.config import get_settings
from app.db import get_db
from app.models import User

bearer = HTTPBearer()
def current_user(credentials: HTTPAuthorizationCredentials = Depends(bearer), db: Session = Depends(get_db)) -> User:
    try: email = jwt.decode(credentials.credentials, get_settings().secret_key, algorithms=["HS256"])["sub"]
    except (jwt.InvalidTokenError, KeyError): raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Sesión inválida")
    user = db.scalar(select(User).where(User.email == email))
    if not user or not user.is_active: raise HTTPException(status_code=401, detail="Usuario no disponible")
    return user
def require_permission(code: str):
    def dependency(user: User = Depends(current_user)) -> User:
        if code not in {p.code for role in user.roles for p in role.permissions}: raise HTTPException(status_code=403, detail="No tiene permiso para esta operación")
        return user
    return dependency
