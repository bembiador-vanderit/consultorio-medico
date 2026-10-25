"""Same-org second-station regression. Existing fixtures use SQLite, never Atlas DB.

Run copied into /tmp with PYTHONPATH=/app:/app/tests so a test file change does
not reload the official backend. All credentials below are synthetic fixtures.
"""
from datetime import timedelta
from uuid import uuid4

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.local_agent import AgentPrinter, LocalAgent
from app.models.print_job import PrintJob, PrintResult
from app.services import local_agents as registry
from test_official_print_routing import official
from test_print_routing import api, request

ROOT = "/api/v1/print-routing"


@pytest.fixture
def second_station(official):
    client, user, first_device, engine, first_uuid, targets = official
    assert engine.dialect.name == "sqlite", "Disposable SQLite only"
    with Session(engine) as db:
        first = db.get(LocalAgent, targets[0][0].agent_id)
        other = LocalAgent(
            organization_id=first.organization_id, center_id=first.center_id,
            workgroup_id=first.workgroup_id, agent_uuid=str(uuid4()),
            display_code="QA-SECOND", station_name="QA Second",
            version="qa-only", protocol_version=3, fingerprint="b" * 64,
            credential_hash=registry.digest("ala_SECOND_SYNTHETIC_ONLY"),
            credential_expires_at=registry.now() + timedelta(days=1),
            paired_by=first.paired_by,
        )
        db.add(other)
        db.flush()
        # A printer identifier may legitimately occur on two stations.
        shared = AgentPrinter(
            organization_id=first.organization_id, agent_id=other.id,
            local_id="printer-qa", display_name="QA Printer on Second",
            is_default=False, connection="Local", is_virtual=True,
            status="Ready", papers=[], available=True,
        )
        unique = AgentPrinter(
            organization_id=first.organization_id, agent_id=first.id,
            local_id="printer-first-only", display_name="QA First Only",
            is_default=False, connection="Local", is_virtual=True,
            status="Ready", papers=[], available=True,
        )
        db.add_all([shared, unique])
        db.commit()
        ids = other.agent_uuid, other.id, shared.id
    yield official, ids, {"Authorization": "Bearer ala_SECOND_SYNTHETIC_ONLY"}


@pytest.mark.parametrize("origin", ["WEB_DESKTOP", "WEB_MOBILE", "WEB_TABLET"])
def test_only_second_station_claims_and_completes_its_job(second_station, origin):
    original, (second_uuid, second_id, second_printer_id), second_device = second_station
    client, user, first_device, engine, first_uuid, _ = original
    listed = client.get(ROOT + "/destinations", headers=user)
    assert listed.status_code == 200
    assert {first_uuid, second_uuid}.issubset({r["target_agent"] for r in listed.json()["destinations"]})
    assert listed.json()["physical_execution_enabled"] is False
    payload = request(second_uuid, origin_type=origin)
    created = client.post(ROOT, headers=user, json=payload)
    assert created.status_code == 200, created.text
    assert client.post(ROOT, headers=user, json=payload).status_code == 200
    assert client.get(ROOT + "/device/poll", headers=first_device).json() is None
    assert client.get(ROOT + f"/device/{payload['job_id']}/delivery", headers=first_device).status_code == 404
    delivery = client.get(ROOT + "/device/poll", headers=second_device).json()
    assert delivery["target_agent"] == second_uuid
    assert delivery["target_printer"] == "printer-qa"
    assert delivery["source_agent"] is None
    for state in ("received", "ready", "printing"):
        body = {"delivery_id": delivery["delivery_id"], "status": state}
        path = ROOT + f"/device/{payload['job_id']}/progress"
        assert client.post(path, headers=first_device, json=body).status_code == 404
        assert client.post(path, headers=second_device, json=body).status_code == 200
    result = {"delivery_id": delivery["delivery_id"], "outcome": "printed", "synthetic_spooler_id": 1234}
    for _ in range(2):
        assert client.post(ROOT + f"/device/{payload['job_id']}/result", headers=second_device, json=result).status_code == 200
    with Session(engine) as db:
        row = db.get(PrintJob, payload["job_id"])
        assert row.agent_id == second_id
        assert row.printer_id == second_printer_id
        assert db.scalar(select(func.count(PrintJob.id))) == 1
        assert db.scalar(select(func.count(PrintResult.job_id))) == 1


def test_first_station_printer_cannot_be_spoofed_as_second(second_station):
    original, (second_uuid, _, _), _ = second_station
    client, user, _, engine, _, _ = original
    response = client.post(ROOT, headers=user, json=request(second_uuid, target_printer="printer-first-only"))
    assert response.status_code == 404
    with Session(engine) as db:
        assert db.scalar(select(func.count(PrintJob.id))) == 0


def test_physical_second_station_isolation_and_single_human_confirmed_receipt(second_station, monkeypatch, tmp_path):
    """HTTP metadata with a mock spool receipt, never a native executor."""
    import json
    from datetime import datetime, UTC
    from app.models.print_job import PrintDelivery
    from test_official_print_routing import physical_grant

    original, (second_uuid, second_id, second_printer_id), second_device = second_station
    client, user, first_device, engine, first_uuid, _ = original
    with Session(engine) as db:
        db.get(AgentPrinter, second_printer_id).is_virtual = False
        db.commit()
    payload = request(second_uuid, document_reference="physical-routing-qa")
    grant = physical_grant(engine, payload)
    path = tmp_path / "second-station-only.json"
    path.write_text(json.dumps(grant))
    monkeypatch.setenv("ATLAS_PHYSICAL_QA_AUTHORIZATION_FILE", str(path))
    for change in ({"target_agent": first_uuid}, {"target_printer": "printer-first-only"},
                   {"job_id": str(uuid4())}, {"copies": 2}):
        assert client.post(ROOT, headers=user, json={**payload, **change}).status_code in (403, 404)
    expired = {**grant, "ExpiresAt": (datetime.now(UTC) - timedelta(seconds=1)).isoformat()}
    path.write_text(json.dumps(expired))
    assert client.post(ROOT, headers=user, json=payload).status_code == 403
    with Session(engine) as db:
        assert db.scalar(select(func.count(PrintJob.id))) == 0
    path.write_text(json.dumps(grant))
    created = client.post(ROOT, headers=user, json=payload)
    assert created.status_code == 200, created.text
    assert created.json()["physical_execution_authorized"] is True
    assert client.get(ROOT + "/device/poll", headers=first_device).json() is None
    device_path = ROOT + f"/device/{payload['job_id']}"
    assert client.get(device_path + "/delivery", headers=first_device).status_code == 404
    delivery = client.get(ROOT + "/device/poll", headers=second_device).json()
    assert delivery["target_agent"] == second_uuid
    for state in ("received", "ready", "printing"):
        body = {"delivery_id": delivery["delivery_id"], "status": state}
        assert client.post(device_path + "/progress", headers=first_device, json=body).status_code == 404
        assert client.post(device_path + "/progress", headers=second_device, json=body).status_code == 200
    receipt = {"delivery_id": delivery["delivery_id"], "outcome": "submitted", "synthetic_spooler_id": 12345}
    assert client.post(device_path + "/result", headers=first_device, json=receipt).status_code == 404
    assert client.post(device_path + "/result", headers=second_device, json=receipt).json()["status"] == "submitted"
    monkeypatch.delenv("ATLAS_PHYSICAL_QA_AUTHORIZATION_FILE")
    confirm = client.post(ROOT + f"/{payload['job_id']}/confirm-physical", headers=user, json={"confirmed": True})
    assert confirm.status_code == 200, confirm.text
    assert confirm.json()["physical_evidence"]["kind"] == "HUMAN_CONFIRMED_PRINTED"
    for _ in range(2):
        replay = client.get(device_path + "/delivery", headers=second_device)
        assert replay.status_code == 200
        assert replay.json()["receipt_only"] is True
        assert replay.json()["result_spooler_id"] == 12345
        assert replay.json()["human_confirmed"] is True
    assert client.get(device_path + "/artifact", headers=second_device,
                      params={"delivery_id": delivery["delivery_id"]}).status_code == 410
    with Session(engine) as db:
        job = db.get(PrintJob, payload["job_id"])
        assert (job.agent_id, job.printer_id, job.status) == (second_id, second_printer_id, "printed")
        assert db.scalar(select(func.count(PrintJob.id))) == 1
        assert db.scalar(select(func.count(PrintDelivery.id))) == 1
        assert db.scalar(select(func.count(PrintResult.job_id))) == 1
