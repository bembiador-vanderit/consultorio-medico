from datetime import timezone

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError

from app.api.deps import current_user
from app.db import get_db
from app.models.clinical_audit import ClinicalAuditLog
from app.schemas.patient_care import RelationshipCreate, RelationshipResponse, RelationshipStatus, RelationshipUpdate
from app.services import patient_care as care

router = APIRouter(prefix="/patient-care", tags=["Relaciones asistenciales longitudinales"])


@router.get("/capabilities")
def capabilities(user=Depends(current_user), db=Depends(get_db)):
    enabled = care.permitted(user) and db.info.get("access_scope") != "platform" and care.available(db)
    return {"enabled":enabled,"can_manage":enabled and care.permitted(user,manage=True)}


@router.get("/patients/{patient_id}/relationships", response_model=list[RelationshipResponse])
def related(patient_id:int,user=Depends(current_user),db=Depends(get_db)):
    return care.list_related(db,user,patient_id)


@router.post("/patients/{patient_id}/relationships", response_model=RelationshipResponse)
def assign(patient_id:int,payload:RelationshipCreate,response:Response,user=Depends(current_user),db=Depends(get_db)):
    try:
        row,created = care.assign(db,user,patient_id,payload)
        response.status_code = 201 if created else 200
        return row
    except SQLAlchemyError:
        db.rollback()
        raise HTTPException(500,"No fue posible guardar la relación asistencial") from None


@router.put("/patients/{patient_id}/relationships/{relationship_id}", response_model=RelationshipResponse)
def update(patient_id:int,relationship_id:int,payload:RelationshipUpdate,user=Depends(current_user),db=Depends(get_db)):
    try:
        return care.update(db,user,patient_id,relationship_id,payload)
    except SQLAlchemyError:
        db.rollback()
        raise HTTPException(500,"No fue posible guardar la relación asistencial") from None


@router.get("/patients/{patient_id}/relationships/{relationship_id}/history")
def history(patient_id:int,relationship_id:int,user=Depends(current_user),db=Depends(get_db)):
    care.authorize(db,user,patient_id)
    care.entry(db,patient_id,relationship_id)
    rows = db.scalars(select(ClinicalAuditLog).where(ClinicalAuditLog.resource_type=="patient_care_relationship",
        ClinicalAuditLog.resource_id==relationship_id).order_by(ClinicalAuditLog.id)).all()
    return [{"id":row.id,"actor_id":row.user_id,"at":row.created_at.replace(tzinfo=timezone.utc),
             "action":row.action,"context":row.context} for row in rows]


@router.get("/my-patients")
def mine(status:RelationshipStatus|None=None,center_id:int|None=Query(default=None,gt=0),
         limit:int=Query(default=50,ge=1,le=200),offset:int=Query(default=0,ge=0),user=Depends(current_user),db=Depends(get_db)):
    return [{"relationship":RelationshipResponse.model_validate(row).model_dump(),
             "patient":{"id":row.patient_id,"name":f"{first} {last}"},
             "clinical_access_granted":False} for row,first,last in care.my_patients(db,user,status=status,center_id=center_id,limit=limit,offset=offset)]
