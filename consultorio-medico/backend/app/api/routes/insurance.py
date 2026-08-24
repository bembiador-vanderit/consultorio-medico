from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import require_permission
from app.db import get_db
from app.models import InsuranceCompany, Patient, PatientInsurance, User
from app.schemas.insurance import (
    InsuranceCompanyCreate,
    InsuranceCompanyResponse,
    PatientInsuranceCreate,
    PatientInsuranceResponse,
)

router = APIRouter(prefix="/insurance", tags=["Seguros médicos"])


def serialize_patient_insurance(item: PatientInsurance) -> PatientInsuranceResponse:
    return PatientInsuranceResponse(
        id=item.id,
        insurance_company_id=item.insurance_company_id,
        insurance_company_name=item.insurance_company.name,
        member_number=item.member_number,
        plan_name=item.plan_name,
        is_primary=item.is_primary,
        is_active=item.is_active,
        created_at=item.created_at,
    )


@router.get(
    "/companies",
    response_model=list[InsuranceCompanyResponse],
)
def list_companies(
    _: User = Depends(require_permission("patients:access")),
    db: Session = Depends(get_db),
):
    return db.scalars(
        select(InsuranceCompany)
        .where(InsuranceCompany.is_active.is_(True))
        .order_by(InsuranceCompany.name)
    ).all()


@router.post(
    "/companies",
    response_model=InsuranceCompanyResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_company(
    payload: InsuranceCompanyCreate,
    _: User = Depends(require_permission("users:manage")),
    db: Session = Depends(get_db),
):
    name = payload.name.strip()
    code = payload.code.strip() if payload.code else None

    if db.scalar(select(InsuranceCompany).where(InsuranceCompany.name == name)):
        raise HTTPException(status_code=409, detail="La compañía de seguros ya existe")
    if code and db.scalar(select(InsuranceCompany).where(InsuranceCompany.code == code)):
        raise HTTPException(status_code=409, detail="El código del seguro ya existe")

    company = InsuranceCompany(name=name, code=code)
    db.add(company)
    db.commit()
    db.refresh(company)
    return company


@router.get(
    "/patients/{patient_id}",
    response_model=list[PatientInsuranceResponse],
)
def list_patient_insurances(
    patient_id: int,
    _: User = Depends(require_permission("patients:access")),
    db: Session = Depends(get_db),
):
    if not db.get(Patient, patient_id):
        raise HTTPException(status_code=404, detail="Paciente no encontrado")

    items = db.scalars(
        select(PatientInsurance)
        .where(PatientInsurance.patient_id == patient_id)
        .order_by(PatientInsurance.is_primary.desc(), PatientInsurance.created_at.desc())
    ).all()
    return [serialize_patient_insurance(item) for item in items]


@router.post(
    "/patients/{patient_id}",
    response_model=PatientInsuranceResponse,
    status_code=status.HTTP_201_CREATED,
)
def add_patient_insurance(
    patient_id: int,
    payload: PatientInsuranceCreate,
    _: User = Depends(require_permission("patients:access")),
    db: Session = Depends(get_db),
):
    if not db.get(Patient, patient_id):
        raise HTTPException(status_code=404, detail="Paciente no encontrado")

    company = db.get(InsuranceCompany, payload.insurance_company_id)
    if not company or not company.is_active:
        raise HTTPException(status_code=422, detail="Compañía de seguros inválida")

    if payload.is_primary:
        current_primary = db.scalars(
            select(PatientInsurance).where(
                PatientInsurance.patient_id == patient_id,
                PatientInsurance.is_primary.is_(True),
                PatientInsurance.is_active.is_(True),
            )
        ).all()
        for item in current_primary:
            item.is_primary = False

    item = PatientInsurance(
        patient_id=patient_id,
        insurance_company_id=payload.insurance_company_id,
        member_number=payload.member_number.strip(),
        plan_name=payload.plan_name.strip() if payload.plan_name else None,
        is_primary=payload.is_primary,
    )
    db.add(item)
    db.commit()
    db.refresh(item)
    return serialize_patient_insurance(item)
