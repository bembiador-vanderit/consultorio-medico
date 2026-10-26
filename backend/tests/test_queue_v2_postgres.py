"""Real PostgreSQL V2 validation; opt in only with an isolated copied database."""

import os
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, time
from threading import Barrier
from types import SimpleNamespace
from uuid import uuid4
from zoneinfo import ZoneInfo

import pytest
from fastapi import FastAPI, Request
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.routes import appointments, auth, clinical_history, patients, queue
from app.core.security import hash_password
from app.db import engine, get_db
from app.models import (
    Appointment, CareCenter, ClinicalHistory, DoctorAgendaSetting, Organization,
    OrganizationMembership, Patient, QueueLine, QueueTicket, QueueTicketEvent,
    Role, SecretaryCenterScope, Specialty, SpecialtyTemplate, User,
)
from app.services import tenancy


pytestmark = pytest.mark.skipif(
    os.environ.get("ATLAS_V2_PG_VALIDATION") != "1",
    reason="Requires an explicitly selected disposable PostgreSQL copy",
)
PASSWORD = os.environ.get("ATLAS_V2_PG_TEST_PASSWORD", "")
DAY = datetime.now(ZoneInfo("America/Santo_Domingo")).date()


def _seed_case():
    assert len(PASSWORD) >= 12
    assert engine.dialect.name == "postgresql"
    assert engine.url.host.startswith("atlas-v2-")
    assert engine.url.database == "atlas_v2_validation"
    tag = uuid4().hex[:10]
    with Session(engine) as db:
        org = db.scalar(select(Organization).where(Organization.slug == "pilot"))
        roles = {row.code: row for row in db.scalars(select(Role).where(Role.code.in_(["admin", "doctor", "secretary"]))).all()}
        specialty = db.scalar(
            select(Specialty).join(SpecialtyTemplate, SpecialtyTemplate.specialty_id == Specialty.id)
            .where(Specialty.organization_id == org.id, SpecialtyTemplate.status == "published")
        )
        assert org and len(roles) == 3 and specialty
        other = Organization(slug=f"atlas-v2-{tag}", name="Organización sintética V2", timezone="America/Santo_Domingo")
        db.add(other)
        db.flush()
        center = CareCenter(organization_id=org.id, name=f"Centro sintético {tag}", city="Prueba")
        other_center = CareCenter(organization_id=other.id, name=f"Otro centro {tag}", city="Prueba")
        db.add_all([center, other_center])
        db.flush()
        people = {}
        for code in ("admin", "doctor", "secretary", "unauthorized"):
            user = User(
                email=f"atlas-v2-{code}-{tag}@synthetic.example.com",
                full_name=f"V2 {code}", password_hash=hash_password(PASSWORD),
                centers=[center] if code != "unauthorized" else [],
                memberships=[OrganizationMembership(
                    organization_id=org.id,
                    roles=[roles[code]] if code in roles else [],
                )],
            )
            if code == "doctor":
                user.specialties = [specialty]
            db.add(user)
            people[code] = user
        other_user = User(
            email=f"atlas-v2-other-{tag}@synthetic.example.com",
            full_name="V2 Otro", password_hash=hash_password(PASSWORD), centers=[other_center],
            memberships=[OrganizationMembership(organization_id=other.id, roles=[roles["admin"]])],
        )
        platform_user = User(
            email=f"atlas-v2-platform-{tag}@synthetic.example.com",
            full_name="V2 Plataforma", password_hash=hash_password(PASSWORD),
            is_platform_admin=True,
        )
        db.add_all([other_user, platform_user])
        db.flush()
        db.add(SecretaryCenterScope(
            organization_id=org.id, secretary_id=people["secretary"].id,
            center_id=center.id, manage_all_doctors=True,
        ))
        db.add(DoctorAgendaSetting(
            organization_id=org.id, doctor_id=people["doctor"].id,
            center_id=center.id, base_mode="queue",
        ))
        line = QueueLine(
            organization_id=org.id, center_id=center.id, doctor_id=people["doctor"].id,
            name=f"Línea C {tag}", prefix="C", is_active=True,
            call_on_consultation_start=False,
        )
        db.add(line)
        db.flush()
        appointment_ids, patient_ids = [], []
        for number in range(1, 15):
            patient = Patient(
                organization_id=org.id, first_name=f"Sintético{number}",
                last_name="V2", date_of_birth=date(1990, 1, 1),
            )
            db.add(patient)
            db.flush()
            appointment = Appointment(
                organization_id=org.id, patient_id=patient.id, doctor_id=people["doctor"].id,
                center_id=center.id, specialty_id=specialty.id, appointment_date=DAY,
                appointment_time=time(9, number), schedule_mode="queue", status="scheduled",
            )
            db.add(appointment)
            db.flush()
            appointment_ids.append(appointment.id)
            patient_ids.append(patient.id)
        db.commit()
        return SimpleNamespace(
            tag=tag, org_id=org.id, other_slug=other.slug,
            center_id=center.id, doctor_id=people["doctor"].id,
            secretary_id=people["secretary"].id, line_id=line.id,
            appointment_ids=appointment_ids, patient_ids=patient_ids,
        )


def _app(case, monkeypatch):
    monkeypatch.setattr(tenancy, "get_settings", lambda: SimpleNamespace(
        platform_hosts=["v2-platform.synthetic.test"],
        tenant_hosts={"v2-one.synthetic.test": "pilot", "v2-two.synthetic.test": case.other_slug},
    ))
    app = FastAPI()
    for router in (auth.router, queue.router, patients.router, appointments.router, clinical_history.router):
        app.include_router(router, prefix="/api/v1")

    def session(request: Request):
        with Session(engine) as db:
            tenancy.resolve_request(db, request)
            yield db

    app.dependency_overrides[get_db] = session
    return app


def _login(client, case, role):
    result = client.post("/api/v1/auth/login", json={
        "email": f"atlas-v2-{role}-{case.tag}@synthetic.example.com", "password": PASSWORD,
    })
    assert result.status_code == 200, (role, result.status_code)
    return {"Authorization": "Bearer " + result.json()["access_token"]}


def _issue(client, case, headers):
    tickets = []
    for appointment_id in case.appointment_ids:
        response = client.post(
            f"/api/v1/queue-tickets/arrivals/{appointment_id}",
            json={"queue_line_id": case.line_id}, headers=headers,
        )
        assert response.status_code == 201, (response.status_code, response.json().get("detail"))
        tickets.append(response.json())
    assert [item["public_code"] for item in tickets] == [f"C-{n:03d}" for n in range(1, 15)]
    return tickets


def _parallel(app, headers, path, count):
    barrier = Barrier(count)

    def invoke(_):
        with TestClient(app, base_url="http://v2-one.synthetic.test") as client:
            barrier.wait(timeout=20)
            response = client.post(path, headers=headers)
            body = response.json()
            return response.status_code, body.get("public_code"), body.get("status")

    with ThreadPoolExecutor(max_workers=count) as pool:
        return list(pool.map(invoke, range(count)))


def _events(ticket_id):
    with Session(engine) as db:
        return list(db.scalars(
            select(QueueTicketEvent).where(QueueTicketEvent.queue_ticket_id == ticket_id)
            .order_by(QueueTicketEvent.id)
        ))


def test_concurrent_initial_call_same_ticket_only_one_wins(monkeypatch):
    case = _seed_case()
    app = _app(case, monkeypatch)
    with TestClient(app, base_url="http://v2-one.synthetic.test") as client:
        secretary = _login(client, case, "secretary")
        doctor = _login(client, case, "doctor")
        tickets = _issue(client, case, secretary)
        before_call = datetime.utcnow()
        first = client.post(f"/api/v1/queue-tickets/{tickets[0]['id']}/call", headers=secretary)
        assert first.status_code == 200
        assert first.json()["status"] == "called" and first.json()["call_count"] == 1
        assert first.json()["first_called_at"] == first.json()["last_called_at"]
        assert before_call <= datetime.fromisoformat(first.json()["first_called_at"]) <= datetime.utcnow()
        recalled = client.post(f"/api/v1/queue-tickets/{tickets[0]['id']}/recall", headers=doctor)
        assert recalled.status_code == 200 and recalled.json()["call_count"] == 2
        assert recalled.json()["first_called_at"] == first.json()["first_called_at"]
        assert datetime.fromisoformat(recalled.json()["last_called_at"]) > datetime.fromisoformat(first.json()["last_called_at"])
        assert [event.event_type for event in _events(tickets[0]["id"])] == ["ARRIVED", "ISSUED", "CALLED", "RECALLED"]
        assert [event.actor_user_id for event in _events(tickets[0]["id"])][2:] == [case.secretary_id, case.doctor_id]

        # 0046 allows only one outstanding call for this doctor and center.
        assert client.post(f"/api/v1/queue-tickets/{tickets[0]['id']}/no-response", headers=secretary).status_code == 200
        next_calls = _parallel(app, secretary, f"/api/v1/queue-lines/{case.line_id}/call-next?day={DAY}", 4)
        assert sorted(status for status, _, _ in next_calls) == [200, 409, 409, 409]
        assert next(code for status, code, _ in next_calls if status == 200) == "C-002"
        assert [event.event_type for event in _events(tickets[1]["id"])].count("CALLED") == 1
        assert client.post(f"/api/v1/queue-tickets/{tickets[1]['id']}/no-response", headers=secretary).status_code == 200

        same = _parallel(app, secretary, f"/api/v1/queue-tickets/{tickets[2]['id']}/call", 2)
        assert sorted(status for status, _, _ in same) == [200, 409], same
        with Session(engine) as db:
            ticket = db.get(QueueTicket, tickets[2]["id"])
            assert ticket.status == "called" and ticket.call_count == 1
            assert ticket.first_called_at and ticket.last_called_at
            assert ticket.called_by_user_id == case.secretary_id
            first_called = ticket.first_called_at
        event_types = [event.event_type for event in _events(tickets[2]["id"])]
        assert event_types == ["ARRIVED", "ISSUED", "CALLED"]

        explicit_recall = client.post(f"/api/v1/queue-tickets/{tickets[2]['id']}/recall", headers=doctor)
        assert explicit_recall.status_code == 200 and explicit_recall.json()["call_count"] == 2
        assert datetime.fromisoformat(explicit_recall.json()["first_called_at"]) == first_called
        recalls = _parallel(app, secretary, f"/api/v1/queue-tickets/{tickets[2]['id']}/recall", 2)
        assert sorted(status for status, _, _ in recalls) == [200, 200], recalls
        with Session(engine) as db:
            ticket = db.get(QueueTicket, tickets[2]["id"])
            assert ticket.call_count == 4 and ticket.first_called_at == first_called
            assert ticket.called_by_user_id == case.secretary_id
            assert ticket.last_called_at > first_called
        assert [event.event_type for event in _events(tickets[2]["id"])] == [
            "ARRIVED", "ISSUED", "CALLED", "RECALLED", "RECALLED", "RECALLED",
        ]


def test_queue_v2_remaining_postgres_behaviors(monkeypatch):
    case = _seed_case()
    app = _app(case, monkeypatch)
    with TestClient(app, base_url="http://v2-one.synthetic.test") as client:
        secretary = _login(client, case, "secretary")
        doctor = _login(client, case, "doctor")
        unauthorized = _login(client, case, "unauthorized")
        tickets = _issue(client, case, secretary)

        first = tickets[0]
        with Session(engine) as db:
            appt = db.get(Appointment, first["appointment_id"])
            original = (appt.status, appt.appointment_time)
            assert db.scalar(select(ClinicalHistory.id).where(ClinicalHistory.appointment_id == appt.id)) is None
        assert client.post(f"/api/v1/queue-tickets/{first['id']}/call", headers=secretary).status_code == 200
        started = client.post(f"/api/v1/queue-tickets/{first['id']}/start", headers=doctor)
        assert started.status_code == 200 and started.json()["status"] == "in_service"
        assert started.json()["consultation_started_at"] and started.json()["consultation_started_by_user_id"] == case.doctor_id
        assert [event.event_type for event in _events(first["id"])] == ["ARRIVED", "ISSUED", "CALLED", "SERVICE_STARTED"]
        with Session(engine) as db:
            appt = db.get(Appointment, first["appointment_id"])
            assert (appt.status, appt.appointment_time) == original
            assert db.scalar(select(ClinicalHistory.id).where(ClinicalHistory.appointment_id == appt.id)) is None

        waiting = tickets[1]
        rejected = client.post(f"/api/v1/queue-tickets/{waiting['id']}/start", headers=doctor)
        assert rejected.status_code == 409
        with Session(engine) as db:
            row = db.get(QueueTicket, waiting["id"])
            assert row.status == "waiting" and row.first_called_at is None and row.consultation_started_at is None
        assert [event.event_type for event in _events(waiting["id"])] == ["ARRIVED", "ISSUED"]

        assert client.post(f"/api/v1/queue-tickets/{first['id']}/complete", headers=doctor).status_code == 200

        with Session(engine) as db:
            db.get(QueueLine, case.line_id).call_on_consultation_start = True
            db.commit()
        auto = client.post(f"/api/v1/queue-tickets/{tickets[1]['id']}/start", headers=doctor)
        assert auto.status_code == 200 and auto.json()["status"] == "in_service" and auto.json()["call_count"] == 1
        assert auto.json()["first_called_at"] == auto.json()["last_called_at"] == auto.json()["consultation_started_at"]
        assert [event.event_type for event in _events(tickets[1]["id"])] == ["ARRIVED", "ISSUED", "CALLED", "SERVICE_STARTED"]
        assert client.post(f"/api/v1/queue-tickets/{tickets[1]['id']}/complete", headers=doctor).status_code == 200

        no_answer = tickets[2]
        assert client.post(f"/api/v1/queue-tickets/{no_answer['id']}/call", headers=secretary).status_code == 200
        no_response = client.post(f"/api/v1/queue-tickets/{no_answer['id']}/no-response", headers=secretary)
        assert no_response.status_code == 200 and no_response.json()["status"] == "no_response"
        assert no_response.json()["public_code"] == no_answer["public_code"]
        assert client.post(f"/api/v1/queue-tickets/{no_answer['id']}/start", headers=doctor).status_code == 409
        assert [event.event_type for event in _events(no_answer["id"])] == ["ARRIVED", "ISSUED", "CALLED", "NO_RESPONSE"]

        left_waiting = tickets[3]
        left = client.post(f"/api/v1/queue-tickets/{left_waiting['id']}/left", headers=secretary)
        assert left.status_code == 200 and left.json()["status"] == "left"
        assert left.json()["left_at"] and left.json()["left_by_user_id"] == case.secretary_id
        assert left.json()["public_code"] == left_waiting["public_code"]
        assert [event.event_type for event in _events(left_waiting["id"])] == ["ARRIVED", "ISSUED", "LEFT"]
        left_called = tickets[4]
        assert client.post(f"/api/v1/queue-tickets/{left_called['id']}/call", headers=doctor).status_code == 200
        assert client.post(f"/api/v1/queue-tickets/{left_called['id']}/left", headers=secretary).status_code == 200
        assert [event.event_type for event in _events(left_called["id"])] == ["ARRIVED", "ISSUED", "CALLED", "LEFT"]

        # Reading the clinical context must not create a call or start event.
        untouched = tickets[5]
        before_events = [event.id for event in _events(untouched["id"])]
        assert client.get(f"/api/v1/patients/{untouched['patient_id']}", headers=doctor).status_code == 200
        assert client.get("/api/v1/appointments", params={"start": DAY.isoformat(), "end": DAY.isoformat()}, headers=doctor).status_code == 200
        assert client.get(f"/api/v1/clinical-history/patients/{untouched['patient_id']}", headers=doctor).status_code == 200
        assert client.get(f"/api/v1/clinical-history/appointments/{untouched['appointment_id']}/context", headers=doctor).status_code == 200
        with Session(engine) as db:
            row = db.get(QueueTicket, untouched["id"])
            assert row.status == "waiting" and row.first_called_at is None and row.consultation_started_at is None
        assert [event.id for event in _events(untouched["id"])] == before_events

        # The doctor can operate the assigned line; an unprivileged account cannot.
        lines = client.get("/api/v1/queue-lines", headers=doctor)
        assert lines.status_code == 200 and any(item["id"] == case.line_id for item in lines.json())
        assert client.get("/api/v1/queue-lines", headers=unauthorized).status_code == 403
        assert client.post(f"/api/v1/queue-tickets/{untouched['id']}/call", headers=unauthorized).status_code == 403
        assert client.post(f"/api/v1/queue-tickets/{tickets[7]['id']}/recall", headers=unauthorized).status_code == 403
        assert client.post(f"/api/v1/queue-lines/{case.line_id}/call-next", params={"day": DAY.isoformat()}, headers=unauthorized).status_code == 403
        assert client.post(f"/api/v1/queue-tickets/{untouched['id']}/call", headers=doctor).status_code == 200
        assert client.post(f"/api/v1/queue-tickets/{untouched['id']}/recall", headers=doctor).status_code == 200
        assert client.post(f"/api/v1/queue-tickets/{untouched['id']}/no-response", headers=doctor).status_code == 200
        next_doctor = client.post(f"/api/v1/queue-lines/{case.line_id}/call-next", params={"day": DAY.isoformat()}, headers=doctor)
        assert next_doctor.status_code == 200 and next_doctor.json()["public_code"] == "C-007"

        states = {
            "called": tickets[6]["id"],
            "completed": first["id"], "no_response": no_answer["id"], "left": left_waiting["id"],
        }
        for state, ticket_id in states.items():
            assert client.post(f"/api/v1/queue-tickets/{ticket_id}/call", headers=secretary).status_code == 409
            if state != "called":
                assert client.post(f"/api/v1/queue-tickets/{ticket_id}/recall", headers=secretary).status_code == 409
        still_waiting = tickets[7]["id"]
        assert client.post(f"/api/v1/queue-tickets/{still_waiting}/recall", headers=secretary).status_code == 409
        assert client.post(f"/api/v1/queue-tickets/{still_waiting}/call", headers=secretary).status_code == 409
        assert client.post(f"/api/v1/queue-tickets/{tickets[6]['id']}/no-response", headers=doctor).status_code == 200
        assert client.post(f"/api/v1/queue-tickets/{still_waiting}/call", headers=secretary).status_code == 200
        with Session(engine) as db:
            for item in tickets:
                ticket = db.get(QueueTicket, item["id"])
                appointment = db.get(Appointment, ticket.appointment_id)
                patient = db.get(Patient, ticket.patient_id)
                assert ticket.organization_id == appointment.organization_id == patient.organization_id == case.org_id
                assert ticket.center_id == appointment.center_id == case.center_id
                assert ticket.doctor_id == appointment.doctor_id == case.doctor_id
                assert ticket.patient_id == appointment.patient_id
                assert ticket.service_date == appointment.appointment_date == DAY
                assert ticket.sequence_number == int(ticket.public_code.split("-")[1])

    with TestClient(app, base_url="http://v2-two.synthetic.test") as other_client:
        other_token = _login(other_client, case, "other")
        assert other_client.get("/api/v1/queue-lines", headers=other_token).json() == []
        assert other_client.get("/api/v1/queue-tickets", params={"day": DAY.isoformat()}, headers=other_token).json() == []
        assert other_client.get(f"/api/v1/queue-tickets/{tickets[0]['id']}/events", headers=other_token).status_code == 404
        assert other_client.post(f"/api/v1/queue-tickets/{tickets[0]['id']}/call", headers=other_token).status_code == 404
        assert other_client.post(f"/api/v1/queue-tickets/{tickets[0]['id']}/start", headers=other_token).status_code == 404
        with TestClient(app, base_url="http://v2-one.synthetic.test") as first_tenant:
            assert first_tenant.post(f"/api/v1/queue-tickets/{tickets[0]['id']}/call", headers=other_token).status_code == 401
        with Session(engine) as db:
            tenancy.bind_scope(db, "tenant", db.scalar(select(Organization.id).where(Organization.slug == case.other_slug)))
            assert db.scalar(select(func.count()).select_from(QueueTicketEvent)) == 0
    with TestClient(app, base_url="http://v2-platform.synthetic.test") as platform_client:
        platform_token = _login(platform_client, case, "platform")
        assert platform_client.post(f"/api/v1/queue-tickets/{tickets[0]['id']}/call", headers=platform_token).status_code == 403
        assert platform_client.post(f"/api/v1/queue-tickets/{tickets[0]['id']}/start", headers=platform_token).status_code == 403
