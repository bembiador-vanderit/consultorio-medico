from fastapi import HTTPException
from sqlalchemy import Select, and_, delete, or_, select
from sqlalchemy.orm import Session

from app.models import Appointment, AppointmentCoverageTransfer, SecretaryCenterScope, User


def is_role(user: User, code: str) -> bool:
    return any(role.code == code for role in user.roles)


def assigned_center_ids(user: User) -> set[int]:
    return {center.id for center in user.centers if center.is_active}


def _secretary_scopes(user: User, db: Session) -> list[SecretaryCenterScope]:
    return list(
        db.scalars(
            select(SecretaryCenterScope).where(SecretaryCenterScope.secretary_id == user.id)
        ).all()
    )


def secretary_doctor_ids_by_center(user: User, db: Session) -> dict[int, set[int] | None]:
    assigned = assigned_center_ids(user)
    result: dict[int, set[int] | None] = {}
    for scope in _secretary_scopes(user, db):
        if scope.center_id not in assigned:
            continue
        result[scope.center_id] = None if scope.manage_all_doctors else {doctor.id for doctor in scope.doctors}
    return result


def secretary_can_manage(user: User, center_id: int, doctor_id: int, db: Session) -> bool:
    allowed = secretary_doctor_ids_by_center(user, db).get(center_id, set())
    return allowed is None or doctor_id in allowed


def remove_center_membership_from_scopes(db: Session, user: User, center_ids: set[int]) -> None:
    if not center_ids:
        return
    if is_role(user, "secretary"):
        db.execute(
            delete(SecretaryCenterScope).where(
                SecretaryCenterScope.secretary_id == user.id,
                SecretaryCenterScope.center_id.in_(center_ids),
            )
        )
    if is_role(user, "doctor"):
        for scope in db.scalars(
            select(SecretaryCenterScope).where(SecretaryCenterScope.center_id.in_(center_ids))
        ).all():
            if user in scope.doctors:
                scope.doctors.remove(user)


def apply_appointment_scope(query: Select, user: User, db: Session) -> Select:
    if not user.is_active:
        raise HTTPException(status_code=403, detail="Usuario inactivo")
    if is_role(user, "admin"):
        return query
    if is_role(user, "secretary"):
        conditions = []
        for center_id, doctor_ids in secretary_doctor_ids_by_center(user, db).items():
            if doctor_ids is None:
                conditions.append(Appointment.center_id == center_id)
            elif doctor_ids:
                conditions.append(and_(
                    Appointment.center_id == center_id,
                    or_(
                        Appointment.doctor_id.in_(doctor_ids),
                        Appointment.coverage_transfer.has(
                            AppointmentCoverageTransfer.original_doctor_id.in_(doctor_ids)
                        ),
                    ),
                ))
        return query.where(or_(*conditions)) if conditions else query.where(Appointment.id == -1)
    if is_role(user, "doctor"):
        return query.where(Appointment.doctor_id == user.id)
    raise HTTPException(status_code=403, detail="No tiene acceso a la agenda")


def ensure_appointment_access(user: User, appointment: Appointment, db: Session | None = None) -> None:
    if not user.is_active:
        raise HTTPException(status_code=403, detail="Usuario inactivo")
    if is_role(user, "admin"):
        return
    if is_role(user, "secretary"):
        if db is not None and appointment.center_id is not None and secretary_can_manage(
            user, appointment.center_id, appointment.doctor_id, db
        ):
            return
        transfer = appointment.coverage_transfer
        if db is not None and transfer is not None and appointment.center_id is not None and secretary_can_manage(
            user, appointment.center_id, transfer.original_doctor_id, db
        ):
            return
        raise HTTPException(status_code=403, detail="No tiene acceso a esta cita")
    if is_role(user, "doctor") and appointment.doctor_id == user.id:
        return
    raise HTTPException(status_code=403, detail="No tiene acceso a esta cita")
