"""Disposable PostgreSQL only; never migrate or write to the official instance."""
import hashlib
import json
from concurrent.futures import ThreadPoolExecutor
from datetime import date, time
from threading import Barrier

from alembic import command
from alembic.config import Config
from fastapi import FastAPI, Request
from fastapi.testclient import TestClient
from sqlalchemy import inspect, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.routes import appointments, auth, clinical_history, queue
from app.core.security import hash_password
from app.db import engine, get_db
from app.models import (Appointment, AppointmentArrival, CareCenter, ClinicalAuditLog, ClinicalHistory,
    DoctorAgendaSetting, OrganizationMembership, Patient, QueueLine, QueueTicket, Role, SecretaryCenterScope, Specialty, User)
from app.services.agenda_schedule import organization_today
from app.services.bootstrap import seed_identity
from app.services.tenancy import resolve_request


def main():
    assert engine.dialect.name == "postgresql"
    assert (engine.url.host or "").startswith("atlas-arrival-qa-")
    assert engine.url.database == "atlas_arrival_qa"
    cfg = Config("alembic.ini")
    command.upgrade(cfg, "0063_appointment_slot_guard")
    with Session(engine) as db:
        seed_identity(db)
        roles = {r.code:r for r in db.scalars(select(Role))}
        center = CareCenter(organization_id=1, name="QA arrival CEMER", city="QA")
        specialty = db.scalar(select(Specialty).where(Specialty.code == "cardiology"))
        assert specialty is not None
        admin = User(full_name="QA arrival admin", email="arrival-admin@example.com", password_hash=hash_password("QAarrival123!"),
            memberships=[OrganizationMembership(organization_id=1, roles=[roles["admin"]])])
        doctor = User(full_name="QA arrival doctor", email="arrival-doctor@example.com", password_hash=hash_password("QAarrival123!"),
            centers=[center], specialties=[specialty], memberships=[OrganizationMembership(organization_id=1, roles=[roles["doctor"]])])
        secretary = User(full_name="QA arrival secretary", email="arrival-secretary@example.com", password_hash=hash_password("QAarrival123!"),
            centers=[center], memberships=[OrganizationMembership(organization_id=1, roles=[roles["secretary"]])])
        db.add_all([admin, doctor, secretary, Patient(id=19, organization_id=1, first_name="QA", last_name="Piloto A", date_of_birth=date(1990,1,1)),
                    Patient(id=20, organization_id=1, first_name="QA", last_name="Piloto B", date_of_birth=date(1991,2,2))]); db.flush()
        db.add(SecretaryCenterScope(organization_id=1, secretary_id=secretary.id, center_id=center.id, manage_all_doctors=True))
        db.add(DoctorAgendaSetting(organization_id=1, doctor_id=doctor.id, center_id=center.id,
            base_mode="timed", allowed_timed=True, allowed_queue=True, default_mode="timed"))
        line = QueueLine(organization_id=1, center_id=center.id, doctor_id=doctor.id, name="QA queue", prefix="QA")
        db.add(line); db.commit()
        ids = {"center":center.id, "doctor":doctor.id, "secretary":secretary.id, "specialty":specialty.id, "line":line.id}
        day = organization_today(db).isoformat()
    app = FastAPI()
    for router in (appointments.router, auth.router, clinical_history.router, queue.router):
        app.include_router(router, prefix="/api/v1")
    def session(request:Request):
        with Session(engine, autoflush=False) as db:
            resolve_request(db, request); yield db
    app.dependency_overrides[get_db] = session
    def client(): return TestClient(app, base_url="http://localhost")
    def login(kind):
        with client() as c:
            r = c.post("/api/v1/auth/login", json={"email":f"arrival-{kind}@example.com", "password":"QAarrival123!"})
            assert r.status_code == 200, r.text
            return {"Authorization":"Bearer " + r.json()["access_token"]}
    admin_headers, secretary_headers, doctor_headers = login("admin"), login("secretary"), login("doctor")
    def book(pid, hour, mode="timed"):
        with client() as c:
            r = c.post("/api/v1/appointments", headers=admin_headers, json={"patient_id":pid, "doctor_id":ids["doctor"],
                "center_id":ids["center"], "specialty_id":ids["specialty"], "appointment_date":day,
                "appointment_time":hour, "schedule_mode":mode})
            assert r.status_code == 201, r.text
            return r.json()
    first = book(19, "08:30")
    with client() as c:
        pre = c.post(f"/api/v1/queue-tickets/arrivals/{first['id']}", headers=secretary_headers, json={"queue_line_id":ids["line"]})
        assert pre.status_code == 409 and "modalidad por turnos" in pre.json()["detail"]
        pending = c.post(f"/api/v1/appointments/{first['id']}/arrival", headers=secretary_headers, json={})
        assert pending.status_code == 503, pending.text
    def fingerprints():
        with engine.connect() as c:
            return {table:hashlib.sha256(c.scalar(text(
                'SELECT coalesce(jsonb_agg(to_jsonb(t) ORDER BY to_jsonb(t)::text),\'[]\'::jsonb)::text FROM "'+table+'" t')).encode()).hexdigest()
                for table in sorted(set(inspect(c).get_table_names())-{"alembic_version", "appointment_arrivals"})}
    before = fingerprints()
    with engine.connect() as c:
        slot_index = c.scalar(text("SELECT indexdef FROM pg_indexes WHERE indexname='uq_appointments_active_timed_slot'"))
    for target in ("0064_appointment_arrivals", "0063_appointment_slot_guard", "0064_appointment_arrivals"):
        (command.downgrade if target.startswith("0063") else command.upgrade)(cfg, target)
        assert fingerprints() == before, "Existing data changed in roundtrip"
    gate = Barrier(2)
    def attempt(_):
        with client() as c:
            gate.wait(timeout=30)
            r = c.post(f"/api/v1/appointments/{first['id']}/arrival", headers=secretary_headers, json={})
            assert r.status_code == 200, r.text
            return r.json()
    with ThreadPoolExecutor(max_workers=2) as pool: results = list(pool.map(attempt, range(2)))
    assert results[0]["arrived_at"] == results[1]["arrived_at"]
    assert all(r["schedule_mode"] == "timed" and r["appointment_time"] == "08:30:00" and r["status"] == "scheduled" for r in results)
    with Session(engine) as db:
        assert len(list(db.scalars(select(AppointmentArrival)))) == 1
        audits = list(db.scalars(select(ClinicalAuditLog).where(ClinicalAuditLog.action == "appointment.arrival")))
        assert len(audits) == 1 and audits[0].user_id == ids["secretary"]
        assert db.scalar(select(QueueTicket.id)) is None
    with client() as c:
        denied = c.post(f"/api/v1/appointments/{first['id']}/arrival", headers=doctor_headers, json={})
        assert denied.status_code == 403
        conflict = c.post("/api/v1/appointments", headers=admin_headers, json={"patient_id":20, "doctor_id":ids["doctor"],
            "center_id":ids["center"], "specialty_id":ids["specialty"], "appointment_date":day,
            "appointment_time":"08:30", "schedule_mode":"timed"})
        assert conflict.status_code == 409
    try:
        with engine.begin() as c:
            c.execute(text("INSERT INTO appointments (organization_id,patient_id,doctor_id,center_id,specialty_id,appointment_date,appointment_time,schedule_mode,status,created_at,updated_at) VALUES (1,20,:d,:c,:s,:day,'08:30','timed','confirmed',now(),now())"),
                {"d":ids["doctor"], "c":ids["center"], "s":ids["specialty"], "day":day})
    except IntegrityError as error:
        assert error.orig.diag.constraint_name == "uq_appointments_active_timed_slot"
    else: raise AssertionError("Check-in released the occupied slot")
    second = book(20, "09:30")
    with client() as c:
        assert c.post(f"/api/v1/appointments/{second['id']}/arrival", headers=secretary_headers, json={}).status_code == 200
        context = c.get(f"/api/v1/clinical-history/appointments/{first['id']}/context", headers=doctor_headers)
        assert context.status_code == 200, context.text
        assert all(context.json()[key] == value for key,value in {"appointment_id":first["id"], "patient_id":19,
            "doctor_id":ids["doctor"], "center_id":ids["center"], "specialty_id":ids["specialty"]}.items())
        url = "/api/v1/clinical-history/patients/19"
        payload = {"appointment_id":first["id"], "consultation_date":day}
        clinical = c.post(url, headers=doctor_headers, json=payload)
        assert clinical.status_code == 201, clinical.text
        assert c.post(url, headers=doctor_headers, json=payload).status_code == 409
    turn = book(20, None, "queue")
    with client() as c:
        r = c.post(f"/api/v1/appointments/{turn['id']}/arrival", headers=secretary_headers, json={"queue_line_id":ids["line"]})
        assert r.status_code == 200 and r.json()["schedule_mode"] == "queue", r.text
    with Session(engine) as db:
        tickets = list(db.scalars(select(QueueTicket)))
        assert len(tickets) == 1 and tickets[0].public_code == "QA-001" and tickets[0].status == "waiting"
        assert len(list(db.scalars(select(ClinicalHistory).where(ClinicalHistory.appointment_id == first["id"])))) == 1
    with engine.connect() as c:
        assert c.scalar(text("SELECT indexdef FROM pg_indexes WHERE indexname='uq_appointments_active_timed_slot'")) == slot_index
    print(json.dumps({"result":"PASS", "pre_fix":409, "roundtrip":"0063->0064->0063->0064",
        "preserved_tables":len(before), "same_appointment_concurrency":[200,200], "arrival_rows_for_first":1,
        "success_audits_for_first":1, "double_booking_http":409, "double_booking_database":"unique_violation",
        "consultation":"201, duplicate 409", "queue_ticket":"QA-001", "slot_index_unchanged":True}))


if __name__ == "__main__":
    main()
