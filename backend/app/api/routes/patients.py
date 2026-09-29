from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, or_, select
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session

from app.api.deps import require_permission
from app.db import get_db
from app.models.insurance import InsuranceCompany, PatientInsurance
from app.models.patient import Patient
from app.models.locality import Locality
from app.models.regional import Country, TerritorialLevel, TerritorialUnit
from app.schemas.center import LocalityResponse
from app.services.administration import effective_permissions
from app.services.insurance import save_insurance, record
from app.services.patient_demographics import normalize_document
from app.schemas.patient import PatientCreate, PatientCreatedResponse, PatientDetailResponse, PatientIdentityResponse, PatientResponse, PatientUpdate
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
                Patient.home_phone.ilike(term),
                Patient.document_number == normalize_document(query),
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


@router.get("/localities", response_model=list[LocalityResponse])
def patient_localities(user=Depends(access), db: Session = Depends(get_db)):
    return db.scalars(select(Locality).where(Locality.is_active.is_(True)).order_by(Locality.name)).all()


def _validate_demographics(payload, db: Session, patient: Patient | None = None):
    if payload.locality_id is not None and (patient is None or patient.locality_id != payload.locality_id):
        locality = db.get(Locality, payload.locality_id)
        if locality is None or not locality.is_active:
            raise HTTPException(status_code=422, detail="Localidad inválida")

    if payload.country_code is not None:
        country = db.get(Country, payload.country_code.upper())
        if country is None or not country.is_active:
            raise HTTPException(status_code=422, detail="País de residencia inválido")

    if payload.territorial_unit_id is not None:
        unit = db.get(TerritorialUnit, payload.territorial_unit_id)
        if unit is None or not unit.is_active or unit.country_code != (payload.country_code or "").upper():
            raise HTTPException(status_code=422, detail="Territorio incompatible con el país")

        required_position = db.scalar(
            select(TerritorialLevel.position)
            .where(
                TerritorialLevel.country_code == unit.country_code,
                TerritorialLevel.is_active.is_(True),
                TerritorialLevel.is_required.is_(True),
            )
            .order_by(TerritorialLevel.position.desc())
            .limit(1)
        )
        if required_position is not None and unit.level.position != required_position:
            raise HTTPException(status_code=422, detail="Seleccione el nivel territorial requerido más específico")

        expected_position = unit.level.position
        ancestor = unit
        while ancestor is not None:
            if not ancestor.is_active or ancestor.country_code != unit.country_code or ancestor.level.position != expected_position:
                raise HTTPException(status_code=422, detail="Jerarquía territorial inválida")
            expected_position -= 1
            ancestor = ancestor.parent
        if expected_position != 0:
            raise HTTPException(status_code=422, detail="Jerarquía territorial inválida")

    if payload.document_number:
        query = select(Patient.id).where(Patient.document_type == payload.document_type, Patient.document_number == payload.document_number)
        if patient is not None:
            query = query.where(Patient.id != patient.id)
        if db.scalar(query.limit(1)) is not None:
            raise HTTPException(status_code=409, detail="Ya existe un paciente con ese documento")


def _integrity_failure(db: Session, error: IntegrityError):
    db.rollback()
    constraint = getattr(getattr(error.orig, "diag", None), "constraint_name", None)
    if constraint == "uq_patients_document" or "UNIQUE constraint failed: patients.document_type, patients.document_number" in str(error.orig):
        raise HTTPException(status_code=409, detail="Ya existe un paciente con ese documento") from None
    raise HTTPException(status_code=500, detail="No fue posible guardar el paciente") from None


def _validate_insurance(payload, db: Session) -> InsuranceCompany:
    if not payload.insurance:
        raise HTTPException(status_code=422, detail="Debe seleccionar una ARS y registrar el número de afiliado")
    company = db.get(InsuranceCompany, payload.insurance.insurance_company_id)
    if not company or not company.is_active:
        raise HTTPException(status_code=422, detail="Compañía de seguros inválida")
    return company


def _require_insurance_write(user):
    if "insurance:manage" not in effective_permissions(user):
        raise HTTPException(403, "No tiene permiso para gestionar seguros")


def _add_insurance(patient: Patient, payload, db: Session, user) -> None:
    if payload.has_insurance:
        save_insurance(db, user, patient.id, payload.insurance, commit=False, check_access=False)


@router.post("", response_model=PatientCreatedResponse, status_code=status.HTTP_201_CREATED)
def create_patient(payload: PatientCreate, user=Depends(access), db: Session = Depends(get_db)):
    require_available_identity(db, date_of_birth=payload.date_of_birth, phone=payload.phone, email=payload.email)
    _validate_demographics(payload, db)
    if payload.has_insurance:
        _require_insurance_write(user)
        _validate_insurance(payload, db)
    patient_data = payload.model_dump(exclude={"has_insurance", "insurance"})
    patient = Patient(**patient_data)
    try:
        db.add(patient)
        db.flush()
        _add_insurance(patient, payload, db, user)
        proof = issue_patient_selection_token(user, patient.id)
        db.commit()
        db.refresh(patient)
    except IntegrityError as error:
        _integrity_failure(db, error)
    except SQLAlchemyError:
        db.rollback()
        raise HTTPException(status_code=500, detail="No fue posible guardar el paciente")
    return PatientCreatedResponse(**PatientDetailResponse.model_validate(patient).model_dump(), selection_token=proof)


@router.get("/{patient_id}", response_model=PatientDetailResponse)
def get_patient(patient_id: int, user=Depends(access), db: Session = Depends(get_db)):
    return require_patient_identity_access(db, user, patient_id)


@router.put("/{patient_id}", response_model=PatientDetailResponse)
def update_patient(patient_id: int, payload: PatientUpdate, user=Depends(access), db: Session = Depends(get_db)):
    patient = require_patient_identity_access(db, user, patient_id)
    patient = db.scalar(select(Patient).where(Patient.id == patient_id).with_for_update().execution_options(populate_existing=True))

    _validate_demographics(payload, db, patient)

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
    if payload.insurance is not None or (deactivate_insurance and db.scalar(select(PatientInsurance.id).where(PatientInsurance.patient_id == patient_id, PatientInsurance.is_active.is_(True)).limit(1))):
        _require_insurance_write(user)
    company = _validate_insurance(payload, db) if payload.insurance is not None else None

    patient_data = payload.model_dump(exclude={"has_insurance", "insurance"})
    legacy_fields = {"first_name", "last_name", "date_of_birth", "phone", "email"}
    patient_data = {key: value for key, value in patient_data.items() if key in legacy_fields or key in payload.model_fields_set}
    # Clearing the pair through a single explicit null clears both safely.
    if {"document_type", "document_number"} & payload.model_fields_set:
        patient_data.update(document_type=payload.document_type, document_number=payload.document_number)
    if company is not None:
        save_insurance(db, user, patient_id, payload.insurance, commit=False, check_access=False)
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
            record(db, user, "patient_deactivated", item.id)

    for field, value in patient_data.items():
        setattr(patient, field, value)

    try:
        db.commit()
        db.refresh(patient)
    except IntegrityError as error:
        _integrity_failure(db, error)
    except SQLAlchemyError:
        db.rollback()
        raise HTTPException(status_code=500, detail="No fue posible guardar el paciente")
    return patient
