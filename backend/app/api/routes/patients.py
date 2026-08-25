from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.api.deps import require_permission
from app.db import get_db
from app.models.insurance import InsuranceCompany, PatientInsurance
from app.models.patient import Patient
from app.schemas.patient import PatientCreate, PatientResponse, PatientUpdate

router = APIRouter(prefix="/patients", tags=["Pacientes"])
access = require_permission("patients:access")


@router.get("/count")
def count_patients(_=Depends(access), db: Session = Depends(get_db)):
    return {"count": db.scalar(select(func.count()).select_from(Patient)) or 0}


@router.get("", response_model=list[PatientResponse])
def list_patients(
    query: str | None = None,
    offset: int = Query(0, ge=0),
    limit: int = Query(25, ge=1, le=100),
    _=Depends(access),
    db: Session = Depends(get_db),
):
    statement = select(Patient).order_by(Patient.last_name, Patient.first_name).offset(offset).limit(limit)
    if query:
        term = f"%{query.strip()}%"
        statement = statement.where(
            or_(
                Patient.first_name.ilike(term),
                Patient.last_name.ilike(term),
                Patient.phone.ilike(term),
            )
        )
    return db.scalars(statement).all()


def _validate_insurance(payload, db: Session) -> InsuranceCompany:
    if not payload.has_insurance:
        return None
    if not payload.insurance:
        raise HTTPException(status_code=422, detail="Debe seleccionar una ARS y registrar el número de afiliado")
    company = db.get(InsuranceCompany, payload.insurance.insurance_company_id)
    if not company or not company.is_active:
        raise HTTPException(status_code=422, detail="Compañía de seguros inválida")
    return company


def _add_insurance(patient: Patient, payload, db: Session) -> None:
    if not payload.has_insurance:
        return
    company = _validate_insurance(payload, db)
    insurance = payload.insurance
    item = PatientInsurance(
        patient_id=patient.id,
        insurance_company_id=company.id,
        member_number=insurance.member_number.strip(),
        plan_name=insurance.plan_name.strip() if insurance.plan_name else None,
        is_primary=insurance.is_primary,
        is_active=True,
    )
    db.add(item)


@router.post("", response_model=PatientResponse, status_code=status.HTTP_201_CREATED)
def create_patient(payload: PatientCreate, _=Depends(access), db: Session = Depends(get_db)):
    patient_data = payload.model_dump(exclude={"has_insurance", "insurance"})
    patient = Patient(**patient_data)
    db.add(patient)
    db.flush()
    _add_insurance(patient, payload, db)
    db.commit()
    db.refresh(patient)
    return patient


@router.get("/{patient_id}", response_model=PatientResponse)
def get_patient(patient_id: int, _=Depends(access), db: Session = Depends(get_db)):
    patient = db.get(Patient, patient_id)
    if not patient:
        raise HTTPException(status_code=404, detail="Paciente no encontrado")
    return patient


@router.put("/{patient_id}", response_model=PatientResponse)
def update_patient(patient_id: int, payload: PatientUpdate, _=Depends(access), db: Session = Depends(get_db)):
    patient = db.get(Patient, patient_id)
    if not patient:
        raise HTTPException(status_code=404, detail="Paciente no encontrado")

    patient_data = payload.model_dump(exclude={"has_insurance", "insurance"})
    for field, value in patient_data.items():
        setattr(patient, field, value)

    if payload.has_insurance:
        if payload.insurance:
            company = _validate_insurance(payload, db)
            active_primary = db.scalars(
                select(PatientInsurance).where(
                    PatientInsurance.patient_id == patient_id,
                    PatientInsurance.is_primary.is_(True),
                    PatientInsurance.is_active.is_(True),
                )
            ).all()
            for item in active_primary:
                item.is_primary = False
            insurance = payload.insurance
            db.add(
                PatientInsurance(
                    patient_id=patient_id,
                    insurance_company_id=company.id,
                    member_number=insurance.member_number.strip(),
                    plan_name=insurance.plan_name.strip() if insurance.plan_name else None,
                    is_primary=insurance.is_primary,
                    is_active=True,
                )
            )
    else:
        active_items = db.scalars(
            select(PatientInsurance).where(
                PatientInsurance.patient_id == patient_id,
                PatientInsurance.is_active.is_(True),
            )
        ).all()
        for item in active_items:
            item.is_active = False
            item.is_primary = False

    db.commit()
    db.refresh(patient)
    return patient
