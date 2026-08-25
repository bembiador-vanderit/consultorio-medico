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


@router.get("/patients/{patient_id}", response_model=list[ClinicalHistoryResponse])
def get_clinical_history(patient_id: int, _=Depends(access), db: Session = Depends(get_db)):
    if not db.get(Patient, patient_id):
        raise HTTPException(status_code=404, detail="Paciente no encontrado")

    return list(
        db.scalars(
            select(ClinicalHistory)
            .where(ClinicalHistory.patient_id == patient_id)
            .order_by(ClinicalHistory.consultation_date.desc(), ClinicalHistory.id.desc())
        )
    )


@router.post("/patients/{patient_id}", response_model=ClinicalHistoryResponse, status_code=status.HTTP_201_CREATED)
def create_clinical_history(
    patient_id: int,
    payload: ClinicalHistoryCreate,
    _=Depends(access),
    db: Session = Depends(get_db),
):
    if not db.get(Patient, patient_id):
        raise HTTPException(status_code=404, detail="Paciente no encontrado")

    history = ClinicalHistory(patient_id=patient_id, **payload.model_dump())
    db.add(history)
    db.commit()
    db.refresh(history)
    return history


@router.put("/{history_id}", response_model=ClinicalHistoryResponse)
def update_clinical_history(
    history_id: int,
    payload: ClinicalHistoryCreate,
    _=Depends(access),
    db: Session = Depends(get_db),
):
    history = db.get(ClinicalHistory, history_id)
    if history is None:
        raise HTTPException(status_code=404, detail="Registro de historia clínica no encontrado")

    for field, value in payload.model_dump().items():
        setattr(history, field, value)

    db.commit()
    db.refresh(history)
    return history
