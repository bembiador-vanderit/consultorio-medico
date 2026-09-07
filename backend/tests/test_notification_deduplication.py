from datetime import date, datetime, time

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.db import Base
from app.models import Appointment, CareCenter, Notification, Patient, Role, User
from app.services.reminders import sync_appointment_reminders


def test_same_logical_appointment_notification_is_created_once():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    db = Session(engine)
    center = CareCenter(name="Centro", city="Santo Domingo", is_active=True)
    doctor = User(
        email="reminder-doctor@example.test", full_name="Doctor Recordatorio",
        password_hash="hash", is_active=True,
        roles=[Role(code="doctor", name="Doctor")], centers=[center],
    )
    patient = Patient(first_name="Ana", last_name="Paciente", date_of_birth=date(1990, 1, 1))
    appointment = Appointment(
        patient=patient, doctor=doctor, center=center,
        appointment_date=date(2026, 9, 4), appointment_time=time(10), status="scheduled",
    )
    db.add(appointment); db.commit()
    now = datetime(2026, 9, 4, 9)

    assert sync_appointment_reminders(db, now=now) == 1
    assert sync_appointment_reminders(db, now=now) == 0
    notifications = list(db.scalars(select(Notification).where(
        Notification.user_id == doctor.id,
        Notification.appointment_id == appointment.id,
        Notification.notification_type == "appointment_due",
    )))
    assert len(notifications) == 1

    db.add(Notification(
        user_id=doctor.id, appointment_id=appointment.id,
        title="Duplicada", message="No debe guardarse", notification_type="appointment_due",
    ))
    with pytest.raises(IntegrityError):
        db.commit()
    db.rollback(); db.close(); engine.dispose()
