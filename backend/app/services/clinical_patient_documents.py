"""Authorization and lifecycle for the two patient-linked clinical documents."""
from datetime import datetime, timezone

from fastapi import HTTPException
from sqlalchemy import inspect, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models import Appointment, CareCenter, ClinicalHistory, Patient, PatientInsurance, User
from app.models.clinical_audit import ClinicalAuditLog
from app.models.clinical_patient_document import PhysicalExamination, PreoperativeEvaluation
from app.schemas.clinical_patient_document import DocumentCreate, DocumentLink, DocumentTransition, DocumentUpdate
from app.services.administration import effective_permissions
from app.services.appointment_scope import assigned_center_ids, ensure_appointment_access, is_role, secretary_can_manage
from app.services.clinical_access import can_access_history
from app.services.clinical_coverage import installation_now
from app.services.clinical_patient_document_fields import ADMINISTRATIVE_KEYS, PHYSICAL_KEYS, PREOPERATIVE_KEYS
from app.services import clinical_forms
from app.services.patient_scope import require_patient_identity_access, require_patient_selection, require_patient_clinical_scope


KINDS = {"preoperative": (PreoperativeEvaluation, PREOPERATIVE_KEYS),
         "physical_exam": (PhysicalExamination, PHYSICAL_KEYS)}
OPEN_STATUSES = {"draft", "pending_evaluation"}


def require_schema(db: Session) -> None:
    # Official pilot remains at 0054 until activation; never query missing tables.
    if not (inspect(db.get_bind()).has_table("preoperative_evaluations") and inspect(db.get_bind()).has_table("physical_examinations")):
        raise HTTPException(503, "Los documentos clínicos aún no están activados")


def _model(kind: str):
    if kind not in KINDS:
        raise HTTPException(404, "Tipo de documento no encontrado")
    return KINDS[kind][0]


def _permission(user: User, code: str) -> None:
    if code not in effective_permissions(user):
        raise HTTPException(403, "No tiene permiso para esta operación")


def _doctor_scope(db: Session, user: User, doctor_id: int, center_id: int) -> None:
    doctor = db.get(User, doctor_id)
    center = db.get(CareCenter, center_id)
    if not doctor or not doctor.is_active or not is_role(doctor, "doctor") or not center or not center.is_active:
        raise HTTPException(404, "Contexto clínico no encontrado")
    if center_id not in assigned_center_ids(doctor):
        raise HTTPException(404, "Contexto clínico no encontrado")
    if is_role(user, "doctor"):
        if doctor_id != user.id or center_id not in assigned_center_ids(user):
            raise HTTPException(404, "Documento no encontrado")
    elif is_role(user, "secretary") and not is_role(user, "admin"):
        if center_id not in assigned_center_ids(user) or not secretary_can_manage(user, center_id, doctor_id, db):
            raise HTTPException(403, "No tiene acceso a este médico y centro")
    elif not is_role(user, "admin"):
        raise HTTPException(403, "No tiene acceso a documentos clínicos")


def _clinical_doctor(db: Session, user: User, row) -> None:
    _permission(user, "clinical_documents:edit_clinical")
    _permission(user, "clinical:access")
    if not is_role(user, "doctor") or row.doctor_id != user.id or row.center_id not in assigned_center_ids(user):
        raise HTTPException(404, "Documento no encontrado")


def _can_view(db: Session, user: User, row) -> bool:
    _permission(user, "clinical_documents:view")
    if is_role(user, "doctor") and row.doctor_id == user.id and row.center_id in assigned_center_ids(user):
        _permission(user, "clinical:access")
        return True
    if is_role(user, "admin"):
        require_patient_identity_access(db, user, row.patient_id)
        return False
    if is_role(user, "secretary") and row.center_id in assigned_center_ids(user) and secretary_can_manage(user, row.center_id, row.doctor_id, db):
        # The document itself is a scoped patient relationship. A secretary may
        # prepare it before an appointment exists, after patient selection was
        # verified on creation. Never expose its clinical content here.
        return False
    raise HTTPException(404, "Documento no encontrado")


def _row(db: Session, kind: str, document_id: int, *, lock: bool = False):
    model = _model(kind)
    query = select(model).where(model.id == document_id)
    if lock:
        query = query.with_for_update().execution_options(populate_existing=True)
    row = db.scalar(query)
    if row is None:
        raise HTTPException(404, "Documento no encontrado")
    return row


def _audit(db: Session, user: User, kind: str, row, action: str, *, changed_fields: list[str] | None = None,
           outcome: str = "success", reason: str | None = None) -> None:
    db.add(ClinicalAuditLog(
        center_id=row.center_id, user_id=user.id,
        action=f"clinical_document:{action}", resource_type=kind, resource_id=row.id,
        clinical_history_id=row.clinical_history_id, outcome=outcome,
        context={"status": row.status, **({"fields": changed_fields} if changed_fields else {}),
                 **({"reason": reason} if reason else {})},
    ))


def _profile(db: Session, row) -> dict:
    if row.identity_snapshot:
        return row.identity_snapshot
    patient = db.get(Patient, row.patient_id)
    doctor = db.get(User, row.doctor_id)
    center = db.get(CareCenter, row.center_id)
    primary = db.scalar(select(PatientInsurance).where(
        PatientInsurance.patient_id == row.patient_id, PatientInsurance.is_active.is_(True),
        PatientInsurance.is_primary.is_(True)).limit(1))
    birthday = patient.date_of_birth
    as_of = row.document_date
    age = as_of.year - birthday.year - ((as_of.month, as_of.day) < (birthday.month, birthday.day))
    return {
        "patient_name": f"{patient.first_name} {patient.last_name}",
        "date_of_birth": patient.date_of_birth.isoformat(),
        "age_at_document": str(age),
        "sex": patient.registered_sex,
        "occupation": patient.occupation,
        "document_type": patient.document_type,
        "document_number": patient.document_number,
        "phone": patient.phone,
        "address": patient.address,
        "insurance_company": primary.insurance_company.name if primary else None,
        "insurance_plan": primary.plan_name if primary else None,
        "doctor_name": doctor.full_name,
        "center_name": center.name,
    }


def serialize(db: Session, user: User, kind: str, row, *, full: bool = True) -> dict:
    clinical = _can_view(db, user, row)
    profile = _profile(db, row) if clinical and full else None
    has_templates = clinical_forms.schema_ready(db)
    version = clinical_forms.document_version(db, row) if has_templates and full else None
    template_id, template_version_id = clinical_forms.document_template_refs(db, row) if has_templates else (None, None)
    admin_keys = clinical_forms.administrative_keys(version.definition) if version else ADMINISTRATIVE_KEYS
    return {
        "kind": kind, "id": row.id, "patient_id": row.patient_id,
        "doctor_id": row.doctor_id, "center_id": row.center_id,
        "appointment_id": row.appointment_id, "clinical_history_id": row.clinical_history_id,
        "document_date": row.document_date, "status": row.status, "revision": row.revision,
        "created_by_user_id": row.created_by_user_id,
        "created_by_name": db.get(User, row.created_by_user_id).full_name,
        "last_updated_by_user_id": row.last_updated_by_user_id,
        "signed_by_user_id": row.signed_by_user_id,
        "created_at": row.created_at, "updated_at": row.updated_at, "signed_at": row.signed_at,
        "doctor_name": profile["doctor_name"] if profile else db.get(User, row.doctor_id).full_name,
        "center_name": profile["center_name"] if profile else db.get(CareCenter, row.center_id).name,
        "patient_name": profile["patient_name"] if profile else f"{db.get(Patient, row.patient_id).first_name} {db.get(Patient, row.patient_id).last_name}",
        "values": (row.content if clinical else {key: value for key, value in (row.content or {}).items()
                                                  if key in admin_keys}) if full else None,
        "patient_profile": profile,
        "template_id": template_id,
        "template_version_id": template_version_id,
        "template_definition": version.definition if version and clinical else None,
        "template_admin_fields": [field for page in version.definition["pages"] for section in page["sections"]
                                  for field in section["fields"] if field.get("editable_by") == "administrative"] if version and not clinical else None,
        "template_source": "versioned" if version else "legacy_0055",
    }


def create(db: Session, user: User, kind: str, payload: DocumentCreate):
    require_schema(db)
    if clinical_forms.schema_ready(db) and is_role(user, "secretary") and not (is_role(user, "admin") or is_role(user, "doctor")):
        capability = "start_preoperative" if kind == "preoperative" else "start_physical_exam"
        if not clinical_forms.secretary_capabilities(db, user)[capability]:
            raise HTTPException(403, "No tiene permiso para iniciar este documento")
    else:
        _permission(user, "clinical_documents:create")
    model = _model(kind)
    if is_role(user, "doctor"):
        if payload.doctor_id is not None and payload.doctor_id != user.id:
            raise HTTPException(404, "Documento no encontrado")
        contextual_appointment = db.get(Appointment, payload.appointment_id) if payload.appointment_id else None
        inferred_center = contextual_appointment.center_id if contextual_appointment else None
        center_id = payload.center_id or inferred_center
        if center_id is None:
            centers = assigned_center_ids(user)
            if len(centers) != 1:
                raise HTTPException(422, "Seleccione un centro autorizado")
            center_id = next(iter(centers))
        payload = payload.model_copy(update={"doctor_id": user.id, "center_id": center_id})
    elif payload.doctor_id is None or payload.center_id is None:
        raise HTTPException(422, "Seleccione centro y médico responsable")
    _doctor_scope(db, user, payload.doctor_id, payload.center_id)
    if is_role(user, "doctor") and payload.doctor_id == user.id:
        _permission(user, "clinical:access")
        require_patient_clinical_scope(db, user, payload.patient_id)
    else:
        _permission(user, "patients:access")
        require_patient_selection(db, user, payload.patient_id, center_id=payload.center_id,
                                  doctor_id=payload.doctor_id, token=payload.patient_selection_token)
    patient = db.get(Patient, payload.patient_id)
    if patient is None:
        raise HTTPException(404, "Paciente no encontrado")
    if db.get(CareCenter, payload.center_id).organization_id != patient.organization_id:
        raise HTTPException(404, "Contexto clínico no encontrado")
    if payload.appointment_id is not None:
        appointment = db.get(Appointment, payload.appointment_id)
        if not appointment or appointment.organization_id != patient.organization_id or (appointment.patient_id, appointment.doctor_id, appointment.center_id) != (
                payload.patient_id, payload.doctor_id, payload.center_id):
            raise HTTPException(404, "Cita no encontrada en este contexto")
        ensure_appointment_access(user, appointment, db)
    if payload.clinical_history_id is not None:
        if not is_role(user, "doctor") or payload.doctor_id != user.id:
            raise HTTPException(403, "Solo el médico puede vincular una consulta")
        history = db.get(ClinicalHistory, payload.clinical_history_id)
        if not history or history.organization_id != patient.organization_id or (history.patient_id, history.doctor_id, history.center_id, history.appointment_id) != (
                payload.patient_id, payload.doctor_id, payload.center_id, payload.appointment_id) or not can_access_history(db, user, history):
            raise HTTPException(404, "Consulta no encontrada en este contexto")
        if history.status != "in_progress":
            raise HTTPException(409, "La consulta ya está finalizada; no puede vincular un documento nuevo")
    # Serialize same-patient creation in PostgreSQL and retain a partial unique
    # index as the final protection against concurrent duplicate open drafts.
    db.scalar(select(Patient).where(Patient.id == payload.patient_id).with_for_update())
    document_date = installation_now().date()
    identity = [model.organization_id == patient.organization_id, model.status.in_(OPEN_STATUSES)]
    if payload.appointment_id is not None:
        identity.append(model.appointment_id == payload.appointment_id)
    elif payload.clinical_history_id is not None:
        identity.extend((model.appointment_id.is_(None), model.clinical_history_id == payload.clinical_history_id))
    else:
        identity.extend((model.patient_id == payload.patient_id, model.doctor_id == payload.doctor_id,
                         model.center_id == payload.center_id, model.appointment_id.is_(None), model.clinical_history_id.is_(None),
                         model.document_date == document_date))
    existing = db.scalar(select(model).where(*identity).order_by(model.id).limit(1))
    if existing:
        if (existing.patient_id, existing.doctor_id, existing.center_id) != (
                payload.patient_id, payload.doctor_id, payload.center_id):
            raise HTTPException(409, "El contexto clínico ya pertenece a otro documento")
        return existing, False
    selected = clinical_forms.resolve(db, kind, center_id=payload.center_id, doctor_id=payload.doctor_id)
    row = model(organization_id=patient.organization_id, patient_id=payload.patient_id,
                doctor_id=payload.doctor_id, center_id=payload.center_id,
                appointment_id=payload.appointment_id, clinical_history_id=payload.clinical_history_id,
                document_date=document_date, status="draft", content={},
                created_by_user_id=user.id, last_updated_by_user_id=user.id)
    db.add(row)
    try:
        db.flush()
        if selected:
            clinical_forms.bind_document_version(db, row, selected[0].id, selected[1].id)
        _audit(db, user, kind, row, "created")
        db.commit()
    except IntegrityError:
        db.rollback()
        existing = db.scalar(select(model).where(*identity).order_by(model.id).limit(1))
        if existing:
            if (existing.patient_id, existing.doctor_id, existing.center_id) != (
                    payload.patient_id, payload.doctor_id, payload.center_id):
                raise HTTPException(409, "El contexto clínico ya pertenece a otro documento")
            return existing, False
        raise
    db.refresh(row)
    return row, True


def link_context(db: Session, user: User, kind: str, document_id: int, payload: DocumentLink) -> dict:
    """Explicitly attach one selected, open standalone draft to a consultation."""
    require_schema(db)
    row = _row(db, kind, document_id, lock=True)
    _clinical_doctor(db, user, row)
    if row.status not in OPEN_STATUSES or row.appointment_id is not None or row.clinical_history_id is not None:
        raise HTTPException(409, "El documento ya tiene contexto o no está pendiente")
    if row.revision != payload.expected_revision:
        raise HTTPException(409, "El documento cambió; recárguelo antes de vincular")
    appointment = db.get(Appointment, payload.appointment_id)
    if not appointment or appointment.organization_id != row.organization_id or (
            appointment.patient_id, appointment.doctor_id, appointment.center_id) != (
            row.patient_id, row.doctor_id, row.center_id):
        raise HTTPException(404, "Cita no encontrada en este contexto")
    ensure_appointment_access(user, appointment, db)
    if payload.clinical_history_id is not None:
        history = db.get(ClinicalHistory, payload.clinical_history_id)
        if not history or history.organization_id != row.organization_id or (
                history.patient_id, history.doctor_id, history.center_id, history.appointment_id) != (
                row.patient_id, row.doctor_id, row.center_id, payload.appointment_id) or not can_access_history(db, user, history):
            raise HTTPException(404, "Consulta no encontrada en este contexto")
        if history.status != "in_progress":
            raise HTTPException(409, "La consulta ya está finalizada")
    model = _model(kind)
    conflicting = db.scalar(select(model.id).where(
        model.organization_id == row.organization_id, model.appointment_id == payload.appointment_id,
        model.status.in_(OPEN_STATUSES), model.id != row.id).limit(1))
    if conflicting is not None:
        raise HTTPException(409, "Ya existe un documento pendiente para esta consulta")
    row.appointment_id = payload.appointment_id
    row.clinical_history_id = payload.clinical_history_id
    row.revision += 1
    row.last_updated_by_user_id = user.id
    row.updated_at = datetime.now(timezone.utc)
    _audit(db, user, kind, row, "linked_to_consultation")
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, "Ya existe un documento pendiente para esta consulta")
    db.refresh(row)
    return serialize(db, user, kind, row)


def list_for_patient(db: Session, user: User, patient_id: int) -> list[dict]:
    require_schema(db)
    _permission(user, "clinical_documents:view")
    rows = [(kind, row) for kind, (model, _) in KINDS.items()
            for row in db.scalars(select(model).where(model.patient_id == patient_id).order_by(model.document_date.desc(), model.id.desc())).all()]
    visible = []
    for kind, row in rows:
        try:
            visible.append(serialize(db, user, kind, row, full=False))
        except HTTPException:
            continue
    if not visible:
        # Do not reveal an out-of-scope patient even if the document list is empty.
        require_patient_identity_access(db, user, patient_id)
    return sorted(visible, key=lambda item: (item["document_date"], item["created_at"]), reverse=True)


def get(db: Session, user: User, kind: str, document_id: int) -> dict:
    require_schema(db)
    return serialize(db, user, kind, _row(db, kind, document_id))


def get_for_print(db: Session, user: User, kind: str, document_id: int) -> dict:
    require_schema(db)
    row = _row(db, kind, document_id)
    if not _can_view(db, user, row):
        raise HTTPException(403, "Solo el médico autorizado puede imprimir contenido clínico")
    return serialize(db, user, kind, row)


def update(db: Session, user: User, kind: str, document_id: int, payload: DocumentUpdate) -> dict:
    require_schema(db)
    row = _row(db, kind, document_id, lock=True)
    clinical = _can_view(db, user, row)
    if row.status == "signed" or (row.status == "completed" and not clinical):
        _audit(db, user, kind, row, "update_blocked", outcome="conflict", reason="document_locked")
        db.commit()
        raise HTTPException(409, "Este documento no admite más cambios")
    if row.revision != payload.expected_revision:
        raise HTTPException(409, "El documento cambió; recárguelo antes de guardar")
    version = clinical_forms.document_version(db, row)
    allowed = clinical_forms.field_keys(version.definition) if version else KINDS[kind][1]
    if not set(payload.values) <= allowed:
        raise HTTPException(422, "Campo no permitido para este documento")
    if version:
        clinical_forms.validate_document_values(version.definition, payload.values)
    if clinical:
        _clinical_doctor(db, user, row)
    else:
        if clinical_forms.schema_ready(db) and is_role(user, "secretary") and not is_role(user, "admin"):
            if not clinical_forms.secretary_capabilities(db, user)["prepare_administrative"]:
                raise HTTPException(403, "No tiene permiso para preparar este documento")
        else:
            _permission(user, "clinical_documents:prepare")
        admin_keys = clinical_forms.administrative_keys(version.definition) if version else ADMINISTRATIVE_KEYS
        if not set(payload.values) <= admin_keys:
            raise HTTPException(403, "Este campo requiere autorización médica")
    content = dict(row.content or {})
    for key, value in payload.values.items():
        if value.strip():
            content[key] = value.strip()
        else:
            content.pop(key, None)
    row.content = content
    row.revision += 1
    row.last_updated_by_user_id = user.id
    row.updated_at = datetime.now(timezone.utc)
    _audit(db, user, kind, row, "updated", changed_fields=sorted(payload.values))
    db.commit()
    db.refresh(row)
    return serialize(db, user, kind, row)


def transition(db: Session, user: User, kind: str, document_id: int, action: str, payload: DocumentTransition) -> dict:
    require_schema(db)
    row = _row(db, kind, document_id, lock=True)
    clinical = _can_view(db, user, row)
    if row.revision != payload.expected_revision:
        raise HTTPException(409, "El documento cambió; recárguelo antes de continuar")
    if action == "submit":
        if clinical_forms.schema_ready(db) and is_role(user, "secretary") and not is_role(user, "admin"):
            if not clinical_forms.secretary_capabilities(db, user)["prepare_administrative"]:
                raise HTTPException(403, "No tiene permiso para preparar este documento")
        else:
            _permission(user, "clinical_documents:prepare")
        if row.status != "draft":
            raise HTTPException(409, "Solo un borrador puede enviarse a evaluación")
        row.status = "pending_evaluation"
    elif action == "complete":
        if not clinical:
            raise HTTPException(403, "Solo el médico puede completar el documento")
        _clinical_doctor(db, user, row)
        if row.status not in OPEN_STATUSES:
            raise HTTPException(409, "Este documento no puede completarse")
        version = clinical_forms.document_version(db, row)
        if version:
            clinical_forms.validate_required_fields(version.definition, row.content or {})
        elif not any(key not in ADMINISTRATIVE_KEYS for key in (row.content or {})):
            raise HTTPException(422, "Registre contenido clínico antes de completar")
        row.status = "completed"
    elif action == "sign":
        _permission(user, "clinical_documents:sign")
        if not clinical:
            raise HTTPException(403, "Solo el médico puede firmar")
        _clinical_doctor(db, user, row)
        if row.status != "completed":
            raise HTTPException(409, "Complete el documento antes de firmarlo")
        row.identity_snapshot = _profile(db, row)
        row.status = "signed"
        row.signed_by_user_id = user.id
        row.signed_at = datetime.now(timezone.utc)
    else:
        raise HTTPException(404, "Acción no encontrada")
    row.revision += 1
    row.last_updated_by_user_id = user.id
    row.updated_at = datetime.now(timezone.utc)
    _audit(db, user, kind, row, action)
    db.commit()
    db.refresh(row)
    return serialize(db, user, kind, row)
