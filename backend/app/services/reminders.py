from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models import Appointment, CommunicationLog, Notification, User
from app.services.appointment_scope import secretary_can_manage
from app.services.clinical_coverage import installation_now
from app.services.communication import send_email, send_whatsapp


REMINDER_TYPE = "appointment_due"
EMAIL_REMINDER_TYPE = "appointment_due_email"
WHATSAPP_REMINDER_TYPE = "appointment_due_whatsapp"


def _appointment_message(appointment: Appointment) -> str:
    patient = appointment.patient
    doctor = appointment.doctor
    center = appointment.center
    center_text = center.name if center else "Centro de atención pendiente"
    return (
        f"Estimado/a {patient.first_name} {patient.last_name},\n\n"
        "Le recordamos su próxima cita médica:\n"
        f"Fecha: {appointment.appointment_date:%d/%m/%Y}\n"
        f"Hora: {appointment.appointment_time:%I:%M %p}\n"
        f"Médico: Dr. {doctor.full_name}\n"
        f"Centro: {center_text}\n\n"
        "Si necesita reprogramar su cita, comuníquese con el consultorio."
    )


def _already_sent(db: Session, appointment_id: int, notification_type: str, *, user_id: int | None = None) -> bool:
    query = select(Notification.id).where(
        Notification.appointment_id == appointment_id,
        Notification.notification_type == notification_type,
    )
    if user_id is not None:
        query = query.where(Notification.user_id == user_id)
    return db.scalar(query.limit(1)) is not None


def _in_app_recipient_ids(db: Session, appointment: Appointment) -> set[int]:
    recipients = {appointment.doctor_id}
    if appointment.center_id is None:
        return recipients
    for user in db.scalars(
        select(User).where(User.is_active.is_(True)).join(User.centers).where(
            User.centers.any(id=appointment.center_id)
        )
    ).all():
        if not any(role.code == "secretary" for role in user.roles):
            continue
        transfer = appointment.coverage_transfer
        if secretary_can_manage(user, appointment.center_id, appointment.doctor_id, db) or (
            transfer is not None
            and secretary_can_manage(user, appointment.center_id, transfer.original_doctor_id, db)
        ):
            recipients.add(user.id)
    return recipients


def sync_in_app_appointment_reminder(
    db: Session,
    appointment: Appointment,
    *,
    now: datetime | None = None,
    horizon_hours: int = 24,
    refresh_existing: bool = False,
) -> int:
    """Upsert the in-app reminder for one future appointment without committing."""
    now = now or installation_now()
    appointment_at = datetime.combine(appointment.appointment_date, appointment.appointment_time)
    if (
        appointment.status not in {"scheduled", "confirmed"}
        or appointment_at < now
        or appointment_at > now + timedelta(hours=horizon_hours)
    ):
        return 0

    message = (
        f"{appointment.patient.first_name} {appointment.patient.last_name}"
        f" — {appointment_at:%d/%m/%Y %H:%M}"
    )
    changed = 0
    for user_id in _in_app_recipient_ids(db, appointment):
        existing = db.scalar(select(Notification).where(
            Notification.user_id == user_id,
            Notification.appointment_id == appointment.id,
            Notification.notification_type == REMINDER_TYPE,
        ))
        if existing is None:
            db.add(Notification(
                user_id=user_id,
                appointment_id=appointment.id,
                title="Cita próxima",
                message=message,
                notification_type=REMINDER_TYPE,
            ))
            changed += 1
        elif refresh_existing:
            existing.title = "Cita próxima"
            existing.message = message
            existing.is_read = False
            existing.read_at = None
            existing.created_at = datetime.utcnow()
            changed += 1
    return changed


def _log_delivery(
    db: Session,
    appointment: Appointment,
    channel: str,
    recipient: str,
    status: str,
    error_message: str | None = None,
) -> None:
    db.add(
        CommunicationLog(
            patient_id=appointment.patient_id,
            appointment_id=appointment.id,
            channel=channel,
            status=status,
            recipient=recipient,
            error_message=error_message,
            sent_at=datetime.utcnow() if status == "sent" else None,
        )
    )


def _mark_channel_sent(db: Session, appointment: Appointment, notification_type: str, title: str, message: str) -> None:
    db.add(
        Notification(
            user_id=appointment.doctor_id,
            appointment_id=appointment.id,
            title=title,
            message=message,
            notification_type=notification_type,
        )
    )


def sync_appointment_reminders(db: Session, *, now: datetime | None = None, horizon_hours: int = 24) -> int:
    """Create in-app reminders and attempt configured patient email/WhatsApp delivery."""
    now = now or installation_now()
    horizon = now + timedelta(hours=horizon_hours)
    appointments = db.scalars(
        select(Appointment).where(
            Appointment.appointment_date >= now.date(),
            Appointment.status.notin_(["cancelled", "canceled", "completed"]),
        )
    ).all()

    created = 0
    for appointment in appointments:
        appointment_at = datetime.combine(appointment.appointment_date, appointment.appointment_time)
        if appointment_at < now or appointment_at > horizon:
            continue

        message = _appointment_message(appointment)
        created += sync_in_app_appointment_reminder(db, appointment, now=now, horizon_hours=horizon_hours)

        if appointment.patient.email and not _already_sent(db, appointment.id, EMAIL_REMINDER_TYPE):
            try:
                send_email(
                    appointment.patient.email,
                    f"Recordatorio de cita médica - {appointment.appointment_date:%d/%m/%Y}",
                    message,
                )
            except Exception as exc:
                _log_delivery(db, appointment, "email", appointment.patient.email, "failed", str(exc))
            else:
                _mark_channel_sent(db, appointment, EMAIL_REMINDER_TYPE, "Recordatorio enviado por correo", message)
                _log_delivery(db, appointment, "email", appointment.patient.email, "sent")
                created += 1

        if appointment.patient.phone and not _already_sent(db, appointment.id, WHATSAPP_REMINDER_TYPE):
            try:
                whatsapp_result = send_whatsapp(appointment.patient.phone, message)
            except Exception as exc:
                _log_delivery(db, appointment, "whatsapp", appointment.patient.phone, "failed", str(exc))
            else:
                settings_configured = whatsapp_result == "" or not whatsapp_result.startswith("https://wa.me/")
                if settings_configured:
                    _mark_channel_sent(db, appointment, WHATSAPP_REMINDER_TYPE, "Recordatorio enviado por WhatsApp", message)
                    _log_delivery(db, appointment, "whatsapp", appointment.patient.phone, "sent")
                    created += 1
                else:
                    _log_delivery(db, appointment, "whatsapp", appointment.patient.phone, "pending", "WhatsApp API no configurada; se generó enlace wa.me")

    if created or db.new:
        try:
            db.commit()
        except IntegrityError:
            # The dashboard sync and the worker can race. The database key is
            # the final arbiter; a competing transaction already created it.
            db.rollback()
            return 0
    return created
