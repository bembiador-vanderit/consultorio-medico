from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.api.deps import require_permission
from app.db import get_db
from app.models.clinical_history import ClinicalHistory
from app.models.diagnosis import Diagnosis
from app.schemas.diagnosis import DiagnosisCreate, DiagnosisResponse

router = APIRouter(prefix="/clinical-history/{history_id}/diagnoses", tags=["Diagnósticos"])
access = require_permission("patients:access")


@router.get("", response_model=list[DiagnosisResponse])
def list_diagnoses(history_id: int, _=Depends(access), db: Session = Depends(get_db)):
    if not db.get(ClinicalHistory, history_id):
        raise HTTPException(status_code=404, detail="Registro de historia clínica no encontrado")
    return list(db.scalars(select(Diagnosis).where(Diagnosis.clinical_history_id == history_id).order_by(Diagnosis.is_primary.desc(), Diagnosis.id)))


@router.post("", response_model=DiagnosisResponse, status_code=status.HTTP_201_CREATED)
def create_diagnosis(history_id: int, payload: DiagnosisCreate, _=Depends(access), db: Session = Depends(get_db)):
    if not db.get(ClinicalHistory, history_id):
        raise HTTPException(status_code=404, detail="Registro de historia clínica no encontrado")

    if payload.is_primary:
        db.execute(update(Diagnosis).where(Diagnosis.clinical_history_id == history_id).values(is_primary=False))

    diagnosis = Diagnosis(clinical_history_id=history_id, **payload.model_dump())
    db.add(diagnosis)
    db.commit()
    db.refresh(diagnosis)
    return diagnosis


@router.put("/{diagnosis_id}", response_model=DiagnosisResponse)
def update_diagnosis(history_id: int, diagnosis_id: int, payload: DiagnosisCreate, _=Depends(access), db: Session = Depends(get_db)):
    diagnosis = db.get(Diagnosis, diagnosis_id)
    if diagnosis is None or diagnosis.clinical_history_id != history_id:
        raise HTTPException(status_code=404, detail="Diagnóstico no encontrado")

    if payload.is_primary:
        db.execute(
            update(Diagnosis)
            .where(Diagnosis.clinical_history_id == history_id, Diagnosis.id != diagnosis_id)
            .values(is_primary=False)
        )

    for field, value in payload.model_dump().items():
        setattr(diagnosis, field, value)
    db.commit()
    db.refresh(diagnosis)
    return diagnosis


@router.delete("/{diagnosis_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_diagnosis(history_id: int, diagnosis_id: int, _=Depends(access), db: Session = Depends(get_db)):
    diagnosis = db.get(Diagnosis, diagnosis_id)
    if diagnosis is None or diagnosis.clinical_history_id != history_id:
        raise HTTPException(status_code=404, detail="Diagnóstico no encontrado")
    db.delete(diagnosis)
    db.commit()
