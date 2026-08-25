from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import require_permission
from app.db import get_db
from app.models.clinical_history import ClinicalHistory
from app.models.patient import Patient
from app.schemas.clinical_history import ClinicalHistoryCreate, ClinicalHistoryResponse

router = APIRouter(prefix="/clinical-history", tags=["Historia clínica"])
access = require_permission("patients:access")


@router.get("/patients/{patient_id}", response_model=ClinicalHistoryResponse | None)
def get_clinical_history(patient_id: int, _=Depends(access), db: Session = Depends(get_db)):
    if not db.get(Patient, patient_id):
        raise HTTPException(status_code=404, detail="Paciente no encontrado")
    return db.scalar(select(ClinicalHistory).where(ClinicalHistory.patient_id == patient_id))


@router.put("/patients/{patient_id}", response_model=ClinicalHistoryResponse, status_code=status.HTTP_200_OK)
def save_clinical_history(
    patient_id: int,
    payload: ClinicalHistoryCreate,
    _=Depends(access),
    db: Session = Depends(get_db),
):
    if not db.get(Patient, patient_id):
        raise HTTPException(status_code=404, detail="Paciente no encontrado")

    history = db.scalar(select(ClinicalHistory).where(ClinicalHistory.patient_id == patient_id))
    if history is None:
        history = ClinicalHistory(patient_id=patient_id, **payload.model_dump())
        db.add(history)
    else:
        for field, value in payload.model_dump().items():
            setattr(history, field, value)

    db.commit()
    db.refresh(history)
    return history
