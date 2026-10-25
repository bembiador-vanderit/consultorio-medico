"""Operational follow-up access is not clinical record access."""
from fastapi import HTTPException
from sqlalchemy import select
from app.models import ClinicalHistory,FollowUp,Patient,User
from app.models.cardiology import ClinicalFollowUpPlan
from app.services.administration import effective_permissions
from app.services.appointment_scope import assigned_center_ids,is_role,secretary_can_manage
from app.services.cardiology import ready
from app.services.clinical_access import add_clinical_audit

def permitted(db,user,task):
    if not user.is_active or not {"patients:view","patients:access"}.issubset(effective_permissions(user)): return False
    if task.center_id not in assigned_center_ids(user): return False
    if is_role(user,"doctor") and task.doctor_id==user.id and "clinical:access" in effective_permissions(user): return True
    return is_role(user,"secretary") and secretary_can_manage(user,task.center_id,task.doctor_id,db)

def require_task(db,user,task_id,*,lock=False):
    if not ready(db): raise HTTPException(409,"Seguimiento estructurado pendiente de activación")
    query=select(FollowUp).where(FollowUp.id==task_id)
    task=db.scalar(query.with_for_update() if lock else query)
    plan=db.scalar(select(ClinicalFollowUpPlan).where(ClinicalFollowUpPlan.follow_up_id==task_id))
    if not task or not plan: raise HTTPException(404,"Seguimiento no disponible")
    history=db.get(ClinicalHistory,plan.clinical_history_id)
    if not history or (history.patient_id,history.doctor_id,history.center_id,history.id)!=(task.patient_id,task.doctor_id,task.center_id,task.clinical_history_id):
        raise HTTPException(404,"Contexto de seguimiento no disponible")
    if not permitted(db,user,task): raise HTTPException(403,"No tiene alcance para este seguimiento")
    return task,plan

def view(db,task,plan):
    patient=db.get(Patient,task.patient_id);doctor=db.get(User,task.doctor_id);history=db.get(ClinicalHistory,plan.clinical_history_id)
    return {"id":task.id,"patient_id":task.patient_id,"patient_name":f"{patient.first_name} {patient.last_name}",
        "doctor_id":task.doctor_id,"doctor_name":doctor.full_name,"center_id":task.center_id,"specialty_id":history.specialty_id,
        "due_at":task.due_at,"reason":task.reason,"condition":plan.condition,"status":task.status,
        "timeframe_value":plan.timeframe_value,"timeframe_unit":plan.kind,"appointment_id":plan.scheduled_appointment_id,
        "clinical_history_id":history.id,"revision":plan.revision}

def for_booking(db,user,task_id,payload):
    task,plan=require_task(db,user,task_id,lock=True)
    history=db.get(ClinicalHistory,plan.clinical_history_id)
    if task.status in {"completed","cancelled"} or plan.scheduled_appointment_id:
        raise HTTPException(409,"El seguimiento ya está cerrado o tiene cita de retorno")
    if (payload.patient_id,payload.doctor_id,payload.center_id,payload.specialty_id)!=(task.patient_id,task.doctor_id,task.center_id,history.specialty_id):
        raise HTTPException(422,"La cita de retorno debe conservar paciente, médico, centro y especialidad del seguimiento")
    if payload.status not in {"scheduled","confirmed"}: raise HTTPException(422,"La cita de retorno debe estar programada")
    return task,plan

def link_booking(db,user,task,plan,appointment):
    plan.scheduled_appointment_id=appointment.id;plan.revision+=1;task.status="scheduled"
    add_clinical_audit(db,user,action="follow_up.appointment_linked",resource_type="follow_up",resource_id=task.id,
        history_id=plan.clinical_history_id,context={"appointment_id":appointment.id})
