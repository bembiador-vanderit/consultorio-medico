"""Opt-in V3 concurrency validation against a disposable PostgreSQL copy."""

import os
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from threading import Barrier

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

import test_queue_v2_postgres as v2
from app.db import engine
from app.core.security import hash_password
from app.models import (
    Appointment, CareCenter, ClinicalHistory, Organization, OrganizationMembership,
    QueueTicket, Role, User,
)


pytestmark = pytest.mark.skipif(
    os.environ.get("ATLAS_V2_PG_VALIDATION") != "1",
    reason="Requires an explicitly selected disposable PostgreSQL copy",
)


def test_two_simultaneous_completions_have_one_winner(monkeypatch):
    case = v2._seed_case()  # Enforces disposable host and database before writing.
    with Session(engine) as db:
        doctor_role = db.scalar(select(Role).where(Role.code == "doctor"))
        other_org = db.scalar(select(Organization).where(Organization.slug == case.other_slug))
        other_center = db.scalar(select(CareCenter).where(CareCenter.organization_id == other_org.id))
        for role_name, org_id, center_id in (
            ("unassigned-doctor", case.org_id, case.center_id),
            ("other-doctor", other_org.id, other_center.id),
        ):
            user = User(
                email=f"atlas-v2-{role_name}-{case.tag}@synthetic.example.com",
                full_name=f"V3 {role_name}", password_hash=hash_password(v2.PASSWORD),
                centers=[db.get(CareCenter, center_id)],
                memberships=[OrganizationMembership(organization_id=org_id, roles=[doctor_role])],
            )
            db.add(user)
        db.commit()
    app = v2._app(case, monkeypatch)
    with TestClient(app, base_url="http://v2-one.synthetic.test") as client:
        secretary = v2._login(client, case, "secretary")
        doctor = v2._login(client, case, "doctor")
        unassigned_doctor = v2._login(client, case, "unassigned-doctor")
        admin = v2._login(client, case, "admin")
        tickets = v2._issue(client, case, secretary)
        ticket_id = tickets[0]["id"]
        assert client.post(f"/api/v1/queue-tickets/{ticket_id}/call", headers=secretary).status_code == 200
        started = client.post(f"/api/v1/queue-tickets/{ticket_id}/start", headers=doctor)
        assert started.status_code == 200 and started.json()["status"] == "in_service"
        with Session(engine) as db:
            ticket = db.get(QueueTicket, ticket_id)
            appointment = db.get(Appointment, ticket.appointment_id)
            before_ticket = (
                ticket.arrived_at, ticket.first_called_at, ticket.last_called_at,
                ticket.call_count, ticket.sequence_number, ticket.consultation_started_at,
            )
            before_appointment = (appointment.status, appointment.appointment_time)
            assert db.scalar(select(ClinicalHistory.id).where(ClinicalHistory.appointment_id == appointment.id)) is None
        assert client.post(f"/api/v1/queue-tickets/{ticket_id}/complete", headers=secretary).status_code == 403
        assert client.post(f"/api/v1/queue-tickets/{ticket_id}/complete", headers=admin).status_code == 403
        assert client.post(f"/api/v1/queue-tickets/{ticket_id}/complete", headers=unassigned_doctor).status_code == 403
        before = datetime.utcnow()
        barrier = Barrier(2)

        def complete_once(_):
            with TestClient(app, base_url="http://v2-one.synthetic.test") as contender:
                barrier.wait(timeout=20)
                response = contender.post(f"/api/v1/queue-tickets/{ticket_id}/complete", headers=doctor)
                return response.status_code, response.json().get("consultation_finished_at")

        with ThreadPoolExecutor(max_workers=2) as workers:
            responses = list(workers.map(complete_once, range(2)))
        assert sorted(status for status, _ in responses) == [200, 409]
        winner_time = datetime.fromisoformat(next(stamp for status, stamp in responses if status == 200))
        with Session(engine) as db:
            ticket = db.get(QueueTicket, ticket_id)
            appointment = db.get(Appointment, ticket.appointment_id)
            assert ticket.status == "completed"
            assert ticket.consultation_finished_by_user_id == case.doctor_id
            assert ticket.consultation_finished_at == winner_time
            assert ticket.consultation_started_at <= ticket.consultation_finished_at <= datetime.utcnow()
            assert ticket.consultation_finished_at >= before
            assert (
                ticket.arrived_at, ticket.first_called_at, ticket.last_called_at,
                ticket.call_count, ticket.sequence_number, ticket.consultation_started_at,
            ) == before_ticket
            assert (appointment.status, appointment.appointment_time) == before_appointment
            assert db.scalar(select(ClinicalHistory.id).where(ClinicalHistory.appointment_id == appointment.id)) is None
        assert [event.event_type for event in v2._events(ticket_id)] == [
            "ARRIVED", "ISSUED", "CALLED", "SERVICE_STARTED", "SERVICE_COMPLETED",
        ]
        assert v2._events(ticket_id)[-1].actor_user_id == case.doctor_id
        assert client.post(f"/api/v1/queue-tickets/{ticket_id}/complete", headers=doctor).status_code == 409
        with Session(engine) as db:
            assert db.get(QueueTicket, ticket_id).consultation_finished_at == winner_time
        assert len([event for event in v2._events(ticket_id) if event.event_type == "SERVICE_COMPLETED"]) == 1

    with TestClient(app, base_url="http://v2-two.synthetic.test") as other_client:
        other_doctor = v2._login(other_client, case, "other-doctor")
        assert other_client.post(f"/api/v1/queue-tickets/{ticket_id}/complete", headers=other_doctor).status_code == 404
    with TestClient(app, base_url="http://v2-platform.synthetic.test") as platform_client:
        platform_token = v2._login(platform_client, case, "platform")
        assert platform_client.post(f"/api/v1/queue-tickets/{ticket_id}/complete", headers=platform_token).status_code == 403
