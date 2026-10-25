"""Synthetic transport/availability tests. No official station or document writes."""
from datetime import timedelta
from types import SimpleNamespace
import pytest
from fastapi import HTTPException, Response
from fastapi.testclient import TestClient
from starlette.requests import Request
from sqlalchemy import select, func
from sqlalchemy.orm import Session
from app.api.routes.local_agents import secure_transport
from app.models import ClinicalAuditLog, Role
from app.models.local_agent import LocalAgent, AgentPrinter
from app.services import local_agents, agent_destinations
from app.services.tenancy import bind_scope
from test_local_agents import registry_api, tenant_api, paired, ROOT


@pytest.mark.parametrize("environment,flag,peer,host,headers,allowed", [
    ("Production", "true", "127.0.0.1", "localhost", [], False),
    ("Development", "false", "127.0.0.1", "localhost", [], False),
    ("Development", "true", "127.0.0.1", "localhost", [], True),
    ("Development", "true", "::1", "[::1]", [], True),
    ("Development", "true", "192.0.2.20", "localhost", [], False),
    ("Development", "true", "192.0.2.20", "127.0.0.1", [], False),
    ("Development", "true", "127.0.0.1", "192.0.2.10", [], False),
    ("Development", "true", "proxy", "localhost", [], False),
    ("Development", "true", "127.0.0.1", "localhost", [(b"x-forwarded-proto", b"https")], False),
    ("Development", "true", "127.0.0.1", "localhost", [(b"x-forwarded-for", b"127.0.0.1")], False),
])
def test_actual_loopback_not_host_or_forwarding(environment, flag, peer, host, headers, allowed, monkeypatch):
    monkeypatch.setenv("ATLAS_AGENT_ENVIRONMENT", environment)
    monkeypatch.setenv("LOCAL_AGENT_ALLOW_LOOPBACK_HTTP", flag)
    request = Request({"type":"http", "scheme":"http", "path":"/", "server":("localhost",8001),
                       "client":(peer,1234), "headers":[(b"host",host.encode()), *headers]})
    if allowed:
        response = Response(); secure_transport(request, response)
        assert response.headers["cache-control"] == "no-store"
    else:
        with pytest.raises(HTTPException) as exc:
            secure_transport(request, Response())
        assert exc.value.status_code == 400


def test_https_scope_not_untrusted_header(monkeypatch):
    monkeypatch.setenv("ATLAS_AGENT_ENVIRONMENT", "Production")
    secure_transport(Request({"type":"http", "scheme":"https", "path":"/", "headers":[],
                              "server":("atlas.example.test",443), "client":("192.0.2.20",1234)}), Response())


def test_availability_mobile_tablet_scope_status_and_permissions(registry_api):
    one,two,h1,h2,engine = registry_api
    device,info,_ = paired(one,h1)
    printer={"local_id":"printer-"+"A"*64,"display_name":"QA PDF","driver":"QA",
             "is_default":False,"connection":"Local","is_virtual":True,"status":"Ready","papers":[{"name":"A4"}]}
    assert one.put(ROOT+"/device/printers",json={"printers":[printer]},headers=device).status_code == 200
    with Session(engine) as db:
        audit_count=db.scalar(select(func.count(ClinicalAuditLog.id)))
    for origin in ("WEB_DESKTOP","WEB_MOBILE","WEB_TABLET"):
        response=one.get(ROOT+"/destinations",params={"origin_type":origin,"paper_name":"A4"},headers=h1)
        assert response.status_code == 200
        body=response.json()
        assert body["source_agent_required"] is False and body["execution_enabled"] is False
        assert len(body["destinations"]) == 1
        assert body["destinations"][0]["document_authorization_required"] is True
        assert body["destinations"][0]["lan_channel_available"] is False
        assert "credential" not in str(body)
    assert two.get(ROOT+"/destinations",headers=h2).json()["destinations"] == []
    assert one.get(ROOT+"/destinations?center_id=999",headers=h1).json()["destinations"] == []
    assert one.get(ROOT+"/destinations?workgroup_id=999",headers=h1).json()["destinations"] == []
    assert one.get(ROOT+"/destinations?paper_name=Letter",headers=h1).json()["destinations"] == []
    with TestClient(one.app, base_url="http://one.example.test") as plaintext:
        assert plaintext.get(ROOT+"/destinations",headers=h1).status_code == 400
    with Session(engine) as db:
        assert db.scalar(select(func.count(ClinicalAuditLog.id))) == audit_count
        row=db.scalar(select(LocalAgent)); row.last_seen_at=local_agents.now()-timedelta(seconds=121); db.commit()
    assert one.get(ROOT+"/destinations",headers=h1).json()["destinations"] == []
    one.post(ROOT+"/device/heartbeat",json=info,headers=device)
    with Session(engine) as db:
        row=db.scalar(select(LocalAgent)); row.revoked_at=local_agents.now(); db.commit()
    assert one.get(ROOT+"/destinations",headers=h1).json()["destinations"] == []
    with Session(engine) as db:
        role=db.scalar(select(Role).where(Role.code=="admin"))
        role.permissions=[p for p in role.permissions if p.code!="local_agents:view"]; db.commit()
    assert one.get(ROOT+"/destinations",headers=h1).status_code == 403
    assert one.get(ROOT+"/destinations",headers=device).status_code == 401


def test_nonadmin_center_scope_does_not_expand_with_group(registry_api):
    one,_,h1,_,engine=registry_api
    paired(one,h1)
    with Session(engine) as db:
        bind_scope(db,"tenant",1)
        restricted=SimpleNamespace(id=1,roles=[],centers=[])
        result=agent_destinations.destinations(db,restricted,origin_type="WEB_MOBILE")
        assert result["destinations"] == []
