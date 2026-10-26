from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, time

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from app.api.routes import queue as routes
from app.api.routes.appointments import delete_appointment, update_appointment
from app.db import Base
from app.models import (
    Appointment, AppointmentContactAttempt, CareCenter, DoctorAgendaSetting,
    Organization, OrganizationMembership, Patient, QueueLine, QueueSequence,
    QueueTicket, Role, SecretaryCenterScope, User,
)
from app.schemas.appointment import AppointmentCreate
from app.schemas.queue import ArrivalCreate, QueueLineCreate, QueueLineUpdate, QueueTicketRead
from app.services.tenancy import bind_scope


@pytest.fixture
def queue_db(tmp_path, monkeypatch):
    engine = create_engine(f"sqlite:///{tmp_path / 'queue-test.sqlite'}", connect_args={"timeout": 30})
    Base.metadata.create_all(engine)
    day = date(2030, 10, 15)
    monkeypatch.setattr("app.services.queue.organization_today", lambda _: day)
    with Session(engine) as db:
        roles = {code: Role(code=code, name=code) for code in ("admin", "doctor", "secretary")}
        db.add_all([*roles.values(), Organization(id=1, slug="one", name="Uno"), Organization(id=2, slug="two", name="Dos")])
        db.flush()
        center = CareCenter(organization_id=1, name="Centro Uno", city="Prueba")
        foreign_center = CareCenter(organization_id=2, name="Centro Dos", city="Prueba")
        db.add_all([center, foreign_center])
        db.flush()
        admin = User(email="admin@synthetic.test", full_name="Administración", password_hash="synthetic",
                     memberships=[OrganizationMembership(organization_id=1, roles=[roles["admin"]]), OrganizationMembership(organization_id=2, roles=[roles["admin"]])])
        doctor = User(email="doctor@synthetic.test", full_name="Médico", password_hash="synthetic", centers=[center],
                      memberships=[OrganizationMembership(organization_id=1, roles=[roles["doctor"]])])
        secretary = User(email="secretary@synthetic.test", full_name="Secretaría", password_hash="synthetic", centers=[center],
                         memberships=[OrganizationMembership(organization_id=1, roles=[roles["secretary"]])])
        db.add_all([admin, doctor, secretary])
        db.flush()
        db.add(SecretaryCenterScope(organization_id=1, secretary_id=secretary.id, center_id=center.id, manage_all_doctors=True))
        patients = [Patient(organization_id=1, first_name=f"Paciente {n}", last_name="Sintético", date_of_birth=date(1990, 1, 1)) for n in range(8)]
        db.add_all(patients)
        db.flush()
        appointments = [Appointment(organization_id=1, patient_id=patient.id, doctor_id=doctor.id, center_id=center.id,
                                    appointment_date=day, appointment_time=time(9, n), schedule_mode="queue", status="scheduled")
                        for n, patient in enumerate(patients)]
        tomorrow = Appointment(organization_id=1, patient_id=patients[0].id, doctor_id=doctor.id, center_id=center.id,
                               appointment_date=date(2030, 10, 16), appointment_time=time(10), schedule_mode="queue")
        db.add_all([*appointments, tomorrow, DoctorAgendaSetting(organization_id=1, center_id=center.id, doctor_id=doctor.id, base_mode="queue")])
        db.commit()
        ids = {"admin": admin.id, "doctor": doctor.id, "secretary": secretary.id, "center": center.id,
               "foreign_center": foreign_center.id, "appointments": [a.id for a in appointments], "tomorrow": tomorrow.id}
    yield engine, ids, day
    engine.dispose()


def scoped(engine, organization_id=1):
    db = Session(engine)
    bind_scope(db, "tenant", organization_id)
    return db


def make_line(db, ids, prefix="C"):
    return routes.create_line(QueueLineCreate(center_id=ids["center"], doctor_id=ids["doctor"], name=f"Línea {prefix}", prefix=prefix),
                              db.get(User, ids["admin"]), db)


def test_queue_line_arrival_order_and_independent_daily_sequences(queue_db, monkeypatch):
    engine, ids, day = queue_db
    with scoped(engine) as db:
        line_c = make_line(db, ids)
        line_t = make_line(db, ids, "T")
        secretary = db.get(User, ids["secretary"])
        # A prior contact for the third patient cannot determine reception order.
        db.add(AppointmentContactAttempt(organization_id=1, appointment_id=ids["appointments"][2],
                                         contacted_by_user_id=secretary.id, contacted_at=datetime.utcnow(), result="will_attend", channel="phone"))
        db.commit()
        before = db.get(Appointment, ids["appointments"][0])
        original_status, original_time = before.status, before.appointment_time
        first = routes.register_arrival(ids["appointments"][0], ArrivalCreate(queue_line_id=line_c.id), secretary, db)
        second = routes.register_arrival(ids["appointments"][1], ArrivalCreate(queue_line_id=line_c.id), secretary, db)
        other = routes.register_arrival(ids["appointments"][2], ArrivalCreate(queue_line_id=line_t.id), secretary, db)
        assert [first.public_code, second.public_code, other.public_code] == ["C-001", "C-002", "T-001"]
        assert first.arrived_at <= second.arrived_at <= other.arrived_at
        assert first.arrival_registered_by == secretary.id == first.ticket_issued_by
        assert first.ticket_issued_at >= first.arrived_at
        assert datetime.utcnow() >= first.arrived_at
        assert before.status == original_status and before.appointment_time == original_time
        assert before.clinical_history is None
        listed = routes.list_tickets(day, user=secretary, db=db)
        assert [ticket.public_code for ticket in listed] == ["C-001", "C-002", "T-001"]
        assert QueueTicketRead.model_validate(listed[0]).public_code == "C-001"
        with pytest.raises(HTTPException) as duplicate:
            routes.register_arrival(ids["appointments"][0], ArrivalCreate(queue_line_id=line_c.id), secretary, db)
        assert duplicate.value.status_code == 409
        assert db.scalar(select(QueueSequence.last_number).where(QueueSequence.queue_line_id == line_c.id)) == 2

        monkeypatch.setattr("app.services.queue.organization_today", lambda _: date(2030, 10, 16))
        tomorrow = routes.register_arrival(ids["tomorrow"], ArrivalCreate(queue_line_id=line_c.id), secretary, db)
        assert tomorrow.public_code == "C-001" and tomorrow.sequence_number == 1


def test_arrival_for_queue_without_hour_keeps_booking_order_distinct_from_ticket(queue_db):
    engine, ids, _ = queue_db
    with scoped(engine) as db:
        line = make_line(db, ids)
        appointment = db.get(Appointment, ids["appointments"][0])
        appointment.appointment_time = None
        appointment.daily_booking_order = 7
        db.commit()
        assert db.scalar(select(QueueTicket.id).where(QueueTicket.appointment_id == appointment.id)) is None
        ticket = routes.register_arrival(appointment.id, ArrivalCreate(queue_line_id=line.id),
                                         db.get(User, ids["secretary"]), db)
        assert ticket.public_code == "C-001" and ticket.sequence_number == 1
        db.refresh(appointment)
        assert appointment.appointment_time is None
        assert appointment.daily_booking_order == 7
        assert appointment.status == "scheduled"


def test_guards_and_appointment_history(queue_db):
    engine, ids, day = queue_db
    with scoped(engine) as db:
        line = make_line(db, ids)
        admin = db.get(User, ids["admin"])
        doctor = db.get(User, ids["doctor"])
        with pytest.raises(HTTPException) as denied:
            routes.register_arrival(ids["appointments"][0], ArrivalCreate(queue_line_id=line.id), doctor, db)
        assert denied.value.status_code == 403
        with pytest.raises(HTTPException) as premature:
            routes.register_arrival(ids["tomorrow"], ArrivalCreate(queue_line_id=line.id), admin, db)
        assert premature.value.status_code == 409
        ticket = routes.register_arrival(ids["appointments"][0], ArrivalCreate(queue_line_id=line.id), admin, db)
        appointment = db.get(Appointment, ticket.appointment_id)
        with pytest.raises(HTTPException) as blocked:
            delete_appointment(ticket.appointment_id, admin, db)
        assert blocked.value.status_code == 409
        with pytest.raises(HTTPException) as blocked:
            update_appointment(ticket.appointment_id, AppointmentCreate(
                patient_id=appointment.patient_id, doctor_id=appointment.doctor_id, center_id=appointment.center_id,
                appointment_date=appointment.appointment_date, appointment_time=time(11), status=appointment.status,
            ), admin, db)
        assert blocked.value.status_code == 409
        assert db.get(Appointment, ticket.appointment_id).appointment_time == time(9)
        with pytest.raises(HTTPException) as blocked:
            routes.update_line(line.id, QueueLineUpdate(name="Nueva", prefix="N", is_active=True), admin, db)
        assert blocked.value.status_code == 409
        routes.update_line(line.id, QueueLineUpdate(name="Línea C", prefix="C", is_active=False), admin, db)
        with pytest.raises(HTTPException) as inactive:
            routes.register_arrival(ids["appointments"][1], ArrivalCreate(queue_line_id=line.id), admin, db)
        assert inactive.value.status_code == 422

    with scoped(engine, 2) as db:
        admin = db.get(User, ids["admin"])
        assert routes.list_lines(user=admin, db=db) == []
        assert routes.list_tickets(day, user=admin, db=db) == []
        for operation in (
            lambda: routes.register_arrival(ids["appointments"][1], ArrivalCreate(queue_line_id=line.id), admin, db),
            lambda: routes.update_line(line.id, QueueLineUpdate(name="Cruce", prefix="X", is_active=True), admin, db),
            lambda: routes.create_line(QueueLineCreate(center_id=ids["center"], doctor_id=ids["doctor"], name="Cruce", prefix="X"), admin, db),
        ):
            with pytest.raises(HTTPException) as hidden:
                operation()
            assert hidden.value.status_code in (403, 404)


def test_concurrent_arrivals_are_unique_and_monotone(queue_db):
    engine, ids, day = queue_db
    with scoped(engine) as db:
        line_id = make_line(db, ids).id

    def register(appointment_id):
        with scoped(engine) as db:
            actor = db.get(User, ids["secretary"])
            return routes.register_arrival(appointment_id, ArrivalCreate(queue_line_id=line_id), actor, db)

    with ThreadPoolExecutor(max_workers=4) as workers:
        tickets = list(workers.map(register, ids["appointments"]))
    assert sorted(ticket.sequence_number for ticket in tickets) == list(range(1, 9))
    assert len({ticket.public_code for ticket in tickets}) == 8
    assert [ticket.sequence_number for ticket in sorted(tickets, key=lambda t: (t.arrived_at, t.id))] == list(range(1, 9))
    with scoped(engine) as db:
        assert db.scalar(select(QueueSequence.last_number).where(QueueSequence.queue_line_id == line_id)) == 8
