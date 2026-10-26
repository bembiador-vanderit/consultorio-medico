"""The same contract cases run on SQLite and disposable migrated PostgreSQL."""
from dataclasses import replace
from datetime import timedelta
import pytest
from fastapi import HTTPException
from sqlalchemy import select, func
from app.models import User, OrganizationMembership, ClinicalAuditLog
from app.models.print_job import PrintJob
from app.services import print_jobs as service
from test_print_job_persistence import store, intent, register, actor_for, progress, resolver_for


@pytest.mark.parametrize('origin', ['WEB_DESKTOP','WEB_MOBILE','WEB_TABLET','SYSTEM'])
def test_origin_without_source_and_authoritative_metadata(store, origin):
    db, scope, printer, _ = store
    job = register(db, scope, replace(intent(printer), origin_type=origin, document_security_class='CLINICAL'))
    assert job.requested_by == actor_for(db).id
    assert job.origin_type == origin and job.source_agent_id is None and job.contract_version == 2
    assert job.document_security_class == 'CLINICAL'
    assert db.scalar(select(func.count(ClinicalAuditLog.id)).where(ClinicalAuditLog.resource_type=='print_job')) == 1


@pytest.mark.parametrize('change', [dict(origin_type='WEB_TABLET'),dict(document_security_class='FINANCIAL'),
    dict(document_type='receipt'),dict(artifact_ref='another-artifact'),dict(content_sha256='b'*64)])
def test_each_changed_intent_conflicts(store, change):
    db, scope, printer, _ = store
    request = intent(printer); register(db, scope, request); db.commit()
    with pytest.raises(HTTPException) as error:
        register(db, scope, replace(request, **change))
    assert error.value.status_code == 409


def test_changed_authenticated_requester_conflicts_and_no_client_actor_field(store):
    db, scope, printer, _ = store
    request = intent(printer); register(db, scope, request); db.commit()
    other = User(email='other-print@example.test',full_name='QA',password_hash='NOT-A-LOGIN')
    db.add(other); db.flush(); db.commit()  # Existing tenant provisioning attaches a membership, no role grant.
    with pytest.raises(HTTPException) as error:
        service.register(db, scope, request, actor=other, document_resolver=resolver_for(scope,request))
    assert error.value.status_code == 409
    with pytest.raises(TypeError):
        replace(request, requested_by=other.id)


def test_actor_must_be_session_identity_and_source_belongs_to_tenant(store):
    db, scope, printer, (other_scope, _) = store
    request = intent(printer)
    for fake in (None, User(id=actor_for(db).id, email='forged@example.test', full_name='QA', password_hash='NO')):
        with pytest.raises(HTTPException) as error:
            service.register(db, scope, request, actor=fake)
        assert error.value.status_code == 403
    with pytest.raises(HTTPException) as error:
        register(db, scope, replace(request, origin_type='LOCAL_AGENT', source_agent_id=other_scope.agent_id))
    assert error.value.status_code == 404
    valid = register(db, scope, replace(request, origin_type='LOCAL_AGENT', source_agent_id=scope.agent_id))
    assert valid.source_agent_id == scope.agent_id


def test_protected_progress_matrix_and_terminal_replays(store):
    db, scope, printer, _ = store
    request = intent(printer); register(db, scope, request)
    delivery = service.deliver(db, scope, request.job_id)
    assert db.get(PrintJob,request.job_id).status == 'queued'  # Delivery is NOT the job state.
    with pytest.raises(HTTPException) as error:
        service.advance(db, scope, request.job_id, 'printing', delivery_id=delivery.id)
    assert error.value.status_code == 409
    for state in ('received','ready','printing'):
        assert service.advance(db, scope, request.job_id,state,delivery_id=delivery.id).status == state
    assert service.cancel(db, scope, request.job_id).status == 'printing'
    assert service.record_result(db,scope,request.job_id,delivery.id,'printed',spool_id=1).outcome == 'printed'
    db.commit()
    for state in ('printing','received'):
        with pytest.raises(HTTPException) as error:
            service.advance(db,scope,request.job_id,state,delivery_id=delivery.id)
        assert error.value.status_code == 409


@pytest.mark.parametrize('terminal',['cancelled','expired'])
def test_terminal_before_execution_cannot_print(store, terminal):
    db, scope, printer, _ = store
    request = intent(printer); register(db, scope, request)
    delivery = service.deliver(db, scope, request.job_id)
    service.advance(db,scope,request.job_id,'received',delivery_id=delivery.id)
    if terminal == 'cancelled':
        service.cancel(db,scope,request.job_id)
    else:
        assert service.advance(db,scope,request.job_id,'ready',delivery_id=delivery.id,
            now=request.expires_at+timedelta(seconds=1)).status == 'expired'
    with pytest.raises(HTTPException) as error:
        service.advance(db,scope,request.job_id,'printing',delivery_id=delivery.id)
    assert error.value.status_code == 409


def test_failure_before_irreversible_boundary_and_unknown_after_it(store):
    db, scope, printer, _ = store
    request = intent(printer); register(db,scope,request)
    delivery = service.deliver(db,scope,request.job_id)
    progress(db,scope,request.job_id,delivery.id)
    with pytest.raises(HTTPException) as error:
        service.record_result(db,scope,request.job_id,delivery.id,'failed',error_code='DRIVER_ERROR')
    assert error.value.status_code == 409
    assert service.record_result(db,scope,request.job_id,delivery.id,'unknown',error_code='OUTCOME_UNKNOWN').outcome == 'unknown'
    assert service.deliver(db,scope,request.job_id) is None
    with pytest.raises(HTTPException):
        service.record_result(db,scope,request.job_id,delivery.id,'failed',error_code='DRIVER_ERROR')
    other = intent(printer); register(db,scope,other)
    attempt = service.deliver(db,scope,other.job_id)
    assert service.record_result(db,scope,other.job_id,attempt.id,'failed',error_code='PRINTER_UNAVAILABLE').outcome == 'failed'


def test_orm_cannot_mutate_intent_or_bypass_progress(store):
    db,scope,printer,_ = store
    request=intent(printer); job=register(db,scope,request); db.commit()
    job.document_security_class='FINANCIAL'
    with pytest.raises(ValueError,match='inmutable'):
        db.flush()
    db.rollback()
    job=service.get_job(db,scope,request.job_id); job.status='printed'
    with pytest.raises(ValueError,match='Transición'):
        db.flush()
    db.rollback()


def test_shared_fingerprint_vector():
    import json
    from pathlib import Path
    from datetime import datetime
    v=json.loads((Path(__file__).parent/'fixtures'/'print-intent-v2.json').read_text())
    request=service.PrintIntent(v['job_id'],1,v['document_reference'],v['content_sha256'],
        datetime.fromisoformat(v['expires_at'].removesuffix('Z')),copies=v['copies'],origin_type=v['origin_type'],
        document_type=v['document_type'],document_security_class=v['document_security_class'])
    assert service.fingerprint(service.PrintScope(7,9,1),request,42,v['target_agent'],v['target_printer'])==v['sha256']


def test_document_requires_backend_resolution_and_matching_tenant(store):
    db,scope,printer,(other_scope,_)=store
    request=intent(printer); actor=actor_for(db)
    with pytest.raises(HTTPException) as error:
        service.register(db,scope,request,actor=actor)
    assert error.value.status_code==403
    with pytest.raises(HTTPException) as error:
        service.register(db,scope,request,actor=actor,document_resolver=resolver_for(other_scope,request))
    assert error.value.status_code==404


def test_changed_valid_printer_is_an_intent_conflict(store):
    from app.models.local_agent import AgentPrinter
    db,scope,printer,_=store
    request=intent(printer); register(db,scope,request); db.commit()
    other=AgentPrinter(organization_id=scope.organization_id,agent_id=scope.agent_id,local_id='printer-other',display_name='QA Other',
        is_default=False,connection='unknown',is_virtual=True,status='ready',papers=[],available=True)
    db.add(other); db.commit()
    with pytest.raises(HTTPException) as error:
        register(db,scope,replace(request,printer_id=other.id))
    assert error.value.status_code==409
