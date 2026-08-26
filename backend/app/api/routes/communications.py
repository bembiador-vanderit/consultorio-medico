from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import current_user, require_permission
from app.db import get_db
from app.core.config import get_settings
from app.models import Appointment, CommunicationLog, User
from app.schemas.communications import (
    CommunicationHistoryItem,
    CommunicationResponse,
    EmailSendRequest,
    WhatsAppSendRequest,
)
from app.services.communication import build_whatsapp_link, send_email, send_whatsapp

router = APIRouter(prefix="/communications", tags=["Comunicaciones"])
access = require_permission("patients:access")


def is_role(user: User, code: str) -> bool:
    return any(role.code == code for role in user.roles)


def assigned_center_ids(user: User) -> set[int]:
    return {center.id for center in user.centers if center.is_active}


def appointment_message(appointment: Appointment) -> str:
    patient = appointment.patient
    doctor = appointment.doctor
    center = appointment.center
    patient_name = f"{patient.first_name} {patient.last_name}"
    center_text = center.name if center else "Centro de atención pendiente"
    city_text = f" ({center.city})" if center and center.city else ""
    reason_text = f"\nMotivo: {appointment.reason}" if appointment.reason else ""
    return (
        f"Estimado/a {patient_name},\n\n"
        "Le recordamos los datos de su cita médica:\n"
        f"Fecha: {appointment.appointment_date.strftime('%d/%m/%Y')}\n"
        f"Hora: {appointment.appointment_time.strftime('%I:%M %p')}\n"
        f"Médico: Dr. {doctor.full_name}\n"
        f"Centro: {center_text}{city_text}"
        f"{reason_text}\n\n"
        "Si necesita reprogramar su cita, comuníquese con el consultorio."
    )


@router.get("/history", response_model=list[CommunicationHistoryItem])
def communication_history(
    user: User = Depends(access),
    db: Session = Depends(get_db),
    patient_id: int | None = Query(default=None, ge=1),
    appointment_id: int | None = Query(default=None, ge=1),
    channel: str | None = Query(default=None, min_length=1, max_length=20),
    communication_status: str | None = Query(default=None, alias="status", min_length=1, max_length=20),
    limit: int = Query(default=100, ge=1, le=500),
):
    query = select(CommunicationLog).join(CommunicationLog.patient)

    if patient_id is not None:
        query = query.where(CommunicationLog.patient_id == patient_id)
    if appointment_id is not None:
        query = query.where(CommunicationLog.appointment_id == appointment_id)
    if channel is not None:
        query = query.where(CommunicationLog.channel == channel)
    if communication_status is not None:
        query = query.where(CommunicationLog.status == communication_status)

    if is_role(user, "secretary"):
        center_ids = assigned_center_ids(user)
        if not center_ids:
            return []
        query = query.join(CommunicationLog.appointment, isouter=True).where(
            Appointment.center_id.in_(center_ids)
        )

    logs = db.scalars(
        query.order_by(CommunicationLog.created_at.desc()).limit(limit)
    ).all()
    return logs


@router.post("/email", response_model=CommunicationResponse)
def deliver_email(payload: EmailSendRequest, _: User = Depends(current_user)):
    try:
        send_email(str(payload.to), payload.subject, payload.body)
    except RuntimeError as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail="No fue posible enviar el correo") from exc
    return CommunicationResponse(channel="email", status="sent", detail="Correo enviado correctamente")


@router.post("/whatsapp", response_model=CommunicationResponse)
def deliver_whatsapp(payload: WhatsAppSendRequest, _: User = Depends(current_user)):
    settings = get_settings()
    action_url = build_whatsapp_link(payload.phone, payload.message)
    try:
        send_whatsapp(payload.phone, payload.message)
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail="No fue posible enviar el mensaje por WhatsApp") from exc

    automatic = bool(settings.whatsapp_access_token and settings.whatsapp_phone_number_id)
    return CommunicationResponse(
        channel="whatsapp",
        status="sent" if automatic else "ready",
        detail="Mensaje enviado por WhatsApp" if automatic else "Enlace de WhatsApp generado; configure la API para envío automático",
        action_url=action_url,
    )


@router.post("/appointments/{appointment_id}/{channel}", response_model=CommunicationResponse)
def deliver_appointment(appointment_id: int, channel: str, user: User = Depends(access), db: Session = Depends(get_db)):
    if channel not in {"email", "whatsapp"}:
        raise HTTPException(status_code=400, detail="Canal no soportado")

    appointment = db.get(Appointment, appointment_id)
    if not appointment:
        raise HTTPException(status_code=404, detail="Cita no encontrada")

    if is_role(user, "secretary") and appointment.center_id not in assigned_center_ids(user):
        raise HTTPException(status_code=403, detail="No tiene acceso a esta cita")

    message = appointment_message(appointment)
    subject = f"Confirmación de cita médica - {appointment.appointment_date.strftime('%d/%m/%Y')}"

    if channel == "email":
        if not appointment.patient.email:
            raise HTTPException(status_code=422, detail="El paciente no tiene correo electrónico registrado")
        try:
            send_email(appointment.patient.email, subject, message)
        except RuntimeError as exc:
            raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)) from exc
        except Exception as exc:
            raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail="No fue posible enviar el correo de la cita") from exc
        return CommunicationResponse(channel="email", status="sent", detail="Confirmación de cita enviada por correo")

    if not appointment.patient.phone:
        raise HTTPException(status_code=422, detail="El paciente no tiene teléfono registrado")
    action_url = build_whatsapp_link(appointment.patient.phone, message)
    try:
        send_whatsapp(appointment.patient.phone, message)
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail="No fue posible enviar la cita por WhatsApp") from exc

    settings = get_settings()
    automatic = bool(settings.whatsapp_access_token and settings.whatsapp_phone_number_id)
    return CommunicationResponse(
        channel="whatsapp",
        status="sent" if automatic else "ready",
        detail="Confirmación de cita enviada por WhatsApp" if automatic else "Enlace de WhatsApp generado para la cita",
        action_url=action_url,
    )
