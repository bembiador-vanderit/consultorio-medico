"""Resolve allowed appointment modes per doctor/center/day; preserve snapshots."""

from dataclasses import dataclass
from datetime import date, datetime
from zoneinfo import ZoneInfo

from fastapi import HTTPException
from sqlalchemy import inspect, or_, select
from sqlalchemy.orm import Session

from app.models import Appointment, CareCenter, DoctorAgendaException, DoctorAgendaSetting, Organization, QueueLine, User


@dataclass(frozen=True)
class AgendaPolicy:
    allowed_timed: bool
    allowed_queue: bool
    default_mode: str

    def allows(self, mode: str) -> bool:
        return (mode == "timed" and self.allowed_timed) or (mode == "queue" and self.allowed_queue)


def multimode_schema_ready(db: Session) -> bool:
    if not isinstance(db, Session):
        return False
    cached = db.info.get("multimode_schema_ready")
    if cached is None:
        columns = {column["name"] for column in inspect(db.get_bind()).get_columns("doctor_agenda_settings")}
        cached = {"allowed_timed", "allowed_queue", "default_mode"}.issubset(columns)
        db.info["multimode_schema_ready"] = cached
    return cached


def validate_policy(allowed_timed: bool, allowed_queue: bool, default_mode: str) -> AgendaPolicy:
    policy = AgendaPolicy(allowed_timed, allowed_queue, default_mode)
    if not (allowed_timed or allowed_queue):
        raise HTTPException(422, "Debe permitir al menos una modalidad")
    if not policy.allows(default_mode):
        raise HTTPException(422, "La modalidad predeterminada debe estar permitida")
    return policy


def singleton(mode: str) -> AgendaPolicy:
    return AgendaPolicy(mode == "timed", mode == "queue", mode)


def lock_center(db: Session, center_id: int) -> None:
    # Settings and appointment writes serialize on the same existing row.
    if isinstance(db, Session):
        db.scalar(select(CareCenter.id).where(CareCenter.id == center_id).with_for_update())


def validate_pair(db: Session, doctor_id: int, center_id: int) -> None:
    center = db.get(CareCenter, center_id)
    doctor = db.get(User, doctor_id)
    if center is None or doctor is None or not center.is_active or not doctor.is_active:
        raise HTTPException(404, "Médico o centro no disponible")
    if not any(role.code == "doctor" for role in doctor.roles) or center not in doctor.centers:
        raise HTTPException(422, "El médico no está asignado a este centro")


def base_mode(db: Session, doctor_id: int, center_id: int) -> str:
    return base_policy(db, doctor_id, center_id).default_mode


def base_policy(db: Session, doctor_id: int, center_id: int) -> AgendaPolicy:
    setting = db.scalar(select(DoctorAgendaSetting).where(
        DoctorAgendaSetting.doctor_id == doctor_id, DoctorAgendaSetting.center_id == center_id,
    ))
    if setting is None:
        return singleton("timed")
    if multimode_schema_ready(db) and setting.default_mode is not None:
        return AgendaPolicy(setting.allowed_timed, setting.allowed_queue, setting.default_mode)
    return singleton(setting.base_mode)


def exception_mode(db: Session, doctor_id: int, center_id: int, day: date) -> str | None:
    exception = exception_policy(db, doctor_id, center_id, day)
    return exception.default_mode if exception else None


def exception_policy(db: Session, doctor_id: int, center_id: int, day: date) -> AgendaPolicy | None:
    exception = db.scalar(select(DoctorAgendaException).where(
        DoctorAgendaException.doctor_id == doctor_id,
        DoctorAgendaException.center_id == center_id,
        DoctorAgendaException.agenda_date == day,
    ))
    if exception is None:
        return None
    if multimode_schema_ready(db) and exception.default_mode is not None:
        return AgendaPolicy(exception.allowed_timed, exception.allowed_queue, exception.default_mode)
    return singleton(exception.mode)


def effective_policy(db: Session, doctor_id: int, center_id: int, day: date) -> AgendaPolicy:
    return exception_policy(db, doctor_id, center_id, day) or base_policy(db, doctor_id, center_id)


def effective_mode(db: Session, doctor_id: int, center_id: int, day: date) -> str:
    return effective_policy(db, doctor_id, center_id, day).default_mode


def queue_line_available(db: Session, doctor_id: int, center_id: int, specialty_id: int | None = None) -> bool:
    query = select(QueueLine.id).where(
        QueueLine.doctor_id == doctor_id, QueueLine.center_id == center_id, QueueLine.is_active.is_(True),
    )
    if specialty_id is not None:
        query = query.where(or_(QueueLine.specialty_id.is_(None), QueueLine.specialty_id == specialty_id))
    return db.scalar(query.limit(1)) is not None


def ensure_booking_mode(db: Session, doctor_id: int, center_id: int, day: date, mode: str, specialty_id: int | None = None) -> None:
    if not effective_policy(db, doctor_id, center_id, day).allows(mode):
        raise HTTPException(409, "La modalidad elegida no está permitida para esta jornada")
    if mode == "queue" and multimode_schema_ready(db) and not queue_line_available(db, doctor_id, center_id, specialty_id):
        raise HTTPException(409, "Configure una línea de turnos para utilizar esta modalidad")


def organization_today(db: Session) -> date:
    organization_id = db.info.get("organization_id") if isinstance(db, Session) else None
    organization = db.get(Organization, organization_id) if organization_id else None
    return datetime.now(ZoneInfo(organization.timezone)).date() if organization else date.today()


def ensure_legacy_day_consistent(db: Session, doctor_id: int, center_id: int, day: date, mode: str, *, exclude_id: int | None = None) -> None:
    if multimode_schema_ready(db):
        return
    query = select(Appointment.id).where(
        Appointment.doctor_id == doctor_id, Appointment.center_id == center_id,
        Appointment.appointment_date == day, Appointment.schedule_mode != mode,
    )
    if exclude_id is not None:
        query = query.where(Appointment.id != exclude_id)
    if db.scalar(query.limit(1)) is not None:
        raise HTTPException(409, "La jornada ya tiene citas con otra modalidad")


def ensure_legacy_base_change_consistent(db: Session, doctor_id: int, center_id: int, mode: str) -> None:
    if multimode_schema_ready(db):
        return
    days = db.scalars(select(Appointment.appointment_date).where(
        Appointment.doctor_id == doctor_id, Appointment.center_id == center_id,
        Appointment.appointment_date >= organization_today(db),
    ).distinct()).all()
    for day in days:
        ensure_legacy_day_consistent(db, doctor_id, center_id, day, exception_mode(db, doctor_id, center_id, day) or mode)
