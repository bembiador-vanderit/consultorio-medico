"""Tenant-scoped operational pauses; no queue or appointment mutations."""

from datetime import date, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models import Organization, ProviderOperationalPause, User
from app.schemas.provider_pause import ProviderPauseStart
from app.services.administration import effective_permissions
from app.services.agenda_schedule import validate_pair
from app.services.appointment_scope import is_role, secretary_can_manage


def _ensure_access(db: Session, user: User, center_id: int, doctor_id: int, *, write: bool) -> None:
    if db.info.get("access_scope") != "tenant" or not user.is_active:
        raise HTTPException(403, "Contexto no autorizado")
    if write and not (is_role(user, "admin") or (is_role(user, "doctor") and user.id == doctor_id)):
        raise HTTPException(403, "No tiene permiso para gestionar esta pausa")
    validate_pair(db, doctor_id, center_id)
    if is_role(user, "admin"):
        return
    if is_role(user, "doctor") and user.id == doctor_id:
        if write and "clinical:access" not in effective_permissions(user):
            raise HTTPException(403, "No tiene permiso clínico para gestionar su pausa")
        return
    if not write and is_role(user, "secretary") and secretary_can_manage(user, center_id, doctor_id, db):
        return
    raise HTTPException(403, "No tiene acceso a esta pausa")


def is_provider_paused(db: Session, doctor_id: int, center_id: int) -> bool:
    """Read-only guard for future auto-call; 0045 does not call it from the queue."""
    organization_id = db.info.get("organization_id")
    if organization_id is None:
        raise RuntimeError("La consulta de pausas requiere contexto de organización")
    return db.scalar(select(ProviderOperationalPause.id).where(
        ProviderOperationalPause.organization_id == organization_id,
        ProviderOperationalPause.doctor_id == doctor_id,
        ProviderOperationalPause.center_id == center_id,
        ProviderOperationalPause.actual_finished_at.is_(None),
    )) is not None


def current_pause(db: Session, center_id: int, doctor_id: int, user: User) -> ProviderOperationalPause | None:
    _ensure_access(db, user, center_id, doctor_id, write=False)
    return db.scalar(select(ProviderOperationalPause).where(
        ProviderOperationalPause.center_id == center_id,
        ProviderOperationalPause.doctor_id == doctor_id,
        ProviderOperationalPause.actual_finished_at.is_(None),
    ))


def start_pause(db: Session, payload: ProviderPauseStart, user: User) -> ProviderOperationalPause:
    doctor_id = payload.doctor_id if payload.doctor_id is not None else user.id
    _ensure_access(db, user, payload.center_id, doctor_id, write=True)
    # Calls and pause starts serialize on the provider row. A call cannot
    # commit after a newly opened pause without observing that pause.
    db.scalar(select(User.id).where(User.id == doctor_id).with_for_update())
    if is_provider_paused(db, doctor_id, payload.center_id):
        raise HTTPException(409, "El médico ya tiene una pausa abierta en este centro")
    now = datetime.utcnow()
    pause = ProviderOperationalPause(
        organization_id=db.info["organization_id"], center_id=payload.center_id,
        doctor_id=doctor_id, reason=payload.reason, notes=payload.notes,
        planned_start_at=payload.planned_start_at, actual_started_at=now,
        started_by_user_id=user.id, created_at=now, updated_at=now,
    )
    db.add(pause)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, "El médico ya tiene una pausa abierta en este centro") from None
    db.refresh(pause)
    return pause


def finish_pause(db: Session, pause_id: int, user: User) -> ProviderOperationalPause:
    pause = db.scalar(select(ProviderOperationalPause).where(
        ProviderOperationalPause.id == pause_id,
    ).with_for_update())
    if pause is None:
        raise HTTPException(404, "Pausa no encontrada")
    _ensure_access(db, user, pause.center_id, pause.doctor_id, write=True)
    if pause.actual_finished_at is not None:
        raise HTTPException(409, "La pausa ya fue finalizada")
    now = datetime.utcnow()
    if now < pause.actual_started_at:
        raise HTTPException(409, "El inicio de pausa es posterior a la hora actual")
    pause.actual_finished_at = now
    pause.finished_by_user_id = user.id
    pause.updated_at = now
    db.commit()
    db.refresh(pause)
    return pause


def pause_history(
    db: Session, center_id: int, doctor_id: int, user: User, day: date | None = None,
) -> list[ProviderOperationalPause]:
    _ensure_access(db, user, center_id, doctor_id, write=False)
    query = select(ProviderOperationalPause).where(
        ProviderOperationalPause.center_id == center_id,
        ProviderOperationalPause.doctor_id == doctor_id,
    )
    if day is not None:
        organization = db.get(Organization, db.info["organization_id"])
        zone = ZoneInfo(organization.timezone)
        start = datetime.combine(day, time.min, zone).astimezone(timezone.utc).replace(tzinfo=None)
        end = datetime.combine(day + timedelta(days=1), time.min, zone).astimezone(timezone.utc).replace(tzinfo=None)
        query = query.where(
            ProviderOperationalPause.actual_started_at < end,
            (ProviderOperationalPause.actual_finished_at.is_(None) | (ProviderOperationalPause.actual_finished_at >= start)),
        )
    return list(db.scalars(query.order_by(ProviderOperationalPause.actual_started_at.desc(), ProviderOperationalPause.id.desc())))
