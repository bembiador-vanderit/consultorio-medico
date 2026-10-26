"""Official authenticated validation routing; separate from disposable QA routes.

    No physical execution, arbitrary URLs, documents or caller-selected tenants.
    Reuses the existing v2 handlers/services, not a second queue/state machine.
"""
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy import select
from typing import Literal
from pydantic import BaseModel,ConfigDict,StrictBool
from app.api.deps import current_user
from app.api.routes.local_agents import device
from app.api.routes import print_routing as handlers
from app.db import get_db
from app.models.local_agent import LocalAgent, AgentPrinter
from app.services import print_routing as routing

router=APIRouter(prefix='/print-routing',tags=['Impresión · validación sin papel'])
POLICY=routing.OfficialValidationPolicy()

class PhysicalConfirmation(BaseModel):
    model_config=ConfigDict(extra='forbid')
    confirmed:StrictBool
    reason:Literal['not_printed','damaged','other']|None=None

@router.post('/{job_id}/confirm-physical')
def confirm_physical(job_id:UUID,payload:PhysicalConfirmation,user=Depends(current_user),db=Depends(get_db)):
    from app.services import physical_print_evidence as physical
    row=routing.user_job(db,user,job_id)
    if payload.confirmed and payload.reason is not None:raise HTTPException(422,'La confirmación positiva no admite motivo de fallo')
    physical.confirm(db,row,user,payload.confirmed,payload.reason)
    db.commit()
    return routing.status(db,row,user=user)


@router.get('/destinations')
def destinations(response: Response,user=Depends(current_user),db=Depends(get_db)):
    if not {'documents:print','local_agents:view'}.issubset(routing.effective_permissions(user)):
        raise HTTPException(403,'No tiene permiso para imprimir')
    rows=[]
    for agent in db.scalars(select(LocalAgent).where(LocalAgent.revoked_at.is_(None))):
        try: POLICY.target(db,user,agent.agent_uuid)
        except HTTPException: continue
        for p in db.scalars(select(AgentPrinter).where(AgentPrinter.agent_id==agent.id)):
            rows.append(dict(target_agent=agent.agent_uuid,target_printer=p.local_id,station_name=agent.station_name,
                printer_name=p.display_name,available=p.available,online=routing.registry.state(agent)=='online',
                center_id=agent.center_id,papers=p.papers,formats=['plain_text'],execution_mode='safe_validation'))
    response.headers['Cache-Control']='no-store'
    return dict(execution_mode='safe_validation',physical_execution_enabled=False,destinations=rows)


@router.post('')
def create(payload: handlers.Create,user=Depends(current_user),db=Depends(get_db)):
    return handlers.create(payload,user,db,POLICY)


@router.get('/device/poll')
def poll(agent=Depends(device),db=Depends(get_db)):
    return handlers.poll(agent,db,POLICY)


@router.get('/device/{job_id}/delivery')
def delivery(job_id: UUID,agent=Depends(device),db=Depends(get_db)):
    return handlers.redelivery(job_id,agent,db,POLICY)


@router.get('/device/{job_id}/artifact')
def artifact(job_id: UUID,delivery_id: UUID,agent=Depends(device),db=Depends(get_db)):
    return handlers.artifact(job_id,delivery_id,agent,db,POLICY)


@router.post('/device/{job_id}/progress')
def progress(job_id: UUID,payload: handlers.Progress,agent=Depends(device),db=Depends(get_db)):
    return handlers.progress(job_id,payload,agent,db,POLICY)


@router.post('/device/{job_id}/result')
def result(job_id: UUID,payload: handlers.Result,agent=Depends(device),db=Depends(get_db)):
    return handlers.result(job_id,payload,agent,db,POLICY)


@router.get('/{job_id}')
def status(job_id: UUID,user=Depends(current_user),db=Depends(get_db)):
    return handlers.status(job_id,user,db,POLICY)


@router.post('/{job_id}/cancel')
def cancel(job_id: UUID,user=Depends(current_user),db=Depends(get_db)):
    return handlers.cancel(job_id,user,db,POLICY)
