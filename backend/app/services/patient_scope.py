from datetime import date

from fastapi import HTTPException
from sqlalchemy import Select, exists, func, or_, select
from sqlalchemy.orm import Session

from app.models import Appointment, ClinicalHistory, Patient, User
from app.services.appointment_scope import apply_appointment_scope, is_role, secretary_can_manage


VISIBLE_APPOINTMENT_STATUSES = {"scheduled", "confirmed", "completed"}


def scope_patient_identities(query: Select, user: User, db: Session) -> Select:
    """Apply organizational identity visibility without granting clinical history."""
    if not user.is_active:
        raise HTTPException(status_code=403, detail="Usuario inactivo")
    if is_role(user, "admin"):
        return query
    if is_role(user, "secretary"):
        appointment_ids = apply_appointment_scope(select(Appointment.patient_id), user, db)
        return query.where(Patient.id.in_(appointment_ids))
    if is_role(user, "doctor"):
        own_appointment = exists(
            select(Appointment.id).where(
                Appointment.patient_id == Patient.id,
                Appointment.doctor_id == user.id,
                Appointment.status.in_(VISIBLE_APPOINTMENT_STATUSES),
            )
        )
        own_history = exists(
            select(ClinicalHistory.id).where(
                ClinicalHistory.patient_id == Patient.id,
                ClinicalHistory.doctor_id == user.id,
            )
        )
        return query.where(or_(own_appointment, own_history))
    raise HTTPException(status_code=403, detail="No tiene acceso a pacientes")


def patient_in_identity_scope(db: Session, user: User, patient_id: int) -> bool:
    query = scope_patient_identities(select(Patient.id).where(Patient.id == patient_id), user, db)
    return db.scalar(query.limit(1)) is not None


def doctor_has_patient_relationship(db: Session, user: User, patient_id: int) -> bool:
    """Check clinical scope without allowing an additional admin role to broaden it."""
    if not user.is_active or not is_role(user, "doctor"):
        return False
    own_appointment = db.scalar(
        select(Appointment.id).where(
            Appointment.patient_id == patient_id,
            Appointment.doctor_id == user.id,
            Appointment.status.in_(VISIBLE_APPOINTMENT_STATUSES),
        ).limit(1)
    )
    if own_appointment is not None:
        return True
    return db.scalar(
        select(ClinicalHistory.id).where(
            ClinicalHistory.patient_id == patient_id,
            ClinicalHistory.doctor_id == user.id,
        ).limit(1)
    ) is not None


def require_patient_identity_access(db: Session, user: User, patient_id: int) -> Patient:
    patient = db.get(Patient, patient_id)
    if patient is None or not patient_in_identity_scope(db, user, patient_id):
        # Do not reveal whether a patient outside scope exists.
        raise HTTPException(status_code=404, detail="Paciente no encontrado")
    return patient


def require_patient_clinical_scope(db: Session, user: User, patient_id: int) -> Patient:
    if not doctor_has_patient_relationship(db, user, patient_id):
        raise HTTPException(status_code=404, detail="Paciente no encontrado")
    patient = db.get(Patient, patient_id)
    if patient is None:
        raise HTTPException(status_code=404, detail="Paciente no encontrado")
    return patient


def validate_identity_search_context(
    db: Session,
    user: User,
    *,
    center_id: int | None,
    doctor_id: int | None,
) -> None:
    if not user.is_active:
        raise HTTPException(status_code=403, detail="Usuario inactivo")
    if is_role(user, "admin"):
        return
    if is_role(user, "doctor"):
        if doctor_id is not None and doctor_id != user.id:
            raise HTTPException(status_code=403, detail="El médico solo puede buscar para sus propias citas")
        if center_id is not None and center_id not in {center.id for center in user.centers if center.is_active}:
            raise HTTPException(status_code=403, detail="No tiene acceso a ese centro")
        return
    if is_role(user, "secretary"):
        if center_id is None or doctor_id is None:
            raise HTTPException(status_code=422, detail="Debe indicar el centro y médico de la cita")
        doctor = db.get(User, doctor_id)
        if (
            doctor is None
            or not doctor.is_active
            or not is_role(doctor, "doctor")
            or center_id not in {center.id for center in doctor.centers if center.is_active}
        ):
            raise HTTPException(status_code=404, detail="Contexto de cita no encontrado")
        if not secretary_can_manage(user, center_id, doctor_id, db):
            raise HTTPException(status_code=403, detail="No tiene autorización para buscar pacientes en ese contexto")
        return
    raise HTTPException(status_code=403, detail="No tiene autorización para buscar pacientes")


def identity_matches(db: Session, *, date_of_birth: date, phone: str | None, email: str | None) -> list[Patient]:
    normalized_phone = phone.strip() if phone else None
    normalized_email = email.strip().lower() if email else None
    if not normalized_phone and not normalized_email:
        raise HTTPException(status_code=422, detail="Indique teléfono o correo junto con la fecha de nacimiento")
    identifiers = []
    if normalized_phone:
        identifiers.append(Patient.phone == normalized_phone)
    if normalized_email:
        identifiers.append(func.lower(Patient.email) == normalized_email)
    return list(
        db.scalars(
            select(Patient)
            .where(Patient.date_of_birth == date_of_birth, or_(*identifiers))
            .order_by(Patient.last_name, Patient.first_name)
            .limit(10)
        ).all()
    )


def mask_phone(value: str | None) -> str | None:
    if not value:
        return None
    visible = value[-4:]
    return f"***{visible}" if len(value) > 4 else visible


def mask_email(value: str | None) -> str | None:
    if not value or "@" not in value:
        return None
    local, domain = value.split("@", 1)
    return f"{local[:1]}***@{domain}"
