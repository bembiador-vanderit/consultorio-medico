"""Opt-in real PostgreSQL concurrent start and finish on a disposable database."""

import os
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session

import test_queue_v2_postgres as v2
from app.api.routes import provider_pauses
from app.db import engine
from app.models import ProviderOperationalPause


pytestmark = pytest.mark.skipif(
    os.environ.get("ATLAS_V2_PG_VALIDATION") != "1",
    reason="Requires an explicitly selected disposable PostgreSQL copy",
)


def test_concurrent_provider_pause_start_and_finish(monkeypatch):
    case = v2._seed_case()  # Enforces disposable host and database before writing.
    app = v2._app(case, monkeypatch)
    app.include_router(provider_pauses.router, prefix="/api/v1")
    with TestClient(app, base_url="http://v2-one.synthetic.test") as client:
        doctor = v2._login(client, case, "doctor")
        secretary = v2._login(client, case, "secretary")

    def race(path, payload=None):
        barrier = Barrier(2)

        def invoke(_):
            with TestClient(app, base_url="http://v2-one.synthetic.test") as contender:
                barrier.wait(timeout=20)
                response = contender.post(path, headers=doctor, json=payload)
                return response.status_code, response.json()

        with ThreadPoolExecutor(max_workers=2) as workers:
            return list(workers.map(invoke, range(2)))

    started = race("/api/v1/provider-pauses/start", {"center_id": case.center_id, "reason": "lunch"})
    assert sorted(status for status, _ in started) == [201, 409]
    pause_id = next(body["id"] for status, body in started if status == 201)
    with TestClient(app, base_url="http://v2-one.synthetic.test") as client:
        current = client.get("/api/v1/provider-pauses/current", params={
            "center_id": case.center_id, "doctor_id": case.doctor_id,
        }, headers=secretary)
        assert current.status_code == 200 and current.json()["id"] == pause_id
        assert client.post("/api/v1/provider-pauses/start", headers=secretary, json={
            "center_id": case.center_id, "doctor_id": case.doctor_id, "reason": "meeting",
        }).status_code == 403
        assert client.post(f"/api/v1/provider-pauses/{pause_id}/finish", headers=secretary).status_code == 403
    with TestClient(app, base_url="http://v2-two.synthetic.test") as client:
        other = v2._login(client, case, "other")
        assert client.get("/api/v1/provider-pauses/current", params={
            "center_id": case.center_id, "doctor_id": case.doctor_id,
        }, headers=other).status_code == 404
    with Session(engine) as db:
        assert db.scalar(select(func.count(ProviderOperationalPause.id)).where(
            ProviderOperationalPause.center_id == case.center_id,
            ProviderOperationalPause.doctor_id == case.doctor_id,
            ProviderOperationalPause.actual_finished_at.is_(None),
        )) == 1
        pause = db.get(ProviderOperationalPause, pause_id)
        assert pause.started_by_user_id == case.doctor_id
        started_at = pause.actual_started_at

    finished = race(f"/api/v1/provider-pauses/{pause_id}/finish")
    assert sorted(status for status, _ in finished) == [200, 409]
    with Session(engine) as db:
        pause = db.get(ProviderOperationalPause, pause_id)
        assert pause.actual_started_at == started_at
        assert pause.actual_finished_at >= started_at
        assert pause.finished_by_user_id == case.doctor_id
        assert db.scalar(select(func.count(ProviderOperationalPause.id)).where(
            ProviderOperationalPause.center_id == case.center_id,
            ProviderOperationalPause.doctor_id == case.doctor_id,
        )) == 1
