"""Synthetic tenant-bound registry HTTP tests; no official database or printers."""
import json
from datetime import timedelta
from uuid import uuid4
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session
from app.api.routes import local_agents
from app.models import ClinicalAuditLog, Permission, Role
from app.models.local_agent import LocalAgent, AgentPairingCode, AgentPrinter
from app.services import local_agents as service
from test_organization_isolation import tenant_api, sign_in

ROOT = "/api/v1/local-agents"


@pytest.fixture
def registry_api(tenant_api):
    app, engine, _ = tenant_api
    app.include_router(local_agents.router, prefix="/api/v1")
    with TestClient(app, base_url="https://one.example.test") as one, TestClient(app, base_url="https://two.example.test") as two:
        yield one, two, sign_in(one), sign_in(two), engine


def create_code(client, headers):
    centers = client.get("/api/v1/centers", headers=headers).json()
    group = client.post(ROOT + "/workgroups", headers=headers, json={"name": "QA Grupo", "center_id": centers[0]["id"]})
    assert group.status_code == 200, group.text
    response = client.post(ROOT + "/pairing-codes", headers=headers, json={"workgroup_id": group.json()["id"]})
    assert response.status_code == 200, response.text
    return response.json()["code"]


def station(code, **changes):
    return {"code": code, "agent_uuid": str(uuid4()), "display_code": "QA-PC-01", "station_name": "QA Estación",
            "version": "1.2.0-dev", "protocol_version": 3, "fingerprint": "a" * 64, **changes}


def paired(client, headers):
    payload = station(create_code(client, headers))
    result = client.post(ROOT + "/pair", json=payload)
    assert result.status_code == 200, result.text
    token = result.json()["credential"]
    heartbeat = {k:v for k,v in payload.items() if k != "code"}
    return {"Authorization": "Bearer " + token}, heartbeat, result.json()


def test_pair_hash_single_use_and_duplicate_uuid(registry_api):
    one, two, h1, h2, engine = registry_api
    code = create_code(one, h1); payload = station(code)
    assert two.post(ROOT + "/pair", json=payload).status_code == 403
    response = one.post(ROOT + "/pair", json=payload)
    assert response.status_code == 200
    assert one.post(ROOT + "/pair", json=payload).status_code == 403
    payload["code"] = create_code(one, h1)
    assert one.post(ROOT + "/pair", json=payload).status_code == 409
    with Session(engine) as db:
        row = db.scalar(select(LocalAgent)); pairing = db.scalar(select(AgentPairingCode).order_by(AgentPairingCode.id))
        assert row.agent_uuid == payload["agent_uuid"] and pairing.consumed_at
        assert response.json()["credential"] not in row.credential_hash
        logs = json.dumps([a.context for a in db.scalars(select(ClinicalAuditLog))])
        assert code not in logs and response.json()["credential"] not in logs
        assert db.scalar(select(func.count(LocalAgent.id))) == 1


def test_expired_code_and_issuer_permission_revoked(registry_api):
    one, _, h1, _, engine = registry_api
    code = create_code(one, h1)
    with Session(engine) as db:
        row = db.scalar(select(AgentPairingCode)); row.expires_at = service.now() - timedelta(seconds=1); db.commit()
    assert one.post(ROOT + "/pair", json=station(code)).status_code == 403
    code = create_code(one, h1)
    with Session(engine) as db:
        admin = db.scalar(select(Role).where(Role.code == "admin"))
        admin.permissions = [p for p in admin.permissions if p.code != "local_agents:manage"]; db.commit()
    assert one.post(ROOT + "/pair", json=station(code)).status_code == 403
    assert one.post(ROOT + "/pairing-codes", json={"workgroup_id": 1}, headers=h1).status_code == 403


def test_heartbeat_rotation_revocation_and_no_heartbeat_audit(registry_api):
    one, _, h1, _, engine = registry_api
    device, info, reply = paired(one, h1)
    with Session(engine) as db:
        before = db.scalar(select(func.count(ClinicalAuditLog.id)))
    for _ in range(2):
        assert one.post(ROOT + "/device/heartbeat", json=info, headers=device).status_code == 200
    with Session(engine) as db:
        assert db.scalar(select(func.count(ClinicalAuditLog.id))) == before
    assert one.get("/api/v1/patients", headers=device).status_code == 401
    assert one.post(ROOT + "/device/heartbeat", json=info, headers=h1).status_code == 401
    assert one.post(ROOT + "/device/heartbeat", json={**info,"agent_uuid":str(uuid4())}, headers=device).status_code == 409
    rotated = one.post(ROOT + "/device/rotate", headers=device)
    assert rotated.status_code == 200
    assert one.post(ROOT + "/device/heartbeat", json=info, headers=device).status_code == 401
    device = {"Authorization":"Bearer " + rotated.json()["credential"]}
    assert one.post(ROOT + "/device/heartbeat", json={**info,"health":"degraded"}, headers=device).json()["status"] == "degraded"
    row = one.get(ROOT + "/registry", headers=h1).json()["agents"][0]
    assert row["status"] == "degraded" and "credential_hash" not in row
    assert one.post(ROOT + f"/{row['id']}/revoke", headers=h1, json={"reason":"QA revoke"}).status_code == 200
    assert one.post(ROOT + "/device/heartbeat", json=info, headers=device).status_code == 401
    assert one.put(ROOT + "/device/printers", json={"printers":[]}, headers=device).status_code == 401
    assert one.post(ROOT + "/device/rotate", headers=device).status_code == 401


def test_printer_sync_disappearance_restoration_and_offline(registry_api):
    one, _, h1, _, engine = registry_api
    device, info, _ = paired(one, h1)
    printer = {"local_id":"printer-" + "A"*64, "display_name":"QA PDF", "driver":"QA Driver",
        "is_default":False,"connection":"Local","is_virtual":True,"status":"Ready", "papers":[{"name":"A4"}]}
    for printers in ([printer], [printer], [], [], [printer]):
        assert one.put(ROOT + "/device/printers", headers=device, json={"printers":printers}).status_code == 200
    with Session(engine) as db:
        assert db.scalar(select(func.count(AgentPrinter.id))) == 1
        assert db.scalar(select(AgentPrinter)).available
        assert db.scalar(select(func.count(ClinicalAuditLog.id)).where(ClinicalAuditLog.action == "local_agent.printer_unavailable")) == 1
        row = db.scalar(select(LocalAgent)); row.last_seen_at = service.now() - timedelta(seconds=121); db.commit()
    assert one.get(ROOT + "/registry", headers=h1).json()["agents"][0]["status"] == "offline"
    assert one.post(ROOT + "/device/heartbeat", headers=device, json=info).status_code == 200
    assert one.get(ROOT + "/registry", headers=h1).json()["agents"][0]["status"] == "online"
    assert one.put(ROOT + "/device/printers", headers=device, json={"printers":[printer,printer]}).status_code == 422
    assert one.put(ROOT + "/device/printers", headers=device, json={"printers":[printer,{**printer,"local_id":"printer-" + "a"*64}]}).status_code == 422


def test_cross_tenant_registry_mutation_and_explicit_station_scope(registry_api):
    one, two, h1, h2, engine = registry_api
    d1, _, _ = paired(one, h1); d2, _, _ = paired(one, h1)
    rows = one.get(ROOT + "/registry", headers=h1).json()["agents"]
    a, b = rows[0]["id"], rows[1]["id"]
    assert two.get(ROOT + "/registry", headers=h2).json()["agents"] == []
    assert two.post(ROOT + f"/{a}/revoke", json={"reason":"QA denied"}, headers=h2).status_code == 404
    assert two.get(ROOT + "/device/peers", headers=d1).status_code == 401
    assert len(one.get(ROOT + "/device/peers", headers=d1).json()) == 1  # Same group is NOT a grant.
    assert one.put(ROOT + f"/{a}/discovery-scope", headers=h1, json={"target_id":b,"allowed":True,"reason":"QA explicit"}).status_code == 200
    peers = one.get(ROOT + "/device/peers", headers=d1).json()
    assert len(peers) == 2 and all(not p["print_routing_allowed"] for p in peers)
    assert len(one.get(ROOT + "/device/peers", headers=d2).json()) == 1  # Directed, not symmetric.
    assert one.put(ROOT + f"/{a}/discovery-scope", headers=d1, json={"target_id":b,"allowed":True,"reason":"QA denied"}).status_code == 401
    with Session(engine) as db:
        admin = db.scalar(select(Role).where(Role.code == "admin"))
        admin.permissions = [p for p in admin.permissions if p.code not in service.PERMISSIONS]; db.commit()
    assert one.get(ROOT + "/registry", headers=h1).status_code == 403
    assert one.post(ROOT + f"/{a}/revoke", json={"reason":"QA denied"}, headers=h1).status_code == 403


def test_pairing_strict_payload_and_tls(registry_api, monkeypatch):
    one, _, h1, _, _ = registry_api
    code = create_code(one, h1)
    assert one.post(ROOT + "/pair", json=station(code,organization_id=2)).status_code == 422
    assert one.post(ROOT + "/pair", json=station(code,agent_uuid="00000000-0000-0000-0000-000000000000")).status_code == 422
    monkeypatch.delenv("LOCAL_AGENT_ALLOW_LOOPBACK_HTTP", raising=False)
    with TestClient(one.app, base_url="http://one.example.test") as plain:
        assert plain.post(ROOT + "/pair", json=station(code)).status_code == 400
        monkeypatch.setenv("LOCAL_AGENT_ALLOW_LOOPBACK_HTTP","true")
        assert plain.post(ROOT + "/pair", json=station(code)).status_code == 400


def test_scope_moves_audit_and_remove_previous_grants(registry_api):
    one, two, h1, h2, engine = registry_api
    device, _, _ = paired(one, h1)
    paired(one, h1)
    rows = one.get(ROOT + "/registry", headers=h1).json()["agents"]
    a, b = rows[0]["id"], rows[1]["id"]
    one.put(ROOT + f"/{a}/discovery-scope", headers=h1, json={"target_id":b,"allowed":True,"reason":"QA explicit"})
    other_center = two.get("/api/v1/centers", headers=h2).json()[0]["id"]
    other_group = two.post(ROOT + "/workgroups", headers=h2, json={"center_id":other_center,"name":"QA Other"}).json()["id"]
    assert one.put(ROOT + f"/{a}", headers=h1, json={"station_name":"QA Denied","workgroup_id":other_group,"reason":"QA denied"}).status_code == 404
    center = one.get("/api/v1/centers", headers=h1).json()[0]["id"]
    group = one.post(ROOT + "/workgroups", headers=h1, json={"center_id":center,"name":"QA New Group"}).json()["id"]
    assert one.put(ROOT + f"/{a}", headers=h1, json={"station_name":"QA Renamed","workgroup_id":group,"reason":"QA move"}).status_code == 200
    assert len(one.get(ROOT + "/device/peers", headers=device).json()) == 1
    with Session(engine) as db:
        changes = list(db.scalars(select(ClinicalAuditLog).where(ClinicalAuditLog.action == "local_agent.configured")))
        assert len(changes) == 1 and changes[0].user_id
        assert changes[0].context["before"]["workgroup_id"] != changes[0].context["after"]["workgroup_id"]
        assert changes[0].context["reason"] == "QA move"


def test_permission_revocation_survives_bootstrap(registry_api):
    from app.services.bootstrap import seed_identity
    one, _, h1, _, engine = registry_api
    with Session(engine) as db:
        admin = db.scalar(select(Role).where(Role.code == "admin"))
        admin.permissions = [p for p in admin.permissions if p.code != "local_agents:manage"]
        db.commit(); seed_identity(db)
    assert one.get(ROOT + "/registry", headers=h1).status_code == 200
    assert one.post(ROOT + "/workgroups", headers=h1, json={"center_id":1,"name":"QA Denied"}).status_code == 403
