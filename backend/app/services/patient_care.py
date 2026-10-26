"""Relationship discovery is NOT clinical-record access or episode responsibility.

The existing patient/clinical scope services intentionally never consult this
table. Assignment cannot bootstrap access to histories, documents or Safety.
"""
from datetime import datetime, timezone

from fastapi import HTTPException
from sqlalchemy import inspect, select
from sqlalchemy.orm import joinedload

from app.models import CareCenter, Patient, Specialty, User
from app.models.clinical_audit import ClinicalAuditLog
from app.models.patient_care import PatientCareRelationship as Relationship
from app.services.administration import effective_permissions
from app.services.appointment_scope import assigned_center_ids, is_role
from app.services.patient_scope import require_patient_identity_access

VIEW = "patient_care:view"
MANAGE = "patient_care:manage"
FIELDS = ("relationship_type", "origin", "status", "center_id", "specialty_id", "started_at",
          "first_seen_at", "last_seen_at", "ended_at", "created_from_clinical_history_id", "last_clinical_history_id")


def utc(value):
    return value.replace(tzinfo=timezone.utc) if value is not None and value.tzinfo is None else value


def available(db):
    return inspect(db.connection()).has_table("patient_care_relationships")


def permitted(user, *, manage=False):
    permissions = effective_permissions(user)
    required = {"patients:view", VIEW} | ({"users:manage", MANAGE} if manage else set())
    return user.is_active and required.issubset(permissions) and (
        is_role(user, "admin") if manage else any(is_role(user, role) for role in ("doctor", "admin")))


def authorize(db, user, patient_id=None, *, manage=False):
    if db.info.get("access_scope") == "platform" or not permitted(user, manage=manage):
        raise HTTPException(403, "No tiene permiso para las relaciones asistenciales")
    if not available(db):
        raise HTTPException(503, "Relaciones asistenciales pendientes de activación")
    if patient_id is not None:
        return require_patient_identity_access(db, user, patient_id)


def snapshot(row):
    return {key: utc(value).isoformat() if isinstance(value, datetime) else value
            for key in FIELDS for value in (getattr(row, key),)}


def audit(db, user, row, action, before, reason=None):
    db.add(ClinicalAuditLog(organization_id=row.organization_id, center_id=row.center_id,
        user_id=user.id, resource_type="patient_care_relationship", resource_id=row.id,
        clinical_history_id=row.last_clinical_history_id, action=f"patient_care.{action}", outcome="success",
        context={"patient_id":row.patient_id, "doctor_id":row.doctor_id, "before":before,
                 "after":snapshot(row), "reason":reason, "revision":row.revision}))


def lock_patient(db, patient_id):
    # One serialization point for all relationship writers, including first
    # insertion. Unique(org,patient,doctor) is the final database safeguard.
    patient = db.scalar(select(Patient).where(Patient.id == patient_id).with_for_update())
    if patient is None:
        raise HTTPException(404, "Paciente no encontrado")
    return patient


def entry(db, patient_id, relationship_id):
    row = db.scalar(select(Relationship).where(Relationship.id == relationship_id,
        Relationship.patient_id == patient_id).execution_options(populate_existing=True))
    if row is None:
        raise HTTPException(404, "Relación asistencial no encontrada")
    return row


def validate_assignment(db, patient, doctor_id, center_id, specialty_id):
    doctor = db.get(User, doctor_id)
    if not doctor or not doctor.is_active or not is_role(doctor, "doctor"):
        raise HTTPException(404, "Médico no autorizado en esta organización")
    if center_id is not None:
        center = db.get(CareCenter, center_id)
        if not center or center.organization_id != patient.organization_id or not center.is_active or center_id not in assigned_center_ids(doctor):
            raise HTTPException(404, "Centro no autorizado para este médico")
    if specialty_id is not None:
        specialty = db.get(Specialty, specialty_id)
        doctor_specialties = {s.id for s in doctor.specialties}
        if doctor.doctor_profile:
            doctor_specialties.add(doctor.doctor_profile.specialty_id)
        if not specialty or specialty.organization_id != patient.organization_id or not specialty.is_active or specialty_id not in doctor_specialties:
            raise HTTPException(404, "Especialidad no autorizada para este médico")


def assign(db, user, patient_id, payload):
    authorize(db, user, patient_id, manage=True)
    patient = lock_patient(db, patient_id)
    validate_assignment(db, patient, payload.doctor_id, payload.center_id, payload.specialty_id)
    existing = db.scalar(select(Relationship).where(Relationship.patient_id == patient_id,
        Relationship.doctor_id == payload.doctor_id))
    if existing:
        # A repeat POST never reopens or silently reconfigures a relationship.
        return existing, False
    now = datetime.now(timezone.utc)
    row = Relationship(organization_id=patient.organization_id, patient_id=patient_id,
        origin="administrative_assignment", started_at=now, ended_at=now if payload.status == "ended" else None,
        created_by_user_id=user.id, updated_by_user_id=user.id, revision=1,
        **payload.model_dump(exclude={"reason"}))
    db.add(row)
    db.flush()
    audit(db, user, row, "manual_assigned", None, payload.reason)
    db.commit()
    db.refresh(row)
    return row, True


def update(db, user, patient_id, relationship_id, payload):
    authorize(db, user, patient_id, manage=True)
    patient = lock_patient(db, patient_id)
    row = entry(db, patient_id, relationship_id)
    if row.revision != payload.revision:
        raise HTTPException(409, "La relación cambió; vuelva a cargarla")
    data = payload.model_dump(exclude={"revision", "reason"})
    changed = {key:value for key,value in data.items() if getattr(row,key) != value}
    if not changed:
        return row
    validate_assignment(db, patient, row.doctor_id, payload.center_id, payload.specialty_id)
    before = snapshot(row)
    now = datetime.now(timezone.utc)
    for key,value in changed.items():
        setattr(row,key,value)
    row.ended_at = now if payload.status == "ended" else None
    row.updated_at, row.updated_by_user_id = now, user.id
    row.revision += 1
    action = ("ended" if row.status == "ended" else "reactivated" if before["status"] in {"ended","historical"} and row.status in {"active","follow_up"}
              else "status_changed" if "status" in changed else "updated")
    audit(db,user,row,action,before,payload.reason)
    db.commit()
    db.refresh(row)
    return row


def observe_completed_consultation(db, user, history):
    """Called only after the authorized conditional completion, before commit.

    No retrospective inference, no read-side mutation, no appointment hook.
    Missing staged schema is an intentional no-op on the official 0058 DB.
    """
    if not available(db):
        return None
    if (history.status != "completed" or not history.completed_at or history.doctor_id != user.id
            or not user.is_active or not is_role(user,"doctor") or "clinical:access" not in effective_permissions(user)):
        raise HTTPException(409, "Se requiere una consulta finalizada por su médico autorizado")
    patient = lock_patient(db,history.patient_id)
    if history.organization_id != patient.organization_id:
        raise HTTPException(404, "Contexto clínico no encontrado")
    row = db.scalar(select(Relationship).where(Relationship.patient_id == patient.id,
        Relationship.doctor_id == user.id).execution_options(populate_existing=True))
    seen = utc(history.completed_at)
    if row is None:
        row = Relationship(organization_id=patient.organization_id, patient_id=patient.id, doctor_id=user.id,
            relationship_type="treating", origin="consultation", status="active", started_at=seen,
            first_seen_at=seen, last_seen_at=seen, center_id=history.center_id, specialty_id=history.specialty_id,
            created_from_clinical_history_id=history.id, last_clinical_history_id=history.id,
            created_by_user_id=user.id, updated_by_user_id=user.id, revision=1)
        db.add(row)
        db.flush()
        audit(db,user,row,"created",None)
        return row
    if row.last_clinical_history_id == history.id:
        return row  # Same clinical event is idempotent, even if retried internally.
    before = snapshot(row)
    if row.first_seen_at is None or seen < utc(row.first_seen_at):
        row.first_seen_at = seen
    if row.last_seen_at is None or seen >= utc(row.last_seen_at):
        row.last_seen_at, row.last_clinical_history_id = seen, history.id
        if history.center_id is not None:
            row.center_id = history.center_id
        if history.specialty_id is not None:
            row.specialty_id = history.specialty_id
    # A delayed older completion must not undo a later administrative ending.
    if row.status in {"ended","historical"} and seen > utc(row.updated_at):
        row.status, row.ended_at = "active", None
    if snapshot(row) != before:
        row.updated_at, row.updated_by_user_id = datetime.now(timezone.utc), user.id
        row.revision += 1
        audit(db,user,row,"reactivated" if before["status"] != row.status else "updated",before)
    return row


def list_related(db,user,patient_id):
    authorize(db,user,patient_id)
    query = select(Relationship).options(joinedload(Relationship.doctor), joinedload(Relationship.center),
        joinedload(Relationship.specialty), joinedload(Relationship.organization)).where(Relationship.patient_id == patient_id)
    return db.scalars(query.order_by(Relationship.last_seen_at.desc().nullslast(),Relationship.id)).all()


def my_patients(db,user,*,status=None,center_id=None,limit=50,offset=0):
    authorize(db,user)
    if not is_role(user,"doctor"):
        raise HTTPException(403,"Consulta exclusiva del médico")
    # Minimal identity discovery for one's own associations, NOT a grant to the
    # patient record. Do not reuse this list in require_patient_clinical_scope.
    query = select(Relationship,Patient.first_name,Patient.last_name).join(Patient,
        (Patient.id == Relationship.patient_id) & (Patient.organization_id == Relationship.organization_id)
    ).options(joinedload(Relationship.doctor), joinedload(Relationship.center),joinedload(Relationship.specialty),
        joinedload(Relationship.organization)).where(Relationship.doctor_id == user.id)
    if status is not None:
        query = query.where(Relationship.status == status)
    if center_id is not None:
        if center_id not in assigned_center_ids(user):
            raise HTTPException(403,"Centro fuera del alcance del médico")
        query = query.where(Relationship.center_id == center_id)
    return db.execute(query.order_by(Relationship.last_seen_at.desc().nullslast(),Relationship.id).limit(limit).offset(offset)).all()
