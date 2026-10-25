"""Unified document personalization and read-only financial PDF output."""
from datetime import timezone
from decimal import Decimal
from typing import Literal
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import current_user
from app.db import get_db
from app.models import CareCenter, Organization, User
from app.models.document_template import DocumentTemplate, DocumentTemplateVersion, DocumentTemplateAudit
from app.models.finance import CashRegister, CashMovement, Invoice
from app.services import document_designer as designer, document_pdf
from app.services import finance
from app.services.administration import effective_permissions

router = APIRouter(prefix="/documents", tags=["Personalización de documentos"])
Kind = Literal["invoice", "receipt", "cash_close"]


class Definition(BaseModel):
    model_config = ConfigDict(extra="forbid")
    page_format: Literal["LETTER", "A4"] = "LETTER"
    orientation: Literal["portrait", "landscape"] = "portrait"
    print_mode: Literal["color", "bw"] = "color"
    ink_saver: bool = True
    typography: Literal["Helvetica", "Times-Roman", "Courier"] = "Helvetica"
    show_logo: bool = True
    show_organization: bool = True
    show_center: bool = True
    show_professional: bool = False
    margin_mm: int = Field(default=18, ge=10, le=25)
    header_style: Literal["plain", "soft", "medium"] = "plain"
    section_style: Literal["plain", "soft", "medium"] = "soft"
    accent_color: str = Field(default="#087f83", pattern=r"^#[0-9a-fA-F]{6}$")
    footer_note: str = Field(default="Documento interno. No es comprobante fiscal.", max_length=250)


class SaveDraft(BaseModel):
    model_config = ConfigDict(extra="forbid")
    document_type: Kind
    name: str = Field(min_length=1, max_length=180)
    center_id: int | None = Field(default=None, gt=0)
    doctor_id: int | None = Field(default=None, gt=0)
    definition: Definition


class PreviewRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    document_type: Kind
    definition: Definition


def _stamp(db, value):
    if not value:
        return "—"
    org = db.get(Organization, db.info.get("organization_id", 1))
    zone = ZoneInfo(org.timezone if org else "UTC")
    return value.replace(tzinfo=timezone.utc).astimezone(zone).strftime("%d/%m/%Y %H:%M")


def _name(db, user_id):
    row = db.get(User, user_id) if user_id else None
    return row.full_name if row else f"Usuario #{user_id}"


def _base(db, center_id):
    center = db.get(CareCenter, center_id)
    org = db.get(Organization, db.info.get("organization_id", 1))
    return {"organization": org.name if org else "Organización", "center": center.name if center else "Centro"}


def _parts(parts):
    return ", ".join(
        f"{finance.METHODS.get(item['method'], item['method'])} {document_pdf.cash(item['amount'])}"
        + (f" · {item['provider']} lote {item['batch_number']}"
           if item.get("provider") and item.get("batch_number") else "")
        for item in (parts or []))


def _invoice_data(db, row):
    movements = list(db.scalars(select(CashMovement).where(CashMovement.invoice_id == row.id).order_by(CashMovement.id)))
    methods = [_parts(m.parts) for m in movements if m.kind == "payment"]
    return {**_base(db, row.center_id), "number": row.number, "issued_at": _stamp(db, row.created_at),
            "patient": row.patient_name, "concept": row.concept, "issuer": _name(db, row.created_by),
            "status": {"pending": "Pendiente", "partial": "Pago parcial", "paid": "Paciente saldado", "void": "Anulada"}[row.state],
            "totals": [("Total", document_pdf.cash(row.base_amount)), ("Parte ARS", document_pdf.cash(row.ars_amount)),
                       ("Parte paciente", document_pdf.cash(row.patient_amount)),
                       ("Pagado neto por paciente", document_pdf.cash(row.paid_amount)),
                       ("Saldo paciente", document_pdf.cash(row.balance))],
            "details": [("Métodos de cobro registrados", "; ".join(methods) or "Sin cobros")],
            "reversal_notice": "FACTURA ANULADA" if row.voided_at else None}


def _receipt_data(db, actor, movement):
    if movement.kind != "payment" or movement.invoice_id is None:
        raise HTTPException(404, "El movimiento no tiene recibo de pago")
    bill = finance.invoice_access(db, actor, movement.invoice_id)
    earlier = list(db.scalars(select(CashMovement).where(CashMovement.invoice_id == bill.id,
        CashMovement.id <= movement.id).order_by(CashMovement.id)))
    paid_until = sum((m.amount if m.kind == "payment" else -m.amount for m in earlier if m.kind in {"payment", "reversal"}), Decimal("0.00"))
    reversed_later = db.scalar(select(CashMovement.id).where(CashMovement.reverses_id == movement.id)) is not None
    return {**_base(db, movement.center_id), "number": f"PAGO-{movement.id:08d}", "invoice": bill.number,
            "issued_at": _stamp(db, movement.created_at), "patient": bill.patient_name,
            "issuer": _name(db, movement.created_by), "status": "Reversado posteriormente" if reversed_later else "Aplicado",
            "totals": [("Monto recibido", document_pdf.cash(movement.amount)),
                       ("Saldo posterior a este cobro", document_pdf.cash(bill.patient_amount - paid_until))],
            "details": [("Métodos / referencias", _parts(movement.parts)), ("Caja", f"#{movement.register_id}")],
            "reversal_notice": "Este cobro fue reversado posteriormente. Conserve ambos comprobantes." if reversed_later else None}


def _close_data(db, row):
    if row.state != "closed":
        raise HTTPException(409, "El cierre PDF requiere una caja cerrada")
    totals = finance.register_totals(db, row)
    if totals["expected_cash"] != row.expected_cash:
        raise HTTPException(409, "El cierre no coincide con sus movimientos; revise la Caja")
    moves = list(db.scalars(select(CashMovement).where(CashMovement.register_id == row.id).order_by(CashMovement.id)))
    collected, reversed_ = totals["collected"], totals["reversed"]
    lines = [(f"#{m.id}", {"payment": "Cobro", "reversal": "Reverso", "adjustment_in": "Ajuste +", "adjustment_out": "Ajuste -"}[m.kind]
              + (f" · {_parts(m.parts)}" if m.parts else ""), document_pdf.cash(m.amount)) for m in moves]
    return {**_base(db, row.center_id), "number": f"CAJA-{row.id:08d}", "issued_at": _stamp(db, row.closed_at),
            "issuer": _name(db, row.closed_by), "status": "Cerrada",
            "details": [("Apertura", _stamp(db, row.opened_at)), ("Cierre", _stamp(db, row.closed_at)),
                        ("Responsable", _name(db, row.opened_by)), ("Observación", row.closing_notes or "—")],
            "totals": [("Fondo inicial", document_pdf.cash(row.opening_amount)),
                       *[(f"Cobrado {label}", document_pdf.cash(collected[key])) for key, label in finance.METHODS.items()],
                       *[(f"Reversado {label}", document_pdf.cash(reversed_[key])) for key, label in finance.METHODS.items()],
                       ("Ajustes entrada", document_pdf.cash(totals["adjustments_in"])),
                       ("Ajustes salida", document_pdf.cash(totals["adjustments_out"])),
                       ("Efectivo esperado", document_pdf.cash(row.expected_cash)),
                       ("Efectivo contado", document_pdf.cash(row.counted_cash)),
                       ("Diferencia", document_pdf.cash(row.difference))],
            "movements": lines or [("—", "Sin movimientos", document_pdf.cash(0))]}


@router.get("/catalog")
def catalog(actor: User = Depends(current_user)):
    designer.require(actor, "documents:view")
    return designer.CATALOG


@router.get("/effective/{kind}")
def effective(kind: Kind, center_id: int | None = None, doctor_id: int | None = None,
              actor: User = Depends(current_user), db: Session = Depends(get_db)):
    designer.require(actor, "documents:view")
    designer.validate_scope(db, actor, center_id, doctor_id)
    return designer.effective(db, kind, center_id, doctor_id)


@router.post("/preview/pdf")
def preview(payload: PreviewRequest, actor: User = Depends(current_user)):
    designer.require(actor, "documents:manage")
    content = document_pdf.render_financial_pdf(payload.document_type, document_pdf.sample_data(payload.document_type),
                                                payload.definition.model_dump())
    return Response(content=content, media_type="application/pdf", headers={"Cache-Control": "no-store"})


@router.post("/drafts")
def save(payload: SaveDraft, actor: User = Depends(current_user), db: Session = Depends(get_db)):
    row, version = designer.save_draft(db, actor, payload.document_type, payload.name,
        payload.definition.model_dump(), payload.center_id, payload.doctor_id)
    return {"template_id": row.id, "version_id": version.id, "version": version.version, "status": version.status}


@router.post("/templates/{template_id}/versions/{version_id}/publish")
def publish(template_id: int, version_id: int, actor: User = Depends(current_user), db: Session = Depends(get_db)):
    version = designer.publish(db, actor, template_id, version_id)
    return {"template_id": template_id, "version_id": version.id, "version": version.version, "status": version.status}


@router.get("/finance/{kind}/{record_id}/pdf")
def finance_pdf(kind: Kind, record_id: int, action: Literal["view", "download", "print", "reprint"] = "view",
                actor: User = Depends(current_user), db: Session = Depends(get_db)):
    designer.require(actor, "documents:view")
    designer.require(actor, "documents:pdf")
    if "finance:read" not in effective_permissions(actor):
        raise HTTPException(403, "No tiene permiso para consultar documentos financieros")
    if action in {"print", "reprint"}:
        designer.require(actor, "documents:print" if action == "print" else "documents:reprint")
    if kind == "invoice":
        row = finance.invoice_access(db, actor, record_id)
        data, center_id = _invoice_data(db, row), row.center_id
    elif kind == "receipt":
        row = db.get(CashMovement, record_id)
        if row is None:
            raise HTTPException(404, "Cobro no disponible")
        finance.center_access(db, actor, row.center_id)
        data, center_id = _receipt_data(db, actor, row), row.center_id
    else:
        row = finance.register_access(db, actor, record_id)
        data, center_id = _close_data(db, row), row.center_id
    profile = designer.effective(db, kind, center_id)
    content = document_pdf.render_financial_pdf(kind, data, profile["definition"])
    if designer.schema_ready(db):
        db.add(DocumentTemplateAudit(template_id=profile["template_id"], center_id=center_id,
            actor_id=actor.id, action=f"pdf_{action}", before={},
            after={"document_type": kind, "record_id": record_id, "template_version": profile["version"]}))
        db.commit()
    filename = f"atlas-{kind}-{record_id}.pdf"
    disposition = "attachment" if action == "download" else "inline"
    return Response(content=content, media_type="application/pdf", headers={
        "Content-Disposition": f'{disposition}; filename="{filename}"', "Cache-Control": "no-store"})
