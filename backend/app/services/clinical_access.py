from datetime import datetime

from fastapi import HTTPException
from sqlalchemy import Select, select
from sqlalchemy.orm import Session

from app.models.clinical_audit import ClinicalAuditLog
from app.models.clinical_coverage import AppointmentCoverageTransfer, ClinicalCoverage
from app.models.clinical_history import ClinicalHistory
from app.models.appointment import Appointment
from app.models.identity import User
from app.services.appointment_scope import is_role


def delegated_coverage_id(db: Session, user: User, history: ClinicalHistory) -> int | None:
    if not is_role(user, "doctor") or history.doctor_id is None or history.center_id is None:
        return None
    if history.center_id not in {center.id for center in user.centers}:
        return None
    now = datetime.utcnow()
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


def has_normal_history_access(db: Session, user: User, history: ClinicalHistory) -> bool:
    if is_role(user, "admin"):
        return True
    if not is_role(user, "doctor") or history.doctor_id != user.id:
        return False

    assigned_center_ids = {center.id for center in user.centers}
    if history.center_id is not None and history.center_id not in assigned_center_ids:
        return False

    # Legacy histories without appointments remain readable, but new orphan
    # histories cannot be created. When an appointment exists, its immutable
    # clinical context must match before any access is granted.
    if history.appointment_id is None:
        return True
    appointment = db.get(Appointment, history.appointment_id)
    return bool(
        appointment
        and appointment.patient_id == history.patient_id
        and appointment.doctor_id == history.doctor_id
        and appointment.center_id == history.center_id
    )


def can_access_history(db: Session, user: User, history: ClinicalHistory) -> bool:
    return has_normal_history_access(db, user, history) or delegated_coverage_id(db, user, history) is not None


def scope_histories(query: Select, user: User) -> Select:
    if is_role(user, "admin"):
        return query
    if is_role(user, "doctor"):
        # Callers already restrict by patient. Filtering each result through
        # can_access_history is necessary because delegated access depends on a
        # concrete transferred appointment for that patient.
        return query
    return query.where(ClinicalHistory.id == -1)


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
    normal_access = has_normal_history_access(db, user, history)
    coverage_id = None if normal_access else delegated_coverage_id(db, user, history)
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
            detail="La cobertura solo permite consultar el historial previo",
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
            context={"coverage_id": coverage_id, "delegated": coverage_id is not None},
        )
        db.commit()
    return history
