"""Explicitly disposable PostgreSQL. Reject any official URL before migrations."""
import hashlib
import json
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from datetime import datetime, timedelta
from alembic import command
from alembic.config import Config
from fastapi import HTTPException
from sqlalchemy import inspect, select, text, func
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from app.db import engine
from app.models.print_job import PrintJob, PrintDelivery, PrintResult
from app.services import print_jobs as service
from app.services.tenancy import bind_scope
from test_print_job_persistence import seed_targets, intent

TABLES = {"print_jobs", "print_deliveries", "print_results"}


def fingerprints():
    with engine.connect() as db:
        return {name: [hashlib.sha256(row.encode()).hexdigest() for row in db.scalars(text(
            f'SELECT to_jsonb(t)::text FROM "{name}" t ORDER BY to_jsonb(t)::text'))]
            for name in sorted(set(inspect(db).get_table_names()) - TABLES - {"alembic_version"})}


def operation(scope, action):
    with Session(engine) as db:
        bind_scope(db, "tenant", scope.organization_id)
        result = action(db)
        db.commit()
        return result


def require_temporary_database():
    if (engine.dialect.name != "postgresql" or engine.url.host != "atlas-print68-qa-pg"
        or engine.url.database not in {"atlas_print68_qa", "atlas_print68_final_qa"}):
        raise RuntimeError("Temporary DB required; official databases are forbidden")


def main():
    require_temporary_database()
    cfg = Config("alembic.ini")
    command.upgrade(cfg, "0067_local_agent_registry")
    targets = seed_targets(engine)
    before = fingerprints()
    with engine.connect() as db:
        old_tables = set(inspect(db).get_table_names())
        old_sequences = set(inspect(db).get_sequence_names())
    command.upgrade(cfg, "0068_print_job_persistence")
    assert fingerprints() == before
    with engine.connect() as db:
        assert set(inspect(db).get_table_names()) - old_tables == TABLES
        assert set(inspect(db).get_sequence_names()) == old_sequences
        assert all(db.scalar(text(f'SELECT count(*) FROM "{t}"')) == 0 for t in TABLES)
        assert len(inspect(db).get_foreign_keys("print_jobs")) == 3
    command.downgrade(cfg, "0067_local_agent_registry")
    assert fingerprints() == before
    with engine.connect() as db:
        assert set(inspect(db).get_table_names()) == old_tables
        assert not any(c["name"] == "uq_local_agent_print_scope" for c in inspect(db).get_unique_constraints("local_agents"))
    command.upgrade(cfg, "0068_print_job_persistence")
    assert fingerprints() == before
    scope, printer = targets[0]
    request = intent(printer)
    with ThreadPoolExecutor(max_workers=8) as pool:
        ids = list(pool.map(lambda _: operation(scope, lambda db: service.register(db, scope, request).id), range(8)))
    assert len(set(ids)) == 1
    with ThreadPoolExecutor(max_workers=8) as pool:
        deliveries = list(pool.map(lambda _: operation(scope, lambda db: service.deliver(db, scope, request.job_id).id), range(8)))
    assert len(set(deliveries)) == 1
    future = datetime.utcnow()+timedelta(seconds=61)
    next_delivery = operation(scope, lambda db: service.deliver(db, scope, request.job_id, now=future).id)
    assert next_delivery != deliveries[0]
    with ThreadPoolExecutor(max_workers=8) as pool:
        results = list(pool.map(lambda _: operation(scope, lambda db: service.record_result(db, scope,
            request.job_id, deliveries[0], "submitted", spool_id=123).job_id), range(8)))
    assert len(set(results)) == 1
    assert operation(scope, lambda db: service.deliver(db, scope, request.job_id)) is None
    assert operation(scope, lambda db: service.record_result(db, scope, request.job_id,
        next_delivery, "printed", spool_id=123).outcome) == "printed"
    assert operation(scope, lambda db: service.record_result(db, scope, request.job_id,
        deliveries[0], "submitted", spool_id=123).outcome) == "printed"
    try:
        operation(scope, lambda db: service.register(db, scope, replace(request, copies=2)))
        raise AssertionError("conflict expected")
    except HTTPException as exc:
        assert exc.status_code == 409
    try:
        operation(targets[1][0], lambda db: service.get_job(db, targets[1][0], request.job_id))
        raise AssertionError("tenant denial expected")
    except HTTPException as exc:
        assert exc.status_code == 404
    # Database-level constraints, bypass service to prove center/printer FK protection.
    with engine.connect() as db:
        for assignment in (f"center_id={targets[1][0].center_id}", f"printer_id={targets[1][1]}"):
            tx = db.begin_nested()
            try:
                db.execute(text(f"UPDATE print_jobs SET {assignment} WHERE id=:id"), {"id":request.job_id})
                raise AssertionError("FK scope accepted invalid target")
            except IntegrityError:
                tx.rollback()
    rolled = intent(printer)
    with Session(engine) as db:
        bind_scope(db, "tenant", scope.organization_id)
        service.register(db, scope, rolled); service.deliver(db, scope, rolled.job_id); db.rollback()
    with Session(engine) as db:
        assert db.get(PrintJob, rolled.job_id) is None
        assert db.scalar(select(func.count(PrintJob.id))) == 1
        assert db.scalar(select(func.count(PrintDelivery.id))) == 2
        assert db.scalar(select(func.count(PrintResult.job_id))) == 1
    assert fingerprints() == before
    print(json.dumps({"result":"PASS", "roundtrip":"0067->0068->0067->0068", "historical_tables":len(before),
        "tables_before":len(old_tables), "tables_after":len(old_tables)+3, "new_sequences":0,
        "concurrent_register":8, "concurrent_delivery":8, "concurrent_ack":8, "jobs":1,
        "deliveries":2, "results":1, "historical_fingerprints":"identical", "scope_fk":"PASS", "rollback":"PASS"}))


if __name__ == "__main__":
    main()
