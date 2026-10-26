"""QA-only router, intentionally NOT included in app.main."""
from datetime import timedelta
from typing import Literal
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy import select
from app.api.deps import current_user
from app.api.routes.local_agents import device, secure_transport
from app.db import get_db
from app.models import User
from app.models.local_agent import AgentPrinter, LocalAgent
from app.models.print_job import PrintJob, PrintDelivery
from app.services import print_jobs as jobs, print_routing as routing

router=APIRouter(prefix='/print-jobs',tags=['Synthetic routing QA'],dependencies=[Depends(secure_transport)])


def policy(request: Request, db=Depends(get_db)):
    value=getattr(request.app.state,'synthetic_print_routing',None)
    bind=db.get_bind()
    url=(bind.engine if hasattr(bind,'engine') else bind).url
    temporary=(url.host=='atlas-routing-qa-pg' and url.database=='atlas_routing_qa')
    if not isinstance(value,routing.SyntheticRoutingPolicy) or not value.synthetic_only or not (temporary or url.get_backend_name()=='sqlite'):
        raise HTTPException(503,'Routing fake disponible solo en fixture aislado')
    return value


class Create(BaseModel):
    model_config=ConfigDict(extra='forbid')
    job_id: UUID
    target_agent: UUID
    target_printer: str=Field(pattern=r'^[A-Za-z0-9_-]{1,100}$')
    document_reference: Literal['qa-general','qa-financial','qa-clinical','physical-routing-qa']
    origin_type: Literal['WEB_DESKTOP','WEB_MOBILE','WEB_TABLET']
    copies: int=Field(default=1,ge=1,le=999,strict=True)
    ttl_seconds: int=Field(default=300,ge=1,le=300,strict=True)

    @field_validator('job_id','target_agent')
    @classmethod
    def nonempty_uuid(cls,value):
        if value.int==0: raise ValueError('Identidad vacía')
        return value


class Progress(BaseModel):
    model_config=ConfigDict(extra='forbid')
    delivery_id: UUID
    status: Literal['received','ready','printing']


class Result(BaseModel):
    model_config=ConfigDict(extra='forbid')
    delivery_id: UUID
    outcome: Literal['submitted','printed','failed','unknown','cancelled','expired']
    synthetic_spooler_id: int|None=Field(default=None,gt=0,strict=True)
    error_code: str|None=Field(default=None,pattern=r'^[A-Z0-9_]{1,40}$')


@router.get('/destinations')
def destinations(user=Depends(current_user), db=Depends(get_db), p=Depends(policy)):
    rows=[]
    for agent in db.scalars(select(LocalAgent).where(LocalAgent.revoked_at.is_(None))):
        try: routing.target(db,user,agent.agent_uuid)
        except HTTPException: continue
        for printer in db.scalars(select(AgentPrinter).where(AgentPrinter.agent_id==agent.id,AgentPrinter.is_virtual.is_(True))):
            rows.append({'target_agent':agent.agent_uuid,'target_printer':printer.local_id,
                'station_name':agent.station_name,'printer_name':printer.display_name,'available':printer.available,
                'online':routing.registry.state(agent)=='online','center_id':agent.center_id})
    if not {'documents:print','local_agents:view'}.issubset(routing.effective_permissions(user)):
        raise HTTPException(403,'No tiene permiso')
    return {'fake_only':True,'destinations':rows}


@router.post('')
def create(payload: Create,user=Depends(current_user),db=Depends(get_db),p=Depends(policy)):
    agent,printer=p.target(db,user,payload.target_agent,payload.target_printer)
    scope=jobs.PrintScope(agent.organization_id,agent.center_id,agent.id)
    if db.get_bind().dialect.name=='postgresql':
        from sqlalchemy import text
        # Stable server-owned expiry for simultaneous first submits of the same UUID.
        # DB uniqueness remains the authority; a hash collision only serializes work.
        db.execute(text('SELECT pg_advisory_xact_lock(hashtextextended(:identity,0))'),
            {'identity':'print-create:'+str(payload.job_id)})
    existing=db.scalar(select(PrintJob).where(PrintJob.id==str(payload.job_id)))
    # Server-owned expiry remains stable for a retry; no client timestamp/actor/class claim.
    doc,expiry=p.prepare(db,user,payload,agent,printer,existing)
    intent=jobs.PrintIntent(str(payload.job_id),printer.id,doc.reference,doc.content_sha256,expiry,
        format='plain_text',copies=payload.copies,origin_type=payload.origin_type,
        document_type=doc.document_type,document_security_class=doc.security_class)
    row=jobs.register(db,scope,intent,actor=user,document_resolver=p.resolve)
    if existing: jobs._audit(db,row,'print_job.retry')
    elif doc.document_type=='physical_routing_qa':jobs._audit(db,row,'print_job.physical_authorized')
    db.commit()
    return routing.status(db,row,user=user)


@router.get('/device/poll')
def poll(row=Depends(device),db=Depends(get_db),p=Depends(policy)):
    value=routing.delivery(db,row,p);db.commit();return value


@router.get('/device/{job_id}/delivery')
def redelivery(job_id: UUID,row=Depends(device),db=Depends(get_db),p=Depends(policy)):
    value=routing.delivery(db,row,p,job_id);db.commit();return value


def device_job(db,agent,job_id,delivery_id):
    scope=jobs.PrintScope(agent.organization_id,agent.center_id,agent.id)
    row=jobs.get_job(db,scope,str(job_id))
    attempt=db.scalar(select(PrintDelivery).where(PrintDelivery.id==str(delivery_id),PrintDelivery.job_id==row.id,PrintDelivery.agent_id==agent.id))
    if attempt is None: raise HTTPException(404,'Entrega no autorizada')
    return scope,row


@router.get('/device/{job_id}/artifact')
def artifact(job_id: UUID,delivery_id: UUID,row=Depends(device),db=Depends(get_db),p=Depends(policy)):
    scope,job=device_job(db,row,job_id,delivery_id)
    if job.status not in {'queued','received','ready'} or job.expires_at<=jobs.utcnow():
        raise HTTPException(410,'Documento expirado o no ejecutable')
    actor=db.get(User,job.requested_by)
    if actor is None or not actor.is_active: raise HTTPException(403,'Solicitante no disponible')
    printer=db.get(AgentPrinter,job.printer_id)
    p.target(db,actor,row.agent_uuid,printer.local_id)
    doc=p.resolve(db,actor,job.artifact_ref,job.document_type)
    if job.document_type=='physical_routing_qa' and not routing.physical_authorized(db,job):
        raise HTTPException(403,'Autorización física QA expirada o revocada')
    if doc.content_sha256!=job.content_sha256: raise HTTPException(409,'Documento cambió')
    return Response(p.content(doc.reference),media_type='text/plain',headers={'Cache-Control':'no-store','X-Content-Type-Options':'nosniff'})


@router.post('/device/{job_id}/progress')
def progress(job_id: UUID,payload: Progress,row=Depends(device),db=Depends(get_db),p=Depends(policy)):
    scope,job=device_job(db,row,job_id,payload.delivery_id)
    job=jobs.advance(db,scope,job.id,payload.status,delivery_id=str(payload.delivery_id));db.commit()
    return routing.status(db,job)


@router.post('/device/{job_id}/result')
def result(job_id: UUID,payload: Result,row=Depends(device),db=Depends(get_db),p=Depends(policy)):
    scope,job=device_job(db,row,job_id,payload.delivery_id)
    from app.models.print_job import PrintResult
    repeated=db.get(PrintResult,job.id) is not None
    previous_status=job.status
    from app.services import physical_print_evidence as physical
    human=physical.confirmation(db,job) if job.document_type=='physical_routing_qa' else None
    if human:
        stored=db.get(PrintResult,job.id)
        if not stored or payload.synthetic_spooler_id!=stored.spool_id:raise HTTPException(409,'Recibo distinto del confirmado')
        jobs._audit(db,job,'print_job.receipt_retry');db.commit();return routing.status(db,job)
    jobs.record_result(db,scope,job.id,str(payload.delivery_id),payload.outcome,spool_id=payload.synthetic_spooler_id,error_code=payload.error_code)
    if job.document_type=='physical_routing_qa':
        if payload.outcome=='submitted' and not repeated:jobs._audit(db,job,'print_job.awaiting_human_confirmation',extra={'spool_id':payload.synthetic_spooler_id})
        elif payload.outcome=='printed' and previous_status!='printed':jobs._audit(db,job,'print_job.os_reported_printed',extra={'spool_id':payload.synthetic_spooler_id})
    if repeated: jobs._audit(db,job,'print_job.receipt_retry')
    db.commit();return routing.status(db,job)


@router.get('/{job_id}')
def status(job_id: UUID,user=Depends(current_user),db=Depends(get_db),p=Depends(policy)):
    row=routing.user_job(db,user,job_id)
    if row.status in {'queued','received','ready'} and row.expires_at<=jobs.utcnow():
        jobs._change(db,row,'expired');db.commit()
    return routing.status(db,row,user=user)


@router.post('/{job_id}/cancel')
def cancel(job_id: UUID,user=Depends(current_user),db=Depends(get_db),p=Depends(policy)):
    row=routing.user_job(db,user,job_id)
    row=jobs.cancel(db,jobs.PrintScope(row.organization_id,row.center_id,row.agent_id),row.id);db.commit()
    return routing.status(db,row,user=user)
