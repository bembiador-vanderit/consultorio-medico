"""Minimal tenant-scoped administration of versioned clinical forms."""
from io import BytesIO
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import current_user
from app.db import get_db
from app.models import CareCenter, ClinicalFormAssignment, ClinicalFormTemplate, User
from app.schemas.clinical_form import FormDefinition
from app.services import clinical_forms as forms


router = APIRouter(prefix="/clinical-forms", tags=["Diseñador de formularios clínicos"])


class TemplateCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str = Field(min_length=1, max_length=180)
    code: str = Field(pattern=r"^[a-z][a-z0-9_]{1,99}$")
    description: str = Field(default="", max_length=1000)
    document_type: Literal["preoperative", "physical_exam"]
    definition: FormDefinition | None = None


class DuplicateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str = Field(min_length=1, max_length=180)
    code: str = Field(pattern=r"^[a-z][a-z0-9_]{1,99}$")


class AssignmentRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    center_id: int | None = Field(default=None, gt=0)
    specialty_id: int | None = Field(default=None, gt=0)
    doctor_id: int | None = Field(default=None, gt=0)


class SecretaryCapabilities(BaseModel):
    model_config = ConfigDict(extra="forbid")
    start_preoperative: bool = False
    start_physical_exam: bool = False
    prepare_administrative: bool = False


@router.get("/templates")
def list_templates(actor: User = Depends(current_user), db: Session = Depends(get_db)):
    forms.require_schema(db)
    forms.require_admin(actor, "clinical_forms:view")
    return [forms.serialize_template(db, row) for row in db.scalars(
        select(ClinicalFormTemplate).order_by(ClinicalFormTemplate.name, ClinicalFormTemplate.id))]


@router.post("/templates", status_code=201)
def create_template(payload: TemplateCreate, actor: User = Depends(current_user), db: Session = Depends(get_db)):
    return forms.create_template(db, actor, **payload.model_dump())


@router.post("/catalog/{kind}", status_code=201)
def install_catalog(kind: Literal["preoperative", "physical_exam"], actor: User = Depends(current_user), db: Session = Depends(get_db)):
    label = "EVALUACIÓN MÉDICA PREOPERATORIA — CEMER" if kind == "preoperative" else "EXAMEN FÍSICO — CEMER"
    return forms.create_template(db, actor, name=label, code=f"cemer_{kind}",
                                 description="Plantilla inicial editable basada en la proforma CEMER.",
                                 document_type=kind, definition=forms.cemer_definition(kind))


@router.get("/templates/{template_id}")
def get_template(template_id: int, actor: User = Depends(current_user), db: Session = Depends(get_db)):
    forms.require_schema(db)
    forms.require_admin(actor, "clinical_forms:view")
    return forms.serialize_template(db, forms._template(db, template_id), definition=True)


@router.put("/templates/{template_id}/versions/{version_id}")
def update_draft(template_id: int, version_id: int, definition: FormDefinition,
                 actor: User = Depends(current_user), db: Session = Depends(get_db)):
    return forms.update_draft(db, actor, template_id, version_id, definition)


@router.post("/templates/{template_id}/versions/{version_id}/publish")
def publish(template_id: int, version_id: int, actor: User = Depends(current_user), db: Session = Depends(get_db)):
    return forms.publish(db, actor, template_id, version_id)


@router.post("/templates/{template_id}/draft")
def fork_draft(template_id: int, actor: User = Depends(current_user), db: Session = Depends(get_db)):
    return forms.fork_draft(db, actor, template_id)


@router.post("/templates/{template_id}/duplicate", status_code=201)
def duplicate(template_id: int, payload: DuplicateRequest, actor: User = Depends(current_user), db: Session = Depends(get_db)):
    return forms.duplicate(db, actor, template_id, **payload.model_dump())


@router.post("/templates/{template_id}/retire")
def retire(template_id: int, actor: User = Depends(current_user), db: Session = Depends(get_db)):
    return forms.retire(db, actor, template_id)


@router.put("/templates/{template_id}/assignment")
def assign(template_id: int, payload: AssignmentRequest, actor: User = Depends(current_user), db: Session = Depends(get_db)):
    row = forms.assign(db, actor, template_id, **payload.model_dump())
    return {"id": row.id, "template_id": row.template_id, "document_type": row.document_type,
            "center_id": row.center_id, "specialty_id": row.specialty_id, "doctor_id": row.doctor_id}


@router.get("/assignments")
def list_assignments(actor: User = Depends(current_user), db: Session = Depends(get_db)):
    forms.require_schema(db)
    forms.require_admin(actor, "clinical_forms:view")
    return [{"id": row.id, "template_id": row.template_id, "document_type": row.document_type,
             "center_id": row.center_id, "specialty_id": row.specialty_id, "doctor_id": row.doctor_id}
            for row in db.scalars(select(ClinicalFormAssignment).order_by(ClinicalFormAssignment.id))]


@router.get("/resolve")
def resolve(kind: Literal["preoperative", "physical_exam"], center_id: int, doctor_id: int,
            actor: User = Depends(current_user), db: Session = Depends(get_db)):
    forms.require_schema(db)
    forms.require_admin(actor, "clinical_forms:view")
    if not db.get(User, doctor_id) or not db.get(CareCenter, center_id):
        raise HTTPException(404, "Contexto no disponible")
    chosen = forms.resolve(db, kind, center_id=center_id, doctor_id=doctor_id)
    return {"template_id": chosen[0].id, "version_id": chosen[1].id,
            "version": chosen[1].version} if chosen else {"template_id": None, "version_id": None, "fallback": "legacy_0055"}


@router.get("/capabilities/me")
def own_capabilities(actor: User = Depends(current_user), db: Session = Depends(get_db)):
    forms.require_schema(db)
    return forms.secretary_capabilities(db, actor)


@router.get("/capabilities/secretaries/{user_id}")
def get_secretary_capabilities(user_id: int, actor: User = Depends(current_user), db: Session = Depends(get_db)):
    forms.require_schema(db)
    forms.require_admin(actor, "clinical_forms:view")
    target = db.get(User, user_id)
    if not target:
        raise HTTPException(404, "Usuario no encontrado")
    return forms.secretary_capabilities(db, target)


@router.put("/capabilities/secretaries/{user_id}")
def set_secretary_capabilities(user_id: int, payload: SecretaryCapabilities,
                               actor: User = Depends(current_user), db: Session = Depends(get_db)):
    return forms.set_secretary_capabilities(db, actor, user_id, payload.model_dump())


@router.get("/templates/{template_id}/preview/pdf")
def preview_pdf(template_id: int, actor: User = Depends(current_user), db: Session = Depends(get_db)):
    forms.require_schema(db)
    forms.require_admin(actor, "clinical_forms:view")
    row = forms._template(db, template_id)
    data = forms.serialize_template(db, row, definition=True)
    if not data["definition"]:
        raise HTTPException(409, "Plantilla sin versión")
    from app.services.clinical_form_pdf import build_form_pdf
    pdf = build_form_pdf(data["definition"], values={}, profile={
        "patient_name": "Paciente de ejemplo", "doctor_name": "Médico de ejemplo",
        "center_name": "Centro de ejemplo", "age_at_document": "—"},
        document_date="2026-01-01", status="preview", signed_at=None)
    return StreamingResponse(BytesIO(pdf), media_type="application/pdf",
                             headers={"Content-Disposition": 'inline; filename="vista-previa.pdf"'})
