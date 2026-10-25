"""Appointment domain/HTTP slot rules. All identities are isolated synthetic data."""
from datetime import date, time
from types import SimpleNamespace

import pytest
from fastapi import Depends, FastAPI, HTTPException
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError

from app.api.routes import appointments
from app.db import get_db
from app.models import Appointment, CareCenter, Patient, User
from app.schemas.appointment import AppointmentCreate
from app.services.appointment_slots import SLOT_CONFLICT_MESSAGE, translate_slot_integrity_error
from test_agenda_schedule_mode import agenda_db, tenant_session


def body(ids, **changes):
    doctor, _, center, _, patient = ids
    return AppointmentCreate(patient_id=patient, doctor_id=doctor, center_id=center,
        appointment_date=date(2030, 10, 20), appointment_time=time(8), schedule_mode="timed", **changes)


def test_create_conflict_same_and_other_patient_no_partial_or_audit(agenda_db):
    engine, ids = agenda_db
    with tenant_session(engine) as db:
        admin = db.get(User, ids[1]); payload = body(ids)
        first = appointments.create_appointment(payload, admin, db)
        other = Patient(first_name="QA", last_name="B", date_of_birth=date(1991, 1, 1))
        db.add(other); db.commit()
        for pid in (payload.patient_id, other.id):
            with pytest.raises(HTTPException) as conflict:
                appointments.create_appointment(payload.model_copy(update={"patient_id":pid}), admin, db)
            assert (conflict.value.status_code, conflict.value.detail) == (409, SLOT_CONFLICT_MESSAGE)
        assert db.scalar(select(func.count()).select_from(Appointment)) == 1
        assert first.daily_booking_order is None


@pytest.mark.parametrize("released_status", ["cancelled", "no_show"])
def test_release_and_conflicting_reactivation(agenda_db, released_status):
    engine, ids = agenda_db
    with tenant_session(engine) as db:
        admin = db.get(User, ids[1]); p = body(ids)
        first = appointments.create_appointment(p, admin, db)
        appointments.update_appointment(first.id, p.model_copy(update={"status":released_status}), admin, db)
        second = appointments.create_appointment(p, admin, db)
        for status in ("scheduled", "confirmed"):
            with pytest.raises(HTTPException) as conflict:
                appointments.update_appointment(first.id, p.model_copy(update={"status":status}), admin, db)
            assert conflict.value.status_code == 409
        assert db.get(Appointment, first.id).status == released_status
        assert db.get(Appointment, second.id).status == "scheduled"


def test_self_edit_reschedule_and_different_hour(agenda_db):
    engine, ids = agenda_db
    with tenant_session(engine) as db:
        admin = db.get(User, ids[1]); p = body(ids)
        first = appointments.create_appointment(p, admin, db)
        second = appointments.create_appointment(p.model_copy(update={"appointment_time":time(9)}), admin, db)
        appointments.update_appointment(first.id, p.model_copy(update={"status":"confirmed"}), admin, db)
        with pytest.raises(HTTPException) as conflict:
            appointments.update_appointment(second.id, p, admin, db)
        assert conflict.value.status_code == 409
        assert db.get(Appointment, second.id).appointment_time == time(9)
        moved = appointments.update_appointment(second.id, p.model_copy(update={"appointment_time":time(9,30)}), admin, db)
        assert moved.appointment_time == time(9,30)


def test_different_doctor_and_center_do_not_conflict(agenda_db):
    engine, ids = agenda_db
    with tenant_session(engine) as db:
        admin = db.get(User, ids[1]); p = body(ids)
        appointments.create_appointment(p, admin, db)
        doctor = db.get(User, ids[0])
        center = CareCenter(name="QA alternate", city="QA")
        db.add(center); db.flush(); doctor.centers.append(center); db.commit()
        appointments.create_appointment(p.model_copy(update={"center_id":center.id}), admin, db)
        other = User(full_name="QA other doctor", email="other-slot@example.com", password_hash="unusable",
            centers=[db.get(CareCenter, ids[2])], roles=doctor.roles, specialties=doctor.specialties)
        db.add(other); db.commit()
        appointments.create_appointment(p.model_copy(update={"doctor_id":other.id}), admin, db)
        assert db.scalar(select(func.count()).select_from(Appointment)) == 3


def test_queue_unaffected_same_day_and_no_ticket_on_booking(agenda_db):
    from app.api.routes.agenda_schedule import set_base_mode
    from app.schemas.agenda_schedule import PolicyChange
    from app.models import QueueTicket
    engine, ids = agenda_db
    with tenant_session(engine) as db:
        admin = db.get(User, ids[1]); p = body(ids)
        set_base_mode(ids[0], ids[2], PolicyChange(allowed_timed=True, allowed_queue=True, default_mode="timed"), admin, db)
        appointments.create_appointment(p, admin, db)
        a = appointments.create_appointment(p.model_copy(update={"schedule_mode":"queue"}), admin, db)
        b = appointments.create_appointment(p.model_copy(update={"schedule_mode":"queue"}), admin, db)
        assert (a.appointment_time, b.appointment_time) == (None, None)
        assert (a.daily_booking_order, b.daily_booking_order) == (1, 2)
        assert db.scalar(select(func.count()).select_from(QueueTicket)) == 0


def test_conflict_http_409_and_cross_tenant_remains_blocked(agenda_db):
    engine, ids = agenda_db
    app = FastAPI(); app.include_router(appointments.router)
    def session():
        with tenant_session(engine) as db:
            yield db
    def actor(db=Depends(get_db)):
        return db.get(User, ids[1])
    # Existing auth fixtures cover roles/permissions; here only inject the actor,
    # not the slot validation or HTTP exception handling.
    app.dependency_overrides[get_db] = session
    app.dependency_overrides[appointments.access] = actor
    with TestClient(app) as client:
        payload = body(ids).model_dump(mode="json")
        assert client.post("/appointments", json=payload).status_code == 201
        r = client.post("/appointments", json=payload)
        assert r.status_code == 409 and r.json()["detail"] == SLOT_CONFLICT_MESSAGE
    with tenant_session(engine, 2) as db:
        with pytest.raises(HTTPException) as denied:
            appointments.create_appointment(body(ids), db.get(User, ids[1]), db)
        assert denied.value.status_code in (403,404,422)


def test_database_conflict_translation_is_narrow_and_rolls_back():
    calls=[]
    db=SimpleNamespace(rollback=lambda:calls.append("rollback"))
    error=IntegrityError("insert", {}, SimpleNamespace(diag=SimpleNamespace(constraint_name="uq_appointments_active_timed_slot")))
    with pytest.raises(HTTPException) as conflict:
        translate_slot_integrity_error(db,error)
    assert conflict.value.status_code == 409 and calls == ["rollback"]
    translate_slot_integrity_error(db,IntegrityError("insert",{},SimpleNamespace(diag=SimpleNamespace(constraint_name="unrelated_fk"))))
    assert calls == ["rollback"]
