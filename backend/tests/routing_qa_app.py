"""Explicit disposable fixture factory. Never import/mount into official main."""
import os
from datetime import timedelta
from fastapi import FastAPI, Depends, Response
from sqlalchemy import select
from sqlalchemy.orm import Session
from app.db import engine, get_db
from app.core.security import create_access_token
from app.models import User, OrganizationMembership, Role, CareCenter
from app.services.bootstrap import seed_identity
from app.services.tenancy import bind_scope
from app.services import local_agents as registry, print_jobs as jobs
from app.models.local_agent import LocalAgent, AgentPrinter, AgentWorkgroup
from app.api.routes.print_routing import router
from app.api.routes.local_agents import router as registry_router
from app.services.print_routing import SyntheticRoutingPolicy


def require_disposable():
    if engine.url.host!='atlas-routing-qa-pg' or engine.url.database!='atlas_routing_qa':
        raise RuntimeError('Only disposable routing QA database; official forbidden')


def seed(station):
    require_disposable()
    with Session(engine) as db:
        seed_identity(db)
        if db.scalar(select(LocalAgent.id)) is not None:return
        role=db.scalar(select(Role).where(Role.code=='admin'))
        user=User(email='routing@example.test',full_name='QA Routing',password_hash='NOT-A-LOGIN',
            memberships=[OrganizationMembership(organization_id=1,roles=[role])])
        db.add(user);db.flush()
        center=CareCenter(id=1,organization_id=1,name='QA CEMER fixture',city='QA');db.add(center);db.flush()
        group=AgentWorkgroup(organization_id=1,center_id=1,name='QA ONLY',created_by=user.id);db.add(group);db.flush()
        agent=LocalAgent(organization_id=1,agent_uuid=station,display_code='QA-FAKE',station_name='Estación fake QA',
            center_id=1,workgroup_id=group.id,version='qa-only',protocol_version=3,fingerprint='a'*64,
            credential_hash=registry.digest(os.environ['ATLAS_FAKE_AGENT_TOKEN']),credential_expires_at=jobs.utcnow()+timedelta(hours=2),paired_by=user.id)
        db.add(agent);db.flush()
        db.add(AgentPrinter(organization_id=1,agent_id=agent.id,local_id='printer-fake',display_name='Fake spooler · SIN PAPEL',
            driver='FAKE ONLY',is_default=False,connection='unknown',is_virtual=True,status='ready',papers=[],available=True))
        db.commit()


def create_app():
    require_disposable()
    app=FastAPI(title='ATLAS ROUTING QA · FAKE ONLY')
    app.state.synthetic_print_routing=SyntheticRoutingPolicy()
    app.include_router(router,prefix='/api/v1')
    app.include_router(registry_router,prefix='/api/v1')

    @app.get('/api/v1/health')
    def health():return {'status':'ok','fake_only':True}

    @app.post('/api/v1/qa/session')
    def session(response: Response,db=Depends(get_db)):
        # Only this marked/disposable app exposes a demo session, never official Atlas.
        user=db.scalar(select(User).where(User.email=='routing@example.test'))
        response.headers['Cache-Control']='no-store'
        return {'access_token':create_access_token(user.email,user.session_version,user.id,{'scope':'tenant','org':1})}
    return app


if __name__=='__main__':
    seed(os.environ['ATLAS_QA_EXISTING_STATION'])
