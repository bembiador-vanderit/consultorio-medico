"""Explicit, read-only shared projections; no write/export/episode endpoints."""
from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy import select

from app.api.deps import current_user, require_permission
from app.db import get_db
from app.models import Appointment, ClinicalHistory, Organization, User
from app.models.clinical_patient_document import PhysicalExamination, PreoperativeEvaluation
from app.models.patient_care import PatientCareRelationship
from app.models.patient_safety import PatientSafetyEntry
from app.schemas.clinical_history import ClinicalHistoryBase
from app.schemas.clinical_sharing import PolicyUpdate, Resource
from app.services import clinical_sharing as sharing
from app.services.clinical_access import history_appointment_context_is_valid
from app.services.clinical_patient_document_fields import PREOPERATIVE_SECTIONS, PHYSICAL_EXAM_FIELDS

router = APIRouter(prefix="/clinical-sharing", tags=["Política clínica compartida"])
manage = require_permission("users:manage")


def patient_centers(db, patient_id):
    centers = set()
    for model in (ClinicalHistory, PreoperativeEvaluation, PhysicalExamination, PatientCareRelationship, Appointment):
        query = select(model.center_id).where(model.patient_id == patient_id, model.center_id.is_not(None))
        if model is Appointment:
            query = query.where(Appointment.status.in_(("scheduled", "confirmed", "completed")))
        centers.update(db.scalars(query))
    return centers


@router.get("/policy")
def get_policy(response: Response, user=Depends(manage), db=Depends(get_db)):
    if db.info.get("access_scope") != "tenant" or not any(r.code == "admin" for r in user.roles):
        raise HTTPException(403, "No tiene permiso para configurar la política clínica")
    response.headers["Cache-Control"] = "no-store"
    return sharing.policy_view(db)


@router.put("/policy")
def put_policy(payload: PolicyUpdate, user=Depends(manage), db=Depends(get_db)):
    return sharing.update_policy(db, user, payload)


@router.get("/patients/{patient_id}/capabilities")
def capabilities(patient_id: int, response: Response, user=Depends(current_user), db=Depends(get_db)):
    response.headers["Cache-Control"] = "no-store"
    result = {"enabled": False, "resources": []}
    if sharing.actor_denial(db, user, "clinical_history") or not sharing.available(db):
        return result
    row = sharing.policy(db)
    if not row or row.mode == "assigned":
        return {**result, "enabled": True}
    centers = patient_centers(db, patient_id) or {None}
    return {"enabled": True, "resources": [resource for resource in sharing.RESOURCES
        if any(sharing.decide(db, user, patient_id, resource, center_id=center, row=row).allowed for center in centers)]}


HISTORY_LABELS = {
    "consultation_date": "Fecha", "reason_for_visit": "Motivo de consulta", "current_illness": "Enfermedad actual",
    "personal_history": "Antecedentes personales", "family_history": "Antecedentes familiares", "allergies": "Alergias",
    "current_medications": "Medicamentos habituales", "previous_surgeries": "Cirugías previas",
    "chronic_conditions": "Enfermedades crónicas", "habits": "Hábitos", "clinical_notes": "Notas clínicas",
}


def document_fields(db, row, kind):
    from app.services import clinical_forms
    labels = dict(PHYSICAL_EXAM_FIELDS) if kind == "physical_exam" else {
        key: label for _, fields in PREOPERATIVE_SECTIONS for key, label in fields}
    if clinical_forms.schema_ready(db):
        version = clinical_forms.document_version(db, row)
        if version:
            labels = {f["key"]: f["label"] for p in version.definition["pages"] for s in p["sections"] for f in s["fields"]}
    return [{"label": labels[key], "value": value} for key, value in (row.content or {}).items() if key in labels]


def record_items(db, user, patient_id, resource, policy, center_filter):
    items, reasons = [], []
    def allowed(center_id):
        if center_filter is not None and center_id != center_filter:
            return False
        decision = sharing.decide(db, user, patient_id, resource, center_id=center_id, row=policy)
        if decision.allowed:
            reasons.append(decision.reason)
        return decision.allowed
    def item(row, title, fields, date):
        doctor = db.get(User, row.doctor_id) if getattr(row, "doctor_id", None) else None
        return {"id": row.id, "title": title, "date": date, "doctor_name": doctor.full_name if doctor else None,
                "center_id": getattr(row, "center_id", None), "status": row.status, "fields": fields, "read_only": True}
    if resource == "clinical_history":
        rows = db.scalars(select(ClinicalHistory).where(ClinicalHistory.patient_id == patient_id,
            ClinicalHistory.status == "completed").order_by(ClinicalHistory.consultation_date.desc(), ClinicalHistory.id.desc()))
        for row in rows:
            if not history_appointment_context_is_valid(db, row) or not allowed(row.center_id):
                continue
            fields = [{"label": HISTORY_LABELS[key], "value": getattr(row, key)} for key in ClinicalHistoryBase.model_fields]
            from app.services.cardiology import shared_fields
            fields.extend(shared_fields(db, row))  # projection only, after existing authorization
            items.append(item(row, "Consulta", fields, row.consultation_date))
    elif resource == "clinical_documents":
        for model, kind, title in ((PreoperativeEvaluation, "preoperative", "Evaluación preoperatoria"),
                                    (PhysicalExamination, "physical_exam", "Examen físico")):
            for row in db.scalars(select(model).where(model.patient_id == patient_id, model.status.in_(("completed", "signed"))).order_by(model.document_date.desc(), model.id.desc())):
                if allowed(row.center_id):
                    items.append({**item(row, title, document_fields(db, row, kind), row.document_date), "kind": kind})
    else:
        # Safety is longitudinal and has no center column. Require real patient
        # evidence at a permitted center; never trust an arbitrary client center.
        centers = patient_centers(db, patient_id)
        if any(allowed(center) for center in centers) or (center_filter is None and allowed(None)):
            for row in db.scalars(select(PatientSafetyEntry).where(PatientSafetyEntry.patient_id == patient_id).order_by(PatientSafetyEntry.id)):
                fields = [{"label": label, "value": getattr(row, key)} for key, label in (
                    ("entry_type", "Tipo"), ("substance_or_agent", "Agente"), ("reaction_description", "Reacción"),
                    ("severity", "Severidad"), ("status", "Estado"), ("source_type", "Procedencia"), ("notes", "Observaciones"))]
                items.append(item(row, "Seguridad clínica", fields, row.recorded_at))
    return items, reasons


@router.get("/patients/{patient_id}/records/{resource}")
def read_records(patient_id: int, resource: Resource, response: Response,
                 center_id: int | None = Query(default=None, gt=0),
                 limit: int = Query(default=25, ge=1, le=50), offset: int = Query(default=0, ge=0),
                 user=Depends(current_user), db=Depends(get_db)):
    response.headers["Cache-Control"] = "no-store"
    if sharing.actor_denial(db, user, resource) or not sharing.available(db):
        raise HTTPException(403, "Información clínica no disponible para esta cuenta")
    org_id = db.info["organization_id"]
    db.scalar(select(Organization).where(Organization.id == org_id).with_for_update())
    row = sharing.policy(db)
    centers = patient_centers(db, patient_id) or {None}
    if center_id is not None:
        centers = centers.intersection({center_id})
    decisions = [sharing.decide(db, user, patient_id, resource, center_id=c, row=row) for c in centers]
    if not any(d.allowed for d in decisions):
        raise HTTPException(404, "Información clínica no disponible")
    items, reasons = record_items(db, user, patient_id, resource, row, center_id)
    sharing.audit_read(db, user, patient_id, resource, row, reasons or [d.reason for d in decisions if d.allowed], center_id)
    db.commit()
    return {"read_only": True, "resource": resource, "policy_revision": row.revision,
            "items": items[offset:offset + limit], "total": len(items), "offset": offset, "limit": limit}
