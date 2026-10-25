"""Concurrent human acknowledgement with mock spool evidence, disposable PG only."""
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from uuid import uuid4
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import select,func
from sqlalchemy.orm import Session
from sqlalchemy.schema import CreateSchema,DropSchema
from app.db import engine,Base,get_db
from app.models import User,Role,ClinicalAuditLog
from app.models.local_agent import LocalAgent,AgentPrinter
from app.models.print_job import PrintJob
from app.services import print_jobs as jobs
from app.services.bootstrap import seed_identity
from app.services.tenancy import bind_scope
from app.core.security import create_access_token
from app.api.routes.official_print_routing import router
from test_print_job_persistence import seed_targets

def main():
    if (engine.url.host,engine.url.database)!=('atlas-print69-qa-pg','atlas_print69_qa'):
        raise RuntimeError('Disposable registry/print contract DB only')
    schema='qa_confirm_'+uuid4().hex
    with engine.begin() as c:c.execute(CreateSchema(schema))
    scoped=engine.execution_options(schema_translate_map={None:schema})
    try:
        Base.metadata.create_all(scoped)
        with Session(scoped) as db:seed_identity(db)
        targets=seed_targets(scoped);scope,printer_id=targets[0];job_id=str(uuid4())
        with Session(scoped) as db:
            bind_scope(db,'tenant',1)
            actor=db.scalar(select(User).where(User.email.like('print-%')))
            actor.memberships[0].roles=[db.scalar(select(Role).where(Role.code=='admin'))]
            db.get(AgentPrinter,printer_id).is_virtual=False;db.commit()
            # Mock receipt only: no runtime grant, registry credential, Windows or physical executor.
            intent=jobs.PrintIntent(job_id,printer_id,'physical-routing-qa','a'*64,jobs.utcnow()+timedelta(minutes=2),
                format='plain_text',document_type='physical_routing_qa',document_security_class='GENERAL')
            jobs.register(db,scope,intent,actor=actor,document_resolver=lambda *_:jobs.ResolvedPrintDocument(1,'physical-routing-qa','physical_routing_qa','GENERAL','a'*64))
            attempt=jobs.deliver(db,scope,job_id)
            for state in ('received','ready','printing'):jobs.advance(db,scope,job_id,state,delivery_id=attempt.id)
            jobs.record_result(db,scope,job_id,attempt.id,'submitted',spool_id=456)
            db.commit();token=create_access_token(actor.email,actor.session_version,actor.id,{'scope':'tenant','org':1})
        app=FastAPI();app.include_router(router,prefix='/api/v1')
        def session():
            with Session(scoped) as db:bind_scope(db,'tenant',1);yield db
        app.dependency_overrides[get_db]=session
        def confirm(_):
            with TestClient(app,base_url='https://localhost') as c:
                r=c.post('/api/v1/print-routing/'+job_id+'/confirm-physical',headers={'Authorization':'Bearer '+token},json={'confirmed':True})
                assert r.status_code==200,r.status_code
                return r.json()
        with ThreadPoolExecutor(2) as pool:results=list(pool.map(confirm,range(2)))
        assert all(r['status']=='printed' and r['physical_evidence']['kind']=='HUMAN_CONFIRMED_PRINTED' for r in results)
        with Session(scoped) as db:
            assert db.scalar(select(func.count(ClinicalAuditLog.id)).where(ClinicalAuditLog.action=='print_job.human_confirmed_yes'))==1
            assert db.get(PrintJob,job_id).status=='printed'
        print('HUMAN_CONFIRMATION_PG=PASS; requests=2x200; human_audits=1; printed_jobs=1; physical_executions=0')
    finally:
        with engine.begin() as c:c.execute(DropSchema(schema,cascade=True))
        engine.dispose()

if __name__=='__main__':main()
