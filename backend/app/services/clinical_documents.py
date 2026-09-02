from datetime import date
from io import BytesIO
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle


def build_requested_tests_pdf(
    *,
    history_id: int,
    consultation_date: date,
    patient_name: str,
    doctor_name: str,
    center_name: str | None,
    center_address: str | None,
    test_names: list[str],
) -> bytes:
    """Build a printable study order from server-owned clinical data."""
    buffer = BytesIO()
    document = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        rightMargin=20 * mm,
        leftMargin=20 * mm,
        topMargin=18 * mm,
        bottomMargin=18 * mm,
        title=f"Orden de estudios #{history_id}",
        author="Atlas Consultorio",
    )
    styles = getSampleStyleSheet()
    title_style = ParagraphStyle(
        "StudyOrderTitle",
        parent=styles["Title"],
        alignment=TA_CENTER,
        textColor=colors.HexColor("#3730a3"),
        fontSize=17,
        leading=21,
        spaceAfter=2 * mm,
    )
    order_title_style = ParagraphStyle(
        "StudyOrderDocumentTitle",
        parent=styles["Heading2"],
        alignment=TA_CENTER,
        spaceAfter=2 * mm,
    )
    subtitle_style = ParagraphStyle(
        "StudyOrderSubtitle",
        parent=styles["Normal"],
        alignment=TA_CENTER,
        textColor=colors.HexColor("#475569"),
        fontSize=9,
        leading=12,
    )
    body_style = ParagraphStyle(
        "StudyOrderBody",
        parent=styles["Normal"],
        fontSize=10,
        leading=14,
    )
    table_header_style = ParagraphStyle(
        "StudyOrderTableHeader",
        parent=body_style,
        textColor=colors.white,
        fontName="Helvetica-Bold",
    )

    safe_center = escape(center_name or "Centro de atención no especificado")
    safe_address = escape(center_address or "")
    story = [
        Paragraph("Atlas Consultorio", title_style),
        Paragraph("ORDEN DE ESTUDIOS Y ANÁLISIS", order_title_style),
        Paragraph(
            f"{safe_center}{f' - {safe_address}' if safe_address else ''}",
            subtitle_style,
        ),
        Spacer(1, 7 * mm),
    ]

    details = [
        [Paragraph("Paciente", body_style), Paragraph(escape(patient_name), body_style)],
        [Paragraph("Médico tratante", body_style), Paragraph(escape(doctor_name), body_style)],
        [Paragraph("Fecha", body_style), Paragraph(consultation_date.strftime("%d/%m/%Y"), body_style)],
        [Paragraph("Historia clínica", body_style), Paragraph(f"#{history_id}", body_style)],
    ]
    details_table = Table(details, colWidths=[38 * mm, 122 * mm])
    details_table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (0, -1), colors.HexColor("#eef2ff")),
                ("TEXTCOLOR", (0, 0), (0, -1), colors.HexColor("#3730a3")),
                ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"),
                ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#cbd5e1")),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("LEFTPADDING", (0, 0), (-1, -1), 7),
                ("RIGHTPADDING", (0, 0), (-1, -1), 7),
                ("TOPPADDING", (0, 0), (-1, -1), 6),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
            ]
        )
    )
    story.extend([details_table, Spacer(1, 9 * mm)])

    rows = [[Paragraph("Estudios solicitados", table_header_style)]]
    rows.extend([[Paragraph(f"[ ] {escape(name)}", body_style)] for name in test_names])
    studies_table = Table(rows, colWidths=[160 * mm], repeatRows=1)
    studies_table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#3730a3")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#cbd5e1")),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("LEFTPADDING", (0, 0), (-1, -1), 8),
                ("RIGHTPADDING", (0, 0), (-1, -1), 8),
                ("TOPPADDING", (0, 0), (-1, -1), 7),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
            ]
        )
    )
    story.extend(
        [
            studies_table,
            Spacer(1, 20 * mm),
            Paragraph("________________________________________", subtitle_style),
            Paragraph(escape(doctor_name), subtitle_style),
            Paragraph("Firma y sello del médico", subtitle_style),
        ]
    )
    def add_page_footer(canvas, doc):
        canvas.saveState()
        canvas.setFillColor(colors.HexColor("#64748b"))
        canvas.setFont("Helvetica", 8)
        canvas.drawString(20 * mm, 10 * mm, f"Atlas Consultorio - Orden #{history_id}")
        canvas.drawRightString(A4[0] - 20 * mm, 10 * mm, f"Página {doc.page}")
        canvas.restoreState()

    document.build(story, onFirstPage=add_page_footer, onLaterPages=add_page_footer)
    return buffer.getvalue()
