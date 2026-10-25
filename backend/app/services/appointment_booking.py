"""Monotonic administrative order for queue appointments, independent of tickets."""

from sqlalchemy import func, inspect, select
from sqlalchemy.orm import Session

from app.models import Appointment, AppointmentBookingSequence


def booking_schema_ready(db: Session) -> bool:
    if not hasattr(db, "get_bind"):
        return False  # Lightweight route doubles have no physical schema.
    return inspect(db.get_bind()).has_table("appointment_booking_sequences")


def next_booking_order(db: Session, *, organization_id: int, center_id: int, doctor_id: int, day) -> int:
    """Caller holds the center row lock; the counter survives physical deletions."""
    sequence = db.scalar(select(AppointmentBookingSequence).where(
        AppointmentBookingSequence.organization_id == organization_id,
        AppointmentBookingSequence.center_id == center_id,
        AppointmentBookingSequence.doctor_id == doctor_id,
        AppointmentBookingSequence.appointment_date == day,
    ).with_for_update())
    if sequence is None:
        prior = db.scalar(select(func.max(Appointment.daily_booking_order)).where(
            Appointment.organization_id == organization_id,
            Appointment.center_id == center_id,
            Appointment.doctor_id == doctor_id,
            Appointment.appointment_date == day,
        )) or 0
        sequence = AppointmentBookingSequence(
            organization_id=organization_id, center_id=center_id, doctor_id=doctor_id,
            appointment_date=day, last_number=prior + 1,
        )
        db.add(sequence)
    else:
        sequence.last_number += 1
    db.flush()
    return sequence.last_number
