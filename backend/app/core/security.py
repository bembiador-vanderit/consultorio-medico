from datetime import datetime, timedelta, timezone
import jwt
from pwdlib import PasswordHash
from app.core.config import get_settings
password_hash = PasswordHash.recommended()
def hash_password(value: str) -> str: return password_hash.hash(value)
def verify_password(value: str, hashed: str) -> bool: return password_hash.verify(value, hashed)
def create_access_token(subject: str, session_version: int = 0, user_id: int | None = None, context: dict | None = None) -> str:
    settings = get_settings()
    expires = datetime.now(timezone.utc) + timedelta(minutes=settings.access_token_expire_minutes)
    return jwt.encode({"sub": subject, "type": "access", "uid": user_id, "sv": session_version, "exp": expires, **(context or {})}, settings.secret_key, algorithm="HS256")
