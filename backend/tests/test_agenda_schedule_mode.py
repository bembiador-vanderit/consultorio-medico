from datetime import date, time

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.api.routes import agenda_schedule as routes
from app.api.routes import appointments
from app.db import Base
from app.models import (
    Appointment, CareCenter, DoctorAgendaException, DoctorAgendaSetting, QueueLine, QueueTicket,
    Organization, OrganizationMembership, Patient, Role, Specialty, User,
)
from app.schemas.agenda_schedule import ModeChange, PolicyChange
from app.schemas.appointment import AppointmentCreate
from app.services.agenda_schedule import effective_mode, queue_line_available
from app.services.appointment_booking import next_booking_order
from app.services.tenancy import bind_scope


@pytest.fixture
def agenda_db(monkeypatch):
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        doctor_role = Role(code="doctor", name="Doctor")
        admin_role = Role(code="admin", name="Admin")
        db.add_all([doctor_role, admin_role, Organization(id=1, slug="pilot", name="Piloto"), Organization(id=2, slug="other", name="Otro")])
        db.flush()
        center_one = CareCenter(organization_id=1, name="Centro Uno", city="Prueba")
        center_two = CareCenter(organization_id=2, name="Centro Dos", city="Prueba")
        specialty = Specialty(organization_id=1, name="General", is_active=True)
        db.add_all([center_one, center_two, specialty])
        db.flush()
        doctor = User(email="doctor@example.test", full_name="Doctor Test", password_hash="synthetic", centers=[center_one], specialties=[specialty], memberships=[OrganizationMembership(organization_id=1, roles=[doctor_role])])
        admin = User(email="admin@example.test", full_name="Admin Test", password_hash="synthetic", memberships=[OrganizationMembership(organization_id=1, roles=[admin_role]), OrganizationMembership(organization_id=2, roles=[admin_role])])
        patient = Patient(organization_id=1, first_name="Paciente", last_name="Sintético", date_of_birth=date(1990, 1, 1))
        db.add_all([doctor, admin, patient])
        db.flush()
        db.add(QueueLine(organization_id=1, center_id=center_one.id, doctor_id=doctor.id,
                         name="Línea QA", prefix="Q", is_active=True))
        db.commit()
        ids = doctor.id, admin.id, center_one.id, center_two.id, patient.id
    monkeypatch.setattr(appointments, "require_patient_selection", lambda *args, **kwargs: None)
    monkeypatch.setattr(appointments, "sync_in_app_appointment_reminder", lambda *args, **kwargs: 0)
    yield engine, ids
    engine.dispose()


def tenant_session(engine, org_id=1):
    db = Session(engine)
    bind_scope(db, "tenant", org_id)
    return db


def test_base_exception_and_single_effective_mode(agenda_db):
    engine, (doctor_id, admin_id, center_id, _, _) = agenda_db
    day = date(2030, 10, 15)
    with tenant_session(engine) as db:
        admin = db.get(User, admin_id)
        assert routes.get_mode(doctor_id, center_id, day, admin, db).effective_mode == "timed"
        assert routes.set_base_mode(doctor_id, center_id, ModeChange(mode="queue"), admin, db).base_mode == "queue"
        assert routes.get_mode(doctor_id, center_id, day, admin, db).effective_mode == "queue"
        resolved_api = appointments.appointment_effective_mode(doctor_id, center_id, day, admin, db)
        assert resolved_api["schedule_mode"] == "queue"
        assert resolved_api["allowed_queue"] is True
        assert appointments.queue_capabilities(admin, db) == {"booking_order_enabled": True}
        resolved = routes.set_exception(doctor_id, center_id, day, ModeChange(mode="timed"), admin, db)
        assert (resolved.base_mode, resolved.exception_mode, resolved.effective_mode) == ("queue", "timed", "timed")
        assert effective_mode(db, doctor_id, center_id, date(2030, 10, 16)) == "queue"
        assert routes.delete_exception(doctor_id, center_id, day, admin, db).effective_mode == "queue"
        assert db.scalar(select(DoctorAgendaException.id)) is None


def test_snapshot_and_multimodal_occupied_day(agenda_db):
    engine, (doctor_id, admin_id, center_id, _, patient_id) = agenda_db
    day = date(2030, 10, 15)
    with tenant_session(engine) as db:
        admin = db.get(User, admin_id)
        payload = AppointmentCreate(patient_id=patient_id, doctor_id=doctor_id, center_id=center_id,
            appointment_date=day, appointment_time=time(9, 0))
        created = appointments.create_appointment(payload, user=admin, db=db)
        assert created.schedule_mode == "timed"
        routes.set_base_mode(doctor_id, center_id,
            PolicyChange(allowed_timed=True, allowed_queue=True, default_mode="timed"), admin, db)
        routes.set_exception(doctor_id, center_id, day,
            PolicyChange(allowed_timed=True, allowed_queue=True, default_mode="queue"), admin, db)
        assert db.get(Appointment, created.id).schedule_mode == "timed"
        assert db.scalar(select(DoctorAgendaSetting.id)) is not None
        queue_same_day = appointments.create_appointment(
            payload.model_copy(update={"appointment_time": None, "schedule_mode": "queue"}), user=admin, db=db)
        assert queue_same_day.schedule_mode == "queue" and queue_same_day.daily_booking_order == 1
        assert db.get(Appointment, created.id).appointment_time == time(9)
        next_day = date(2030, 10, 16)
        routes.set_exception(doctor_id, center_id, next_day, ModeChange(mode="queue"), admin, db)
        moved = appointments.update_appointment(created.id, payload.model_copy(update={"appointment_date": next_day}), user=admin, db=db)
        assert moved.schedule_mode == "queue"
        assert moved.appointment_time is None  # Queue V2 has no artificial hour.
        assert moved.daily_booking_order == 1
        new_queue = appointments.create_appointment(
            payload.model_copy(update={"appointment_date": next_day, "appointment_time": time(10, 0)}),
            user=admin, db=db,
        )
        assert new_queue.schedule_mode == "queue"
        assert db.get(Appointment, created.id).schedule_mode == "queue"


def test_non_admin_cannot_read_or_modify_settings(agenda_db):
    engine, (doctor_id, _, center_id, _, _) = agenda_db
    with tenant_session(engine) as db:
        doctor = db.get(User, doctor_id)
        with pytest.raises(HTTPException) as denied:
            routes.get_mode(doctor_id, center_id, date(2030, 10, 15), doctor, db)
        assert denied.value.status_code == 403


def test_cross_tenant_configuration_is_not_visible_or_mutable(agenda_db):
    engine, (doctor_id, admin_id, center_id, foreign_center_id, _) = agenda_db
    with tenant_session(engine, 2) as db:
        admin = db.get(User, admin_id)
        for action in (
            lambda: routes.get_mode(doctor_id, center_id, date(2030, 10, 15), admin, db),
            lambda: appointments.appointment_effective_mode(doctor_id, center_id, date(2030, 10, 15), admin, db),
            lambda: routes.set_base_mode(doctor_id, center_id, ModeChange(mode="queue"), admin, db),
            lambda: routes.set_exception(doctor_id, center_id, date(2030, 10, 15), ModeChange(mode="queue"), admin, db),
        ):
            with pytest.raises(HTTPException) as denied:
                action()
            assert denied.value.status_code in (403, 404)
        assert db.get(CareCenter, foreign_center_id) is not None
        assert db.scalar(select(DoctorAgendaSetting.id)) is None


def test_queue_booking_order_is_server_owned_and_survives_edits_and_deletion(agenda_db):
    engine, (doctor_id, admin_id, center_id, _, patient_id) = agenda_db
    day = date(2030, 10, 16)
    with tenant_session(engine) as db:
        admin = db.get(User, admin_id)
        routes.set_exception(doctor_id, center_id, day, ModeChange(mode="queue"), admin, db)
        payload = AppointmentCreate(patient_id=patient_id, doctor_id=doctor_id,
            center_id=center_id, appointment_date=day, appointment_time=None)
        first = appointments.create_appointment(payload, user=admin, db=db)
        second = appointments.create_appointment(payload.model_copy(update={"appointment_time": time(8)}), user=admin, db=db)
        assert (first.daily_booking_order, second.daily_booking_order) == (1, 2)
        assert first.appointment_time is None and second.appointment_time is None
        assert db.scalar(select(QueueTicket.id)) is None
        assert db.scalar(select(Appointment.id).where(Appointment.id == first.id)) is not None
        updated = appointments.update_appointment(first.id, payload.model_copy(update={"notes": "QA"}), user=admin, db=db)
        assert updated.daily_booking_order == 1
        appointments.delete_appointment(second.id, user=admin, db=db)
        third = appointments.create_appointment(payload, user=admin, db=db)
        assert third.daily_booking_order == 3  # No reuse of a deleted number.
        cancelled = appointments.update_appointment(third.id,
            payload.model_copy(update={"status": "cancelled"}), user=admin, db=db)
        assert cancelled.daily_booking_order == 3
        moved_day = date(2030, 10, 17)
        routes.set_exception(doctor_id, center_id, moved_day, ModeChange(mode="queue"), admin, db)
        moved = appointments.update_appointment(first.id,
            payload.model_copy(update={"appointment_date": moved_day}), user=admin, db=db)
        assert moved.daily_booking_order == 1 and moved.appointment_time is None
        later = appointments.create_appointment(payload, user=admin, db=db)
        assert later.daily_booking_order == 4


def test_timed_requires_time_and_queue_does_not_create_ticket(agenda_db):
    engine, (doctor_id, admin_id, center_id, _, patient_id) = agenda_db
    with tenant_session(engine) as db:
        admin = db.get(User, admin_id)
        timed = AppointmentCreate(patient_id=patient_id, doctor_id=doctor_id,
            center_id=center_id, appointment_date=date(2030, 10, 15), appointment_time=None)
        with pytest.raises(HTTPException) as error:
            appointments.create_appointment(timed, user=admin, db=db)
        assert error.value.status_code == 422
        created = appointments.create_appointment(timed.model_copy(update={"appointment_time": time(9)}), user=admin, db=db)
        assert created.daily_booking_order is None


def test_multimode_defaults_validation_exceptions_and_existing_snapshots(agenda_db):
    engine, (doctor_id, admin_id, center_id, _, patient_id) = agenda_db
    day = date(2030, 10, 20)
    with tenant_session(engine) as db:
        admin = db.get(User, admin_id)
        both = PolicyChange(allowed_timed=True, allowed_queue=True, default_mode="queue")
        resolved = routes.set_base_mode(doctor_id, center_id, both, admin, db)
        assert resolved.base_policy.allowed_timed and resolved.base_policy.allowed_queue
        assert resolved.base_policy.default_mode == "queue"
        payload = AppointmentCreate(patient_id=patient_id, doctor_id=doctor_id, center_id=center_id,
            appointment_date=day, appointment_time=None)
        queue = appointments.create_appointment(payload, user=admin, db=db)
        timed = appointments.create_appointment(payload.model_copy(update={
            "schedule_mode": "timed", "appointment_time": time(9, 30)}), user=admin, db=db)
        assert (queue.schedule_mode, queue.appointment_time, queue.daily_booking_order) == ("queue", None, 1)
        assert (timed.schedule_mode, timed.appointment_time, timed.daily_booking_order) == ("timed", time(9, 30), None)
        with pytest.raises(HTTPException) as invalid:
            routes.set_base_mode(doctor_id, center_id,
                PolicyChange(allowed_timed=False, allowed_queue=False, default_mode="timed"), admin, db)
        assert invalid.value.status_code == 422
        with pytest.raises(HTTPException) as invalid:
            routes.set_base_mode(doctor_id, center_id,
                PolicyChange(allowed_timed=True, allowed_queue=False, default_mode="queue"), admin, db)
        assert invalid.value.status_code == 422
        routes.set_exception(doctor_id, center_id, day, ModeChange(mode="timed"), admin, db)
        assert appointments.appointment_effective_mode(doctor_id, center_id, day, admin, db)["allowed_queue"] is False
        with pytest.raises(HTTPException) as denied:
            appointments.create_appointment(payload.model_copy(update={"schedule_mode": "queue"}), user=admin, db=db)
        assert denied.value.status_code == 409
        assert db.get(Appointment, queue.id).schedule_mode == "queue"
        assert db.get(Appointment, timed.id).schedule_mode == "timed"
        assert db.get(Appointment, queue.id).daily_booking_order == 1
        routes.set_exception(doctor_id, center_id, day, both, admin, db)
        assert appointments.appointment_effective_mode(doctor_id, center_id, day, admin, db)["default_mode"] == "queue"
        routes.set_base_mode(doctor_id, center_id, ModeChange(mode="timed"), admin, db)
        assert db.get(Appointment, queue.id).schedule_mode == "queue"
        assert db.get(Appointment, timed.id).schedule_mode == "timed"


def test_queue_line_required_and_mode_edit_guarded(agenda_db):
    engine, (doctor_id, admin_id, center_id, _, patient_id) = agenda_db
    day = date(2030, 10, 21)
    with tenant_session(engine) as db:
        admin = db.get(User, admin_id)
        routes.set_base_mode(doctor_id, center_id,
            PolicyChange(allowed_timed=True, allowed_queue=True, default_mode="timed"), admin, db)
        payload = AppointmentCreate(patient_id=patient_id, doctor_id=doctor_id, center_id=center_id,
            appointment_date=day, appointment_time=time(8, 0))
        timed = appointments.create_appointment(payload, user=admin, db=db)
        line = db.scalar(select(QueueLine).where(QueueLine.doctor_id == doctor_id))
        line.is_active = False
        db.flush()
        assert queue_line_available(db, doctor_id, center_id) is False
        with pytest.raises(HTTPException) as unavailable:
            appointments.create_appointment(payload.model_copy(update={"schedule_mode": "queue", "appointment_time": None}), user=admin, db=db)
        assert unavailable.value.status_code == 409
        assert "línea de turnos" in unavailable.value.detail
        line.is_active = True
        db.flush()
        queue = appointments.update_appointment(timed.id, payload.model_copy(update={
            "schedule_mode": "queue", "appointment_time": None}), user=admin, db=db)
        assert queue.schedule_mode == "queue" and queue.daily_booking_order == 1
        back = appointments.update_appointment(timed.id, payload.model_copy(update={
            "schedule_mode": "timed", "appointment_time": time(10)}), user=admin, db=db)
        assert back.schedule_mode == "timed" and back.daily_booking_order is None


def test_booking_sequence_is_independent_by_doctor_center_and_day(agenda_db):
    engine, (doctor_id, _, center_id, _, _) = agenda_db
    with tenant_session(engine) as db:
        other_center = CareCenter(organization_id=1, name="Centro adicional QA", city="Prueba")
        other_doctor = User(email="other-doctor@example.test", full_name="Doctor Adicional",
            password_hash="synthetic")
        db.add_all([other_center, other_doctor])
        db.flush()
        first = date(2030, 10, 16)
        def next_for(center, doctor, day):
            return next_booking_order(db, organization_id=1, center_id=center,
                doctor_id=doctor, day=day)
        assert [next_for(center_id, doctor_id, first) for _ in range(2)] == [1, 2]
        assert next_for(other_center.id, doctor_id, first) == 1
        assert next_for(center_id, other_doctor.id, first) == 1
        assert next_for(center_id, doctor_id, date(2030, 10, 17)) == 1
