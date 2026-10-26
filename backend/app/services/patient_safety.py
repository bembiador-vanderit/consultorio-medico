"""One patient-owned source of safety information; no automatic clinical decisions."""
from datetime import date, datetime, timezone

from fastapi import HTTPException
from sqlalchemy import inspect, select

from app.models import ClinicalHistory
from app.models.clinical_audit import ClinicalAuditLog
from app.models.patient_safety import PatientSafetyEntry
from app.schemas.patient_safety import SafetyContent
from app.services.administration import effective_permissions
from app.services.clinical_access import has_normal_history_access
from app.services.patient_scope import require_patient_clinical_scope

VIEW = "patient_safety:view"
EDIT = "patient_safety:edit"


def available(db):
    return inspect(db.get_bind()).has_table("patient_safety_entries")


def authorize(db, user, patient_id=None, *, write=False):
    required = {"patients:view", "clinical:access", VIEW} | ({EDIT} if write else set())
    if not required.issubset(effective_permissions(user)) or not any(role.code == "doctor" for role in user.roles):
        raise HTTPException(403, "No tiene permiso para esta información clínica")
    if not available(db):
        raise HTTPException(503, "Seguridad clínica pendiente de activación")
    if patient_id is not None:
        return require_patient_clinical_scope(db, user, patient_id)


def snapshot(row):
    values = {key: getattr(row, key) for key in SafetyContent.model_fields}
    return {key: value.isoformat() if isinstance(value, (date, datetime)) else value for key, value in values.items()}


def audit(db, user, row, action, before, reason):
    # Full clinical snapshots remain restricted to the medical safety-history
    # endpoint; the generic administrative audit listing excludes this resource.
    db.add(ClinicalAuditLog(organization_id=row.organization_id, user_id=user.id,
        resource_type="patient_safety_entry", resource_id=row.id,
        clinical_history_id=row.clinical_history_id, action=f"patient_safety.{action}",
        outcome="success", context={"patient_id": row.patient_id, "before": before,
            "after": snapshot(row), "reason": reason, "revision": row.revision}))


def get_entry(db, patient_id, entry_id, *, lock=False):
    query = select(PatientSafetyEntry).where(PatientSafetyEntry.id == entry_id, PatientSafetyEntry.patient_id == patient_id)
    if lock:
        query = query.with_for_update().execution_options(populate_existing=True)
    row = db.scalar(query)
    if row is None:
        raise HTTPException(404, "Registro de seguridad no encontrado")
    return row


def create(db, user, patient_id, payload):
    patient = authorize(db, user, patient_id, write=True)
    if payload.clinical_history_id is not None:
        history = db.get(ClinicalHistory, payload.clinical_history_id)
        if not history or history.patient_id != patient_id or not has_normal_history_access(db, user, history):
            raise HTTPException(404, "Contexto clínico no autorizado para este paciente")
    if payload.status != "active" and not payload.change_reason:
        raise HTTPException(422, "Indique el motivo del estado del registro")
    data = payload.model_dump(exclude={"change_reason"})
    row = PatientSafetyEntry(organization_id=patient.organization_id, patient_id=patient_id,
        recorded_by_user_id=user.id, updated_by_user_id=user.id, revision=1, **data)
    db.add(row)
    db.flush()
    audit(db, user, row, "created", None, payload.change_reason)
    db.commit()
    db.refresh(row)
    return row


def update(db, user, patient_id, entry_id, payload):
    authorize(db, user, patient_id, write=True)
    row = get_entry(db, patient_id, entry_id, lock=True)
    if payload.revision != row.revision:
        raise HTTPException(409, "El registro cambió; vuelva a cargarlo antes de guardar")
    data = payload.model_dump(exclude={"revision", "change_reason"})
    changed = {key: value for key, value in data.items() if getattr(row, key) != value}
    if not changed:
        return row
    if row.status == "entered_in_error":
        raise HTTPException(409, "Un registro marcado por error se conserva como histórico; agregue uno correcto")
    if "status" in changed and not payload.change_reason:
        raise HTTPException(422, "Indique el motivo del cambio de estado")
    before = snapshot(row)
    for key, value in changed.items():
        setattr(row, key, value)
    row.updated_by_user_id = user.id
    row.updated_at = datetime.now(timezone.utc)
    row.revision += 1
    action = "entered_in_error" if row.status == "entered_in_error" else "status_changed" if "status" in changed else "updated"
    audit(db, user, row, action, before, payload.change_reason)
    db.commit()
    db.refresh(row)
    return row
