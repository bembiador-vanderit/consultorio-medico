from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import require_permission
from app.db import get_db
from app.models.clinical_history import ClinicalHistory
from app.models.prescription import Prescription
from app.schemas.prescription import PrescriptionCreate, PrescriptionResponse

router = APIRouter(prefix="/clinical-history/{history_id}/prescriptions", tags=["Recetas"])
access = require_permission("patients:access")


@router.get("", response_model=list[PrescriptionResponse])
def list_prescriptions(history_id: int, _=Depends(access), db: Session = Depends(get_db)):
    if not db.get(ClinicalHistory, history_id):
        raise HTTPException(status_code=404, detail="Registro de historia clínica no encontrado")
    return list(db.scalars(select(Prescription).where(Prescription.clinical_history_id == history_id).order_by(Prescription.id)))


@router.post("", response_model=PrescriptionResponse, status_code=status.HTTP_201_CREATED)
def create_prescription(history_id: int, payload: PrescriptionCreate, _=Depends(access), db: Session = Depends(get_db)):
    if not db.get(ClinicalHistory, history_id):
        raise HTTPException(status_code=404, detail="Registro de historia clínica no encontrado")
    prescription = Prescription(clinical_history_id=history_id, **payload.model_dump())
    db.add(prescription)
    db.commit()
    db.refresh(prescription)
    return prescription


@router.put("/{prescription_id}", response_model=PrescriptionResponse)
def update_prescription(history_id: int, prescription_id: int, payload: PrescriptionCreate, _=Depends(access), db: Session = Depends(get_db)):
    prescription = db.get(Prescription, prescription_id)
    if prescription is None or prescription.clinical_history_id != history_id:
        raise HTTPException(status_code=404, detail="Medicamento no encontrado")
    for field, value in payload.model_dump().items():
        setattr(prescription, field, value)
    db.commit()
    db.refresh(prescription)
    return prescription


@router.delete("/{prescription_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_prescription(history_id: int, prescription_id: int, _=Depends(access), db: Session = Depends(get_db)):
    prescription = db.get(Prescription, prescription_id)
    if prescription is None or prescription.clinical_history_id != history_id:
        raise HTTPException(status_code=404, detail="Medicamento no encontrado")
    db.delete(prescription)
    db.commit()
