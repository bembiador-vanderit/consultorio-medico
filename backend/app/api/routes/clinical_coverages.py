from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.api.deps import require_permission
from app.db import get_db
from app.models import Appointment, AppointmentCoverageTransfer, CareCenter, ClinicalCoverage, ClinicalHistory, User
from app.schemas.clinical_coverage import ClinicalCoverageCreate, ClinicalCoverageResponse, EligibleSubstituteResponse
from app.services.appointment_scope import is_role
from app.services.clinical_access import add_clinical_audit

router = APIRouter(prefix="/clinical-coverages", tags=["Cobertura clínica"])
access = require_permission("clinical:access")


def coverage_status(coverage: ClinicalCoverage, now: datetime | None = None) -> str:
    now = now or datetime.utcnow()
    if coverage.revoked_at is not None:
        return "revoked"
    if now < coverage.starts_at:
        return "future"
    if now >= coverage.ends_at:
        return "expired"
    return "active"


def serialize(coverage: ClinicalCoverage) -> ClinicalCoverageResponse:
    return ClinicalCoverageResponse(
        id=coverage.id,
        principal_doctor_id=coverage.principal_doctor_id,
        principal_doctor_name=coverage.principal.full_name,
        substitute_doctor_id=coverage.substitute_doctor_id,
        substitute_doctor_name=coverage.substitute.full_name,
        center_id=coverage.center_id,
        center_name=coverage.center.name,
        starts_at=coverage.starts_at,
        ends_at=coverage.ends_at,
        revoked_at=coverage.revoked_at,
        status=coverage_status(coverage),
        created_at=coverage.created_at,
    )


def require_principal(user: User) -> None:
    if not user.is_active or not is_role(user, "doctor"):
        raise HTTPException(status_code=403, detail="Solo el médico principal puede gestionar su cobertura")


@router.get("", response_model=list[ClinicalCoverageResponse])
def list_coverages(user: User = Depends(access), db: Session = Depends(get_db)):
    require_principal(user)
    query = select(ClinicalCoverage).where(
        (ClinicalCoverage.principal_doctor_id == user.id) | (ClinicalCoverage.substitute_doctor_id == user.id)
    ).order_by(ClinicalCoverage.created_at.desc())
    return [serialize(item) for item in db.scalars(query)]


@router.get("/eligible-substitutes", response_model=list[EligibleSubstituteResponse])
def eligible_substitutes(center_id: int, user: User = Depends(access), db: Session = Depends(get_db)):
    require_principal(user)
    center = db.get(CareCenter, center_id)
    if center is None or not center.is_active or center not in user.centers:
        raise HTTPException(status_code=422, detail="Centro inválido para el médico principal")
    doctors = [
        candidate for candidate in center.users
        if candidate.id != user.id and candidate.is_active and is_role(candidate, "doctor")
    ]
    return [EligibleSubstituteResponse(id=item.id, full_name=item.full_name) for item in doctors]


@router.post("", response_model=ClinicalCoverageResponse, status_code=status.HTTP_201_CREATED)
def create_coverage(payload: ClinicalCoverageCreate, user: User = Depends(access), db: Session = Depends(get_db)):
    require_principal(user)
    center = db.get(CareCenter, payload.center_id)
    substitute = db.get(User, payload.substitute_doctor_id)
    if center is None or not center.is_active or center not in user.centers:
        raise HTTPException(status_code=422, detail="Centro inválido para la cobertura")
    if substitute is None or not substitute.is_active or not is_role(substitute, "doctor"):
        raise HTTPException(status_code=422, detail="Médico suplente inválido")
    if substitute.id == user.id:
        raise HTTPException(status_code=422, detail="El médico principal y el suplente deben ser diferentes")
    if center not in substitute.centers:
        raise HTTPException(status_code=422, detail="El médico suplente no pertenece al centro")
    coverage = ClinicalCoverage(
        principal_doctor_id=user.id, substitute_doctor_id=substitute.id,
        center_id=center.id, starts_at=payload.starts_at, ends_at=payload.ends_at,
        created_by_id=user.id,
    )
    db.add(coverage)
    db.flush()
    add_clinical_audit(
        db, user, action="coverage.create", resource_type="clinical_coverage", resource_id=coverage.id,
        context={"principal_doctor_id": user.id, "substitute_doctor_id": substitute.id, "center_id": center.id},
    )
    db.commit(); db.refresh(coverage)
    return serialize(coverage)


@router.post("/{coverage_id}/revoke", response_model=ClinicalCoverageResponse)
def revoke_coverage(coverage_id: int, user: User = Depends(access), db: Session = Depends(get_db)):
    require_principal(user)
    coverage = db.scalar(
        select(ClinicalCoverage)
        .where(ClinicalCoverage.id == coverage_id)
        .with_for_update()
    )
    if coverage is None:
        raise HTTPException(status_code=404, detail="Cobertura no encontrada")
    if coverage.principal_doctor_id != user.id:
        raise HTTPException(status_code=403, detail="Solo el médico principal puede revocar esta cobertura")
    if coverage.revoked_at is None:
        coverage.revoked_at = datetime.utcnow()
        transfers = list(db.scalars(
            select(AppointmentCoverageTransfer).where(
                AppointmentCoverageTransfer.coverage_id == coverage.id
            )
        ).all())
        for transfer in transfers:
            appointment = transfer.appointment
            has_history = db.scalar(
                select(ClinicalHistory.id).where(ClinicalHistory.appointment_id == appointment.id)
            ) is not None
            if appointment.status in {"scheduled", "confirmed"} and not has_history:
                appointment.doctor_id = transfer.original_doctor_id
                add_clinical_audit(
                    db,
                    user,
                    action="coverage.appointment.restore",
                    resource_type="appointment",
                    resource_id=appointment.id,
                    context={
                        "coverage_id": coverage.id,
                        "principal_doctor_id": transfer.original_doctor_id,
                        "substitute_doctor_id": transfer.substitute_doctor_id,
                        "center_id": appointment.center_id,
                        "patient_id": appointment.patient_id,
                    },
                )
                db.delete(transfer)
        add_clinical_audit(
            db, user, action="coverage.revoke", resource_type="clinical_coverage", resource_id=coverage.id,
            context={"principal_doctor_id": coverage.principal_doctor_id, "substitute_doctor_id": coverage.substitute_doctor_id, "center_id": coverage.center_id},
        )
        try:
            db.commit()
        except SQLAlchemyError:
            db.rollback()
            raise HTTPException(status_code=500, detail="No fue posible revocar la cobertura")
        db.refresh(coverage)
    return serialize(coverage)


@router.post("/{coverage_id}/appointments/{appointment_id}/transfer")
def transfer_appointment(coverage_id: int, appointment_id: int, user: User = Depends(access), db: Session = Depends(get_db)):
    require_principal(user)
    coverage = db.scalar(
        select(ClinicalCoverage)
        .where(ClinicalCoverage.id == coverage_id)
        .with_for_update()
    )
    appointment = db.scalar(
        select(Appointment)
        .where(Appointment.id == appointment_id)
        .with_for_update()
    )
    if coverage is None or appointment is None:
        raise HTTPException(status_code=404, detail="Cobertura o cita no encontrada")
    if coverage.principal_doctor_id != user.id:
        raise HTTPException(status_code=403, detail="El suplente no puede autoasignarse una cobertura")
    if coverage_status(coverage) != "active":
        raise HTTPException(status_code=409, detail="La cobertura no está activa")
    if appointment.status not in {"scheduled", "confirmed"}:
        raise HTTPException(status_code=409, detail="El estado de la cita no permite transferencia")
    if appointment.doctor_id != coverage.principal_doctor_id or appointment.center_id != coverage.center_id:
        raise HTTPException(status_code=409, detail="La cita no corresponde al médico y centro de la cobertura")
    if db.scalar(select(ClinicalHistory.id).where(ClinicalHistory.appointment_id == appointment.id)) is not None:
        raise HTTPException(status_code=409, detail="Una cita con consulta iniciada no puede transferirse")
    appointment_at = datetime.combine(appointment.appointment_date, appointment.appointment_time)
    if not coverage.starts_at <= appointment_at < coverage.ends_at:
        raise HTTPException(status_code=409, detail="La cita está fuera del período de cobertura")
    transfer = AppointmentCoverageTransfer(
        appointment_id=appointment.id, coverage_id=coverage.id,
        original_doctor_id=appointment.doctor_id, substitute_doctor_id=coverage.substitute_doctor_id,
        executed_by_id=user.id,
    )
    db.add(transfer)
    appointment.doctor_id = coverage.substitute_doctor_id
    try:
        db.flush()
        add_clinical_audit(
            db, user, action="coverage.appointment.transfer", resource_type="appointment", resource_id=appointment.id,
            context={"coverage_id": coverage.id, "principal_doctor_id": coverage.principal_doctor_id, "substitute_doctor_id": coverage.substitute_doctor_id, "center_id": coverage.center_id, "patient_id": appointment.patient_id},
        )
        db.commit()
    except SQLAlchemyError:
        db.rollback()
        raise HTTPException(status_code=500, detail="No fue posible transferir la cita")
    return {"appointment_id": appointment.id, "coverage_id": coverage.id, "doctor_id": appointment.doctor_id}
