from datetime import date
from io import BytesIO

from fastapi import APIRouter, Depends, Query, HTTPException, status
from fastapi.responses import StreamingResponse
from pydantic import EmailStr
from sqlalchemy import select
from sqlalchemy.orm import Session
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle

from app.api.deps import require_permission
from app.core.config import get_settings
from app.db import get_db
from app.models import Appointment, User
from app.services.communication import send_email_with_attachment

router = APIRouter(prefix="/reports", tags=["Reportes"])
access = require_permission("patients:access")


def is_role(user: User, code: str) -> bool:
    return any(role.code == code for role in user.roles)


def assigned_center_ids(user: User) -> set[int]:
    return {center.id for center in user.centers if center.is_active}


def fmt_date(value: date) -> str:
    return value.strftime("%d/%m/%Y")


def get_appointment_rows(
    *,
    start: date | None,
    end: date | None,
    appointment_status: str | None,
    doctor_id: int | None,
    center_id: int | None,
    search: str | None,
    user: User,
    db: Session,
) -> list[Appointment]:
    query = select(Appointment).order_by(Appointment.appointment_date, Appointment.appointment_time)
    if start:
        query = query.where(Appointment.appointment_date >= start)
    if end:
        query = query.where(Appointment.appointment_date <= end)
    if appointment_status:
        query = query.where(Appointment.status == appointment_status)
    if doctor_id:
        query = query.where(Appointment.doctor_id == doctor_id)
    if center_id:
        query = query.where(Appointment.center_id == center_id)

    if is_role(user, "secretary"):
        ids = assigned_center_ids(user)
        query = query.where(Appointment.center_id.in_(ids)) if ids else query.where(Appointment.id == -1)
    elif is_role(user, "doctor"):
        query = query.where(Appointment.doctor_id == user.id)

    appointments = list(db.scalars(query).all())
    needle = (search or "").strip().lower()
    if needle:
        appointments = [
            appointment for appointment in appointments
            if needle in " ".join([
                f"{appointment.patient.first_name} {appointment.patient.last_name}",
                appointment.doctor.full_name,
                appointment.center.name if appointment.center else "",
                appointment.reason or "",
            ]).lower()
        ]
    return appointments


def build_appointment_report_pdf(appointments: list[Appointment], start: date | None, end: date | None) -> bytes:
    buffer = BytesIO()
    document = SimpleDocTemplate(
        buffer, pagesize=A4, rightMargin=14 * mm, leftMargin=14 * mm,
        topMargin=14 * mm, bottomMargin=14 * mm,
        title="Reporte de citas", author="Atlas Consultorio",
    )
    styles = getSampleStyleSheet()
    title_style = ParagraphStyle("ReportTitle", parent=styles["Title"], alignment=TA_CENTER, fontSize=16, leading=20, spaceAfter=4 * mm)
    small_style = ParagraphStyle("ReportSmall", parent=styles["Normal"], fontSize=8, leading=10)
    cell_style = ParagraphStyle("ReportCell", parent=styles["Normal"], fontSize=7.5, leading=9)

    story = [Paragraph("Atlas Consultorio", title_style), Paragraph("Reporte de citas", styles["Heading2"])]
    period = f"{fmt_date(start) if start else 'Inicio'} - {fmt_date(end) if end else 'Fin'}"
    story.append(Paragraph(f"Período: {period} &nbsp;&nbsp; Total: {len(appointments)}", small_style))
    story.append(Spacer(1, 5 * mm))

    rows = [["Fecha", "Hora", "Paciente", "Médico", "Centro", "Estado", "Motivo"]]
    labels = {"scheduled": "Programada", "confirmed": "Confirmada", "completed": "Completada", "cancelled": "Cancelada", "no_show": "No asistió"}
    for appointment in appointments:
        patient_name = f"{appointment.patient.first_name} {appointment.patient.last_name}"
        center_name = appointment.center.name if appointment.center else "—"
        rows.append([
            Paragraph(fmt_date(appointment.appointment_date), cell_style),
            Paragraph(appointment.appointment_time.strftime("%H:%M"), cell_style),
            Paragraph(patient_name, cell_style),
            Paragraph(appointment.doctor.full_name, cell_style),
            Paragraph(center_name, cell_style),
            Paragraph(labels.get(appointment.status, appointment.status), cell_style),
            Paragraph(appointment.reason or "—", cell_style),
        ])

    table = Table(rows, repeatRows=1, colWidths=[19 * mm, 14 * mm, 35 * mm, 34 * mm, 34 * mm, 22 * mm, 31 * mm])
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#0f766e")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, 0), 7.5),
        ("GRID", (0, 0), (-1, -1), 0.35, colors.HexColor("#cbd5e1")),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f8fafc")]),
        ("LEFTPADDING", (0, 0), (-1, -1), 3), ("RIGHTPADDING", (0, 0), (-1, -1), 3),
        ("TOPPADDING", (0, 0), (-1, -1), 3), ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
    ]))
    story.append(table)
    document.build(story)
    return buffer.getvalue()


def report_filename(start: date | None, end: date | None) -> str:
    return f"reporte-citas-{start.isoformat() if start else 'inicio'}-{end.isoformat() if end else 'fin'}.pdf"


@router.get("/appointments/pdf")
def appointment_report_pdf(
    start: date | None = Query(None),
    end: date | None = Query(None),
    status: str | None = Query(None),
    doctor_id: int | None = Query(None),
    center_id: int | None = Query(None),
    search: str | None = Query(None),
    user: User = Depends(access),
    db: Session = Depends(get_db),
):
    appointments = get_appointment_rows(
        start=start, end=end, appointment_status=status, doctor_id=doctor_id,
        center_id=center_id, search=search, user=user, db=db,
    )
    content = build_appointment_report_pdf(appointments, start, end)
    filename = report_filename(start, end)
    return StreamingResponse(BytesIO(content), media_type="application/pdf", headers={"Content-Disposition": f'attachment; filename="{filename}"'})


@router.post("/appointments/email")
def appointment_report_email(
    to: EmailStr,
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
        start=start, end=end, appointment_status=appointment_status, doctor_id=doctor_id,
        center_id=center_id, search=search, user=user, db=db,
    )
    if not appointments:
        raise HTTPException(status_code=422, detail="No hay citas para enviar en el reporte")

    content = build_appointment_report_pdf(appointments, start, end)
    filename = report_filename(start, end)
    settings = get_settings()
    if not settings.smtp_host or not settings.smtp_from:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="SMTP no está configurado")

    period = f"{fmt_date(start) if start else 'Inicio'} - {fmt_date(end) if end else 'Fin'}"
    try:
        send_email_with_attachment(
            str(to),
            f"Reporte de citas - {period}",
            f"Adjunto encontrará el reporte de citas de Atlas Consultorio correspondiente al período {period}. Total de citas: {len(appointments)}.",
            filename=filename,
            content=content,
        )
    except RuntimeError as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail="No fue posible enviar el reporte por correo") from exc

    return {"channel": "email", "status": "sent", "detail": "Reporte PDF enviado por correo"}
