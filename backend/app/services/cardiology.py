"""Cardiology composition over the canonical appointment/ClinicalHistory episode."""
from calendar import monthrange
from datetime import datetime, time, timedelta
from fastapi import HTTPException
from sqlalchemy import inspect, select
from app.models import FollowUp, Patient, User
from app.models.cardiology import CardiologyAssessment, ClinicalFollowUpPlan
from app.services.clinical_access import add_clinical_audit
from app.schemas.cardiology import SYMPTOMS, BACKGROUND, EXAM

def ready(db):
    return inspect(db.connection()).has_table("cardiology_assessments")

def is_cardiology(history):
    return bool(history.specialty and history.specialty.code == "cardiology")

def view(row):
    return {"revision":row.revision if row else 0, **{k:getattr(row,k) if row else ({"kind":"none"} if k=="follow_up" else [] if k=="studies" else None if k in {"impression","plan"} else {}) for k in ("symptoms","cardiovascular_history","examination","impression","plan","studies","follow_up")}}

def save(db,user,history,payload):
    if not ready(db): raise HTTPException(409,"Workspace cardiológico pendiente de activación")
    if not is_cardiology(history): raise HTTPException(409,"Esta consulta no corresponde a Cardiología")
    row=db.scalar(select(CardiologyAssessment).where(CardiologyAssessment.clinical_history_id==history.id))
    if payload.expected_revision != (row.revision if row else 0):
        raise HTTPException(409,"La evaluación cardiológica cambió; vuelva a cargarla")
    from app.models import StudyOrder
    for study in payload.studies:
        if study.study_order_id:
            order=db.get(StudyOrder,study.study_order_id)
            if not order or order.clinical_history_id!=history.id: raise HTTPException(422,"El estudio no pertenece a esta consulta")
    if row is None:
        row=CardiologyAssessment(clinical_history_id=history.id,updated_by_user_id=user.id);db.add(row)
    else: row.revision+=1
    for key,value in payload.model_dump(exclude={"expected_revision"},mode="json").items(): setattr(row,key,value)
    row.updated_by_user_id=user.id
    db.flush()
    add_clinical_audit(db,user,action="cardiology.save",resource_type="cardiology_assessment",resource_id=row.id,history_id=history.id,context={"revision":row.revision})
    return row

def complete_follow_up(db,user,history):
    """Called under the history lock, in the same transaction as completion."""
    if not ready(db): return
    row=db.scalar(select(CardiologyAssessment).where(CardiologyAssessment.clinical_history_id==history.id))
    if not row or row.follow_up.get("kind","none")=="none": return
    if db.scalar(select(ClinicalFollowUpPlan.id).where(ClinicalFollowUpPlan.clinical_history_id==history.id)): return
    f=row.follow_up;kind=f["kind"];value=f.get("value");day=history.consultation_date
    if kind=="date": day=datetime.fromisoformat(f["date"]).date()
    elif kind in {"days","weeks"}: day+=timedelta(days=value*(7 if kind=="weeks" else 1))
    elif kind=="months":
        month=day.month-1+value;year=day.year+month//12;month=month%12+1
        day=day.replace(year=year,month=month,day=min(day.day,monthrange(year,month)[1]))
    task=FollowUp(patient_id=history.patient_id,doctor_id=history.doctor_id,center_id=history.center_id,
        clinical_history_id=history.id,due_at=None if kind=="studies" else datetime.combine(day,time()),
        reason=f["reason"],priority="normal",status="pending")
    db.add(task);db.flush()
    db.add(ClinicalFollowUpPlan(follow_up_id=task.id,clinical_history_id=history.id,kind=kind,timeframe_value=value,
        condition=f.get("condition"),created_by_user_id=user.id))
    add_clinical_audit(db,user,action="follow_up.indicated",resource_type="follow_up",resource_id=task.id,history_id=history.id)

def shared_fields(db,history):
    """Projection only; caller must ALREADY have authorized this resource/center."""
    if not ready(db): return []
    row=db.scalar(select(CardiologyAssessment).where(CardiologyAssessment.clinical_history_id==history.id))
    if not row: return []
    fields=[]
    for values,labels,prefix in ((row.symptoms,SYMPTOMS,"Síntoma"),(row.cardiovascular_history,BACKGROUND,"Antecedente")):
        for key,value in values.items():
            present=value.get("present");text="Sí" if present is True else "No" if present is False else "No registrado"
            fields.append({"label":f"{prefix}: {labels.get(key,key)}","value":text+(" · "+value["detail"] if value.get("detail") else "")})
    fields.extend({"label":EXAM.get(k,k),"value":v} for k,v in row.examination.items())
    fields.extend([{"label":"Impresión clínica","value":row.impression},{"label":"Plan","value":row.plan}])
    return fields
