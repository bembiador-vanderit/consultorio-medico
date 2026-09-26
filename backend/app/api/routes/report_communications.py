from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.api.deps import require_permission
from app.db import get_db
from app.models import User
from app.api.routes.reports import build_appointment_report_pdf, get_appointment_rows, report_filename, fmt_date
from app.services.communication import build_whatsapp_link, send_whatsapp_document

router = APIRouter(prefix="/communications/reports", tags=["Comunicaciones"])
access = require_permission("patients:access")


@router.post("/appointments/whatsapp")
def appointment_report_whatsapp(
    phone: str,
    start: date | None = Query(None),
    end: date | None = Query(None),
    appointment_status: str | None = Query(None),
    doctor_id: int | None = Query(None),
    center_id: int | None = Query(None),
    search: str | None = Query(None),
    user: User = Depends(access),
    db: Session = Depends(get_db),
):
    appointments = get_appointment_rows(
        start=start,
        end=end,
        appointment_status=appointment_status,
        doctor_id=doctor_id,
        center_id=center_id,
        search=search,
        user=user,
        db=db,
    )
    if not appointments:
        raise HTTPException(status_code=422, detail="No hay citas para enviar en el reporte")

    normalized_phone = "".join(ch for ch in phone if ch.isdigit())
    if len(normalized_phone) < 8:
        raise HTTPException(status_code=422, detail="Número de WhatsApp inválido")

    period = f"{fmt_date(start) if start else 'Inicio'} - {fmt_date(end) if end else 'Fin'}"
    filename = report_filename(start, end)
    caption = f"Reporte de citas de Atlas Consultorio. Período: {period}. Total de citas: {len(appointments)}."
    content = build_appointment_report_pdf(appointments, start, end)

    try:
        action_url = send_whatsapp_document(normalized_phone, filename, content, caption)
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="No fue posible enviar el reporte PDF por WhatsApp",
        ) from exc

    from app.core.config import get_settings
    settings = get_settings()
    automatic = bool(settings.whatsapp_access_token and settings.whatsapp_phone_number_id)
    return {
        "channel": "whatsapp",
        "status": "sent" if automatic else "ready",
        "detail": "Reporte PDF enviado por WhatsApp" if automatic else "Enlace de WhatsApp generado; configure la API para envío automático",
        "action_url": action_url,
        "filename": filename,
        "appointments": len(appointments),
    }
