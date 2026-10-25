from datetime import timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import joinedload

from app.api.deps import current_user
from app.db import get_db
from app.models.clinical_audit import ClinicalAuditLog
from app.models.patient_safety import PatientSafetyEntry
from app.schemas.patient_safety import SafetyCreate, SafetyResponse, SafetyUpdate
from app.services import patient_safety as safety
from app.services.administration import effective_permissions

router = APIRouter(prefix="/patient-safety", tags=["Seguridad clínica longitudinal"])


@router.get("/capabilities")
def capabilities(user=Depends(current_user), db=Depends(get_db)):
    # Allows the unchanged official 0057 instance to coexist with staged code.
    permissions = effective_permissions(user)
    enabled = {"patients:view", "clinical:access", safety.VIEW}.issubset(permissions) and any(r.code == "doctor" for r in user.roles) and safety.available(db)
    return {"enabled": enabled, "can_edit": enabled and safety.EDIT in permissions}


@router.get("/patients/{patient_id}", response_model=list[SafetyResponse])
def list_entries(patient_id: int, user=Depends(current_user), db=Depends(get_db)):
    safety.authorize(db, user, patient_id)
    return db.scalars(select(PatientSafetyEntry).options(joinedload(PatientSafetyEntry.recorded_by), joinedload(PatientSafetyEntry.updated_by)).where(PatientSafetyEntry.patient_id == patient_id)
        .order_by(PatientSafetyEntry.recorded_at.desc(), PatientSafetyEntry.id.desc())).all()


@router.post("/patients/{patient_id}", response_model=SafetyResponse, status_code=201)
def create_entry(patient_id: int, payload: SafetyCreate, user=Depends(current_user), db=Depends(get_db)):
    try:
        return safety.create(db, user, patient_id, payload)
    except SQLAlchemyError:
        db.rollback()
        raise HTTPException(500, "No fue posible guardar el registro de seguridad") from None


@router.put("/patients/{patient_id}/entries/{entry_id}", response_model=SafetyResponse)
def update_entry(patient_id: int, entry_id: int, payload: SafetyUpdate, user=Depends(current_user), db=Depends(get_db)):
    try:
        return safety.update(db, user, patient_id, entry_id, payload)
    except SQLAlchemyError:
        db.rollback()
        raise HTTPException(500, "No fue posible guardar el registro de seguridad") from None


@router.get("/patients/{patient_id}/entries/{entry_id}/history")
def history(patient_id: int, entry_id: int, user=Depends(current_user), db=Depends(get_db)):
    safety.authorize(db, user, patient_id)
    safety.get_entry(db, patient_id, entry_id)
    rows = db.scalars(select(ClinicalAuditLog).where(ClinicalAuditLog.resource_type == "patient_safety_entry",
        ClinicalAuditLog.resource_id == entry_id).order_by(ClinicalAuditLog.id)).all()
    # Existing audit storage uses naive UTC; expose an explicit offset rather
    # than letting the browser interpret that value as local wall-clock time.
    return [{"id": row.id, "actor_id": row.user_id, "at": row.created_at.replace(tzinfo=timezone.utc), "action": row.action,
             "context": row.context} for row in rows]
