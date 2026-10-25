"""Bounded PDF renderer for immutable clinical-form versions."""
import base64
from io import BytesIO

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, letter, landscape
from reportlab.lib.utils import ImageReader, simpleSplit
from reportlab.pdfgen import canvas

from app.schemas.clinical_form import FormDefinition


PROFILE_BINDINGS = {
    "patient.full_name": "patient_name", "patient.birth_date": "date_of_birth",
    "patient.age": "age_at_document", "patient.sex": "sex", "patient.document": "document_number",
    "patient.phone": "phone", "patient.address": "address", "patient.insurance": "insurance_company",
    "doctor.display_name": "doctor_name", "doctor.specialty": "doctor_specialty",
    "center.name": "center_name", "document.date": "document_date",
    "document.created_at": "created_at",
}


def _text(value: object) -> str:
    return str(value or "").replace("\r", " ").replace("\n", " ")


def build_form_pdf(definition: dict, *, values: dict[str, str], profile: dict,
                   document_date: str, status: str, signed_at: object) -> bytes:
    form = FormDefinition.model_validate(definition)
    if not form.pages:
        raise ValueError("La plantilla no contiene páginas")
    output = BytesIO()
    pdf = canvas.Canvas(output, pageCompression=1)
    style = form.appearance
    accent = colors.HexColor(style.primary_color)
    for page in sorted(form.pages, key=lambda item: (item.page_number, item.sort_order)):
        page_size = A4 if page.page_size == "A4" else letter
        if page.orientation == "landscape":
            page_size = landscape(page_size)
        width, height = page_size
        pdf.setPageSize(page_size)
        left, right = page.margins.left * 2.83465, page.margins.right * 2.83465
        top, bottom = page.margins.top * 2.83465, page.margins.bottom * 2.83465
        usable = width - left - right
        y = height - top
        pdf.setFillColor(accent)
        pdf.setFont(style.font, style.font_size + 4)
        if style.show_logo and style.logo_data:
            raw = base64.b64decode(style.logo_data.partition(",")[2])
            pdf.drawImage(ImageReader(BytesIO(raw)), left, y - 32, width=58, height=30,
                          preserveAspectRatio=True, anchor="c", mask="auto")
        heading_x = left + (65 if style.show_logo and style.logo_data else 0)
        for heading in (style.center_heading, style.doctor_heading, style.specialty_heading, style.header, style.subtitle):
            if heading:
                font_size = style.font_size + (3 if heading == style.header else 1)
                pdf.setFont(style.font, font_size)
                for line in simpleSplit(_text(heading), style.font, font_size, width - right - heading_x):
                    pdf.drawString(heading_x, y, line)
                    y -= font_size + 4
        if page.title:
            font_size = style.font_size + 1
            pdf.setFont(style.font, font_size)
            for line in simpleSplit(_text(page.title), style.font, font_size, usable):
                pdf.drawString(left, y, line)
                y -= font_size + 5
        if y < bottom + 80:
            raise ValueError(f"La página {page.page_number} no tiene espacio para el encabezado")
        pdf.setStrokeColor(accent)
        pdf.line(left, y, width - right, y)
        y -= 14
        pdf.setFillColor(colors.black)
        # Identity is snapped by 0055 on signing. Preview supplies synthetic data.
        for label, value in (("Paciente", profile.get("patient_name")), ("Fecha", document_date),
                             ("Médico", profile.get("doctor_name")), ("Centro", profile.get("center_name"))):
            if value:
                pdf.setFont(style.font, style.font_size)
                for line in simpleSplit(f"{label}: {_text(value)}", style.font, style.font_size, usable):
                    pdf.drawString(left, y, line)
                    y -= style.font_size + 4
                if y < bottom + 40:
                    raise ValueError(f"La página {page.page_number} no tiene espacio para la identificación")
        y -= 7
        for section in sorted(page.sections, key=lambda item: item.sort_order):
            if not section.printable:
                continue
            if y < bottom + 35:
                raise ValueError(f"La página {page.page_number} no tiene espacio para la sección {section.title}")
            pdf.setFillColor(accent)
            pdf.setFont(style.font, style.font_size + 1)
            pdf.drawString(left, y, _text(section.title).upper())
            y -= style.font_size + 6
            pdf.setFillColor(colors.black)
            fields = [field for field in sorted(section.fields, key=lambda item: (item.row, item.column, item.sort_order))
                      if field.visible and field.printable]
            # Consecutive short fields share a row; long content gets full width.
            short = []

            def draw_short() -> None:
                nonlocal y, short
                if not short:
                    return
                cells = 2 if usable < 450 else 3
                for start in range(0, len(short), cells):
                    row = short[start:start + cells]
                    cell_width = usable / cells
                    for index, (label, value) in enumerate(row):
                        pdf.setFont(style.font, style.font_size)
                        line = f"{label}: {value or '________'}"
                        available = cell_width - 6
                        if pdf.stringWidth(line, style.font, style.font_size) > available:
                            # Do not silently truncate clinical values.
                            raise ValueError(f"Valor demasiado largo para un campo compacto: {label}")
                        pdf.drawString(left + index * cell_width, y, line)
                    y -= style.font_size + (5 if style.density == "compact" else 7)
                short = []

            for field in fields:
                label = field.label.upper() if field.label_uppercase else field.label
                if field.type == "divider":
                    draw_short()
                    pdf.line(left, y, width - right, y)
                    y -= 9
                    continue
                if field.type == "section_title":
                    draw_short()
                    pdf.setFont(style.font, style.font_size)
                    pdf.drawString(left, y, _text(label))
                    y -= 13
                    continue
                value = values.get(field.key, field.default_value or "")
                if field.data_binding:
                    value = document_date if field.data_binding == "document.date" else profile.get(PROFILE_BINDINGS.get(field.data_binding, ""), "")
                if field.type in {"yes_no", "checkbox"}:
                    value = {"yes": "Sí", "no": "No"}.get(str(value), "")
                if field.unit and value:
                    value = f"{value} {field.unit}"
                if field.type in {"text_long", "static_text", "signature_placeholder"}:
                    draw_short()
                    pdf.setFont(style.font, style.font_size)
                    content = _text(value if field.type != "static_text" else field.label)
                    lines = simpleSplit(f"{label}: {content}" if field.type != "static_text" else content,
                                        style.font, style.font_size, usable)
                    for line in lines or [f"{label}: __________"]:
                        pdf.drawString(left, y, line)
                        y -= style.font_size + 5
                else:
                    short.append((_text(label), _text(value)))
                if y < bottom + 30:
                    raise ValueError(f"La página {page.page_number} excede el área imprimible")
            draw_short()
            y -= 7
        if status == "signed" and signed_at:
            pdf.setFont(style.font, style.font_size)
            signature = f"Firmado por: {_text(profile.get('doctor_name'))} · {_text(signed_at)}"
            lines = simpleSplit(signature, style.font, style.font_size, usable)
            if y - len(lines) * (style.font_size + 3) < bottom + 15:
                raise ValueError(f"La página {page.page_number} no tiene espacio para la firma")
            for line in lines:
                y -= style.font_size + 3
                pdf.drawString(left, y, line)
        pdf.setFont(style.font, max(7, style.font_size - 1))
        if style.footer:
            footer_font = max(7, style.font_size - 1)
            footer_width = usable - 95
            footer_lines = simpleSplit(_text(style.footer), style.font, footer_font, footer_width)
            if len(footer_lines) > 1:
                raise ValueError(f"El pie de la página {page.page_number} excede el espacio imprimible")
            if footer_lines:
                pdf.drawString(left, bottom + 3, footer_lines[0])
        pdf.drawRightString(width - right, bottom + 3, f"Página {page.page_number} de {len(form.pages)}")
        pdf.showPage()
    pdf.save()
    return output.getvalue()
