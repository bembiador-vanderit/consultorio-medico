from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Appointment, Notification, User


def sync_appointment_reminders(
    db: Session,
    *,
    now: datetime | None = None,
    horizon_hours: int = 24,
) -> int:
    """Create idempotent in-app reminders for appointments in the next 24 hours.

    Reminders are generated for the assigned doctor and active secretaries
    assigned to the appointment's center. Existing reminders are detected by
    recipient + appointment + notification type, so repeated scheduler runs
    cannot create duplicates.
    """
    now = now or datetime.utcnow()
    horizon = now + timedelta(hours=horizon_hours)

    appointments = db.scalars(
        select(Appointment).where(
            Appointment.appointment_date >= now.date(),
            Appointment.status.notin_(["cancelled", "canceled", "completed"]),
        )
    ).all()

    created = 0
    for appointment in appointments:
        appointment_at = datetime.combine(
            appointment.appointment_date,
            appointment.appointment_time,
        )
        if appointment_at < now or appointment_at > horizon:
            continue

        recipients = {appointment.doctor_id}
        if appointment.center_id is not None:
            for user in db.scalars(
                select(User).where(User.is_active.is_(True)).join(User.centers).where(
                    User.centers.any(id=appointment.center_id)
                )
            ).all():
                if any(role.code == "secretary" for role in user.roles):
                    recipients.add(user.id)

        message = (
            f"{appointment.patient.first_name} {appointment.patient.last_name} — "
            f"{appointment_at:%d/%m/%Y %H:%M}"
        )
        for user_id in recipients:
            existing = db.scalar(
                select(Notification.id).where(
                    Notification.user_id == user_id,
                    Notification.appointment_id == appointment.id,
                    Notification.notification_type == "appointment_due",
                ).limit(1)
            )
            if existing:
                continue
            db.add(
                Notification(
                    user_id=user_id,
                    appointment_id=appointment.id,
                    title="Cita próxima",
                    message=message,
                    notification_type="appointment_due",
                )
            )
            created += 1

    if created:
        db.commit()
    return created
