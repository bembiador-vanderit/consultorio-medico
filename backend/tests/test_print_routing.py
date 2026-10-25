"""HTTP routing contract. Synthetic content only; native spooler never involved."""
from datetime import timedelta
from uuid import uuid4
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select, func
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool
from app.db import Base,get_db
from app.models import User,Role,OrganizationMembership,ClinicalAuditLog,Organization
from app.models.local_agent import LocalAgent,AgentPrinter
from app.models.print_job import PrintJob,PrintResult
from app.services import local_agents as registry,print_jobs as jobs
from app.services.bootstrap import seed_identity
from app.services.print_routing import SyntheticRoutingPolicy
from app.services.tenancy import bind_scope
from app.core.security import create_access_token
from app.api.routes.print_routing import router
from test_print_job_persistence import seed_targets

@pytest.fixture
def api(monkeypatch):
    e=create_engine('sqlite://',poolclass=StaticPool,connect_args={'check_same_thread':False})
    Base.metadata.create_all(e)
    with Session(e) as db:seed_identity(db)
    targets=seed_targets(e)
    with Session(e) as db:
        role=db.scalar(select(Role).where(Role.code=='admin'))
        user=db.scalar(select(User).where(User.email.like('print-%')))
        user.memberships[0].roles=[role]
        agent=db.get(LocalAgent,targets[0][0].agent_id);agent.credential_hash=registry.digest('ala_QA_ROUTING_ONLY')
        token=create_access_token(user.email,user.session_version,user.id,{'scope':'tenant','org':1})
        db.commit();agent_uuid=agent.agent_uuid
    app=FastAPI();app.state.synthetic_print_routing=SyntheticRoutingPolicy();app.include_router(router,prefix='/api/v1')
    def session():
        with Session(e) as db:bind_scope(db,'tenant',1);yield db
    app.dependency_overrides[get_db]=session
    with TestClient(app,base_url='https://localhost') as client:
        yield client,{'Authorization':'Bearer '+token},{'Authorization':'Bearer ala_QA_ROUTING_ONLY'},e,agent_uuid,targets
    e.dispose()

def request(station,**change):
    return {'job_id':str(uuid4()),'target_agent':station,'target_printer':'printer-qa','document_reference':'qa-general',
        'origin_type':'WEB_DESKTOP','copies':1,**change}

ROOT='/api/v1/print-jobs'
def submit(api,**change):
    c,h,d,e,station,_=api;payload=request(station,**change);r=c.post(ROOT,headers=h,json=payload)
    assert r.status_code==200,r.text
    delivery=c.get(ROOT+'/device/poll',headers=d).json()
    return payload,delivery

def test_display_name_change_does_not_change_routing_identity(api):
    c,h,d,e,station,targets=api
    with Session(e) as db:
        agent=db.get(LocalAgent,targets[0][0].agent_id)
        original_id=agent.id
        agent.station_name='QA Nombre Nuevo'
        db.commit()
    destinations=c.get('/api/v1/print-jobs/destinations',headers=h).json()['destinations']
    selected=next(row for row in destinations if row['target_agent']==station)
    assert selected['station_name']=='QA Nombre Nuevo'
    payload,delivery=submit(api)
    assert payload['target_agent']==station and delivery['job_id']==payload['job_id']
    with Session(e) as db:
        job=db.get(PrintJob,payload['job_id'])
        assert job.agent_id==original_id

@pytest.mark.parametrize('origin',['WEB_DESKTOP','WEB_MOBILE','WEB_TABLET'])
def test_full_http_states_origin_document_and_audit(api,origin):
    c,h,d,e,station,_=api
    assert c.get(ROOT+'/destinations',headers=h).json()['destinations']
    p,delivery=submit(api,origin_type=origin)
    path=ROOT+'/device/'+p['job_id']
    assert c.get(path+'/artifact',params={'delivery_id':delivery['delivery_id']},headers=d).status_code==200
    for state in ('received','ready','printing'):
        r=c.post(path+'/progress',headers=d,json={'delivery_id':delivery['delivery_id'],'status':state})
        assert r.json()['status']==state,r.text
        assert c.get(ROOT+'/'+p['job_id'],headers=h).json()['status']==state
    r=c.post(path+'/result',headers=d,json={'delivery_id':delivery['delivery_id'],'outcome':'printed','synthetic_spooler_id':100001})
    assert r.json()['status']=='printed'
    assert c.get(path+'/artifact',params={'delivery_id':delivery['delivery_id']},headers=d).status_code==410
    assert c.post(path+'/result',headers=d,json={'delivery_id':delivery['delivery_id'],'outcome':'printed','synthetic_spooler_id':100001}).status_code==200
    with Session(e) as db:
        row=db.get(PrintJob,p['job_id']);assert row.source_agent_id is None and row.requested_by and row.origin_type==origin
        assert db.scalar(select(func.count(PrintResult.job_id)))==1
        logs=list(db.scalars(select(ClinicalAuditLog).where(ClinicalAuditLog.resource_type=='print_job')))
        assert any(x.action=='print_job.receipt_retry' for x in logs)
        assert all('SIN DATOS' not in str(x.context) for x in logs)

@pytest.mark.parametrize('value',[0,1000,-1,1.5,True])
def test_copy_bounds_and_forbidden_client_actor(api,value):
    c,h,d,e,station,_=api
    assert c.post(ROOT,headers=h,json=request(station,copies=value)).status_code==422
    assert c.post(ROOT,headers=h,json=request(station,requested_by=99)).status_code==422

@pytest.mark.parametrize('copies',[1,3,999])
def test_valid_copies_and_immutable_retry(api,copies):
    c,h,d,e,station,_=api;p=request(station,copies=copies)
    first=c.post(ROOT,headers=h,json=p);assert first.status_code==200
    assert c.post(ROOT,headers=h,json=p).json()['job_id']==p['job_id']
    assert c.post(ROOT,headers=h,json={**p,'origin_type':'WEB_MOBILE'}).status_code==409
    with Session(e) as db:assert db.scalar(select(func.count(PrintJob.id)))==1

@pytest.mark.parametrize('ref',['qa-general','qa-financial','qa-clinical'])
def test_classification_resolved_server_side_and_target_denial(api,ref):
    c,h,d,e,station,targets=api
    r=c.post(ROOT,headers=h,json=request(station,document_reference=ref));assert r.status_code==200,r.text
    assert r.json()['security_class'] in {'GENERAL','FINANCIAL','CLINICAL'}
    with Session(e) as db:other=db.get(LocalAgent,targets[1][0].agent_id).agent_uuid
    assert c.post(ROOT,headers=h,json=request(other)).status_code==404
    assert c.get(ROOT+'/'+r.json()['job_id'],headers=d).status_code==401
    assert c.get(ROOT+'/device/poll',headers=h).status_code==401
    assert c.get(ROOT+'/device/'+r.json()['job_id']+'/artifact',params={'delivery_id':str(uuid4())},headers=d).status_code==404

def test_offline_then_online_unavailable_and_expiry(api):
    c,h,d,e,station,targets=api
    with Session(e) as db:a=db.get(LocalAgent,targets[0][0].agent_id);a.last_seen_at=jobs.utcnow()-timedelta(hours=1);db.commit()
    p=request(station);assert c.post(ROOT,headers=h,json=p).json()['status']=='queued'
    assert c.get(ROOT+'/device/poll',headers=d).json() is None
    with Session(e) as db:a=db.get(LocalAgent,targets[0][0].agent_id);a.last_seen_at=jobs.utcnow();db.commit()
    delivery=c.get(ROOT+'/device/poll',headers=d).json();assert delivery['job_id']==p['job_id']
    with Session(e) as db:printer=db.get(AgentPrinter,targets[0][1]);printer.available=False;db.commit()
    assert c.get(ROOT+'/device/'+p['job_id']+'/delivery',headers=d).json()['printer_available'] is False
    with Session(e) as db:
        # Intent expiry cannot be mutated: advance the service clock, not historical rows.
        row=db.get(PrintJob,p['job_id']);expiry=row.expires_at
    from unittest.mock import patch
    with patch('app.services.print_jobs.utcnow',return_value=expiry+timedelta(seconds=1)):
        assert c.get(ROOT+'/'+p['job_id'],headers=h).json()['status']=='expired'
        assert c.get(ROOT+'/device/'+p['job_id']+'/artifact',params={'delivery_id':delivery['delivery_id']},headers=d).status_code==410

@pytest.mark.parametrize('phase',['queued','received','ready'])
def test_cancel_preexecution_and_unknown_never_reprints(api,phase):
    c,h,d,e,station,_=api;p,delivery=submit(api)
    for state in ('received','ready'):
        if phase=='queued' or (phase=='received' and state=='ready'):break
        c.post(ROOT+'/device/'+p['job_id']+'/progress',headers=d,json={'delivery_id':delivery['delivery_id'],'status':state})
    assert c.post(ROOT+'/'+p['job_id']+'/cancel',headers=h).json()['status']=='cancelled'
    assert c.get(ROOT+'/device/poll',headers=d).json() is None

def test_transport_and_permissions_fail_closed(api):
    c,h,d,e,station,_=api
    assert c.post('http://localhost'+ROOT,headers=h,json=request(station)).status_code==400
    assert c.get(ROOT+'/destinations').status_code in (401,403)
    with Session(e) as db:
        u=db.scalar(select(User).where(User.email.like('print-%')));u.memberships[0].denied_permissions=['documents:print'];db.commit()
        fresh={'Authorization':'Bearer '+create_access_token(u.email,u.session_version,u.id,{'scope':'tenant','org':1})}
    assert c.post(ROOT,headers=h,json=request(station)).status_code==401
    assert c.post(ROOT,headers=fresh,json=request(station)).status_code==403
