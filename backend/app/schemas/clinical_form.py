"""Strict, code-free schema for versioned form layouts."""
import base64
import binascii
import math
import re
from datetime import date, time
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


FieldType = Literal[
    "text_short", "text_long", "integer", "decimal", "date", "time", "yes_no",
    "single_select", "multi_select", "checkbox", "patient_field", "doctor_field",
    "calculated", "signature_placeholder", "static_text", "divider", "section_title",
]
Binding = Literal[
    "patient.full_name", "patient.birth_date", "patient.age", "patient.sex", "patient.document",
    "patient.phone", "patient.address", "patient.insurance", "doctor.display_name",
    "doctor.specialty", "center.name", "document.date", "document.created_at",
]


class FormField(BaseModel):
    model_config = ConfigDict(extra="forbid")
    key: str = Field(pattern=r"^[a-z][a-z0-9_]{0,79}$")
    label: str = Field(min_length=1, max_length=180)
    type: FieldType
    required: bool = False
    label_uppercase: bool = False
    placeholder: str = Field(default="", max_length=200)
    help_text: str = Field(default="", max_length=500)
    default_value: str | None = Field(default=None, max_length=5000)
    unit: str = Field(default="", max_length=30)
    options: list[str] = Field(default_factory=list, max_length=30)
    width: int = Field(default=12, ge=1, le=12)
    row: int = Field(default=1, ge=1, le=200)
    column: int = Field(default=1, ge=1, le=12)
    colspan: int = Field(default=12, ge=1, le=12)
    sort_order: int = Field(default=1, ge=1, le=200)
    visible: bool = True
    printable: bool = True
    read_only: bool = False
    editable_by: Literal["clinical", "administrative"] = "clinical"
    data_binding: Binding | None = None
    validation: dict[str, float] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_type(self):
        if self.column + self.colspan > 13:
            raise ValueError("El campo excede las columnas de la cuadrícula")
        if self.type in {"single_select", "multi_select"}:
            if not self.options or len(set(self.options)) != len(self.options):
                raise ValueError("La selección requiere opciones únicas")
        elif self.options:
            raise ValueError("Las opciones solo pertenecen a campos de selección")
        if self.data_binding and self.type not in {"patient_field", "doctor_field", "calculated"}:
            raise ValueError("El vínculo Atlas no corresponde al tipo de campo")
        if self.type in {"patient_field", "doctor_field", "calculated"} and not self.data_binding:
            raise ValueError("Seleccione un vínculo Atlas permitido")
        if self.type == "patient_field" and not self.data_binding.startswith("patient."):
            raise ValueError("Vínculo de paciente inválido")
        if self.type == "doctor_field" and not self.data_binding.startswith("doctor."):
            raise ValueError("Vínculo de médico inválido")
        if self.type in {"static_text", "divider", "section_title", "signature_placeholder"} and self.required:
            raise ValueError("Un bloque de presentación no puede ser obligatorio")
        if self.editable_by == "administrative" and (self.data_binding or self.type in {"calculated", "signature_placeholder", "static_text", "divider", "section_title"}):
            raise ValueError("Este bloque no admite captura administrativa")
        if self.default_value is not None:
            value = self.default_value
            if self.type == "integer" and not re.fullmatch(r"-?\d+", value):
                raise ValueError("Valor inicial entero inválido")
            if self.type == "decimal" and not re.fullmatch(r"-?\d+(?:\.\d+)?", value):
                raise ValueError("Valor inicial decimal inválido")
            if self.type in {"date", "time"}:
                try:
                    (date if self.type == "date" else time).fromisoformat(value)
                except ValueError as exc:
                    raise ValueError("Valor inicial de fecha/hora inválido") from exc
            if self.type == "single_select" and value not in self.options:
                raise ValueError("Valor inicial fuera de opciones")
            if self.type == "multi_select" and any(part not in self.options for part in value.split("|")):
                raise ValueError("Valor inicial fuera de opciones")
            if self.type in {"yes_no", "checkbox"} and value not in {"yes", "no"}:
                raise ValueError("Valor inicial Sí/No inválido")
            if self.type in {"patient_field", "doctor_field", "calculated"}:
                raise ValueError("Los campos vinculados no admiten valor inicial manual")
        # Validation metadata is declarative only. No regular expressions or code
        # from users are executed in either browser or backend.
        if set(self.validation) - {"min", "max", "max_length"}:
            raise ValueError("Metadatos de validación no admitidos")
        if any(not math.isfinite(value) or abs(value) > 1_000_000_000 for value in self.validation.values()):
            raise ValueError("Límite de validación inválido")
        if "max_length" in self.validation and not (1 <= self.validation["max_length"] <= 5000 and self.validation["max_length"].is_integer()):
            raise ValueError("Longitud máxima inválida")
        if "min" in self.validation and "max" in self.validation and self.validation["min"] > self.validation["max"]:
            raise ValueError("Rango de validación inválido")
        return self


class FormSection(BaseModel):
    model_config = ConfigDict(extra="forbid")
    key: str = Field(pattern=r"^[a-z][a-z0-9_]{0,79}$")
    title: str = Field(min_length=1, max_length=180)
    sort_order: int = Field(default=1, ge=1, le=100)
    printable: bool = True
    fields: list[FormField] = Field(default_factory=list, max_length=150)


class FormMargins(BaseModel):
    model_config = ConfigDict(extra="forbid")
    top: int = Field(default=12, ge=5, le=35)
    bottom: int = Field(default=12, ge=5, le=35)
    left: int = Field(default=12, ge=5, le=35)
    right: int = Field(default=12, ge=5, le=35)


class FormPage(BaseModel):
    model_config = ConfigDict(extra="forbid")
    page_number: int = Field(ge=1, le=12)
    title: str = Field(default="", max_length=180)
    orientation: Literal["portrait", "landscape"] = "portrait"
    page_size: Literal["A4", "Letter"] = "Letter"
    margins: FormMargins = Field(default_factory=FormMargins)
    sort_order: int = Field(default=1, ge=1, le=12)
    sections: list[FormSection] = Field(default_factory=list, max_length=30)


class FormAppearance(BaseModel):
    model_config = ConfigDict(extra="forbid")
    show_logo: bool = False
    # PNG/JPEG only; no arbitrary URL, SVG, CSS, script or remote fetch.
    logo_data: str | None = Field(default=None, max_length=750_000)
    doctor_heading: str = Field(default="", max_length=180)
    specialty_heading: str = Field(default="", max_length=180)
    center_heading: str = Field(default="", max_length=180)
    header: str = Field(default="", max_length=180)
    subtitle: str = Field(default="", max_length=180)
    footer: str = Field(default="", max_length=300)
    primary_color: str = Field(default="#24415c", pattern=r"^#[0-9a-fA-F]{6}$")
    font: Literal["Helvetica", "Times-Roman", "Courier"] = "Helvetica"
    font_size: int = Field(default=9, ge=7, le=14)
    density: Literal["compact", "normal", "comfortable"] = "normal"

    @model_validator(mode="after")
    def validate_logo(self):
        if not self.logo_data:
            return self
        prefix, _, encoded = self.logo_data.partition(",")
        if prefix not in {"data:image/png;base64", "data:image/jpeg;base64"}:
            raise ValueError("Solo se permiten logotipos PNG o JPEG")
        try:
            raw = base64.b64decode(encoded, validate=True)
        except (ValueError, binascii.Error) as exc:
            raise ValueError("Logotipo inválido") from exc
        if len(raw) > 500_000 or not (raw.startswith(b"\x89PNG\r\n\x1a\n") if "png" in prefix else raw.startswith(b"\xff\xd8\xff")):
            raise ValueError("Logotipo inválido o demasiado grande")
        return self


class FormDefinition(BaseModel):
    model_config = ConfigDict(extra="forbid")
    appearance: FormAppearance = Field(default_factory=FormAppearance)
    pages: list[FormPage] = Field(default_factory=list, max_length=12)

    @model_validator(mode="after")
    def validate_structure(self):
        if len({page.page_number for page in self.pages}) != len(self.pages):
            raise ValueError("Número de página duplicado")
        if sorted(page.page_number for page in self.pages) != list(range(1, len(self.pages) + 1)):
            raise ValueError("Las páginas deben numerarse consecutivamente desde 1")
        keys = [field.key for page in self.pages for section in page.sections for field in section.fields]
        if len(keys) > 150 or len(keys) != len(set(keys)):
            raise ValueError("Demasiados campos o claves repetidas")
        for page in self.pages:
            sections = [section.key for section in page.sections]
            if len(sections) != len(set(sections)):
                raise ValueError("Sección repetida en una página")
        return self
