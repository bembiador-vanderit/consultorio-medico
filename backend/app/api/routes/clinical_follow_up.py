from datetime import datetime
from fastapi import APIRouter,Depends,HTTPException
from sqlalchemy import select
from app.api.deps import require_permission
from app.db import get_db
from app.models import ClinicalHistory,FollowUp
from app.models.cardiology import ClinicalFollowUpPlan,FollowUpContactAttempt
from app.schemas.cardiology import FollowUpContactWrite
from app.services import clinical_follow_up as service
from app.services.cardiology import ready
from app.services.appointment_scope import is_role
from app.services.clinical_access import add_clinical_audit

router=APIRouter(prefix="/follow-ups",tags=["Seguimiento operativo"])
access=require_permission("patients:access")

@router.get("/inbox")
def inbox(status:str|None=None,user=Depends(access),db=Depends(get_db)):
    if not ready(db): return {"enabled":False,"items":[]}
    if not (is_role(user,"doctor") or is_role(user,"secretary")): raise HTTPException(403,"No tiene acceso a seguimientos")
    rows=db.execute(select(FollowUp,ClinicalFollowUpPlan).join(ClinicalFollowUpPlan,ClinicalFollowUpPlan.follow_up_id==FollowUp.id).order_by(FollowUp.due_at,FollowUp.id)).all()
    return {"enabled":True,"items":[service.view(db,t,p) for t,p in rows if service.permitted(db,user,t) and (status is None or t.status==status)]}

@router.get("/operational/{task_id}/contacts")
def contacts(task_id:int,user=Depends(access),db=Depends(get_db)):
    service.require_task(db,user,task_id)
    return [{"id":r.id,"result":r.result,"note":r.note,"actor_id":r.recorded_by_user_id,"created_at":r.created_at} for r in db.scalars(select(FollowUpContactAttempt).where(FollowUpContactAttempt.follow_up_id==task_id).order_by(FollowUpContactAttempt.id))]

@router.post("/operational/{task_id}/contacts",status_code=201)
def record_contact(task_id:int,payload:FollowUpContactWrite,user=Depends(access),db=Depends(get_db)):
    task,plan=service.require_task(db,user,task_id,lock=True)
    if task.status in {"completed","cancelled"}: raise HTTPException(409,"El seguimiento está cerrado")
    if payload.result=="scheduled" and not plan.scheduled_appointment_id: raise HTTPException(409,"Primero registre la cita de retorno desde Agenda")
    row=FollowUpContactAttempt(follow_up_id=task.id,recorded_by_user_id=user.id,**payload.model_dump());db.add(row);db.flush()
    if payload.result=="declined": task.status="cancelled"
    elif payload.result in {"contacted","studies_ready","studies_pending"} and task.status!="scheduled": task.status="contacted"
    plan.revision+=1
    add_clinical_audit(db,user,action="follow_up.contact",resource_type="follow_up_contact",resource_id=row.id,history_id=plan.clinical_history_id,context={"follow_up_id":task.id,"result":row.result})
    db.commit()
    return {"id":row.id,"status":task.status}

@router.post("/operational/{task_id}/complete")
def complete(task_id:int,user=Depends(require_permission("clinical:access")),db=Depends(get_db)):
    task,plan=service.require_task(db,user,task_id,lock=True)
    if not is_role(user,"doctor") or user.id!=task.doctor_id: raise HTTPException(403,"Solo el médico responsable puede cerrar el seguimiento")
    returned=db.scalar(select(ClinicalHistory).where(ClinicalHistory.appointment_id==plan.scheduled_appointment_id)) if plan.scheduled_appointment_id else None
    if not returned or returned.status!="completed" or (returned.patient_id,returned.doctor_id,returned.center_id)!=(task.patient_id,task.doctor_id,task.center_id):
        raise HTTPException(409,"Complete primero la consulta de retorno vinculada")
    if task.status!="completed":
        task.status="completed";task.completed_at=datetime.utcnow();plan.revision+=1
        add_clinical_audit(db,user,action="follow_up.completed",resource_type="follow_up",resource_id=task.id,history_id=plan.clinical_history_id,context={"return_history_id":returned.id})
        db.commit()
    return service.view(db,task,plan)
