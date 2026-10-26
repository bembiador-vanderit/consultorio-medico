"""Operational doctor pauses within the resolved tenant context."""

from datetime import date

from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.api.deps import require_permission
from app.db import get_db
from app.models import ProviderOperationalPause, User
from app.schemas.provider_pause import ProviderPauseRead, ProviderPauseStart
from app.services.provider_pause import current_pause, finish_pause, pause_history, start_pause


router = APIRouter(prefix="/provider-pauses", tags=["Pausas operativas"])
read_access = require_permission("patients:access")


def _read(pause: ProviderOperationalPause) -> ProviderPauseRead:
    duration = (
        (pause.actual_finished_at - pause.actual_started_at).total_seconds()
        if pause.actual_finished_at is not None else None
    )
    return ProviderPauseRead.model_validate(pause).model_copy(update={"duration_seconds": duration})


@router.post("/start", response_model=ProviderPauseRead, status_code=status.HTTP_201_CREATED)
def start(payload: ProviderPauseStart, user: User = Depends(read_access), db: Session = Depends(get_db)):
    return _read(start_pause(db, payload, user))


@router.post("/{pause_id}/finish", response_model=ProviderPauseRead)
def finish(pause_id: int, user: User = Depends(read_access), db: Session = Depends(get_db)):
    return _read(finish_pause(db, pause_id, user))


@router.get("/current", response_model=ProviderPauseRead | None)
def current(center_id: int, doctor_id: int, user: User = Depends(read_access), db: Session = Depends(get_db)):
    pause = current_pause(db, center_id, doctor_id, user)
    return _read(pause) if pause is not None else None


@router.get("", response_model=list[ProviderPauseRead])
def history(center_id: int, doctor_id: int, day: date | None = None,
            user: User = Depends(read_access), db: Session = Depends(get_db)):
    return [_read(pause) for pause in pause_history(db, center_id, doctor_id, user, day)]
