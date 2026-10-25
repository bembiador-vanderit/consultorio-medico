"""Opt-in 0046 line contention on a disposable PostgreSQL copy only."""

import os
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

import test_queue_v2_postgres as v2
from app.db import engine
from app.models import Appointment, QueueCallPolicy, QueueTicket, QueueTicketEvent, SecretaryCenterScope
from app.api.routes import administration
from app.services.queue_call import call_next
from app.services.tenancy import bind_scope


pytestmark = pytest.mark.skipif(
    os.environ.get("ATLAS_V2_PG_VALIDATION") != "1",
    reason="Requires an explicitly selected disposable PostgreSQL copy",
)


def test_concurrent_call_next_and_auto_evaluation(monkeypatch):
    case = v2._seed_case()  # Guards host and database name before any writes.
    app = v2._app(case, monkeypatch)
    with TestClient(app, base_url="http://v2-one.synthetic.test") as client:
        secretary = v2._login(client, case, "secretary")
        doctor = v2._login(client, case, "doctor")
        tickets = v2._issue(client, case, secretary)

    barrier = Barrier(2)

    def manual(headers):
        with TestClient(app, base_url="http://v2-one.synthetic.test") as client:
            barrier.wait(timeout=20)
            response = client.post(f"/api/v1/queue-lines/{case.line_id}/call-next",
                                   params={"day": v2.DAY.isoformat()}, headers=headers)
            return response.status_code, response.json()

    with ThreadPoolExecutor(max_workers=2) as pool:
        outcomes = list(pool.map(manual, (secretary, doctor)))
    assert sorted(status for status, _ in outcomes) == [200, 409]
    winner = next(body for status, body in outcomes if status == 200)
    assert winner["id"] == tickets[0]["id"] and winner["status"] == "called"
    assert winner["called_by_user_id"] in {case.secretary_id, case.doctor_id}
    with Session(engine) as db:
        assert db.scalar(select(func.count(QueueTicket.id)).where(
            QueueTicket.queue_line_id == case.line_id, QueueTicket.status == "called")) == 1
        assert db.scalar(select(func.count(QueueTicketEvent.id)).where(
            QueueTicketEvent.queue_ticket_id == winner["id"], QueueTicketEvent.event_type == "CALLED")) == 1
        original_appointment_id = db.get(QueueTicket, winner["id"]).appointment_id
        assert db.get(Appointment, original_appointment_id) is not None
        db.add(QueueCallPolicy(organization_id=case.org_id, center_id=case.center_id,
                               queue_line_id=case.line_id, call_mode="automatic", preparation_seconds=0))
        db.commit()
    with TestClient(app, base_url="http://v2-one.synthetic.test") as client:
        assert client.post(f"/api/v1/queue-tickets/{winner['id']}/no-response", headers=secretary).status_code == 200

    barrier = Barrier(2)

    def automatic(_):
        with Session(engine) as db:
            bind_scope(db, "tenant", case.org_id)
            barrier.wait(timeout=20)
            try:
                return call_next(db, case.line_id, v2.DAY, None, automatic=True).id
            except Exception as exc:
                return getattr(exc, "status_code", None)

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(automatic, range(2)))
    assert sorted(results, key=lambda item: item == 409) == [tickets[1]["id"], 409]
    with Session(engine) as db:
        row = db.get(QueueTicket, tickets[1]["id"])
        assert row.status == "called" and row.called_by_user_id is None
        assert row.appointment_id == tickets[1]["appointment_id"]
        events = list(db.scalars(select(QueueTicketEvent).where(
            QueueTicketEvent.queue_ticket_id == row.id, QueueTicketEvent.event_type == "CALLED")))
        assert len(events) == 1 and events[0].actor_user_id is None and events[0].call_source == "automatic"


def test_policy_api_permissions_and_validation(monkeypatch):
    case = v2._seed_case()
    app = v2._app(case, monkeypatch)
    app.include_router(administration.router, prefix="/api/v1")
    path = f"/api/v1/queue-lines/{case.line_id}/call-policy"
    with TestClient(app, base_url="http://v2-one.synthetic.test") as client:
        admin = v2._login(client, case, "admin")
        doctor = v2._login(client, case, "doctor")
        secretary = v2._login(client, case, "secretary")
        unauthorized = v2._login(client, case, "unauthorized")
        assert client.get(path, headers=doctor).json()["call_mode"] == "manual"
        assert client.get(path, headers=secretary).status_code == 200
        assert client.get(path, headers=unauthorized).status_code == 403
        assert client.put(path, headers=doctor, json={"call_mode": "automatic", "preparation_seconds": 0}).status_code == 403
        payload = {"call_mode": "assisted", "preparation_seconds": 75, "start_consultation_can_call": False}
        assert client.put(path, headers=admin, json=payload).status_code == 428
        proof = client.post("/api/v1/administration/reauthenticate", headers=admin,
                            json={"password": v2.PASSWORD, "method": "PUT", "path": path})
        assert proof.status_code == 200
        assert client.put(path, headers={**admin, "X-Reauthentication": proof.json()["proof"]},
                          json={"call_mode": "automatic", "preparation_seconds": -1}).status_code == 422
        proof = client.post("/api/v1/administration/reauthenticate", headers=admin,
                            json={"password": v2.PASSWORD, "method": "PUT", "path": path})
        assert proof.status_code == 200
        updated = client.put(path, headers={**admin, "X-Reauthentication": proof.json()["proof"]}, json=payload)
        assert updated.status_code == 200 and updated.json()["preparation_seconds"] == 75
        assert client.get(path, headers=doctor).json()["call_mode"] == "assisted"
    with Session(engine) as db:
        scope = db.scalar(select(SecretaryCenterScope).where(SecretaryCenterScope.secretary_id == case.secretary_id))
        scope.manage_all_doctors = False
        db.commit()
        with pytest.raises(IntegrityError):
            db.execute(text("UPDATE queue_call_policies SET preparation_seconds = -1 WHERE queue_line_id = :line_id"),
                       {"line_id": case.line_id})
        db.rollback()
        with pytest.raises(IntegrityError):
            db.execute(text("UPDATE queue_call_policies SET call_mode = 'invalid' WHERE queue_line_id = :line_id"),
                       {"line_id": case.line_id})
        db.rollback()
    with TestClient(app, base_url="http://v2-one.synthetic.test") as client:
        assert client.get(path, headers=secretary).status_code == 403
    with TestClient(app, base_url="http://v2-two.synthetic.test") as client:
        other = v2._login(client, case, "other")
        assert client.get(path, headers=other).status_code == 404
