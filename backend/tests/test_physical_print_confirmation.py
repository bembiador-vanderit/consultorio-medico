"""Mock physical receipts only, SQLite fixtures / disposable PostgreSQL; no Windows printing."""
from uuid import uuid4
import json
import pytest
from sqlalchemy import select,func
from sqlalchemy.orm import Session
from test_official_print_routing import official,physical_grant,ROOT
from test_print_routing import api,request
from app.models import ClinicalAuditLog,User
from app.models.print_job import PrintJob,PrintResult
from app.core.security import create_access_token
from app.db import get_db
from app.services.tenancy import bind_scope

def submitted(official,monkeypatch,tmp_path,outcome='submitted'):
    c,h,d,e,station,_=official;p=request(station,document_reference='physical-routing-qa')
    grant=physical_grant(e,p);path=tmp_path/'grant.json';path.write_text(json.dumps(grant))
    monkeypatch.setenv('ATLAS_PHYSICAL_QA_AUTHORIZATION_FILE',str(path))
    assert c.post(ROOT,headers=h,json=p).status_code==200
    if outcome=='queued':
        monkeypatch.delenv('ATLAS_PHYSICAL_QA_AUTHORIZATION_FILE');return p,None
    dl=c.get(ROOT+'/device/poll',headers=d).json();route=ROOT+'/device/'+p['job_id']
    for state in ('received','ready','printing'):
        assert c.post(route+'/progress',headers=d,json={'delivery_id':dl['delivery_id'],'status':state}).status_code==200
    assert c.post(route+'/result',headers=d,json={'delivery_id':dl['delivery_id'],'outcome':outcome,'synthetic_spooler_id':123}).status_code==200
    monkeypatch.delenv('ATLAS_PHYSICAL_QA_AUTHORIZATION_FILE')
    return p,dl

@pytest.mark.parametrize('yes',[True,False])
def test_human_result_idempotence_conflict_and_durable_device_receipt(official,monkeypatch,tmp_path,yes):
    c,h,d,e,_,_=official;p,dl=submitted(official,monkeypatch,tmp_path)
    path=ROOT+'/'+p['job_id'];status=c.get(path,headers=h).json()
    assert status['status']=='submitted' and status['physical_evidence']['kind']=='AWAITING_HUMAN_CONFIRMATION'
    assert status['can_confirm_physical'] is True
    for _ in range(2):
        r=c.post(path+'/confirm-physical',headers=h,json={'confirmed':yes});assert r.status_code==200,r.text
        assert r.json()['status']==('printed' if yes else 'unknown') and not r.json()['can_confirm_physical']
        assert r.json()['physical_evidence']['confirmation']['confirmed']==yes
    assert c.post(path+'/confirm-physical',headers=h,json={'confirmed':not yes}).status_code==409
    with Session(e) as db:
        events=list(db.scalars(select(ClinicalAuditLog).where(ClinicalAuditLog.action.like('print_job.human_confirmed_%'))))
        assert len(events)==1 and events[0].user_id==db.get(PrintJob,p['job_id']).requested_by
        assert events[0].context['spool_id']==123 and events[0].created_at
        assert db.get(PrintResult,p['job_id']).spool_id==123
    # A stale agent's same spool receipt cannot undo a human result.
    route=ROOT+'/device/'+p['job_id']
    assert c.post(route+'/result',headers=d,json={'delivery_id':dl['delivery_id'],'outcome':'submitted','synthetic_spooler_id':123}).json()['status']==('printed' if yes else 'unknown')
    delivery=c.get(route+'/delivery',headers=d).json()
    assert delivery['human_confirmed']==yes and delivery['result_spooler_id']==123 and delivery['receipt_only']

def test_os_final_evidence_does_not_need_human_confirmation(official,monkeypatch,tmp_path):
    c,h,d,e,_,_=official;p,_=submitted(official,monkeypatch,tmp_path,'printed')
    status=c.get(ROOT+'/'+p['job_id'],headers=h).json()
    assert status['status']=='printed' and status['physical_evidence']['kind']=='OS_REPORTED_PRINTED'
    assert not status['can_confirm_physical']
    assert c.post(ROOT+'/'+p['job_id']+'/confirm-physical',headers=h,json={'confirmed':True}).status_code==409

def test_safe_validation_and_missing_evidence_cannot_be_confirmed(official,monkeypatch,tmp_path):
    c,h,d,e,station,_=official;p=request(station);assert c.post(ROOT,headers=h,json=p).status_code==200
    assert c.post(ROOT+'/'+p['job_id']+'/confirm-physical',headers=h,json={'confirmed':True}).status_code==409
    pending,_=submitted(official,monkeypatch,tmp_path,'queued')
    assert c.post(ROOT+'/'+pending['job_id']+'/confirm-physical',headers=h,json={'confirmed':True}).status_code==409
    c.post(ROOT+'/'+pending['job_id']+'/cancel',headers=h)
    assert c.post(ROOT+'/'+pending['job_id']+'/confirm-physical',headers=h,json={'confirmed':True}).status_code==409

def test_permission_tenant_actor_injection_and_read_only_audit(official,monkeypatch,tmp_path):
    c,h,d,e,station,targets=official;p,_=submitted(official,monkeypatch,tmp_path);path=ROOT+'/'+p['job_id']+'/confirm-physical'
    assert c.post(path,json={'confirmed':True}).status_code in (401,403)
    assert c.post(path,headers=h,json={'confirmed':True,'confirmed_by':42}).status_code==422
    assert c.post(path,headers=h,json={'confirmed':'true'}).status_code==422
    with Session(e) as db:
        user=db.scalar(select(User).where(User.email.like('print-%')))
        other={'Authorization':'Bearer '+create_access_token(user.email,user.session_version,user.id,{'scope':'tenant','org':2})}
        before=db.scalar(select(func.count(ClinicalAuditLog.id)))
    original=c.app.dependency_overrides[get_db]
    def other_session():
        with Session(e) as db:bind_scope(db,'tenant',2);yield db
    c.app.dependency_overrides[get_db]=other_session
    try:assert c.post(path,headers=other,json={'confirmed':True}).status_code in (403,404)
    finally:c.app.dependency_overrides[get_db]=original
    for _ in range(2):assert c.get(ROOT+'/'+p['job_id'],headers=h).status_code==200
    with Session(e) as db:
        assert db.scalar(select(func.count(ClinicalAuditLog.id)))==before
        user=db.scalar(select(User).where(User.email.like('print-%')));user.memberships[0].denied_permissions=['documents:print'];db.commit();db.refresh(user)
        denied={'Authorization':'Bearer '+create_access_token(user.email,user.session_version,user.id,{'scope':'tenant','org':1})}
    assert c.post(path,headers=denied,json={'confirmed':True}).status_code==403

def test_unknown_not_promoted_and_negative_never_requeues(official,monkeypatch,tmp_path):
    c,h,d,e,_,_=official;p,dl=submitted(official,monkeypatch,tmp_path)
    assert c.post(ROOT+'/'+p['job_id']+'/confirm-physical',headers=h,json={'confirmed':False,'reason':'damaged'}).status_code==200
    assert c.get(ROOT+'/device/poll',headers=d).json() is None
    assert c.post(ROOT+'/'+p['job_id']+'/confirm-physical',headers=h,json={'confirmed':True}).status_code==409
