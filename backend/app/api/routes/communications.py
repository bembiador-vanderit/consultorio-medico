from fastapi import APIRouter, Depends, HTTPException, status

from app.api.deps import current_user
from app.models import User
from app.schemas.communications import CommunicationResponse, EmailSendRequest, WhatsAppSendRequest
from app.services.communication import build_whatsapp_link, send_email, send_whatsapp

router = APIRouter(prefix="/communications", tags=["Comunicaciones"])


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
    action_url = build_whatsapp_link(payload.phone, payload.message)
    try:
        send_whatsapp(payload.phone, payload.message)
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail="No fue posible enviar el mensaje por WhatsApp") from exc
    settings_mode = "api" if action_url and action_url.startswith("https://wa.me/") else "manual"
    return CommunicationResponse(
        channel="whatsapp",
        status="sent" if settings_mode == "api" else "ready",
        detail="Mensaje enviado por WhatsApp" if settings_mode == "api" else "Enlace de WhatsApp generado; configure la API para envío automático",
        action_url=action_url,
    )
