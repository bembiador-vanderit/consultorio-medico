from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import inspect
from sqlalchemy.orm import Session

from app.api.deps import current_user
from app.db import get_db
from app.models import User
from app.schemas.user_preference import UserPreferencesPayload, UserPreferencesResponse
from app.services.user_preferences import get_preferences, put_preferences

router = APIRouter(prefix="/me/preferences", tags=["Preferencias personales"])


def require_activated_schema(db: Session) -> None:
    if not inspect(db.connection()).has_table("user_preferences"):
        raise HTTPException(503, "Preferencias personales pendientes de activación")


@router.get("", response_model=UserPreferencesResponse)
def read_preferences(user: User = Depends(current_user), db: Session = Depends(get_db)):
    require_activated_schema(db)
    return get_preferences(db, user.id)


@router.put("", response_model=UserPreferencesResponse)
def save_preferences(payload: UserPreferencesPayload, user: User = Depends(current_user), db: Session = Depends(get_db)):
    require_activated_schema(db)
    return put_preferences(db, user.id, payload.model_dump())
