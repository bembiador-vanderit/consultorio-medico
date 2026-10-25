"""One presentation renderer for sample previews and persisted financial records."""
from io import BytesIO
from decimal import Decimal
from html import escape

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_RIGHT
from reportlab.lib.pagesizes import A4, letter
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle

from app.services.document_designer import DOCUMENT_TYPES


def cash(value):
    return f"DOP {Decimal(str(value)).quantize(Decimal('0.01')):,.2f}"


def sample_data(kind: str):
    common = {"organization": "Atlas Pérgamo · Ejemplo", "center": "Centro de muestra", "issued_at": "18/10/2026 10:00",
              "issuer": "Usuario de muestra", "is_sample": True}
    if kind == "invoice":
        return {**common, "number": "INT-1-00000001", "patient": "Paciente de muestra", "concept": "Consulta de muestra",
                "totals": [("Total", cash('2000')), ("Cobertura ARS", cash('500')), ("Parte paciente", cash('1500')),
                           ("Pagado por paciente", cash('1000')), ("Saldo paciente", cash('500'))],
                "details": [("Métodos de pago", "Efectivo DOP 1,000.00")], "status": "Pago parcial"}
    if kind == "receipt":
        return {**common, "number": "PAGO-00000001", "invoice": "INT-1-00000001", "patient": "Paciente de muestra",
                "totals": [("Monto recibido", cash('1000')), ("Saldo posterior", cash('500'))],
                "details": [("Método", "Efectivo DOP 1,000.00")], "status": "Vigente"}
    return {**common, "number": "CAJA-00000001", "issuer": "Cajero de muestra",
            "details": [("Apertura", "18/10/2026 08:00"), ("Cierre", "18/10/2026 18:00")],
            "totals": [("Fondo inicial", cash('2000')), ("Cobrado efectivo", cash('600')),
                       ("Cobrado tarjeta", cash('0')), ("Cobrado transferencia", cash('500')),
                       ("Reversos", cash('0')), ("Efectivo esperado", cash('2600')),
                       ("Efectivo contado", cash('2600')), ("Diferencia", cash('0'))],
            "movements": [("#1", "Efectivo", cash('600')), ("#2", "Transferencia", cash('500'))], "status": "Cerrada"}


def render_financial_pdf(kind: str, data: dict, definition: dict) -> bytes:
    if kind not in DOCUMENT_TYPES:
        raise ValueError("Tipo documental no disponible")
    sink = BytesIO()
    page = A4 if definition.get("page_format") == "A4" else letter
    if definition.get("orientation") == "landscape":
        page = (page[1], page[0])
    margin = min(25, max(10, int(definition.get("margin_mm", 18)))) * mm
    doc = SimpleDocTemplate(sink, pagesize=page, leftMargin=margin, rightMargin=margin,
                            topMargin=margin, bottomMargin=margin)
    black = definition.get("print_mode") == "bw"
    accent = colors.HexColor("#444444" if black else definition.get("accent_color", "#087f83"))
    soft = colors.HexColor("#f0f0f0" if black else "#eaf5f5")
    if black and not definition.get("ink_saver", True):
        soft = colors.HexColor("#e3e3e3")
    face = definition.get("typography", "Helvetica")
    if face not in {"Helvetica", "Times-Roman", "Courier"}:
        face = "Helvetica"
    text = ParagraphStyle("text", fontName=face, fontSize=9, leading=14, textColor=colors.black)
    small = ParagraphStyle("small", parent=text, fontSize=7.5, leading=11)
    title = ParagraphStyle("title", parent=text, fontName="Helvetica-Bold", fontSize=15, leading=19, textColor=accent)
    section = ParagraphStyle("section", parent=text, fontName="Helvetica-Bold", fontSize=9, leading=14)
    right = ParagraphStyle("right", parent=text, alignment=TA_RIGHT)
    center = ParagraphStyle("center", parent=text, alignment=TA_CENTER)
    safe = lambda value: escape(str(value if value is not None else ""))
    story = []
    header = []
    if definition.get("show_logo", True):
        header.append(Paragraph("ATLAS PÉRGAMO", title))
    if definition.get("show_organization", True):
        header.append(Paragraph(safe(data.get("organization", "")), text))
    if definition.get("show_center", True):
        header.append(Paragraph(safe(data.get("center", "")), small))
    header_style = definition.get("header_style", "plain")
    if header:
        header_table = Table([[item] for item in header], colWidths=[doc.width])
        header_background = (colors.white if header_style == "plain" else
                             colors.HexColor("#e7e7e7" if header_style == "medium" and black else
                                             "#f3f3f3" if black else "#d9ebea" if header_style == "medium" else "#edf7f6"))
        header_table.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, -1), header_background),
            ("LINEBELOW", (0, -1), (-1, -1), .8, accent), ("BOTTOMPADDING", (0, -1), (-1, -1), 8)]))
        story.append(header_table)
    story.extend([Spacer(1, 9), Table([[Paragraph(DOCUMENT_TYPES[kind].upper(), title), Paragraph(safe(data.get("number", "")), right)]],
                                      colWidths=[doc.width * .64, doc.width * .36])])
    story.append(Spacer(1, 9))
    info = [("Fecha", data.get("issued_at", "")), ("Estado", data.get("status", ""))]
    if data.get("patient"):
        info.append(("Paciente", data["patient"]))
    if data.get("invoice"):
        info.append(("Factura", data["invoice"]))
    if data.get("concept"):
        info.append(("Concepto", data["concept"]))
    if data.get("issuer"):
        info.append(("Usuario", data["issuer"]))
    section_style = definition.get("section_style", "soft")
    story.append(_rows(info, doc.width, text, section, safe, soft, section_style))
    story.extend([Spacer(1, 12), Paragraph("Importes y desglose", section), Spacer(1, 4)])
    story.append(_rows(data.get("totals", []), doc.width, text, section, safe, soft, section_style))
    if data.get("details"):
        story.extend([Spacer(1, 10), Paragraph("Detalles", section), Spacer(1, 4),
                      _rows(data["details"], doc.width, text, section, safe, soft, section_style)])
    if data.get("movements"):
        story.extend([Spacer(1, 10), Paragraph("Movimientos de Caja", section), Spacer(1, 4)])
        lines = [[Paragraph(safe(a), text), Paragraph(safe(b), text), Paragraph(safe(c), right)] for a, b, c in data["movements"]]
        table = Table(lines, colWidths=[doc.width * .18, doc.width * .54, doc.width * .28], repeatRows=0)
        table.setStyle(TableStyle([("LINEBELOW", (0, 0), (-1, -1), .25, colors.lightgrey),
                                   ("VALIGN", (0, 0), (-1, -1), "TOP"), ("TOPPADDING", (0, 0), (-1, -1), 5)]))
        story.append(table)
    if data.get("reversal_notice"):
        story.extend([Spacer(1, 10), Paragraph(safe(data["reversal_notice"]), section)])
    if definition.get("show_professional", False) and data.get("professional"):
        story.extend([Spacer(1, 16), Paragraph(safe(data["professional"]), center)])
    note = definition.get("footer_note", "Documento interno. No es comprobante fiscal.")
    story.extend([Spacer(1, 20), Paragraph(safe(note), small)])
    if data.get("is_sample"):
        story.append(Paragraph("VISTA PREVIA · DATOS FICTICIOS", small))
    doc.build(story)
    return sink.getvalue()


def _rows(rows, width, text, section, safe, soft, section_style):
    body = [[Paragraph(safe(k), section), Paragraph(safe(v), text)] for k, v in rows]
    table = Table(body, colWidths=[width * .42, width * .58], hAlign="LEFT")
    shade = (colors.white if section_style == "plain" else
             colors.HexColor("#e0e0e0" if soft.red == soft.green else "#d9ebea") if section_style == "medium" else soft)
    table.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, -1), shade),
                               ("ROWBACKGROUNDS", (0, 0), (-1, -1), [shade, colors.white]),
                               ("LINEBELOW", (0, 0), (-1, -1), .3, colors.lightgrey),
                               ("VALIGN", (0, 0), (-1, -1), "TOP"),
                               ("LEFTPADDING", (0, 0), (-1, -1), 8), ("TOPPADDING", (0, 0), (-1, -1), 5),
                               ("BOTTOMPADDING", (0, 0), (-1, -1), 5)]))
    return table
