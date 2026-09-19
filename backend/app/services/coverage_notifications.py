from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Appointment, CareCenter, ClinicalCoverage, Notification, Role, User
from app.services.appointment_scope import secretary_can_manage


TRANSFER_NOTIFICATION_TYPE = "coverage_transfer"
RESTORE_NOTIFICATION_TYPE = "coverage_restored"


def _recipient_ids(db: Session, coverage: ClinicalCoverage) -> set[int]:
    recipients: set[int] = set()
    substitute = db.get(User, coverage.substitute_doctor_id)
    if substitute is not None and substitute.is_active:
        recipients.add(substitute.id)

    secretaries = db.scalars(
        select(User).where(
            User.is_active.is_(True),
            User.roles.any(Role.code == "secretary"),
            User.centers.any(CareCenter.id == coverage.center_id),
        )
    ).unique().all()
    for secretary in secretaries:
        if secretary_can_manage(secretary, coverage.center_id, coverage.substitute_doctor_id, db) or secretary_can_manage(
            secretary, coverage.center_id, coverage.principal_doctor_id, db
        ):
            recipients.add(secretary.id)
    return recipients


def add_coverage_appointment_notifications(
    db: Session,
    appointment: Appointment,
    coverage: ClinicalCoverage,
    *,
    restored: bool = False,
) -> None:
    notification_type = RESTORE_NOTIFICATION_TYPE if restored else TRANSFER_NOTIFICATION_TYPE
    appointment_at = datetime.combine(appointment.appointment_date, appointment.appointment_time)
    if restored:
        title = "Cita restaurada por cobertura"
        message = (
            f"La cita por cobertura de {coverage.principal.full_name} para el "
            f"{appointment_at:%d/%m/%Y a las %H:%M} fue restaurada al médico principal."
        )
    else:
        title = "Nueva cita transferida por cobertura"
        message = (
            f"Se te ha transferido una cita por cobertura de {coverage.principal.full_name} para el "
            f"{appointment_at:%d/%m/%Y a las %H:%M}."
        )

    for user_id in _recipient_ids(db, coverage):
        existing = db.scalar(
            select(Notification).where(
                Notification.user_id == user_id,
                Notification.appointment_id == appointment.id,
                Notification.notification_type == notification_type,
            ).limit(1)
        )
        if existing is not None:
            existing.title = title
            existing.message = message
            existing.is_read = False
            existing.read_at = None
            existing.created_at = datetime.now(UTC).replace(tzinfo=None)
        else:
            db.add(Notification(
                user_id=user_id,
                appointment_id=appointment.id,
                title=title,
                message=message,
                notification_type=notification_type,
            ))
