"""Isolated PostgreSQL HTTP concurrency probe; refuses every official DB."""
from concurrent.futures import ThreadPoolExecutor
from uuid import uuid4
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import select,func
from sqlalchemy.orm import Session
from sqlalchemy.schema import CreateSchema,DropSchema
from app.db import engine,Base,get_db
from app.models import User,Role,ClinicalAuditLog
from app.models.local_agent import LocalAgent,AgentPrinter
from app.models.print_job import PrintJob,PrintDelivery
from app.services.bootstrap import seed_identity
from app.services.tenancy import bind_scope
from app.services.local_agents import digest
from app.core.security import create_access_token
from app.api.routes.official_print_routing import router
from test_print_job_persistence import seed_targets


def main():
    if (engine.url.host,engine.url.database)!=('atlas-print69-qa-pg','atlas_print69_qa'):
        raise RuntimeError('Disposable contract DB only')
    schema='qa_http_'+uuid4().hex
    with engine.begin() as c:c.execute(CreateSchema(schema))
    scoped=engine.execution_options(schema_translate_map={None:schema})
    try:
        Base.metadata.create_all(scoped)
        with Session(scoped) as db:seed_identity(db)
        targets=seed_targets(scoped);credential='ala_'+('q'*43)
        with Session(scoped) as db:
            actor=db.scalar(select(User).where(User.email.like('print-%')))
            actor.memberships[0].roles=[db.scalar(select(Role).where(Role.code=='admin'))]
            a=db.get(LocalAgent,targets[0][0].agent_id);a.credential_hash=digest(credential)
            p=db.get(AgentPrinter,targets[0][1]);p.is_virtual=False
            db.commit();station=a.agent_uuid
            user_token=create_access_token(actor.email,actor.session_version,actor.id,{'scope':'tenant','org':1})
        app=FastAPI();app.include_router(router,prefix='/api/v1')
        def session():
            with Session(scoped) as db:bind_scope(db,'tenant',1);yield db
        app.dependency_overrides[get_db]=session
        payload=dict(job_id=str(uuid4()),target_agent=station,target_printer='printer-qa',document_reference='qa-general',origin_type='WEB_DESKTOP',copies=1)
        def create(_):
            with TestClient(app,base_url='https://localhost') as c:
                r=c.post('/api/v1/print-routing',headers={'Authorization':'Bearer '+user_token},json=payload)
                assert r.status_code==200,r.status_code
                return r.json()
        with ThreadPoolExecutor(2) as pool: rows=list(pool.map(create,range(2)))
        assert rows[0]['intent_hash']==rows[1]['intent_hash'] and rows[0]['job_id']==rows[1]['job_id']
        def claim(_):
            with TestClient(app,base_url='https://localhost') as c:
                r=c.get('/api/v1/print-routing/device/poll',headers={'Authorization':'Bearer '+credential})
                assert r.status_code==200,r.status_code
                return r.json()
        with ThreadPoolExecutor(2) as pool: leases=list(pool.map(claim,range(2)))
        assert leases[0]['delivery_id']==leases[1]['delivery_id']
        with Session(scoped) as db:
            assert db.scalar(select(func.count(PrintJob.id)))==1
            assert db.scalar(select(func.count(PrintDelivery.id)))==1
            assert db.scalar(select(func.count(ClinicalAuditLog.id)).where(ClinicalAuditLog.action=='print_job.created'))==1
        print('OFFICIAL_PG_HTTP_CONCURRENCY=PASS; creates=2x200; logical_jobs=1; claims=2; leases=1; create_audits=1; physical=0')
    finally:
        with engine.begin() as c:c.execute(DropSchema(schema,cascade=True))
        engine.dispose()


if __name__=='__main__':main()
