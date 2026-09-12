from datetime import date, datetime, time

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.api.deps import current_user
from app.api.routes import follow_ups
from app.db import Base, get_db
from app.models import Appointment, CareCenter, Notification, Patient, Role, SecretaryCenterScope, User
from app.services.reminders import sync_appointment_reminders, sync_in_app_appointment_reminder


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


def test_appointment_reminder_only_notifies_secretaries_in_doctor_scope():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    db = Session(engine)
    center = CareCenter(name="Centro", city="Santo Domingo", is_active=True)
    doctor = User(
        email="scope-reminder-doctor@example.test", full_name="Doctor Alcance",
        password_hash="hash", is_active=True,
        roles=[Role(code="doctor", name="Doctor")], centers=[center],
    )
    secretary_role = Role(code="secretary", name="Secretaria")
    authorized = User(
        email="authorized-reminder@example.test", full_name="Secretaria Autorizada",
        password_hash="hash", is_active=True, roles=[secretary_role], centers=[center],
    )
    outsider = User(
        email="outside-reminder@example.test", full_name="Secretaria Fuera",
        password_hash="hash", is_active=True, roles=[secretary_role], centers=[center],
    )
    patient = Patient(first_name="Ana", last_name="Paciente", date_of_birth=date(1990, 1, 1))
    appointment = Appointment(
        patient=patient, doctor=doctor, center=center,
        appointment_date=date(2026, 9, 4), appointment_time=time(10), status="scheduled",
    )
    db.add_all([appointment, authorized, outsider]); db.flush()
    db.add_all([
        SecretaryCenterScope(
            secretary_id=authorized.id, center_id=center.id,
            manage_all_doctors=False, doctors=[doctor],
        ),
        SecretaryCenterScope(
            secretary_id=outsider.id, center_id=center.id,
            manage_all_doctors=False, doctors=[],
        ),
    ])
    db.commit()
    now = datetime(2026, 9, 4, 9)

    assert sync_appointment_reminders(db, now=now) == 2
    assert sync_appointment_reminders(db, now=now) == 0
    recipients = set(db.scalars(select(Notification.user_id).where(
        Notification.appointment_id == appointment.id,
        Notification.notification_type == "appointment_due",
    )).all())
    assert recipients == {doctor.id, authorized.id}
    assert outsider.id not in recipients
    db.close(); engine.dispose()


def test_same_day_future_is_due_but_past_and_beyond_24_hours_are_not():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    db = Session(engine)
    center = CareCenter(name="Centro", city="Santo Domingo", is_active=True)
    doctor = User(
        email="same-day-doctor@example.test", full_name="Doctora Mismo Día",
        password_hash="hash", is_active=True,
        roles=[Role(code="doctor", name="Doctor")], centers=[center],
    )
    patient = Patient(first_name="Ana", last_name="Paciente", date_of_birth=date(1990, 1, 1))
    now = datetime(2026, 9, 8, 11)
    appointments = [
        Appointment(patient=patient, doctor=doctor, center=center, appointment_date=now.date(), appointment_time=time(13), status="scheduled"),
        Appointment(patient=patient, doctor=doctor, center=center, appointment_date=now.date(), appointment_time=time(10), status="scheduled"),
        Appointment(patient=patient, doctor=doctor, center=center, appointment_date=date(2026, 9, 9), appointment_time=time(11, 1), status="scheduled"),
    ]
    db.add_all(appointments); db.commit()

    assert sync_in_app_appointment_reminder(db, appointments[0], now=now) == 1
    assert sync_in_app_appointment_reminder(db, appointments[1], now=now) == 0
    assert sync_in_app_appointment_reminder(db, appointments[2], now=now) == 0
    db.commit()
    notified_ids = set(db.scalars(select(Notification.appointment_id)).all())
    assert notified_ids == {appointments[0].id}
    db.close(); engine.dispose()


def test_reprogrammed_due_appointment_refreshes_existing_reminder():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    db = Session(engine)
    center = CareCenter(name="Centro", city="Santo Domingo", is_active=True)
    doctor = User(
        email="refresh-doctor@example.test", full_name="Doctora Reprogramada",
        password_hash="hash", is_active=True,
        roles=[Role(code="doctor", name="Doctor")], centers=[center],
    )
    patient = Patient(first_name="Ana", last_name="Paciente", date_of_birth=date(1990, 1, 1))
    appointment = Appointment(
        patient=patient, doctor=doctor, center=center,
        appointment_date=date(2026, 9, 8), appointment_time=time(13), status="scheduled",
    )
    db.add(appointment); db.flush()
    reminder = Notification(
        user_id=doctor.id, appointment_id=appointment.id, title="Cita próxima",
        message="Horario anterior", notification_type="appointment_due", is_read=True,
        read_at=datetime(2026, 9, 8, 9),
    )
    db.add(reminder); db.commit()

    appointment.appointment_time = time(14)
    assert sync_in_app_appointment_reminder(
        db, appointment, now=datetime(2026, 9, 8, 11), refresh_existing=True
    ) == 1
    db.commit(); db.refresh(reminder)
    assert reminder.is_read is False
    assert reminder.read_at is None
    assert "08/09/2026 14:00" in reminder.message
    db.close(); engine.dispose()


def test_pending_notification_list_matches_count_policy_and_revalidates_secretary_scope(monkeypatch):
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    db = Session(engine)
    now = datetime(2026, 9, 9, 9)
    monkeypatch.setattr(follow_ups, "installation_now", lambda: now)

    center = CareCenter(name="Centro", city="Santo Domingo", is_active=True)
    doctor_role = Role(code="doctor", name="Doctor")
    doctor = User(
        email="notification-scope-doctor@example.test", full_name="Doctora Visible",
        password_hash="hash", is_active=True, roles=[doctor_role], centers=[center],
    )
    other_doctor = User(
        email="notification-scope-other@example.test", full_name="Doctor Fuera",
        password_hash="hash", is_active=True, roles=[doctor_role], centers=[center],
    )
    secretary = User(
        email="notification-scope-secretary@example.test", full_name="Secretaria",
        password_hash="hash", is_active=True,
        roles=[Role(code="secretary", name="Secretaria")], centers=[center],
    )
    patients = [
        Patient(first_name=f"Paciente{index}", last_name="Prueba", date_of_birth=date(1990, 1, index + 1))
        for index in range(4)
    ]
    appointments = [
        Appointment(
            patient=patients[0], doctor=doctor, center=center,
            appointment_date=now.date(), appointment_time=time(10), status="scheduled",
        ),
        Appointment(
            patient=patients[1], doctor=doctor, center=center,
            appointment_date=now.date(), appointment_time=time(11), status="confirmed",
        ),
        Appointment(
            patient=patients[2], doctor=other_doctor, center=center,
            appointment_date=now.date(), appointment_time=time(12), status="scheduled",
        ),
        Appointment(
            patient=patients[3], doctor=doctor, center=center,
            appointment_date=now.date() - date.resolution, appointment_time=time(8), status="scheduled",
        ),
    ]
    db.add_all([*appointments, secretary]); db.flush()
    scope = SecretaryCenterScope(
        secretary_id=secretary.id, center_id=center.id,
        manage_all_doctors=False, doctors=[doctor],
    )
    notifications = [
        Notification(
            user_id=secretary.id, appointment_id=appointment.id,
            title="Cita próxima", message=f"{appointment.patient.first_name} — aviso",
            notification_type="appointment_due", is_read=index == 1,
        )
        for index, appointment in enumerate(appointments)
    ]
    db.add_all([scope, *notifications]); db.commit()

    app = FastAPI()
    app.include_router(follow_ups.router, prefix="/api/v1")
    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[current_user] = lambda: secretary
    client = TestClient(app)

    pending = client.get("/api/v1/follow-ups/notifications", params={"unread_only": True})
    assert pending.status_code == 200
    assert [item["id"] for item in pending.json()] == [notifications[0].id]
    visible_history = client.get("/api/v1/follow-ups/notifications")
    assert {item["id"] for item in visible_history.json()} == {notifications[0].id, notifications[1].id}
    assert client.post(f"/api/v1/follow-ups/notifications/{notifications[0].id}/read").status_code == 200
    assert client.get(
        "/api/v1/follow-ups/notifications", params={"unread_only": True}
    ).json() == []

    scope.doctors = [other_doctor]
    db.commit()
    after_scope_change = client.get(
        "/api/v1/follow-ups/notifications", params={"unread_only": True}
    )
    assert [item["id"] for item in after_scope_change.json()] == [notifications[2].id]
    assert client.post("/api/v1/follow-ups/notifications/sync").json() == {"created": 0}

    db.close(); engine.dispose()
