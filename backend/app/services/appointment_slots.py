"""Timed slot occupancy is independent of patient, specialty and queue order.

Call after authorization and while holding the existing center lock. The partial
unique index is the final arbiter for concurrent/non-HTTP writers after 0063.
This service never grants access or changes tenant scope.
"""
from functools import wraps

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.models.appointment import Appointment, SLOT_OCCUPYING_STATUSES, TIMED_SLOT_INDEX

SLOT_CONFLICT_MESSAGE = "El médico ya tiene una cita activa en ese horario."


def ensure_slot_available(db, *, organization_id, center_id, doctor_id, day,
                          start_time, schedule_mode, status, exclude_id=None):
    if schedule_mode != "timed" or status not in SLOT_OCCUPYING_STATUSES:
        return
    query = select(Appointment.id).where(
        Appointment.organization_id == organization_id,
        Appointment.center_id == center_id,
        Appointment.doctor_id == doctor_id,
        Appointment.appointment_date == day,
        Appointment.appointment_time == start_time,
        Appointment.schedule_mode == "timed",
        Appointment.status.in_(SLOT_OCCUPYING_STATUSES),
    )
    if exclude_id is not None:
        query = query.where(Appointment.id != exclude_id)
    if db.scalar(query.limit(1)) is not None:
        raise HTTPException(409, SLOT_CONFLICT_MESSAGE)


def translate_slot_integrity_error(db, error):
    """Do not mask unrelated FK/check/unique violations as scheduling conflicts."""
    if getattr(getattr(getattr(error, "orig", None), "diag", None), "constraint_name", None) == TIMED_SLOT_INDEX:
        db.rollback()
        raise HTTPException(409, SLOT_CONFLICT_MESSAGE) from error


def slot_write(operation):
    @wraps(operation)
    def wrapped(*args, **kwargs):
        try:
            return operation(*args, **kwargs)
        except IntegrityError as error:
            db = kwargs.get("db")
            if db is None:
                from inspect import signature
                db = signature(operation).bind(*args, **kwargs).arguments["db"]
            translate_slot_integrity_error(db, error)
            raise
    return wrapped
