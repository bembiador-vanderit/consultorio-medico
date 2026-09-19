from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, or_, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.api.deps import require_permission
from app.db import get_db
from app.models.insurance import InsuranceCompany, PatientInsurance
from app.models.patient import Patient
from app.schemas.patient import PatientCreate, PatientCreatedResponse, PatientIdentityResponse, PatientResponse, PatientUpdate
from app.services.patient_scope import (
    identity_matches,
    issue_patient_selection_token,
    mask_email,
    mask_phone,
    require_patient_identity_access,
    require_available_identity,
    scope_patient_identities,
    validate_identity_search_context,
)

router = APIRouter(prefix="/patients", tags=["Pacientes"])
access = require_permission("patients:access")


@router.get("/count")
def count_patients(user=Depends(access), db: Session = Depends(get_db)):
    query = scope_patient_identities(select(func.count()).select_from(Patient), user, db)
    return {"count": db.scalar(query) or 0}


@router.get("", response_model=list[PatientResponse])
def list_patients(
    query: str | None = None,
    offset: int = Query(0, ge=0),
    limit: int = Query(25, ge=1, le=100),
    user=Depends(access),
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
    statement = scope_patient_identities(statement, user, db)
    return db.scalars(statement).all()


@router.get("/identity-search", response_model=list[PatientIdentityResponse])
def search_patient_identity(
    date_of_birth: date,
    phone: str | None = None,
    email: str | None = None,
    center_id: int | None = None,
    doctor_id: int | None = None,
    user=Depends(access),
    db: Session = Depends(get_db),
):
    validate_identity_search_context(db, user, center_id=center_id, doctor_id=doctor_id)
    return [
        PatientIdentityResponse(
            id=patient.id,
            first_name=patient.first_name,
            last_name=patient.last_name,
            date_of_birth=patient.date_of_birth,
            phone_masked=mask_phone(patient.phone),
            email_masked=mask_email(patient.email),
            selection_token=issue_patient_selection_token(
                user, patient.id, center_id=center_id,
                doctor_id=doctor_id if doctor_id is not None else (user.id if any(role.code == "doctor" for role in user.roles) else None),
            ),
        )
        for patient in identity_matches(db, date_of_birth=date_of_birth, phone=phone, email=email)
    ]


def _validate_insurance(payload, db: Session) -> InsuranceCompany:
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


@router.post("", response_model=PatientCreatedResponse, status_code=status.HTTP_201_CREATED)
def create_patient(payload: PatientCreate, user=Depends(access), db: Session = Depends(get_db)):
    require_available_identity(db, date_of_birth=payload.date_of_birth, phone=payload.phone, email=payload.email)
    if payload.has_insurance:
        _validate_insurance(payload, db)
    patient_data = payload.model_dump(exclude={"has_insurance", "insurance"})
    patient = Patient(**patient_data)
    try:
        db.add(patient)
        db.flush()
        _add_insurance(patient, payload, db)
        proof = issue_patient_selection_token(user, patient.id)
        db.commit()
        db.refresh(patient)
    except SQLAlchemyError:
        db.rollback()
        raise HTTPException(status_code=500, detail="No fue posible guardar el paciente")
    return PatientCreatedResponse(**PatientResponse.model_validate(patient).model_dump(), selection_token=proof)


@router.get("/{patient_id}", response_model=PatientResponse)
def get_patient(patient_id: int, user=Depends(access), db: Session = Depends(get_db)):
    return require_patient_identity_access(db, user, patient_id)


@router.put("/{patient_id}", response_model=PatientResponse)
def update_patient(patient_id: int, payload: PatientUpdate, user=Depends(access), db: Session = Depends(get_db)):
    patient = require_patient_identity_access(db, user, patient_id)
    patient = db.scalar(select(Patient).where(Patient.id == patient_id).with_for_update().execution_options(populate_existing=True))

    identity_before = (patient.date_of_birth, patient.phone, (patient.email or "").strip().lower() or None)
    identity_after = (payload.date_of_birth, payload.phone, str(payload.email).lower() if payload.email else None)
    if identity_before != identity_after:
        require_available_identity(db, date_of_birth=payload.date_of_birth, phone=payload.phone, email=payload.email, exclude_patient_id=patient_id)

    # Omission preserves affiliations. Explicit false is the existing opt-out;
    # an insurance object alone is an update. true + null remains a no-op for
    # PatientForm, which sends that pair when the insurance did not change.
    deactivate_insurance = "has_insurance" in payload.model_fields_set and payload.has_insurance is False
    if deactivate_insurance and payload.insurance is not None:
        raise HTTPException(status_code=422, detail="No puede registrar un seguro y desactivarlo en la misma actualización")
    company = _validate_insurance(payload, db) if payload.insurance is not None else None

    patient_data = payload.model_dump(exclude={"has_insurance", "insurance"})
    for field, value in patient_data.items():
        setattr(patient, field, value)

    if company is not None:
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
        db.add(PatientInsurance(
            patient_id=patient_id, insurance_company_id=company.id,
            member_number=insurance.member_number.strip(),
            plan_name=insurance.plan_name.strip() if insurance.plan_name else None,
            is_primary=insurance.is_primary, is_active=True,
        ))
    elif deactivate_insurance:
        active_items = db.scalars(
            select(PatientInsurance).where(
                PatientInsurance.patient_id == patient_id,
                PatientInsurance.is_active.is_(True),
            )
        ).all()
        for item in active_items:
            item.is_active = False
            item.is_primary = False

    try:
        db.commit()
        db.refresh(patient)
    except SQLAlchemyError:
        db.rollback()
        raise HTTPException(status_code=500, detail="No fue posible guardar el paciente")
    return patient
