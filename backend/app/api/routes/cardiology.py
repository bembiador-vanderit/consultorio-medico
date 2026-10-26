from fastapi import APIRouter,Depends,HTTPException
from sqlalchemy import select
from app.api.deps import require_permission
from app.db import get_db
from app.models.cardiology import CardiologyAssessment
from app.schemas.cardiology import CardiologyWrite
from app.services import cardiology
from app.services.clinical_access import require_history_access

router=APIRouter(prefix="/clinical-history",tags=["Consulta cardiológica"])
access=require_permission("clinical:access")

@router.get("/{history_id}/cardiology")
def read_assessment(history_id:int,user=Depends(access),db=Depends(get_db)):
    history=require_history_access(db,user,history_id,action="cardiology.read")
    if not cardiology.ready(db): raise HTTPException(409,"Workspace cardiológico pendiente de activación")
    if not cardiology.is_cardiology(history): raise HTTPException(409,"Esta consulta no corresponde a Cardiología")
    row=db.scalar(select(CardiologyAssessment).where(CardiologyAssessment.clinical_history_id==history_id))
    return cardiology.view(row)

@router.put("/{history_id}/cardiology")
def save_assessment(history_id:int,payload:CardiologyWrite,user=Depends(access),db=Depends(get_db)):
    history=require_history_access(db,user,history_id,action="cardiology.save",write=True)
    row=cardiology.save(db,user,history,payload)
    db.commit();db.refresh(row)
    return cardiology.view(row)
