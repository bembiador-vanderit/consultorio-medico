from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session
from app.api.deps import require_permission
from app.db import get_db
from app.models.patient import Patient
from app.schemas.patient import PatientCreate, PatientResponse, PatientUpdate

router = APIRouter(prefix="/patients", tags=["Pacientes"])
access = require_permission("patients:access")

@router.get("/count")
def count_patients(_=Depends(access), db: Session = Depends(get_db)):
    return {"count": db.scalar(select(func.count()).select_from(Patient)) or 0}

@router.get("", response_model=list[PatientResponse])
def list_patients(query: str | None = None, offset: int = Query(0, ge=0), limit: int = Query(25, ge=1, le=100), _=Depends(access), db: Session = Depends(get_db)):
    statement = select(Patient).order_by(Patient.last_name, Patient.first_name).offset(offset).limit(limit)
    if query:
        term = f"%{query.strip()}%"
        statement = statement.where(or_(Patient.first_name.ilike(term), Patient.last_name.ilike(term), Patient.phone.ilike(term)))
    return db.scalars(statement).all()

@router.post("", response_model=PatientResponse, status_code=status.HTTP_201_CREATED)
def create_patient(payload: PatientCreate, _=Depends(access), db: Session = Depends(get_db)):
    patient = Patient(**payload.model_dump()); db.add(patient); db.commit(); db.refresh(patient); return patient

@router.get("/{patient_id}", response_model=PatientResponse)
def get_patient(patient_id: int, _=Depends(access), db: Session = Depends(get_db)):
    patient = db.get(Patient, patient_id)
    if not patient: raise HTTPException(status_code=404, detail="Paciente no encontrado")
    return patient

@router.put("/{patient_id}", response_model=PatientResponse)
def update_patient(patient_id: int, payload: PatientUpdate, _=Depends(access), db: Session = Depends(get_db)):
    patient = db.get(Patient, patient_id)
    if not patient: raise HTTPException(status_code=404, detail="Paciente no encontrado")
    for field, value in payload.model_dump().items(): setattr(patient, field, value)
    db.commit(); db.refresh(patient); return patient
