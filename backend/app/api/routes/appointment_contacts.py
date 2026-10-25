"""Pre-appointment telephone contacts, separate from appointment status."""

from datetime import date, datetime

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from app.api.deps import require_permission
from app.db import get_db
from app.models import Appointment, AppointmentContactAttempt, User
from app.schemas.appointment_contact import (
    ContactAttemptCreate, ContactAttemptResponse, ContactFilter,
    DailyContactItem, DailyContactResponse, DailyContactTotals,
)
from app.services.appointment_scope import apply_appointment_scope, ensure_appointment_access, is_role


router = APIRouter(prefix="/appointment-contacts", tags=["Contactos previos"])
access = require_permission("patients:access")


def _appointment(db: Session, appointment_id: int, user: User) -> Appointment:
    appointment = db.get(Appointment, appointment_id)
    if appointment is None:
        raise HTTPException(404, "Cita no encontrada")
    ensure_appointment_access(user, appointment, db)
    return appointment


def _response(attempt: AppointmentContactAttempt) -> ContactAttemptResponse:
    return ContactAttemptResponse(
        id=attempt.id,
        appointment_id=attempt.appointment_id,
        contacted_by_user_id=attempt.contacted_by_user_id,
        contacted_by_name=attempt.contacted_by.full_name,
        contacted_at=attempt.contacted_at,
        channel=attempt.channel,
        contact_value=attempt.contact_value,
        result=attempt.result,
        notes=attempt.notes,
        created_at=attempt.created_at,
    )


@router.post("/{appointment_id}", response_model=ContactAttemptResponse, status_code=status.HTTP_201_CREATED)
def record_contact(
    appointment_id: int,
    payload: ContactAttemptCreate,
    user: User = Depends(access),
    db: Session = Depends(get_db),
):
    if not (is_role(user, "secretary") or is_role(user, "admin")):
        raise HTTPException(403, "Solo secretaría o administración puede registrar contactos previos")
    appointment = _appointment(db, appointment_id, user)
    if appointment.status not in {"scheduled", "confirmed"}:
        raise HTTPException(409, "Solo pueden registrarse contactos previos en citas previstas")
    now = datetime.utcnow()
    attempt = AppointmentContactAttempt(
        organization_id=appointment.organization_id,
        appointment_id=appointment.id,
        contacted_by_user_id=user.id,
        contacted_at=now,
        created_at=now,
        channel=payload.channel,
        contact_value=payload.contact_value,
        result=payload.result,
        notes=payload.notes,
    )
    db.add(attempt)
    db.commit()
    db.refresh(attempt)
    return _response(attempt)


@router.get("/{appointment_id}", response_model=list[ContactAttemptResponse])
def list_contact_history(
    appointment_id: int,
    user: User = Depends(access),
    db: Session = Depends(get_db),
):
    _appointment(db, appointment_id, user)
    attempts = db.scalars(
        select(AppointmentContactAttempt)
        .options(joinedload(AppointmentContactAttempt.contacted_by))
        .where(AppointmentContactAttempt.appointment_id == appointment_id)
        .order_by(AppointmentContactAttempt.contacted_at, AppointmentContactAttempt.id)
    ).all()
    return [_response(attempt) for attempt in attempts]


@router.get("", response_model=DailyContactResponse)
def daily_contacts(
    day: date,
    center_id: int | None = None,
    doctor_id: int | None = None,
    result: ContactFilter | None = Query(default=None),
    user: User = Depends(access),
    db: Session = Depends(get_db),
):
    query = select(Appointment).options(
        joinedload(Appointment.patient), joinedload(Appointment.doctor), joinedload(Appointment.center)
    ).where(
        Appointment.appointment_date == day,
        Appointment.status.in_(("scheduled", "confirmed")),
    ).order_by(Appointment.appointment_time, Appointment.id)
    if center_id is not None:
        query = query.where(Appointment.center_id == center_id)
    if doctor_id is not None:
        query = query.where(Appointment.doctor_id == doctor_id)
    appointments = db.scalars(apply_appointment_scope(query, user, db)).all()
    ids = [appointment.id for appointment in appointments]
    latest: dict[int, AppointmentContactAttempt] = {}
    if ids:
        attempts = db.scalars(
            select(AppointmentContactAttempt)
            .options(joinedload(AppointmentContactAttempt.contacted_by))
            .where(AppointmentContactAttempt.appointment_id.in_(ids))
            .order_by(
                AppointmentContactAttempt.appointment_id,
                AppointmentContactAttempt.contacted_at.desc(),
                AppointmentContactAttempt.id.desc(),
            )
        ).all()
        for attempt in attempts:
            latest.setdefault(attempt.appointment_id, attempt)

    counts = {value: 0 for value in ("will_attend", "will_not_attend", "no_answer", "retry")}
    items: list[DailyContactItem] = []
    for appointment in appointments:
        attempt = latest.get(appointment.id)
        if attempt is not None:
            counts[attempt.result] += 1
        if result is not None and (attempt.result if attempt else "pending") != result:
            continue
        items.append(DailyContactItem(
            appointment_id=appointment.id,
            patient_name=f"{appointment.patient.first_name} {appointment.patient.last_name}",
            patient_phone=appointment.patient.phone,
            appointment_date=appointment.appointment_date,
            appointment_time=appointment.appointment_time,
            doctor_name=appointment.doctor.full_name,
            center_name=appointment.center.name if appointment.center else None,
            status=appointment.status,
            latest_contact=_response(attempt) if attempt else None,
        ))
    contacted = len(latest)
    return DailyContactResponse(
        date=day,
        totals=DailyContactTotals(
            total_expected=len(appointments), contacted=contacted,
            not_contacted=len(appointments) - contacted, **counts,
        ),
        items=items,
    )
