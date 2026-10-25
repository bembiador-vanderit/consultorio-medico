"""Disposable PostgreSQL only. Never run migrations against official Atlas."""
import hashlib
import json
from concurrent.futures import ThreadPoolExecutor
from datetime import date
from uuid import uuid4
from alembic import command
from alembic.config import Config
from fastapi import FastAPI
from sqlalchemy import inspect, select, text
from sqlalchemy.orm import Session
from app.db import engine
from app.models import CareCenter, Organization, OrganizationMembership, Patient, Role, User
from app.models.local_agent import AgentPairingCode, LocalAgent
from app.schemas.local_agent import PairRequest, WorkgroupCreate
from app.services import local_agents as service
from app.services.bootstrap import seed_identity
from app.services.tenancy import bind_scope
from app.api.routes.local_agents import router

NEW_TABLES = {"agent_workgroups", "local_agents", "agent_pairing_codes", "agent_printers", "authorized_station_scopes"}


def guard():
    assert engine.dialect.name == "postgresql"
    assert engine.url.host == "atlas-agent67-qa-pg" and engine.url.database in {"atlas_agent67_qa", "atlas_agent67_final_qa"}


def fingerprints():
    with engine.connect() as db:
        result = {}
        for name in sorted(set(inspect(db).get_table_names()) - NEW_TABLES - {"alembic_version"}):
            rows = list(db.scalars(text(f'SELECT to_jsonb(t)::text FROM "{name}" t ORDER BY to_jsonb(t)::text')))
            result[name] = [hashlib.sha256(row.encode()).hexdigest() for row in rows]
        return result


def fixture_code():
    guard()
    with Session(engine) as db:
        bind_scope(db, "tenant", 1)
        user = db.scalar(select(User).where(User.email == "registry-qa@example.test"))
        group = service.group_create(db, user, WorkgroupCreate(center_id=1, name="QA Workgroup"))
        return service.create_code(db, user, group.id)["code"]


def concurrent_pair(payload):
    with Session(engine) as db:
        bind_scope(db, "tenant", 1)
        try:
            service.pair(db, PairRequest(**payload))
            return 200
        except Exception as exc:
            from fastapi import HTTPException
            if isinstance(exc, HTTPException):
                return exc.status_code
            raise


def main():
    guard()
    cfg = Config("alembic.ini")
    command.upgrade(cfg, "0066_document_designer")
    with Session(engine) as db:
        seed_identity(db)
        admin = db.scalar(select(Role).where(Role.code == "admin"))
        db.add(User(email="registry-qa@example.test", full_name="QA Registry", password_hash="NOT-A-LOGIN",
            memberships=[OrganizationMembership(organization_id=1, roles=[admin])]))
        db.add(CareCenter(id=1, organization_id=1, name="QA Centro", city="QA"))
        db.add(Patient(organization_id=1, first_name="QA", last_name="Registry", date_of_birth=date(1990,1,1)))
        db.commit()
    before = fingerprints()
    command.upgrade(cfg, "0067_local_agent_registry")
    after = fingerprints()
    assert all(set(rows).issubset(after[name]) for name, rows in before.items())
    assert {name for name in before if before[name] != after[name]} <= {"permissions", "role_permissions"}
    with engine.connect() as db:
        assert all(db.scalar(text(f'SELECT count(*) FROM "{name}"')) == 0 for name in NEW_TABLES)
        assert any(c["name"] == "uq_agent_printer_local" for c in inspect(db).get_unique_constraints("agent_printers"))
    command.downgrade(cfg, "0066_document_designer")
    assert fingerprints() == before
    command.upgrade(cfg, "0067_local_agent_registry")
    reapplied = fingerprints()
    assert all(set(rows).issubset(reapplied[name]) for name, rows in before.items())
    payload = dict(code=fixture_code(), agent_uuid=str(uuid4()), display_code="QA-PG", station_name="QA Concurrent",
        version="1.2.0-dev", protocol_version=3, fingerprint="a"*64)
    with ThreadPoolExecutor(max_workers=2) as pool:
        outcomes = sorted(pool.map(concurrent_pair, [payload, payload]))
    assert outcomes == [200, 403], outcomes
    with Session(engine) as db:
        assert len(list(db.scalars(select(LocalAgent)))) == 1
        assert len(list(db.scalars(select(AgentPairingCode).where(AgentPairingCode.consumed_at.is_not(None))))) == 1
    print(json.dumps({"result":"PASS", "roundtrip":"0066->0067->0066->0067", "historical_tables":len(before),
        "concurrency":outcomes, "new_tables":sorted(NEW_TABLES)}))


# HTTP fixture deliberately has no lifecycle seed, workers, printing or real accounts.
app = FastAPI()
app.include_router(router, prefix="/api/v1")

if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1 and sys.argv[1] == "code":
        print(fixture_code())  # Harness captures in memory; never append to logs/report.
    else:
        main()
