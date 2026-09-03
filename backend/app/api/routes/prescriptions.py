from io import BytesIO

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import require_permission
from app.db import get_db
from app.models.center import CareCenter
from app.models.clinical_history import ClinicalHistory
from app.models.identity import User
from app.models.patient import Patient
from app.models.prescription import Prescription
from app.schemas.prescription import PrescriptionCreate, PrescriptionResponse
from app.services.clinical_documents import PrescriptionLine, build_prescription_pdf

router = APIRouter(prefix="/clinical-history/{history_id}/prescriptions", tags=["Recetas"])
access = require_permission("clinical:access")


@router.get("", response_model=list[PrescriptionResponse])
def list_prescriptions(history_id: int, _=Depends(access), db: Session = Depends(get_db)):
    if not db.get(ClinicalHistory, history_id):
        raise HTTPException(status_code=404, detail="Registro de historia clínica no encontrado")
    return list(db.scalars(select(Prescription).where(Prescription.clinical_history_id == history_id).order_by(Prescription.id)))


@router.get("/pdf")
def get_prescription_pdf(history_id: int, _=Depends(access), db: Session = Depends(get_db)):
    history = db.get(ClinicalHistory, history_id)
    if history is None:
        raise HTTPException(status_code=404, detail="Registro de historia clínica no encontrado")

    prescriptions = list(
        db.scalars(
            select(Prescription)
            .where(Prescription.clinical_history_id == history_id)
            .order_by(Prescription.id)
        )
    )
    if not prescriptions:
        raise HTTPException(status_code=422, detail="La consulta no tiene medicamentos recetados")

    patient = db.get(Patient, history.patient_id)
    doctor = db.get(User, history.doctor_id) if history.doctor_id is not None else None
    center = db.get(CareCenter, history.center_id) if history.center_id is not None else None
    if patient is None:
        raise HTTPException(status_code=404, detail="Paciente no encontrado")

    content = build_prescription_pdf(
        history_id=history.id,
        consultation_date=history.consultation_date,
        patient_name=f"{patient.first_name} {patient.last_name}",
        doctor_name=doctor.full_name if doctor else "Médico no especificado",
        center_name=center.name if center else None,
        center_address=(
            ", ".join(part for part in (center.address, center.city) if part)
            if center
            else None
        ),
        prescription_lines=[
            PrescriptionLine(
                medication=item.medication,
                presentation=item.presentation,
                dose=item.dose,
                route=item.route,
                frequency=item.frequency,
                duration=item.duration,
                quantity=item.quantity,
                instructions=item.instructions,
            )
            for item in prescriptions
        ],
    )
    filename = f"receta-{history.id}.pdf"
    return StreamingResponse(
        BytesIO(content),
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


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
