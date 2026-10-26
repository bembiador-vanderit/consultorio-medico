"""Opt-in concurrency validation against an isolated, disposable PostgreSQL 0053 DB."""

import os
from concurrent.futures import ThreadPoolExecutor
from datetime import date
from threading import Barrier

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import engine
from app.models import Appointment, CareCenter, Organization, Patient, QueueTicket, Specialty, User
from app.services.agenda_schedule import lock_center
from app.services.appointment_booking import next_booking_order


pytestmark = pytest.mark.skipif(
    os.environ.get("ATLAS_BOOKING_PG_VALIDATION") != "1",
    reason="Requires disposable PostgreSQL 0053 database",
)


def test_two_concurrent_bookings_get_distinct_monotonic_orders():
    assert engine.dialect.name == "postgresql"
    assert engine.url.host == "atlas-0053-booking-qa"
    assert engine.url.database == "atlas_0053_qa"
    day = date(2030, 10, 16)
    with Session(engine) as db:
        org = Organization(slug="qa-booking-0053", name="QA booking")
        db.add(org)
        db.flush()
        center = CareCenter(organization_id=org.id, name="QA center", city="QA")
        doctor = User(email="doctor-booking-0053@example.test", full_name="QA Doctor", password_hash="synthetic")
        specialty = Specialty(organization_id=org.id, name="QA specialty", code="QA-BOOKING")
        patient = Patient(organization_id=org.id, first_name="QA", last_name="Patient", date_of_birth=date(1990, 1, 1))
        db.add_all([center, doctor, specialty, patient])
        db.commit()
        ids = (org.id, center.id, doctor.id, specialty.id, patient.id)

    gate = Barrier(2)

    def book():
        gate.wait()
        with Session(engine) as db:
            lock_center(db, ids[1])
            order = next_booking_order(db, organization_id=ids[0], center_id=ids[1], doctor_id=ids[2], day=day)
            appointment = Appointment(organization_id=ids[0], center_id=ids[1], doctor_id=ids[2],
                specialty_id=ids[3], patient_id=ids[4], appointment_date=day,
                appointment_time=None, schedule_mode="queue", daily_booking_order=order, status="scheduled")
            db.add(appointment)
            db.commit()
            return appointment.id, order

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: book(), range(2)))
    assert sorted(order for _, order in results) == [1, 2]
    with Session(engine) as db:
        appointments = db.scalars(select(Appointment).where(Appointment.id.in_([item[0] for item in results]))).all()
        assert sorted(item.daily_booking_order for item in appointments) == [1, 2]
        assert all(item.appointment_time is None for item in appointments)
        assert not db.scalars(select(QueueTicket).where(QueueTicket.appointment_id.in_([item[0] for item in results]))).first()
        db.delete(appointments[1])
        db.commit()
    with Session(engine) as db:
        lock_center(db, ids[1])
        assert next_booking_order(db, organization_id=ids[0], center_id=ids[1], doctor_id=ids[2], day=day) == 3
        db.rollback()
