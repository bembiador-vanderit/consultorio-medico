"""Insurance rules and transactional audit, independent of HTTP presentation."""
from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session
from app.models import Appointment, Patient, PatientInsurance, InsuranceCompany, User
from app.models.insurance import InsurancePlan, AppointmentCoverage
from app.models.administration import SecurityAudit
from app.services.appointment_scope import ensure_appointment_access
from app.services.patient_scope import require_patient_identity_access
from app.schemas.insurance import PatientInsuranceCreate, CoverageWrite


def record(db, actor, action, entity, center_id=None):
    db.add(SecurityAudit(actor_id=actor.id, action=f"insurance:{action}:{entity}", center_id=center_id))


def patient_lock(db, user, patient_id):
    require_patient_identity_access(db, user, patient_id)
    return db.scalar(select(Patient).where(Patient.id == patient_id).with_for_update().execution_options(populate_existing=True))


def save_insurance(db: Session, user: User, patient_id: int, payload: PatientInsuranceCreate, insurance_id=None, *, commit=True, check_access=True):
    if check_access:
        patient_lock(db, user, patient_id)
    item = None
    if insurance_id is not None:
        item = db.scalar(select(PatientInsurance).where(PatientInsurance.id == insurance_id, PatientInsurance.patient_id == patient_id))
        if not item:
            raise HTTPException(404, "Seguro del paciente no encontrado")
    company = db.get(InsuranceCompany, payload.insurance_company_id)
    if not company or (payload.is_active and not company.is_active):
        raise HTTPException(422, "Aseguradora no disponible")
    data = payload.model_dump()
    if payload.plan_id is not None:
        plan = db.get(InsurancePlan, payload.plan_id)
        if not plan or plan.insurance_company_id != company.id or (payload.is_active and not plan.is_active):
            raise HTTPException(422, "Plan no disponible para esta aseguradora")
        data["plan_name"] = plan.name
    if payload.is_primary:
        for old in db.scalars(select(PatientInsurance).where(PatientInsurance.patient_id == patient_id, PatientInsurance.is_primary.is_(True))):
            old.is_primary = False
            record(db, user, "primary_removed", old.id)
        db.flush()
    if item is None:
        item = PatientInsurance(patient_id=patient_id, **data)
        db.add(item)
    else:
        for key, value in data.items():
            setattr(item, key, value)
    db.flush()
    record(db, user, "patient_updated" if insurance_id else "patient_created", item.id)
    if commit:
        db.commit()
        db.refresh(item)
    return item


def appointment_access(db, user, appointment_id, lock=False):
    query = select(Appointment).where(Appointment.id == appointment_id)
    if lock:
        query = query.with_for_update().execution_options(populate_existing=True)
    appointment = db.scalar(query)
    if appointment is None:
        raise HTTPException(404, "Cita no encontrada")
    ensure_appointment_access(user, appointment, db)
    return appointment


def save_coverage(db: Session, user: User, appointment_id: int, payload: CoverageWrite):
    appointment = appointment_access(db, user, appointment_id, lock=True)
    row = db.scalar(select(AppointmentCoverage).where(AppointmentCoverage.appointment_id == appointment_id))
    if payload.revision != (row.revision if row else 0):
        raise HTTPException(409, "La cobertura cambió; vuelva a cargarla antes de guardar")
    # Preserve the existing snapshot on financial/authorization edits. Re-selecting
    # a different affiliation is explicit and prohibited after completion.
    selecting = row is None or row.patient_insurance_id != payload.patient_insurance_id
    if selecting and appointment.status in {"completed", "cancelled", "no_show"}:
        raise HTTPException(409, "Esta cita conserva el seguro registrado; no admite otra afiliación")
    snapshot = row.insurance_snapshot if row else {}
    if selecting:
        snapshot = {}
        if payload.patient_insurance_id is not None:
            insurance = db.scalar(select(PatientInsurance).where(PatientInsurance.id == payload.patient_insurance_id).with_for_update())
            if not insurance or insurance.patient_id != appointment.patient_id or not insurance.is_active:
                raise HTTPException(422, "Seguro no disponible para este paciente")
            company = db.get(InsuranceCompany, insurance.insurance_company_id)
            plan = db.get(InsurancePlan, insurance.plan_id) if insurance.plan_id else None
            if not company.is_active or (plan and not plan.is_active):
                raise HTTPException(422, "Aseguradora o plan inactivo")
            if (insurance.valid_from and appointment.appointment_date < insurance.valid_from) or (insurance.valid_until and appointment.appointment_date > insurance.valid_until):
                raise HTTPException(422, "El seguro no está vigente en la fecha de la cita")
            snapshot = {"company_id": company.id, "company_name": company.name,
                        "plan_id": insurance.plan_id, "plan_name": insurance.plan_name,
                        "member_number": insurance.member_number, "policy_holder": insurance.policy_holder,
                        "relationship_to_holder": insurance.relationship_to_holder,
                        "valid_from": str(insurance.valid_from) if insurance.valid_from else None,
                        "valid_until": str(insurance.valid_until) if insurance.valid_until else None}
    data = payload.model_dump(exclude={"revision"})
    if row is None:
        row = AppointmentCoverage(appointment_id=appointment_id, insurance_snapshot=snapshot, **data)
        db.add(row)
    else:
        for key, value in data.items():
            setattr(row, key, value)
        row.insurance_snapshot = snapshot
        row.revision += 1
    db.flush()
    record(db, user, "coverage_updated", row.id, appointment.center_id)
    record(db, user, "authorization_" + row.authorization_status, row.id, appointment.center_id)
    db.commit()
    db.refresh(row)
    return row
