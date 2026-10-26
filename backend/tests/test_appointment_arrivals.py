from datetime import timedelta

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.deps import current_user
from app.api.routes import appointments
from app.db import get_db
from app.models import Appointment, AppointmentArrival, ClinicalAuditLog, Permission, QueueSequence, QueueTicket, Role, User
from app.schemas.appointment import AppointmentArrivalCreate, AppointmentCreate
from app.services.appointment_arrivals import register_arrival
from test_queue_arrivals import queue_db, scoped, make_line
from test_clinical_security_lifecycle import clinical_app


def hourly(db, ids, status="scheduled"):
    row = db.get(Appointment, ids["appointments"][0])
    row.schedule_mode = "timed"; row.status = status
    db.commit()
    return row


@pytest.mark.parametrize("status", ["scheduled", "confirmed"])
def test_hourly_arrival_preserves_booking_no_ticket_and_one_audit(queue_db, monkeypatch, status):
    engine, ids, day = queue_db
    monkeypatch.setattr("app.services.appointment_arrivals.organization_today", lambda _: day)
    with scoped(engine) as db:
        row = hourly(db, ids, status); original = (row.appointment_time, row.appointment_date)
        actor = db.get(User, ids["secretary"])
        first = appointments.check_in(row.id, AppointmentArrivalCreate(), actor, db)
        second = appointments.check_in(row.id, AppointmentArrivalCreate(), actor, db)
        assert first.arrived_at == second.arrived_at and first.arrived_at is not None
        assert first.arrival_registered_by == actor.id
        assert first.schedule_mode == "timed" and first.status == status
        assert (first.appointment_time, first.appointment_date) == original
        assert first.daily_booking_order is None and not first.has_clinical_history
        assert db.scalar(select(func.count()).select_from(AppointmentArrival)) == 1
        audit = list(db.scalars(select(ClinicalAuditLog).where(ClinicalAuditLog.action == "appointment.arrival")))
        assert len(audit) == 1 and audit[0].user_id == actor.id
        assert audit[0].context["patient_id"] == row.patient_id
        assert audit[0].context["before"]["status"] == audit[0].context["after"]["status"] == status
        assert db.scalar(select(func.count()).select_from(QueueTicket)) == 0
        assert db.scalar(select(func.count()).select_from(QueueSequence)) == 0
        # The exact 0063 occupying state stays unchanged after check-in.
        from app.services.appointment_slots import ensure_slot_available
        with pytest.raises(HTTPException) as conflict:
            ensure_slot_available(db, organization_id=1, center_id=row.center_id, doctor_id=row.doctor_id,
                day=day, start_time=row.appointment_time, schedule_mode="timed", status="scheduled")
        assert conflict.value.status_code == 409


@pytest.mark.parametrize("status", ["cancelled", "completed", "no_show"])
def test_terminal_denied_without_success_audit(queue_db, monkeypatch, status):
    engine, ids, day = queue_db
    monkeypatch.setattr("app.services.appointment_arrivals.organization_today", lambda _: day)
    with scoped(engine) as db:
        row = hourly(db, ids, status)
        with pytest.raises(HTTPException) as error:
            register_arrival(db, row.id, db.get(User, ids["admin"]))
        assert error.value.status_code == 409
        assert db.scalar(select(func.count()).select_from(AppointmentArrival)) == 0
        assert db.scalar(select(func.count()).select_from(ClinicalAuditLog)) == 0


@pytest.mark.parametrize("offset", [-1, 1])
def test_wrong_day_denied(queue_db, monkeypatch, offset):
    engine, ids, day = queue_db
    monkeypatch.setattr("app.services.appointment_arrivals.organization_today", lambda _: day + timedelta(days=offset))
    with scoped(engine) as db:
        row = hourly(db, ids)
        with pytest.raises(HTTPException) as error:
            register_arrival(db, row.id, db.get(User, ids["admin"]))
        assert error.value.status_code == 409


def test_scope_tenant_role_and_disabled_center(queue_db, monkeypatch):
    engine, ids, day = queue_db
    monkeypatch.setattr("app.services.appointment_arrivals.organization_today", lambda _: day)
    with scoped(engine) as db:
        row = hourly(db, ids)
        with pytest.raises(HTTPException) as denied:
            register_arrival(db, row.id, db.get(User, ids["doctor"]))
        assert denied.value.status_code == 403
        secretary = db.get(User, ids["secretary"])
        secretary.centers.clear(); db.commit()
        with pytest.raises(HTTPException) as denied:
            register_arrival(db, row.id, secretary)
        assert denied.value.status_code == 403
    with scoped(engine, 2) as db:
        with pytest.raises(HTTPException) as denied:
            register_arrival(db, ids["appointments"][0], db.get(User, ids["admin"]))
        assert denied.value.status_code == 404


def test_common_operation_queue_delegates_unchanged(queue_db):
    engine, ids, _ = queue_db
    with scoped(engine) as db:
        line = make_line(db, ids)
        result = appointments.check_in(ids["appointments"][0], AppointmentArrivalCreate(queue_line_id=line.id),
            db.get(User, ids["secretary"]), db)
        assert result.schedule_mode == "queue" and result.arrived_at is not None
        ticket = db.scalar(select(QueueTicket))
        assert ticket.public_code == "C-001" and ticket.status == "waiting"
        assert db.scalar(select(func.count()).select_from(AppointmentArrival)) == 0


def test_arrived_context_is_immutable_and_cannot_delete(queue_db, monkeypatch):
    engine, ids, day = queue_db
    monkeypatch.setattr("app.services.appointment_arrivals.organization_today", lambda _: day)
    with scoped(engine) as db:
        row = hourly(db, ids); admin = db.get(User, ids["admin"])
        register_arrival(db, row.id, admin)
        payload = AppointmentCreate(patient_id=row.patient_id, doctor_id=row.doctor_id, center_id=row.center_id,
            appointment_date=day+timedelta(days=1), appointment_time=row.appointment_time, schedule_mode="timed")
        with pytest.raises(HTTPException) as denied:
            appointments.update_appointment(row.id, payload, admin, db)
        assert denied.value.status_code == 409
        with pytest.raises(HTTPException) as denied:
            appointments.delete_appointment(row.id, admin, db)
        assert denied.value.status_code == 409


def test_http_permission_denial_does_not_grant_clinical_access(queue_db, monkeypatch):
    engine, ids, day = queue_db
    monkeypatch.setattr("app.services.appointment_arrivals.organization_today", lambda _: day)
    with scoped(engine) as db:
        row = hourly(db, ids)
        actor = db.get(User, ids["secretary"])
        app = FastAPI(); app.include_router(appointments.router)
        app.dependency_overrides[get_db] = lambda: db
        app.dependency_overrides[current_user] = lambda: actor
        with TestClient(app) as client:
            assert client.post(f"/appointments/{row.id}/arrival", json={}).status_code == 403
            # Catalog provisioning is deliberately outside tenant HTTP scope;
            # production must continue rejecting attempts to create permissions there.
            role_id = actor.roles[0].id
            with Session(engine) as provisioning:
                provisioned_role = provisioning.get(Role, role_id)
                provisioned_role.permissions.append(Permission(code="patients:access", description="QA"))
                provisioning.commit()
            db.expire_all()
            assert client.post(f"/appointments/{row.id}/arrival", json={}).status_code == 200
            actor.tenant_membership().denied_permissions = ["patients:access"]; db.commit()
            assert client.post(f"/appointments/{row.id}/arrival", json={}).status_code == 403


def test_schema_not_activated_is_controlled_and_legacy_reads_work(queue_db, monkeypatch):
    engine, ids, day = queue_db
    monkeypatch.setattr("app.services.appointment_arrivals.organization_today", lambda _: day)
    AppointmentArrival.__table__.drop(engine)
    with scoped(engine) as db:
        row = hourly(db, ids)
        read = appointments.response(row)
        assert read.arrival_enabled is False and read.arrived_at is None
        with pytest.raises(HTTPException) as error:
            register_arrival(db, row.id, db.get(User, ids["admin"]))
        assert error.value.status_code == 503


def test_hourly_arrival_continues_exact_consultation_context_without_duplicate(clinical_app, monkeypatch):
    from datetime import date, time
    data = clinical_app; db = data["db"]; day = date.today()
    monkeypatch.setattr("app.services.appointment_arrivals.organization_today", lambda _: day)
    row = Appointment(patient_id=data["patient_a"].id, doctor_id=data["doctor_a"].id,
        center_id=data["center"].id, specialty_id=data["specialty"].id,
        appointment_date=day, appointment_time=time(11, 37), schedule_mode="timed", status="confirmed")
    db.add(row); db.commit()
    register_arrival(db, row.id, data["admin"])
    client = data["client"]
    response = client.post(f"/api/v1/clinical-history/patients/{row.patient_id}",
        json={"appointment_id":row.id, "consultation_date":day.isoformat()})
    assert response.status_code == 201, response.text
    body = response.json()
    assert (body["patient_id"], body["doctor_id"], body["center_id"], body["specialty_id"], body["appointment_id"]) == (
        row.patient_id, row.doctor_id, row.center_id, row.specialty_id, row.id)
    again = client.post(f"/api/v1/clinical-history/patients/{row.patient_id}",
        json={"appointment_id":row.id, "consultation_date":day.isoformat()})
    assert again.status_code == 409
