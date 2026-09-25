from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from app.api.deps import require_permission
from app.db import get_db
from app.models import InsuranceCompany, PatientInsurance, User
from app.models.insurance import InsurancePlan, AppointmentCoverage
from app.schemas.insurance import (InsuranceCompanyCreate, InsuranceCompanyResponse, InsurancePlanCreate,
    InsurancePlanResponse, PatientInsuranceCreate, PatientInsuranceResponse, CoverageWrite, CoverageResponse, AUTHORIZATION_STATES)
from app.services.patient_scope import require_patient_identity_access
from app.services.insurance import save_insurance, save_coverage, appointment_access, patient_lock, record

router = APIRouter(prefix="/insurance", tags=["Seguros médicos"])
read = require_permission("patients:access")
def write(user: User = Depends(require_permission("insurance:manage")), _: User = Depends(read)):
    return user
catalog = require_permission("users:manage")


def serialize_patient_insurance(item):
    data = {field: getattr(item, field) for field in PatientInsuranceResponse.model_fields if field != "insurance_company_name"}
    return PatientInsuranceResponse(**data, insurance_company_name=item.insurance_company.name)


def commit_catalog(db, user, item, action):
    try:
        db.flush()
        record(db, user, action, item.id)
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, "Ya existe un registro con ese nombre o código")
    db.refresh(item)
    return item


@router.get("/companies", response_model=list[InsuranceCompanyResponse])
def list_companies(include_inactive: bool = False, user: User = Depends(read), db: Session = Depends(get_db)):
    query = select(InsuranceCompany)
    if not include_inactive:
        query = query.where(InsuranceCompany.is_active.is_(True))
    return db.scalars(query.order_by(InsuranceCompany.name)).all()


@router.post("/companies", response_model=InsuranceCompanyResponse, status_code=201)
def create_company(payload: InsuranceCompanyCreate, user: User = Depends(catalog), db: Session = Depends(get_db)):
    item = InsuranceCompany(**payload.model_dump())
    db.add(item)
    return commit_catalog(db, user, item, "company_created")


@router.put("/companies/{company_id}", response_model=InsuranceCompanyResponse)
def update_company(company_id: int, payload: InsuranceCompanyCreate, user: User = Depends(catalog), db: Session = Depends(get_db)):
    item = db.get(InsuranceCompany, company_id)
    if item is None:
        raise HTTPException(404, "Aseguradora no encontrada")
    for key, value in payload.model_dump().items():
        setattr(item, key, value)
    return commit_catalog(db, user, item, "company_updated")


@router.get("/plans", response_model=list[InsurancePlanResponse])
def list_plans(insurance_company_id: int | None = None, include_inactive: bool = False,
               user: User = Depends(read), db: Session = Depends(get_db)):
    query = select(InsurancePlan)
    if insurance_company_id is not None:
        if db.get(InsuranceCompany, insurance_company_id) is None:
            raise HTTPException(404, "Aseguradora no encontrada")
        query = query.where(InsurancePlan.insurance_company_id == insurance_company_id)
    if not include_inactive:
        query = query.where(InsurancePlan.is_active.is_(True))
    return db.scalars(query.order_by(InsurancePlan.name)).all()


def plan_company(db, payload):
    company = db.get(InsuranceCompany, payload.insurance_company_id)
    if not company or (payload.is_active and not company.is_active):
        raise HTTPException(422, "Aseguradora no disponible")


@router.post("/plans", response_model=InsurancePlanResponse, status_code=201)
def create_plan(payload: InsurancePlanCreate, user: User = Depends(catalog), db: Session = Depends(get_db)):
    plan_company(db, payload)
    item = InsurancePlan(**payload.model_dump())
    db.add(item)
    return commit_catalog(db, user, item, "plan_created")


@router.put("/plans/{plan_id}", response_model=InsurancePlanResponse)
def update_plan(plan_id: int, payload: InsurancePlanCreate, user: User = Depends(catalog), db: Session = Depends(get_db)):
    item = db.get(InsurancePlan, plan_id)
    if item is None:
        raise HTTPException(404, "Plan no encontrado")
    if item.insurance_company_id != payload.insurance_company_id:
        raise HTTPException(422, "Un plan conserva su aseguradora")
    plan_company(db, payload)
    for key, value in payload.model_dump().items():
        setattr(item, key, value)
    return commit_catalog(db, user, item, "plan_updated")


@router.get("/patients/{patient_id}", response_model=list[PatientInsuranceResponse])
def list_patient_insurances(patient_id: int, user: User = Depends(read), db: Session = Depends(get_db)):
    require_patient_identity_access(db, user, patient_id)
    items = db.scalars(select(PatientInsurance).where(PatientInsurance.patient_id == patient_id)
        .order_by(PatientInsurance.is_active.desc(), PatientInsurance.is_primary.desc(), PatientInsurance.created_at.desc())).all()
    return [serialize_patient_insurance(item) for item in items]


@router.post("/patients/{patient_id}", response_model=PatientInsuranceResponse, status_code=201)
def add_patient_insurance(patient_id: int, payload: PatientInsuranceCreate, user: User = Depends(write), db: Session = Depends(get_db)):
    return serialize_patient_insurance(save_insurance(db, user, patient_id, payload))


@router.put("/patients/{patient_id}/{insurance_id}", response_model=PatientInsuranceResponse)
def update_patient_insurance(patient_id: int, insurance_id: int, payload: PatientInsuranceCreate,
                             user: User = Depends(write), db: Session = Depends(get_db)):
    return serialize_patient_insurance(save_insurance(db, user, patient_id, payload, insurance_id))


@router.delete("/patients/{patient_id}/{insurance_id}", status_code=204)
def deactivate_patient_insurance(patient_id: int, insurance_id: int, user: User = Depends(write), db: Session = Depends(get_db)):
    patient_lock(db, user, patient_id)
    item = db.scalar(select(PatientInsurance).where(PatientInsurance.id == insurance_id, PatientInsurance.patient_id == patient_id))
    if item is None:
        raise HTTPException(404, "Seguro del paciente no encontrado")
    item.is_active = item.is_primary = False
    record(db, user, "patient_deactivated", item.id)
    db.commit()


@router.get("/authorization-states")
def authorization_states(user: User = Depends(read)):
    return [{"code": code, "label": label} for code, label in AUTHORIZATION_STATES.items()]


@router.get("/appointments/{appointment_id}/coverage", response_model=CoverageResponse | None)
def get_coverage(appointment_id: int, user: User = Depends(read), db: Session = Depends(get_db)):
    appointment_access(db, user, appointment_id)
    return db.scalar(select(AppointmentCoverage).where(AppointmentCoverage.appointment_id == appointment_id))


@router.put("/appointments/{appointment_id}/coverage", response_model=CoverageResponse)
def put_coverage(appointment_id: int, payload: CoverageWrite, user: User = Depends(write), db: Session = Depends(get_db)):
    return save_coverage(db, user, appointment_id, payload)
