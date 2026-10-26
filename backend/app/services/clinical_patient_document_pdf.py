"""Monochrome printable representation of signed or draft clinical records."""
from io import BytesIO
from xml.sax.saxutils import escape

from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer

from app.services.clinical_patient_document_fields import PHYSICAL_EXAM_FIELDS, PREOPERATIVE_SECTIONS


def build_document_pdf(document: dict) -> bytes:
    buffer = BytesIO()
    title = "Evaluación médica preoperatoria" if document["kind"] == "preoperative" else "Examen físico"
    pdf = SimpleDocTemplate(buffer, pagesize=A4, leftMargin=18 * mm, rightMargin=18 * mm,
                            topMargin=16 * mm, bottomMargin=16 * mm, title=title, author="Atlas Pérgamo")
    styles = getSampleStyleSheet()
    profile = document["patient_profile"] or {}
    status_label = {"draft": "Borrador", "pending_evaluation": "Pendiente de evaluación",
                    "completed": "Completada", "signed": "Firmada"}[document["status"]]
    story = [Paragraph(escape(title.upper()), styles["Title"]),
             Paragraph(f"Estado: {status_label} · Fecha: {document['document_date']}", styles["Normal"]),
             Spacer(1, 5 * mm)]
    for label, value in (
        ("Paciente", profile.get("patient_name")), ("Fecha de nacimiento", profile.get("date_of_birth")),
        ("Edad en la fecha del documento", profile.get("age_at_document")),
        ("Sexo registrado", profile.get("sex")), ("Ocupación", profile.get("occupation")),
        ("Documento", profile.get("document_number")), ("Teléfono", profile.get("phone")),
        ("Dirección", profile.get("address")), ("ARS", profile.get("insurance_company")),
        ("Plan", profile.get("insurance_plan")), ("Médico tratante", profile.get("doctor_name")),
        ("Centro", profile.get("center_name")),
    ):
        if value:
            story.append(Paragraph(f"<b>{escape(label)}:</b> {escape(str(value))}", styles["Normal"]))
    sections = PREOPERATIVE_SECTIONS if document["kind"] == "preoperative" else (("Examen físico", PHYSICAL_EXAM_FIELDS),)
    values = document["values"] or {}
    for heading, fields in sections:
        lines = [Paragraph(escape(heading), styles["Heading2"])]
        lines.extend(Paragraph(f"<b>{escape(label)}:</b> {escape(values.get(key) or '—').replace(chr(10), '<br/>')}", styles["Normal"])
                     for key, label in fields)
        story.extend(lines)
    if document["status"] == "signed":
        story.extend([Spacer(1, 8 * mm), Paragraph(f"Firmada por: {escape(profile.get('doctor_name') or '')}", styles["Normal"]),
                      Paragraph(f"Fecha de firma: {document['signed_at']}", styles["Normal"])])
    else:
        story.append(Paragraph("Documento sin firma clínica", styles["Normal"]))
    pdf.build(story)
    return buffer.getvalue()
