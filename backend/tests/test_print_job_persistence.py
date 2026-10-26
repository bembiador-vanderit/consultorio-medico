"""Metadata persistence only: synthetic targets, no spooler or official database."""
from dataclasses import replace
from datetime import datetime, timedelta
from uuid import uuid4
import os
import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine, select, func
from sqlalchemy.orm import Session
from app.db import Base
from app.models import CareCenter, Organization, User, OrganizationMembership
from app.models.local_agent import AgentWorkgroup, LocalAgent, AgentPrinter
from app.models.print_job import PrintJob, PrintDelivery, PrintResult
from app.services import print_jobs as service
from app.services.tenancy import bind_scope


def seed_targets(engine):
    now = datetime.utcnow()
    with Session(engine, join_transaction_mode="create_savepoint") as db:
        for org in (1, 2):
            if db.get(Organization, org) is None:
                db.add(Organization(id=org, slug=f"print-qa-{org}", name=f"QA Print {org}"))
        db.flush()
        user = User(email=f"print-{uuid4()}@example.test", full_name="QA Print", password_hash="NOT-A-LOGIN",
                    memberships=[OrganizationMembership(organization_id=i) for i in (1,2)])
        db.add(user); db.flush()
        scopes = []
        for org in (1, 2):
            center = CareCenter(organization_id=org, name="QA Center", city="QA")
            db.add(center); db.flush()
            group = AgentWorkgroup(organization_id=org, center_id=center.id, name="QA", created_by=user.id)
            db.add(group); db.flush()
            agent = LocalAgent(organization_id=org, agent_uuid=str(uuid4()), display_code="QA", station_name="QA",
                center_id=center.id, workgroup_id=group.id, version="qa", protocol_version=3,
                fingerprint="a"*64, credential_hash=uuid4().hex*2, credential_expires_at=now+timedelta(days=1), paired_by=user.id)
            db.add(agent); db.flush()
            printer = AgentPrinter(organization_id=org, agent_id=agent.id, local_id="printer-qa", display_name="QA",
                is_default=False, connection="unknown", is_virtual=True, status="ready", papers=[], available=True)
            db.add(printer); db.flush()
            scopes.append((service.PrintScope(org, center.id, agent.id), printer.id))
        db.commit()
        return scopes


def intent(printer):
    return service.PrintIntent(str(uuid4()), printer, "artifact-qa", "a"*64, datetime.utcnow()+timedelta(minutes=10))


def actor_for(db):
    return db.scalar(select(User).where(User.email.like('print-%')).order_by(User.id))


def register(db, scope, request, **kwargs):
    return service.register(db, scope, request, actor=actor_for(db), document_resolver=resolver_for(scope,request), **kwargs)


def resolver_for(scope, request):
    # Trusted synthetic domain fixture only; never a production resolver or a client proof.
    return lambda db, actor, reference, kind: service.ResolvedPrintDocument(scope.organization_id,
        request.artifact_ref, request.document_type, request.document_security_class, request.content_sha256)


def progress(db, scope, job_id, delivery_id):
    for state in ('received','ready','printing'):
        service.advance(db, scope, job_id, state, delivery_id=delivery_id)


@pytest.fixture(params=['sqlite','postgres'])
def store(request):
    if request.param == 'postgres':
        if os.environ.get('ATLAS_PRINT_CONTRACT_PG') != '1':
            pytest.skip('Requires explicitly enabled disposable contract PostgreSQL')
        from app.db import engine
        if (engine.url.host,engine.url.database) not in {('atlas-print69-qa-pg','atlas_print69_qa'),('atlas-routing-qa-pg','atlas_routing_qa')}:
            raise RuntimeError('Refusing official/non-QA database')
        with engine.connect() as connection:
            outer = connection.begin()
            try:
                # Hide the harness' historical synthetic jobs inside this rollback-only fixture.
                from sqlalchemy import text
                for table in ('print_results','print_deliveries','print_jobs'):
                    connection.execute(text('DELETE FROM '+table))
                targets = seed_targets(connection)
                with Session(connection, join_transaction_mode='create_savepoint') as db:
                    bind_scope(db, 'tenant', 1)
                    yield db, targets[0][0], targets[0][1], targets[1]
            finally:
                outer.rollback()
    else:
        engine = create_engine('sqlite://')
        Base.metadata.create_all(engine)
        targets = seed_targets(engine)
        with Session(engine) as db:
            bind_scope(db, 'tenant', 1)
            yield db, targets[0][0], targets[0][1], targets[1]
        engine.dispose()


def test_same_id_reopens_and_new_id_is_legitimate(store):
    db, scope, printer, _ = store
    request = intent(printer)
    first = register(db, scope, request); db.commit()
    assert register(db, scope, request).id == first.id
    register(db, scope, intent(printer)); db.commit()
    assert db.scalar(select(func.count(PrintJob.id))) == 2
    with pytest.raises(HTTPException) as error:
        register(db, scope, replace(request, copies=2))
    assert error.value.status_code == 409


def test_retry_keeps_identity_even_when_printer_becomes_unavailable(store):
    db, scope, printer, _ = store
    request = intent(printer); register(db, scope, request); db.commit()
    db.get(AgentPrinter, printer).available = False; db.commit()
    assert register(db, scope, request, now=request.expires_at+timedelta(seconds=1)).id == request.job_id
    assert db.scalar(select(func.count(PrintJob.id))) == 1


def test_delivery_lost_response_and_reconnection(store):
    db, scope, printer, _ = store
    request = intent(printer); register(db, scope, request); db.commit()
    now = datetime.utcnow()
    first = service.deliver(db, scope, request.job_id, now=now); db.commit()
    assert service.deliver(db, scope, request.job_id, now=now).id == first.id
    second = service.deliver(db, scope, request.job_id, now=now+timedelta(seconds=61)); db.commit()
    assert second.number == 2 and second.id != first.id
    progress(db, scope, request.job_id, first.id)
    # Late receipt for first delivery remains valid; one logical result only.
    service.record_result(db, scope, request.job_id, first.id, "submitted", spool_id=9); db.commit()
    service.record_result(db, scope, request.job_id, second.id, "submitted", spool_id=9); db.commit()
    assert service.deliver(db, scope, request.job_id) is None
    assert db.scalar(select(func.count(PrintResult.job_id))) == 1
    assert db.scalar(select(func.count(PrintDelivery.id))) == 2
    assert db.get(PrintDelivery, second.id).acknowledged_at is not None


def test_result_conflict_and_sanitization(store):
    db, scope, printer, _ = store
    request = intent(printer); register(db, scope, request)
    attempt = service.deliver(db, scope, request.job_id)
    service.record_result(db, scope, request.job_id, attempt.id, "unknown", error_code="OUTCOME_UNKNOWN"); db.commit()
    with pytest.raises(HTTPException) as error:
        service.record_result(db, scope, request.job_id, attempt.id, "printed", spool_id=7)
    assert error.value.status_code == 409
    with pytest.raises(HTTPException) as error:
        service.record_result(db, scope, request.job_id, attempt.id, "failed", error_code="patient contents unsafe")
    assert error.value.status_code == 422


def test_spool_confirmation_is_monotonic_not_a_second_print(store):
    db, scope, printer, _ = store
    request = intent(printer); register(db, scope, request)
    attempt = service.deliver(db, scope, request.job_id)
    progress(db, scope, request.job_id, attempt.id)
    service.record_result(db, scope, request.job_id, attempt.id, "submitted", spool_id=7)
    assert service.record_result(db, scope, request.job_id, attempt.id, "printed", spool_id=7).outcome == "printed"
    assert service.record_result(db, scope, request.job_id, attempt.id, "submitted", spool_id=7).outcome == "printed"
    db.commit()
    assert db.scalar(select(func.count(PrintResult.job_id))) == 1
    assert service.deliver(db, scope, request.job_id) is None


def test_cancel_and_expire(store):
    db, scope, printer, _ = store
    request = intent(printer); register(db, scope, request)
    assert service.cancel(db, scope, request.job_id).status == "cancelled"
    assert service.deliver(db, scope, request.job_id) is None
    other = intent(printer); register(db, scope, other)
    assert service.deliver(db, scope, other.job_id, now=other.expires_at) is None
    assert db.get(PrintJob, other.job_id).status == "expired"
    third = intent(printer); register(db, scope, third); service.deliver(db, scope, third.job_id)
    assert service.cancel(db, scope, third.job_id).status == "cancelled"
    db.commit()


def test_scope_and_printer_isolation(store):
    db, scope, printer, (other_scope, other_printer) = store
    request = intent(printer); register(db, scope, request); db.commit()
    for bad in (other_scope, replace(scope, center_id=other_scope.center_id), replace(scope, agent_id=other_scope.agent_id)):
        with pytest.raises(HTTPException) as error:
            service.get_job(db, bad, request.job_id)
        assert error.value.status_code in (403, 404)
    with pytest.raises(HTTPException) as error:
        register(db, scope, intent(other_printer))
    assert error.value.status_code == 404


def test_unbound_session_never_grants_print_scope(store):
    db, scope, printer, _ = store
    with Session(db.bind) as unbound:
        with pytest.raises(HTTPException) as error:
            service.register(unbound, scope, intent(printer))
        assert error.value.status_code == 403


def test_rollback_leaves_no_partial_job_or_delivery(store):
    db, scope, printer, _ = store
    request = intent(printer); register(db, scope, request); service.deliver(db, scope, request.job_id)
    db.rollback()
    assert db.get(PrintJob, request.job_id) is None
    assert db.scalar(select(func.count(PrintDelivery.id))) == 0


@pytest.mark.parametrize("change", [{"artifact_ref":"https://unsafe/path"}, {"content_sha256":"bad"}, {"copies":0}, {"job_id":"invalid"}])
def test_invalid_metadata(store, change):
    db, scope, printer, _ = store
    with pytest.raises(HTTPException) as error:
        register(db, scope, replace(intent(printer), **change))
    assert error.value.status_code == 422


def test_migration_harness_rejects_official_url_before_connecting(monkeypatch):
    from types import SimpleNamespace
    import validate_print_job_postgres as harness
    monkeypatch.setattr(harness, "engine", SimpleNamespace(dialect=SimpleNamespace(name="postgresql"),
        url=SimpleNamespace(host="postgres", database="official")))
    with pytest.raises(RuntimeError, match="official databases are forbidden"):
        harness.require_temporary_database()
