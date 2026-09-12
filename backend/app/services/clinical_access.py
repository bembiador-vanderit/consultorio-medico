from fastapi import HTTPException
from sqlalchemy import Select, select
from sqlalchemy.orm import Session

from app.models.clinical_audit import ClinicalAuditLog
from app.models.clinical_coverage import AppointmentCoverageTransfer, ClinicalCoverage
from app.models.clinical_history import ClinicalHistory
from app.models.appointment import Appointment
from app.models.identity import User
from app.services.appointment_scope import is_role
from app.services.clinical_coverage import installation_now


def delegated_coverage_id(db: Session, user: User, history: ClinicalHistory) -> int | None:
    if not is_role(user, "doctor") or history.doctor_id is None or history.center_id is None:
        return None
    if history.center_id not in {center.id for center in user.centers}:
        return None
    now = installation_now()
    query = (
        select(ClinicalCoverage.id)
        .join(AppointmentCoverageTransfer, AppointmentCoverageTransfer.coverage_id == ClinicalCoverage.id)
        .join(Appointment, Appointment.id == AppointmentCoverageTransfer.appointment_id)
        .where(
            ClinicalCoverage.principal_doctor_id == history.doctor_id,
            ClinicalCoverage.substitute_doctor_id == user.id,
            ClinicalCoverage.center_id == history.center_id,
            ClinicalCoverage.revoked_at.is_(None),
            ClinicalCoverage.starts_at <= now,
            ClinicalCoverage.ends_at > now,
            Appointment.patient_id == history.patient_id,
        )
        .limit(1)
    )
    return db.scalar(query)


def principal_continuity_coverage_id(db: Session, user: User, history: ClinicalHistory) -> int | None:
    """Keep the principal's read access to episodes authored under a concrete transfer."""
    if not is_role(user, "doctor") or history.appointment_id is None:
        return None
    return db.scalar(
        select(ClinicalCoverage.id)
        .join(AppointmentCoverageTransfer, AppointmentCoverageTransfer.coverage_id == ClinicalCoverage.id)
        .join(Appointment, Appointment.id == AppointmentCoverageTransfer.appointment_id)
        .where(
            AppointmentCoverageTransfer.appointment_id == history.appointment_id,
            AppointmentCoverageTransfer.original_doctor_id == user.id,
            AppointmentCoverageTransfer.substitute_doctor_id == history.doctor_id,
            ClinicalCoverage.center_id == history.center_id,
            Appointment.patient_id == history.patient_id,
            Appointment.center_id == history.center_id,
        )
        .limit(1)
    )


def history_appointment_context_is_valid(db: Session, history: ClinicalHistory) -> bool:
    """Validate the immutable clinical context copied from a linked appointment."""
    if history.appointment_id is None:
        return True
    appointment = db.get(Appointment, history.appointment_id)
    return bool(
        appointment
        and appointment.patient_id == history.patient_id
        and appointment.doctor_id == history.doctor_id
        and appointment.center_id == history.center_id
        and appointment.specialty_id == history.specialty_id
    )


def has_normal_history_access(db: Session, user: User, history: ClinicalHistory) -> bool:
    if not is_role(user, "doctor") or history.doctor_id != user.id:
        return False

    assigned_center_ids = {center.id for center in user.centers}
    if history.center_id is not None and history.center_id not in assigned_center_ids:
        return False

    # Legacy histories without appointments remain readable, but new orphan
    # histories cannot be created. When an appointment exists, its immutable
    # clinical context must match before any access is granted.
    return history_appointment_context_is_valid(db, history)


def can_access_history(db: Session, user: User, history: ClinicalHistory) -> bool:
    if not history_appointment_context_is_valid(db, history):
        return False
    return (
        has_normal_history_access(db, user, history)
        or delegated_coverage_id(db, user, history) is not None
        or principal_continuity_coverage_id(db, user, history) is not None
    )


def scope_histories(query: Select, user: User) -> Select:
    if is_role(user, "doctor"):
        # Callers already restrict by patient. Filtering each result through
        # can_access_history is necessary because delegated access depends on a
        # concrete transferred appointment for that patient.
        return query
    return query.where(ClinicalHistory.id == -1)


def ensure_attending_doctor(user: User, appointment: Appointment) -> None:
    """Clinical work is limited to the doctor currently responsible for the appointment."""
    if not user.is_active or not is_role(user, "doctor") or appointment.doctor_id != user.id:
        raise HTTPException(status_code=404, detail="Cita no encontrada")


def add_clinical_audit(
    db: Session,
    user: User,
    *,
    action: str,
    resource_type: str,
    resource_id: int | None = None,
    history_id: int | None = None,
    outcome: str = "success",
    context: dict | None = None,
) -> None:
    db.add(ClinicalAuditLog(
        user_id=user.id,
        action=action,
        resource_type=resource_type,
        resource_id=resource_id,
        clinical_history_id=history_id,
        outcome=outcome,
        context=context,
    ))


def _deny(
    db: Session,
    user: User,
    *,
    action: str,
    history_id: int,
    resource_type: str,
    resource_id: int | None,
    reason: str,
    status_code: int,
    detail: str,
) -> None:
    add_clinical_audit(
        db,
        user,
        action=action,
        resource_type=resource_type,
        resource_id=resource_id,
        history_id=history_id,
        outcome="denied",
        context={"reason": reason},
    )
    db.commit()
    raise HTTPException(status_code=status_code, detail=detail)


def require_history_access(
    db: Session,
    user: User,
    history_id: int,
    *,
    action: str,
    resource_type: str = "clinical_history",
    resource_id: int | None = None,
    write: bool = False,
    audit_read: bool = False,
) -> ClinicalHistory:
    history = db.get(ClinicalHistory, history_id)
    if history is None:
        raise HTTPException(status_code=404, detail="Registro de historia clínica no encontrado")
    if not history_appointment_context_is_valid(db, history):
        _deny(
            db,
            user,
            action=action,
            history_id=history.id,
            resource_type=resource_type,
            resource_id=resource_id,
            reason="invalid_appointment_context",
            status_code=403,
            detail="No tiene acceso a esta historia clínica",
        )
    normal_access = has_normal_history_access(db, user, history)
    delegated_id = None if normal_access else delegated_coverage_id(db, user, history)
    principal_continuity_id = (
        None if normal_access or delegated_id is not None
        else principal_continuity_coverage_id(db, user, history)
    )
    coverage_id = delegated_id or principal_continuity_id
    if not normal_access and coverage_id is None:
        _deny(
            db,
            user,
            action=action,
            history_id=history.id,
            resource_type=resource_type,
            resource_id=resource_id,
            reason="outside_clinical_scope",
            status_code=403,
            detail="No tiene acceso a esta historia clínica",
        )
    if write and coverage_id is not None:
        _deny(
            db, user, action=action, history_id=history.id, resource_type=resource_type,
            resource_id=resource_id, reason="delegated_access_is_read_only", status_code=403,
            detail="El acceso a episodios por cobertura es de solo lectura",
        )
    if write and history.status == "completed":
        _deny(
            db,
            user,
            action=action,
            history_id=history.id,
            resource_type=resource_type,
            resource_id=resource_id,
            reason="consultation_completed",
            status_code=409,
            detail="La consulta finalizada es de solo lectura",
        )
    if write and history.appointment_id is not None:
        appointment = db.get(Appointment, history.appointment_id)
        if appointment is None or appointment.status not in {"scheduled", "confirmed"}:
            _deny(
                db,
                user,
                action=action,
                history_id=history.id,
                resource_type=resource_type,
                resource_id=resource_id,
                reason="appointment_not_attendable",
                status_code=409,
                detail="La cita vinculada no permite continuar la atención",
            )
    if audit_read:
        add_clinical_audit(
            db,
            user,
            action=action,
            resource_type=resource_type,
            resource_id=resource_id,
            history_id=history.id,
            context={
                "coverage_id": coverage_id,
                "delegated": delegated_id is not None,
                "principal_continuity": principal_continuity_id is not None,
            },
        )
        db.commit()
    return history
