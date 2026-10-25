"""Official routes with normal sessions and existing registry credentials; no physical executor."""
from uuid import uuid4
import pytest
from sqlalchemy.orm import Session
from sqlalchemy import select,func
from test_print_routing import api,request
from app.api.routes.official_print_routing import router
from app.models import ClinicalAuditLog,User,Role,Permission
from app.core.security import create_access_token
from app.models.local_agent import AgentPrinter,LocalAgent
from app.models.print_job import PrintJob,PrintResult
from app.services import print_jobs as jobs, print_routing as routing

ROOT='/api/v1/print-routing'

@pytest.fixture
def official(api):
    c,h,d,e,station,targets=api
    c.app.include_router(router,prefix='/api/v1')
    with Session(e) as db:
        p=db.get(AgentPrinter,targets[0][1]);p.is_virtual=False;db.commit()
    return api

@pytest.mark.parametrize('origin',['WEB_DESKTOP','WEB_MOBILE','WEB_TABLET'])
@pytest.mark.parametrize('ref',['qa-general','qa-financial','qa-clinical'])
def test_official_lifecycle_scoped_delivery_and_test_marker(official,origin,ref):
    c,h,d,e,station,_=official
    dest=c.get(ROOT+'/destinations',headers=h)
    assert dest.status_code==200 and dest.json()['physical_execution_enabled'] is False
    p=request(station,origin_type=origin,document_reference=ref)
    first=c.post(ROOT,headers=h,json=p);assert first.status_code==200,first.text
    assert first.json()['execution_mode']=='safe_validation'
    assert c.post(ROOT,headers=h,json=p).json()['job_id']==p['job_id']
    delivery=c.get(ROOT+'/device/poll',headers=d).json()
    assert c.get(ROOT+'/device/'+p['job_id']+'/delivery',headers=d).json()['delivery_id']==delivery['delivery_id']
    path=ROOT+'/device/'+p['job_id']
    assert c.get(path+'/artifact',params={'delivery_id':delivery['delivery_id']},headers=d).status_code==200
    for state in ('received','ready','printing'):
        assert c.post(path+'/progress',headers=d,json={'delivery_id':delivery['delivery_id'],'status':state}).json()['status']==state
    assert c.post(ROOT+'/'+p['job_id']+'/cancel',headers=h).json()['status']=='printing'
    result={'delivery_id':delivery['delivery_id'],'outcome':'printed','synthetic_spooler_id':1234}
    for _ in range(2): assert c.post(path+'/result',headers=d,json=result).json()['status']=='printed'
    assert c.get(ROOT+'/'+p['job_id'],headers=h).json()['status']=='printed'
    assert c.get(path+'/artifact',params={'delivery_id':delivery['delivery_id']},headers=d).status_code==410
    with Session(e) as db:
        assert db.scalar(select(func.count(PrintResult.job_id)))==1
        row=db.get(PrintJob,p['job_id']);assert row.source_agent_id is None and row.requested_by
        assert any(a.action=='print_job.receipt_retry' for a in db.scalars(select(ClinicalAuditLog)))

def test_official_auth_device_tls_and_forbidden_metadata(official):
    c,h,d,e,station,_=official
    assert c.get(ROOT+'/destinations').status_code in (401,403)
    assert c.get(ROOT+'/device/poll',headers=h).status_code==401
    assert c.get('http://localhost'+ROOT+'/device/poll',headers=d).status_code==400
    assert c.post(ROOT,headers=h,json=request(station,requested_by=42)).status_code==422
    assert c.post(ROOT,headers=h,json=request(station,document_reference='patient.pdf')).status_code==422
    assert c.post(ROOT,headers=h,json=request(str(uuid4()))).status_code==404
    # User routes use normal Atlas auth, never a forwarded header as authorization.
    assert c.get(ROOT+'/destinations',headers={'x-forwarded-proto':'https'}).status_code in (401,403)
    with Session(e) as db:
        user=db.scalar(select(User).where(User.email.like('print-%')))
        user.memberships[0].denied_permissions=['documents:print'];db.commit()
        denied={'Authorization':'Bearer '+create_access_token(user.email,user.session_version,user.id,{'scope':'tenant','org':1})}
    assert c.get(ROOT+'/destinations',headers=denied).status_code==403
    assert c.post(ROOT,headers=denied,json=request(station)).status_code==403

def test_official_cross_center_and_document_permission_denial(official):
    c,h,d,e,station,targets=official
    with Session(e) as db:
        user=db.scalar(select(User).where(User.email.like('print-%')))
        member=user.memberships[0]
        # A non-admin with explicit print/view still has no authorized center.
        limited=Role(code='qa_print_scope',name='QA temporary scope',permissions=list(db.scalars(select(Permission).where(Permission.code.in_(['documents:print','local_agents:view'])))))
        db.add(limited);member.roles=[limited];db.commit()
        token={'Authorization':'Bearer '+create_access_token(user.email,user.session_version,user.id,{'scope':'tenant','org':1})}
    assert c.get(ROOT+'/destinations',headers=token).json()['destinations']==[]
    assert c.post(ROOT,headers=token,json=request(station)).status_code==404
    with Session(e) as db:
        user=db.scalar(select(User).where(User.email.like('print-%')))
        user.memberships[0].roles=[db.scalar(select(Role).where(Role.code=='admin'))]
        user.memberships[0].denied_permissions=['clinical_documents:view'];db.commit()
        token={'Authorization':'Bearer '+create_access_token(user.email,user.session_version,user.id,{'scope':'tenant','org':1})}
        other=db.get(LocalAgent,targets[1][0].agent_id).agent_uuid
    assert c.post(ROOT,headers=token,json=request(other)).status_code==404
    assert c.post(ROOT,headers=token,json=request(station,document_reference='qa-clinical')).status_code==403

@pytest.mark.parametrize('state',['cancelled','unknown'])
def test_official_final_states_are_receipt_only(official,state):
    c,h,d,e,station,_=official;p=request(station)
    assert c.post(ROOT,headers=h,json=p).status_code==200
    dl=c.get(ROOT+'/device/poll',headers=d).json();path=ROOT+'/device/'+p['job_id']
    if state=='cancelled': c.post(ROOT+'/'+p['job_id']+'/cancel',headers=h)
    else:
        for stage in ('received','ready','printing'):
            c.post(path+'/progress',headers=d,json={'delivery_id':dl['delivery_id'],'status':stage})
        c.post(path+'/result',headers=d,json={'delivery_id':dl['delivery_id'],'outcome':'unknown','error_code':'OUTCOME_UNKNOWN'})
    assert c.get(path+'/delivery',headers=d).json()['receipt_only'] is True
    assert c.get(ROOT+'/device/poll',headers=d).json() is None


def test_physical_default_denied_and_no_public_config_toggle(official):
    c,h,d,e,station,_=official
    assert c.post(ROOT,headers=h,json=request(station,document_reference='physical-routing-qa')).status_code==403
    for extra in ({'physical_execution_enabled':True},{'Enabled':True},{'authorization':{'Enabled':True}}):
        assert c.post(ROOT,headers=h,json=request(station,**extra)).status_code==422
    with Session(e) as db:assert db.scalar(select(func.count(PrintJob.id)))==0


def physical_grant(e,p):
    from datetime import datetime,UTC,timedelta
    from hashlib import sha256
    from app.services.tenancy import bind_scope
    expiry=(datetime.now(UTC)+timedelta(minutes=2)).replace(microsecond=0)
    with Session(e) as db:
        bind_scope(db,'tenant',1)
        user=db.scalar(select(User).where(User.email.like('print-%')))
        agent=db.scalar(select(LocalAgent).where(LocalAgent.agent_uuid==p['target_agent']))
        printer=db.scalar(select(AgentPrinter).where(AgentPrinter.agent_id==agent.id,AgentPrinter.local_id==p['target_printer']))
        content=sha256(routing.OfficialValidationPolicy().content('physical-routing-qa')).hexdigest()
        intent=jobs.PrintIntent(p['job_id'],printer.id,'physical-routing-qa',content,expiry.replace(tzinfo=None),
            format='plain_text',copies=1,origin_type='WEB_DESKTOP',document_type='physical_routing_qa',document_security_class='GENERAL')
        fingerprint=jobs.fingerprint(jobs.PrintScope(agent.organization_id,agent.center_id,agent.id),intent,user.id,agent.agent_uuid,printer.local_id)
        return dict(Enabled=True,AllowedJobId=p['job_id'],AllowedAgentId=agent.agent_uuid,AllowedPrinterId=printer.local_id,
            OrganizationId=1,CenterId=agent.center_id,MaxCopies=1,ExecutionMode='PhysicalQa',PrinterFingerprint='a'*64,
            ContentSha256=content,IntentHash=fingerprint,ValidFrom=(datetime.now(UTC)-timedelta(seconds=5)).isoformat(),ExpiresAt=expiry.isoformat())


def test_operator_file_pins_one_job_without_global_enable(official,monkeypatch,tmp_path):
    import json
    c,h,d,e,station,_=official;p=request(station,document_reference='physical-routing-qa')
    grant=physical_grant(e,p);path=tmp_path/'grant.json';path.write_text(json.dumps(grant))
    monkeypatch.setenv('ATLAS_PHYSICAL_QA_AUTHORIZATION_FILE',str(path))
    assert c.get(ROOT+'/destinations',headers=h).json()['physical_execution_enabled'] is False
    for changed in ({'job_id':str(uuid4())},{'copies':2},{'origin_type':'WEB_MOBILE'},{'target_printer':'other'}):
        assert c.post(ROOT,headers=h,json={**p,**changed}).status_code in (403,404)
    first=c.post(ROOT,headers=h,json=p);assert first.status_code==200,first.text
    assert first.json()['physical_execution_authorized'] is True and first.json()['execution_mode']=='physical_qa'
    dl=c.get(ROOT+'/device/poll',headers=d).json()
    assert dl['document_type']=='physical_routing_qa'
    assert c.get(ROOT+'/device/'+p['job_id']+'/artifact',headers=d,params={'delivery_id':dl['delivery_id']}).status_code==200
    monkeypatch.delenv('ATLAS_PHYSICAL_QA_AUTHORIZATION_FILE')
    assert c.get(ROOT+'/'+p['job_id'],headers=h).json()['physical_execution_authorized'] is False
    assert c.get(ROOT+'/device/'+p['job_id']+'/artifact',headers=d,params={'delivery_id':dl['delivery_id']}).status_code==403
    with Session(e) as db:
        assert db.scalar(select(func.count(PrintJob.id)))==1
        assert any(a.action=='print_job.physical_authorized' for a in db.scalars(select(ClinicalAuditLog)))


@pytest.mark.parametrize('change',['expiry','fingerprint','center','mode','extra'])
def test_invalid_operational_grant_is_not_a_permission(official,monkeypatch,tmp_path,change):
    import json
    c,h,d,e,station,_=official;p=request(station,document_reference='physical-routing-qa');grant=physical_grant(e,p)
    if change=='expiry':grant['ExpiresAt']=grant['ValidFrom']
    elif change=='fingerprint':grant['IntentHash']='b'*64
    elif change=='center':grant['CenterId']=999
    elif change=='mode':grant['ExecutionMode']='Physical'
    else:grant['UnsafeToggle']=True
    path=tmp_path/'grant.json';path.write_text(json.dumps(grant));monkeypatch.setenv('ATLAS_PHYSICAL_QA_AUTHORIZATION_FILE',str(path))
    assert c.post(ROOT,headers=h,json=p).status_code==403
