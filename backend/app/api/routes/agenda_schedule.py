from dataclasses import asdict
from datetime import date

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import require_permission
from app.db import get_db
from app.models import DoctorAgendaException, DoctorAgendaSetting, User
from app.schemas.agenda_schedule import AgendaModeRead, ModeChange, PolicyChange
from app.services.agenda_schedule import (
    base_policy, effective_policy, ensure_legacy_base_change_consistent,
    ensure_legacy_day_consistent, exception_policy, lock_center, multimode_schema_ready,
    organization_today, queue_line_available, singleton, validate_pair, validate_policy,
)

router = APIRouter(prefix="/agenda-settings", tags=["Configuración de agenda"])
access = require_permission("centers:manage")


def require_tenant_admin(user: User, db: Session) -> None:
    if db.info.get("access_scope") == "platform" or not any(role.code == "admin" for role in user.roles):
        raise HTTPException(403, "Solo la administración del centro puede configurar la agenda")


def read_mode(db: Session, doctor_id: int, center_id: int, day: date) -> AgendaModeRead:
    base = base_policy(db, doctor_id, center_id)
    exception = exception_policy(db, doctor_id, center_id, day)
    effective = exception or base
    return AgendaModeRead(
        doctor_id=doctor_id, center_id=center_id, agenda_date=day,
        base_mode=base.default_mode, exception_mode=exception.default_mode if exception else None,
        effective_mode=effective.default_mode, base_policy=asdict(base),
        exception_policy=asdict(exception) if exception else None,
        effective_policy=asdict(effective), queue_line_available=queue_line_available(db, doctor_id, center_id),
        multimode_enabled=multimode_schema_ready(db),
    )


@router.get("/{doctor_id}/{center_id}/{day}", response_model=AgendaModeRead)
def get_mode(doctor_id: int, center_id: int, day: date, user: User = Depends(access), db: Session = Depends(get_db)):
    require_tenant_admin(user, db)
    validate_pair(db, doctor_id, center_id)
    return read_mode(db, doctor_id, center_id, day)


@router.put("/{doctor_id}/{center_id}/base", response_model=AgendaModeRead)
def set_base_mode(doctor_id: int, center_id: int, payload: PolicyChange | ModeChange, user: User = Depends(access), db: Session = Depends(get_db)):
    require_tenant_admin(user, db)
    lock_center(db, center_id)
    validate_pair(db, doctor_id, center_id)
    ready = multimode_schema_ready(db)
    if not ready and isinstance(payload, PolicyChange):
        raise HTTPException(409, "La configuración multimodal requiere activar la migración 0054")
    policy = validate_policy(payload.allowed_timed, payload.allowed_queue, payload.default_mode) if isinstance(payload, PolicyChange) else singleton(payload.mode)
    ensure_legacy_base_change_consistent(db, doctor_id, center_id, policy.default_mode)
    setting = db.scalar(select(DoctorAgendaSetting).where(
        DoctorAgendaSetting.doctor_id == doctor_id, DoctorAgendaSetting.center_id == center_id,
    ))
    if setting is None:
        setting = DoctorAgendaSetting(doctor_id=doctor_id, center_id=center_id, base_mode=policy.default_mode)
        db.add(setting)
    else:
        setting.base_mode = policy.default_mode
    if ready:
        setting.allowed_timed = policy.allowed_timed
        setting.allowed_queue = policy.allowed_queue
        setting.default_mode = policy.default_mode
    db.commit()
    return read_mode(db, doctor_id, center_id, organization_today(db))


@router.put("/{doctor_id}/{center_id}/exceptions/{day}", response_model=AgendaModeRead)
def set_exception(doctor_id: int, center_id: int, day: date, payload: PolicyChange | ModeChange, user: User = Depends(access), db: Session = Depends(get_db)):
    require_tenant_admin(user, db)
    lock_center(db, center_id)
    validate_pair(db, doctor_id, center_id)
    ready = multimode_schema_ready(db)
    if not ready and isinstance(payload, PolicyChange):
        raise HTTPException(409, "La configuración multimodal requiere activar la migración 0054")
    policy = validate_policy(payload.allowed_timed, payload.allowed_queue, payload.default_mode) if isinstance(payload, PolicyChange) else singleton(payload.mode)
    ensure_legacy_day_consistent(db, doctor_id, center_id, day, policy.default_mode)
    exception = db.scalar(select(DoctorAgendaException).where(
        DoctorAgendaException.doctor_id == doctor_id,
        DoctorAgendaException.center_id == center_id,
        DoctorAgendaException.agenda_date == day,
    ))
    if exception is None:
        exception = DoctorAgendaException(doctor_id=doctor_id, center_id=center_id, agenda_date=day, mode=policy.default_mode)
        db.add(exception)
    else:
        exception.mode = policy.default_mode
    if ready:
        exception.allowed_timed = policy.allowed_timed
        exception.allowed_queue = policy.allowed_queue
        exception.default_mode = policy.default_mode
    db.commit()
    return read_mode(db, doctor_id, center_id, day)


@router.delete("/{doctor_id}/{center_id}/exceptions/{day}", response_model=AgendaModeRead)
def delete_exception(doctor_id: int, center_id: int, day: date, user: User = Depends(access), db: Session = Depends(get_db)):
    require_tenant_admin(user, db)
    lock_center(db, center_id)
    validate_pair(db, doctor_id, center_id)
    ensure_legacy_day_consistent(db, doctor_id, center_id, day, base_policy(db, doctor_id, center_id).default_mode)
    exception = db.scalar(select(DoctorAgendaException).where(
        DoctorAgendaException.doctor_id == doctor_id,
        DoctorAgendaException.center_id == center_id,
        DoctorAgendaException.agenda_date == day,
    ))
    if exception is not None:
        db.delete(exception)
        db.commit()
    return read_mode(db, doctor_id, center_id, day)
