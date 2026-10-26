"""Tenant-scoped, versioned document presentation. Values always come from source records."""
from datetime import datetime

from fastapi import HTTPException
from sqlalchemy import func, inspect, select
from sqlalchemy.orm import Session

from app.models import CareCenter, User
from app.models.document_template import DocumentTemplate, DocumentTemplateVersion, DocumentTemplateAudit
from app.services.administration import effective_permissions
from app.services.appointment_scope import assigned_center_ids, is_role

DOCUMENT_TYPES = {
    "invoice": "Factura interna", "receipt": "Recibo de pago", "cash_close": "Cierre de caja",
}
CATALOG = [
    {"code": "consultation_summary", "name": "Resumen de consulta", "category": "Clínica", "status": "existente"},
    {"code": "prescription", "name": "Receta médica", "category": "Clínica", "status": "existente"},
    {"code": "laboratory_order", "name": "Orden de laboratorio", "category": "Clínica", "status": "existente"},
    {"code": "study_order", "name": "Orden de estudios", "category": "Clínica", "status": "existente"},
    {"code": "preoperative", "name": "Evaluación preoperatoria", "category": "Clínica", "status": "existente"},
    {"code": "physical_exam", "name": "Examen físico", "category": "Clínica", "status": "existente"},
    *({"code": key, "name": name, "category": "Finanzas", "status": "disponible"} for key, name in DOCUMENT_TYPES.items()),
    {"code": "ars_claim", "name": "Reclamación ARS", "category": "ARS", "status": "futuro"},
    {"code": "financial_report", "name": "Reporte financiero", "category": "Reportes", "status": "futuro"},
]

DEFAULT_DEFINITION = {
    "page_format": "LETTER", "orientation": "portrait", "print_mode": "color",
    "ink_saver": True, "typography": "Helvetica", "show_logo": True,
    "show_organization": True, "show_center": True, "show_professional": False,
    "margin_mm": 18, "header_style": "plain", "section_style": "soft",
    "accent_color": "#087f83", "footer_note": "Documento interno. No es comprobante fiscal.",
}


def schema_ready(db: Session) -> bool:
    return inspect(db.get_bind()).has_table("document_templates")


def require_catalog(db: Session):
    if not schema_ready(db):
        raise HTTPException(503, "Diseñador de documentos pendiente de activación")


def require(actor: User, code: str):
    if code not in effective_permissions(actor):
        raise HTTPException(403, "No tiene permiso para esta operación documental")


def validate_scope(db, actor, center_id, doctor_id):
    if doctor_id is not None and center_id is None:
        raise HTTPException(422, "Seleccione centro para personalizar por médico")
    if center_id is not None:
        center = db.get(CareCenter, center_id)
        if center is None or (not is_role(actor, "admin") and center_id not in assigned_center_ids(actor)):
            raise HTTPException(404, "Centro no disponible")
    if doctor_id is not None:
        doctor = db.get(User, doctor_id)
        if doctor is None or not any(role.code == "doctor" for role in doctor.roles) or center_id not in {c.id for c in doctor.centers}:
            raise HTTPException(422, "El médico no está autorizado en este centro")


def scope_key(center_id=None, doctor_id=None):
    return f"doctor:{center_id}:{doctor_id}" if doctor_id else f"center:{center_id}" if center_id else "organization"


def effective(db: Session, kind: str, center_id=None, doctor_id=None) -> dict:
    if kind not in DOCUMENT_TYPES:
        raise HTTPException(422, "Tipo documental no disponible")
    if not schema_ready(db):
        return {"definition": dict(DEFAULT_DEFINITION), "source": "atlas_default", "template_id": None, "version": None}
    for key in (scope_key(center_id, doctor_id), scope_key(center_id), "organization"):
        if key.startswith("doctor:") and doctor_id is None or key.startswith("center:") and center_id is None:
            continue
        row = db.scalar(select(DocumentTemplate).where(DocumentTemplate.document_type == kind, DocumentTemplate.scope_key == key))
        if row:
            version = db.scalar(select(DocumentTemplateVersion).where(DocumentTemplateVersion.template_id == row.id,
                DocumentTemplateVersion.status == "published").order_by(DocumentTemplateVersion.version.desc()).limit(1))
            if version:
                return {"definition": version.definition, "source": key, "template_id": row.id, "version": version.version}
    return {"definition": dict(DEFAULT_DEFINITION), "source": "atlas_default", "template_id": None, "version": None}


def save_draft(db: Session, actor: User, kind: str, name: str, definition: dict, center_id=None, doctor_id=None):
    require_catalog(db)
    require(actor, "documents:manage")
    validate_scope(db, actor, center_id, doctor_id)
    key = scope_key(center_id, doctor_id)
    row = db.scalar(select(DocumentTemplate).where(DocumentTemplate.document_type == kind,
        DocumentTemplate.scope_key == key).with_for_update())
    if row is None:
        code = f"{kind}_{key.replace(':', '_')}"
        row = DocumentTemplate(code=code, name=name, document_type=kind, scope_key=key,
                               center_id=center_id, doctor_id=doctor_id, created_by=actor.id)
        db.add(row)
        db.flush()
    draft = db.scalar(select(DocumentTemplateVersion).where(DocumentTemplateVersion.template_id == row.id,
        DocumentTemplateVersion.status == "draft").with_for_update())
    previous = dict(draft.definition) if draft else {}
    if draft is None:
        next_version = (db.scalar(select(func.max(DocumentTemplateVersion.version)).where(
            DocumentTemplateVersion.template_id == row.id)) or 0) + 1
        draft = DocumentTemplateVersion(template_id=row.id, version=next_version, status="draft",
                                        definition=definition, created_by=actor.id)
        db.add(draft)
        db.flush()
        action = "create_draft"
    elif previous != definition:
        draft.definition = definition
        action = "update_draft"
    else:
        return row, draft
    db.add(DocumentTemplateAudit(template_id=row.id, version_id=draft.id, center_id=center_id,
        actor_id=actor.id, action=action, before=previous, after=definition))
    db.commit()
    return row, draft


def publish(db: Session, actor: User, template_id: int, version_id: int):
    require_catalog(db)
    require(actor, "documents:publish")
    row = db.get(DocumentTemplate, template_id)
    if row is None:
        raise HTTPException(404, "Plantilla no disponible")
    version = db.scalar(select(DocumentTemplateVersion).where(DocumentTemplateVersion.id == version_id,
        DocumentTemplateVersion.template_id == row.id).with_for_update())
    if version is None or version.status != "draft":
        raise HTTPException(409, "Solo se publica un borrador vigente")
    prior = db.scalar(select(DocumentTemplateVersion).where(DocumentTemplateVersion.template_id == row.id,
        DocumentTemplateVersion.status == "published").with_for_update())
    if prior:
        prior.status = "archived"
    version.status = "published"
    version.published_at = datetime.utcnow()
    db.add(DocumentTemplateAudit(template_id=row.id, version_id=version.id, center_id=row.center_id,
        actor_id=actor.id, action="publish", before={"version": prior.version if prior else None},
        after={"version": version.version}))
    db.commit()
    return version
