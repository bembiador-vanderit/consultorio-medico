"""Explicit read decisions only. Never consumed by clinical write authorization.

Care relationships are signals, not grants. No policy, missing staged schema,
unknown context, unconfigured resources and cross-tenant requests fail closed.
"""
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from fastapi import HTTPException
from sqlalchemy import inspect, select, or_, exists, false

from app.models import CareCenter, ClinicalHistory, Organization, Patient, User
from app.models.clinical_audit import ClinicalAuditLog
from app.models.clinical_sharing import ClinicalSharingPolicy
from app.models.patient_care import PatientCareRelationship
from app.services.administration import effective_permissions
from app.services.appointment_scope import assigned_center_ids, is_role
from app.services.access_schedule import access_state

RESOURCES = ("clinical_history", "clinical_documents", "patient_safety")
POLICY_FIELDS = ("mode", "limit_to_same_center", *RESOURCES)
READ_PERMISSIONS = {"clinical_history": set(), "clinical_documents": {"clinical_documents:view"},
                    "patient_safety": {"patient_safety:view"}}


@dataclass(frozen=True)
class Decision:
    allowed: bool
    reason: str
    policy_revision: int = 0
    read_only: bool = True


def available(db):
    return inspect(db.connection()).has_table("clinical_sharing_policies")


def policy(db):
    return db.scalar(select(ClinicalSharingPolicy)) if available(db) else None


def policy_view(db):
    row = policy(db)
    return {"enabled": available(db), "revision": row.revision if row else 0,
            **{key: getattr(row, key) if row else ("assigned" if key == "mode" else key == "limit_to_same_center")
               for key in POLICY_FIELDS}}


def actor_denial(db, user, resource):
    if db.info.get("access_scope") != "tenant" or not db.info.get("organization_id"):
        return "cross_tenant"
    membership = user.tenant_membership()
    if not user.is_active or not membership or membership.state != "active" or not is_role(user, "doctor"):
        return "not_active_doctor"
    required = {"patients:view", "clinical:access"} | READ_PERMISSIONS.get(resource, set())
    if not required.issubset(effective_permissions(user)):
        return "no_clinical_read_permission"
    # current_user also enforces the session lease; direct service users cannot
    # bypass the membership's current access window.
    if not access_state(db, membership)["allowed"]:
        return "outside_access_schedule"
    return None


def future_episode_access(*, doctor_id, patient_id, organization_id, care_context_id, resource_type):
    """Reserved adapter contract. No episode model, grants or break-glass in V1."""
    return Decision(False, "episode_access_not_implemented")


def shared_patient_ids(db, user):
    """Read-side discovery only. NEVER use this predicate for patient writes.

    The existing search UI can find authorized shared records without a second
    search API. Candidates require actual finalized resource/center evidence.
    """
    from app.models.clinical_patient_document import PreoperativeEvaluation, PhysicalExamination
    from app.models.patient_safety import PatientSafetyEntry
    empty = select(Patient.id).where(false())
    if actor_denial(db, user, "clinical_history"):
        return empty
    row = policy(db)
    if row is None or row.mode == "assigned":
        return empty
    center_limited = row.limit_to_same_center or row.mode == "same_center"
    centers = assigned_center_ids(user)
    evidence = []
    def contextual(model, *conditions):
        query = select(model.id).where(model.patient_id == Patient.id, *conditions)
        if center_limited:
            query = query.where(model.center_id.in_(centers))
        return exists(query)
    if row.clinical_history:
        evidence.append(contextual(ClinicalHistory, ClinicalHistory.status == "completed"))
    if row.clinical_documents and not actor_denial(db, user, "clinical_documents"):
        evidence.extend(contextual(model, model.status.in_(("completed", "signed"))) for model in (PreoperativeEvaluation,PhysicalExamination))
    if row.patient_safety and not actor_denial(db, user, "patient_safety"):
        has_safety = exists(select(PatientSafetyEntry.id).where(PatientSafetyEntry.patient_id == Patient.id))
        if center_limited:
            context = or_(contextual(ClinicalHistory), contextual(PreoperativeEvaluation), contextual(PhysicalExamination), contextual(PatientCareRelationship))
            evidence.append(has_safety & context)
        else:
            evidence.append(has_safety)
    if not evidence:
        return empty
    query = select(Patient.id).where(or_(*evidence))
    if row.mode == "active_relationship":
        query = query.where(exists(select(PatientCareRelationship.id).where(
            PatientCareRelationship.patient_id == Patient.id, PatientCareRelationship.doctor_id == user.id,
            PatientCareRelationship.status.in_(("active", "follow_up")))))
    return query


def decide(db, user, patient_id, resource, *, center_id=None, care_context_id=None, row=None):
    reason = actor_denial(db, user, resource)
    if reason:
        return Decision(False, reason)
    org_id = db.info["organization_id"]
    patient = db.get(Patient, patient_id)
    if not patient or patient.organization_id != org_id:
        return Decision(False, "cross_tenant")
    if resource not in RESOURCES:
        return Decision(False, "resource_not_shared")
    if center_id is not None:
        center = db.get(CareCenter, center_id)
        if not center or center.organization_id != org_id or not center.is_active:
            return Decision(False, "outside_center_scope")
    if care_context_id is not None:
        # Existing CareContext is a center directory, not an encounter. The
        # canonical context here is ClinicalHistory, and arbitrary ids grant none.
        context = db.get(ClinicalHistory, care_context_id)
        if not context or context.organization_id != org_id or context.patient_id != patient_id or context.center_id != center_id:
            return Decision(False, "invalid_context")
    row = row or policy(db)
    if not row or row.organization_id != org_id or not getattr(row, resource):
        return Decision(False, "resource_not_shared")
    def result(allowed, why):
        return Decision(allowed, why, row.revision)
    if row.mode == "assigned":
        # Retain all existing author/coverage permissions in their original
        # endpoints. The opt-in gateway does not broaden that baseline.
        if care_context_id is not None and context.doctor_id == user.id:
            return result(True, "assigned_context")
        return result(False, "assigned_context_required")
    if row.limit_to_same_center or row.mode == "same_center":
        if center_id is None or center_id not in assigned_center_ids(user):
            return result(False, "outside_center_scope")
    if row.mode == "active_relationship":
        related = db.scalar(select(PatientCareRelationship.id).where(
            PatientCareRelationship.patient_id == patient_id, PatientCareRelationship.doctor_id == user.id,
            PatientCareRelationship.status.in_(("active", "follow_up"))).limit(1))
        return result(related is not None, "active_care_relationship" if related else "no_active_relationship")
    if row.mode == "same_center":
        return result(True, "same_center_policy")
    if row.mode == "organization":
        return result(True, "same_organization_policy")
    return result(False, "policy_not_supported")


def update_policy(db, user, payload):
    membership = user.tenant_membership()
    if (db.info.get("access_scope") != "tenant" or not user.is_active or not membership or membership.state != "active"
            or not is_role(user, "admin") or "users:manage" not in effective_permissions(user)):
        raise HTTPException(403, "No tiene permiso para configurar la política clínica")
    if not available(db):
        raise HTTPException(503, "Política clínica pendiente de activación")
    org_id = db.info["organization_id"]
    # Stable lock even on first creation; serializes policy changes and shared
    # reads so a revoked policy cannot authorize a subsequent resource read.
    db.scalar(select(Organization).where(Organization.id == org_id).with_for_update())
    row = policy(db)
    before = {key: getattr(row, key) for key in POLICY_FIELDS} if row else None
    if payload.revision != (row.revision if row else 0):
        raise HTTPException(409, "La política cambió; vuelva a cargarla")
    values = payload.model_dump(include=set(POLICY_FIELDS))
    if before == values:
        return policy_view(db)
    if row is None:
        row = ClinicalSharingPolicy(organization_id=org_id, updated_by_user_id=user.id)
        db.add(row)
    else:
        row.revision += 1
    for key, value in values.items():
        setattr(row, key, value)
    row.updated_by_user_id, row.updated_at = user.id, datetime.now(timezone.utc)
    db.flush()
    db.add(ClinicalAuditLog(organization_id=org_id, user_id=user.id, action="clinical_sharing.policy_updated",
        resource_type="clinical_sharing_policy", resource_id=row.id, outcome="success",
        context={"before": before, "after": values, "reason": payload.reason, "revision": row.revision}))
    db.commit()
    return policy_view(db)


def audit_read(db, user, patient_id, resource, row, reasons, center_id=None):
    # Called only by an explicit resource opening, never by capabilities/render.
    # Organization row lock (held by caller) makes dedup safe across processes.
    now = datetime.now(timezone.utc)
    resource_type = f"shared_{resource}"
    recent = db.scalars(select(ClinicalAuditLog).where(
        ClinicalAuditLog.user_id == user.id, ClinicalAuditLog.resource_id == patient_id,
        ClinicalAuditLog.resource_type == resource_type,
        ClinicalAuditLog.created_at >= (now - timedelta(minutes=5)).replace(tzinfo=None)))
    if any((log.context or {}).get("policy_revision") == row.revision and log.center_id == center_id for log in recent):
        return
    db.add(ClinicalAuditLog(organization_id=row.organization_id, user_id=user.id, center_id=center_id,
        action="clinical_sharing.read", resource_type=resource_type, resource_id=patient_id,
        outcome="success", context={"patient_id": patient_id, "resource_type": resource,
            "policy_revision": row.revision, "reasons": sorted(set(reasons)), "read_only": True}))
