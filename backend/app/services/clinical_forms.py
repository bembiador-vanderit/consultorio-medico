"""Template lifecycle, assignment resolution and document field validation."""
from copy import deepcopy
from decimal import Decimal, InvalidOperation
from datetime import datetime, timezone

from fastapi import HTTPException
from sqlalchemy import inspect, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models import CareCenter, ClinicalFormAssignment, ClinicalFormTemplate, ClinicalFormVersion, SecretaryDocumentGrant, Specialty, User
from app.models.administration import SecurityAudit
from app.schemas.clinical_form import FormDefinition
from app.services.administration import effective_permissions
from app.services.appointment_scope import assigned_center_ids, is_role
from app.services.clinical_patient_document_fields import PHYSICAL_EXAM_FIELDS, PREOPERATIVE_SECTIONS


def schema_ready(db: Session) -> bool:
    cached = db.info.get("clinical_forms_0056_ready")
    if cached is not None:
        return cached
    get_bind = getattr(db, "get_bind", None)
    if not get_bind:
        return False
    inspector = inspect(get_bind())
    ready = bool(inspector.has_table("clinical_form_templates") and
                 all("template_version_id" in {col["name"] for col in inspector.get_columns(table)}
                     for table in ("preoperative_evaluations", "physical_examinations")))
    db.info["clinical_forms_0056_ready"] = ready
    return ready


def require_schema(db: Session) -> None:
    if not schema_ready(db):
        raise HTTPException(503, "El diseñador de formularios aún no está activado")


def require_admin(user: User, code: str) -> None:
    if not is_role(user, "admin") or code not in effective_permissions(user):
        raise HTTPException(403, "No tiene permiso para administrar formularios clínicos")


def audit(db: Session, actor: User, action: str, center_id: int | None = None) -> None:
    db.add(SecurityAudit(actor_id=actor.id, action=f"clinical_form:{action}", outcome="success", center_id=center_id))


def _template(db: Session, template_id: int, lock: bool = False) -> ClinicalFormTemplate:
    query = select(ClinicalFormTemplate).where(ClinicalFormTemplate.id == template_id)
    if lock:
        query = query.with_for_update().execution_options(populate_existing=True)
    row = db.scalar(query)
    if row is None:
        raise HTTPException(404, "Plantilla no encontrada")
    return row


def _version(db: Session, version_id: int) -> ClinicalFormVersion:
    row = db.get(ClinicalFormVersion, version_id)
    if row is None:
        raise HTTPException(404, "Versión no encontrada")
    return row


def serialize_template(db: Session, row: ClinicalFormTemplate, *, definition: bool = False) -> dict:
    versions = list(db.scalars(select(ClinicalFormVersion).where(ClinicalFormVersion.template_id == row.id).order_by(ClinicalFormVersion.version.desc())))
    draft = next((version for version in versions if version.status == "draft"), None)
    chosen = draft or next((version for version in versions if version.id == row.current_version_id), None)
    return {
        "id": row.id, "name": row.name, "code": row.code, "description": row.description,
        "document_type": row.document_type, "status": row.status,
        "current_version_id": row.current_version_id,
        "current_version": next((v.version for v in versions if v.id == row.current_version_id), None),
        "draft_version_id": draft.id if draft else None,
        "editable_version_id": chosen.id if chosen else None,
        "definition": deepcopy(chosen.definition) if definition and chosen else None,
        "created_at": row.created_at, "updated_at": row.updated_at,
    }


def create_template(db: Session, actor: User, *, name: str, code: str, description: str,
                    document_type: str, definition: FormDefinition | None = None) -> dict:
    require_schema(db)
    require_admin(actor, "clinical_forms:create")
    row = ClinicalFormTemplate(name=name, code=code, description=description,
                               document_type=document_type, status="draft", created_by_user_id=actor.id)
    db.add(row)
    try:
        db.flush()
        version = ClinicalFormVersion(template_id=row.id, version=1, status="draft",
                                      definition=(definition or FormDefinition()).model_dump(mode="json"),
                                      created_by_user_id=actor.id)
        db.add(version)
        db.flush()
        audit(db, actor, f"create:{row.id}")
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(409, "Ya existe una plantilla con ese código") from exc
    return serialize_template(db, row, definition=True)


def update_draft(db: Session, actor: User, template_id: int, version_id: int, definition: FormDefinition) -> dict:
    require_schema(db)
    require_admin(actor, "clinical_forms:edit_draft")
    template = _template(db, template_id, lock=True)
    version = _version(db, version_id)
    if version.template_id != template.id or version.status != "draft" or template.status == "retired":
        raise HTTPException(409, "Solo puede editar un borrador de una plantilla vigente")
    version.definition = definition.model_dump(mode="json")
    template.updated_at = datetime.now(timezone.utc)
    audit(db, actor, f"edit_draft:{template.id}:v{version.version}")
    db.commit()
    return serialize_template(db, template, definition=True)


def fork_draft(db: Session, actor: User, template_id: int) -> dict:
    require_schema(db)
    require_admin(actor, "clinical_forms:edit_draft")
    template = _template(db, template_id, lock=True)
    if template.status == "retired" or template.current_version_id is None:
        raise HTTPException(409, "La plantilla no tiene una versión publicada vigente")
    if db.scalar(select(ClinicalFormVersion.id).where(ClinicalFormVersion.template_id == template.id,
                                                       ClinicalFormVersion.status == "draft")):
        raise HTTPException(409, "Ya existe un borrador de esta plantilla")
    current = _version(db, template.current_version_id)
    next_number = db.scalar(select(ClinicalFormVersion.version).where(
        ClinicalFormVersion.template_id == template.id).order_by(ClinicalFormVersion.version.desc()).limit(1)) + 1
    db.add(ClinicalFormVersion(template_id=template.id, version=next_number, status="draft",
                               definition=deepcopy(current.definition), created_by_user_id=actor.id))
    audit(db, actor, f"fork:{template.id}:v{next_number}")
    db.commit()
    return serialize_template(db, template, definition=True)


def publish(db: Session, actor: User, template_id: int, version_id: int) -> dict:
    require_schema(db)
    require_admin(actor, "clinical_forms:publish")
    template = _template(db, template_id, lock=True)
    version = _version(db, version_id)
    if template.status == "retired" or version.template_id != template.id or version.status != "draft":
        raise HTTPException(409, "Seleccione un borrador vigente")
    definition = FormDefinition.model_validate(version.definition)
    if not definition.pages or any(not page.sections for page in definition.pages):
        raise HTTPException(422, "La plantilla necesita páginas con secciones")
    if not any(section.fields for page in definition.pages for section in page.sections):
        raise HTTPException(422, "La plantilla necesita campos")
    version.status = "published"
    version.published_at = datetime.now(timezone.utc)
    template.current_version_id = version.id
    template.status = "published"
    template.updated_at = datetime.now(timezone.utc)
    audit(db, actor, f"publish:{template.id}:v{version.version}")
    db.commit()
    return serialize_template(db, template, definition=True)


def retire(db: Session, actor: User, template_id: int) -> dict:
    require_schema(db)
    require_admin(actor, "clinical_forms:retire")
    template = _template(db, template_id, lock=True)
    if template.status == "retired":
        raise HTTPException(409, "La plantilla ya está retirada")
    template.status = "retired"
    audit(db, actor, f"retire:{template.id}")
    db.commit()
    return serialize_template(db, template)


def duplicate(db: Session, actor: User, template_id: int, *, name: str, code: str) -> dict:
    require_schema(db)
    require_admin(actor, "clinical_forms:create")
    source = _template(db, template_id)
    source_data = serialize_template(db, source, definition=True)
    definition = FormDefinition.model_validate(source_data["definition"])
    return create_template(db, actor, name=name, code=code, description=source.description,
                           document_type=source.document_type, definition=definition)


def assignment_key(center_id: int | None, specialty_id: int | None, doctor_id: int | None) -> str:
    if doctor_id and specialty_id:
        raise HTTPException(422, "Asigne por médico o por especialidad, no ambos")
    if (doctor_id or specialty_id) and not center_id:
        raise HTTPException(422, "La asignación por médico o especialidad requiere centro")
    return f"c:{center_id or 0}:s:{specialty_id or 0}:d:{doctor_id or 0}"


def assign(db: Session, actor: User, template_id: int, *, center_id: int | None,
           specialty_id: int | None, doctor_id: int | None) -> ClinicalFormAssignment:
    require_schema(db)
    require_admin(actor, "clinical_forms:assign")
    template = _template(db, template_id)
    if template.status != "published" or not template.current_version_id:
        raise HTTPException(409, "Solo puede asignar una plantilla publicada")
    key = assignment_key(center_id, specialty_id, doctor_id)
    if center_id and not db.get(CareCenter, center_id):
        raise HTTPException(404, "Centro no disponible")
    if specialty_id and not db.get(Specialty, specialty_id):
        raise HTTPException(404, "Especialidad no disponible")
    if doctor_id:
        doctor = db.get(User, doctor_id)
        if not doctor or not is_role(doctor, "doctor") or center_id not in assigned_center_ids(doctor):
            raise HTTPException(404, "Médico no disponible en este centro")
    existing = db.scalar(select(ClinicalFormAssignment).where(
        ClinicalFormAssignment.document_type == template.document_type,
        ClinicalFormAssignment.scope_key == key).with_for_update())
    if existing:
        existing.template_id = template.id
        row = existing
    else:
        row = ClinicalFormAssignment(template_id=template.id, document_type=template.document_type,
                                     scope_key=key, center_id=center_id, specialty_id=specialty_id,
                                     doctor_id=doctor_id, created_by_user_id=actor.id)
        db.add(row)
    audit(db, actor, f"assign:{template.id}:{key}", center_id)
    db.commit()
    db.refresh(row)
    return row


def resolve(db: Session, kind: str, *, center_id: int, doctor_id: int) -> tuple[ClinicalFormTemplate, ClinicalFormVersion] | None:
    if not schema_ready(db):
        return None
    doctor = db.get(User, doctor_id)
    specialties = {item.id for item in doctor.specialties} if doctor else set()
    rows = db.scalars(select(ClinicalFormAssignment).where(ClinicalFormAssignment.document_type == kind)).all()
    candidates = []
    for row in rows:
        if row.center_id not in (None, center_id):
            continue
        if row.doctor_id is not None and row.doctor_id != doctor_id:
            continue
        if row.specialty_id is not None and row.specialty_id not in specialties:
            continue
        rank = 4 if row.doctor_id is not None else 3 if row.specialty_id is not None else 2 if row.center_id is not None else 1
        template = db.get(ClinicalFormTemplate, row.template_id)
        if template and template.status == "published" and template.current_version_id:
            candidates.append((rank, row.id, template))
    if not candidates:
        return None  # Explicit Atlas/0055 legacy fallback.
    _, _, template = max(candidates, key=lambda item: (item[0], item[1]))
    version = _version(db, template.current_version_id)
    return template, version


def document_version(db: Session, row) -> ClinicalFormVersion | None:
    template_id, version_id = document_template_refs(db, row)
    if version_id is None:
        return None
    version = _version(db, version_id)
    if version.template_id != template_id or version.status != "published":
        raise HTTPException(409, "Referencia de plantilla del documento inválida")
    return version


def document_template_refs(db: Session, row) -> tuple[int | None, int | None]:
    if not schema_ready(db):
        return None, None
    if row.__tablename__ not in {"preoperative_evaluations", "physical_examinations"}:
        raise ValueError("Tipo de documento no admitido")
    result = db.execute(text(f"SELECT template_id, template_version_id FROM {row.__tablename__} WHERE id = :id"),
                        {"id": row.id}).first()
    return (result.template_id, result.template_version_id) if result else (None, None)


def bind_document_version(db: Session, row, template_id: int, version_id: int) -> None:
    if not schema_ready(db):
        raise RuntimeError("Schema 0056 required")
    if row.__tablename__ not in {"preoperative_evaluations", "physical_examinations"}:
        raise ValueError("Tipo de documento no admitido")
    db.execute(text(f"UPDATE {row.__tablename__} SET template_id = :template, template_version_id = :version WHERE id = :id"),
               {"template": template_id, "version": version_id, "id": row.id})


def field_keys(definition: dict) -> set[str]:
    return {field["key"] for page in definition["pages"] for section in page["sections"] for field in section["fields"]}


def administrative_keys(definition: dict) -> set[str]:
    return {field["key"] for page in definition["pages"] for section in page["sections"]
            for field in section["fields"] if field.get("editable_by") == "administrative"}


def validate_document_values(definition: dict, values: dict[str, str]) -> None:
    fields = {field["key"]: field for page in definition["pages"] for section in page["sections"] for field in section["fields"]}
    if not set(values) <= fields.keys():
        raise HTTPException(422, "Campo no definido en la versión del documento")
    for key, value in values.items():
        field = fields[key]
        if not field["visible"] or field["read_only"] or field["data_binding"] or field["type"] in {"static_text", "divider", "section_title", "signature_placeholder"}:
            raise HTTPException(422, f"El campo {key} no admite edición")
        if field["type"] in {"yes_no", "checkbox"} and value not in {"", "yes", "no"}:
            raise HTTPException(422, f"Valor Sí/No inválido: {key}")
        if field["type"] == "single_select" and value and value not in field["options"]:
            raise HTTPException(422, f"Opción inválida: {key}")
        if field["type"] == "multi_select" and value and any(part not in field["options"] for part in value.split("|")):
            raise HTTPException(422, f"Opciones inválidas: {key}")
        if field["type"] in {"integer", "decimal"} and value.strip():
            try:
                number = Decimal(value)
                if not number.is_finite() or (field["type"] == "integer" and number != number.to_integral_value()):
                    raise InvalidOperation()
            except (InvalidOperation, ValueError) as exc:
                raise HTTPException(422, f"Número inválido: {key}") from exc
            if ("min" in field["validation"] and number < Decimal(str(field["validation"]["min"]))) or (
                "max" in field["validation"] and number > Decimal(str(field["validation"]["max"]))):
                raise HTTPException(422, f"Número fuera de rango: {key}")
        if "max_length" in field["validation"] and len(value) > field["validation"]["max_length"]:
            raise HTTPException(422, f"Texto demasiado largo: {key}")
        if field["type"] in {"date", "time"} and value.strip():
            try:
                from datetime import date, time
                date.fromisoformat(value) if field["type"] == "date" else time.fromisoformat(value)
            except ValueError as exc:
                raise HTTPException(422, f"Fecha u hora inválida: {key}") from exc


def validate_required_fields(definition: dict, values: dict[str, str]) -> None:
    missing = [field["label"] for page in definition["pages"] for section in page["sections"]
               for field in section["fields"] if field["visible"] and field["required"]
               and not (values.get(field["key"]) or field.get("default_value") or field.get("data_binding"))]
    if missing:
        raise HTTPException(422, f"Complete los campos obligatorios: {', '.join(missing[:5])}")


def secretary_capabilities(db: Session, user: User) -> dict[str, bool]:
    if not is_role(user, "secretary") or not schema_ready(db):
        return {"start_preoperative": False, "start_physical_exam": False, "prepare_administrative": False}
    grant = db.scalar(select(SecretaryDocumentGrant).where(SecretaryDocumentGrant.user_id == user.id))
    capabilities = {key: bool(getattr(grant, key, False)) for key in
                    ("start_preoperative", "start_physical_exam", "prepare_administrative")}
    denied = set(user.denied_permissions or [])
    if "clinical_documents:create" in denied:
        capabilities["start_preoperative"] = capabilities["start_physical_exam"] = False
    if "clinical_documents:prepare" in denied:
        capabilities["prepare_administrative"] = False
    return capabilities


def set_secretary_capabilities(db: Session, actor: User, user_id: int, values: dict[str, bool]) -> dict[str, bool]:
    require_schema(db)
    require_admin(actor, "clinical_forms:assign")
    user = db.get(User, user_id)
    if not user or not is_role(user, "secretary"):
        raise HTTPException(404, "Secretaría no encontrada")
    grant = db.scalar(select(SecretaryDocumentGrant).where(SecretaryDocumentGrant.user_id == user_id).with_for_update())
    if grant is None:
        grant = SecretaryDocumentGrant(user_id=user_id, updated_by_user_id=actor.id)
        db.add(grant)
    for key, value in values.items():
        setattr(grant, key, value)
    grant.updated_by_user_id = actor.id
    audit(db, actor, f"secretary_grant:{user_id}")
    db.commit()
    return secretary_capabilities(db, user)


YES_NO = {
    "dolor_toracico", "dolor_reposo", "dolor_esfuerzo", "disnea_esfuerzo", "disnea_reposo",
    "palpitaciones", "claudicacion", "sincope", "mareos", "cefalea", "hta", "hta_leve",
    "hta_moderada", "hta_severa", "valvulopatia", "preeclampsia", "eclampsia", "iam", "acv",
    "arritmias", "fiebre_reumatica", "angina_estable", "angina_inestable", "anticonceptivos",
    "obesidad", "tabaquismo", "alcoholismo", "diabetes", "hepatitis", "asma_b", "alergia",
    "bronquitis", "enfermedad_tiroidea", "falcemia", "enfisema_pulmonar",
}
INTEGER = {"g", "p", "c", "a", "fc", "fr"}
DECIMAL = {"peso", "sato2"}
LONG = {"diagnostico_enfermedad", "procedimiento", "medicamentos", "antecedentes_otros",
        "enfermedades_otros", "corazon", "pulmones", "abdomen", "extremidades_inferiores",
        "ecg_otros", "rx_otros", "ecocardiograma", "test_esfuerzo", "estudios_otros",
        "conclusion_ecocardiograma", "otras_patologias", "riesgos_alergicos", "recomendaciones"}


def _catalog_field(key: str, label: str, order: int) -> dict:
    kind = "yes_no" if key in YES_NO else "integer" if key in INTEGER else "decimal" if key in DECIMAL else "text_long" if key in LONG else "text_short"
    unit = {"peso": "kg", "fc": "lpm", "fr": "rpm", "sato2": "%"}.get(key, "")
    return {"key": key, "label": label, "type": kind, "label_uppercase": True,
            "unit": unit, "row": order, "column": 1, "colspan": 12, "sort_order": order,
            "editable_by": "administrative" if key == "procedimiento" else "clinical"}


def cemer_definition(kind: str) -> FormDefinition:
    if kind == "preoperative":
        groups = [PREOPERATIVE_SECTIONS[:5], PREOPERATIVE_SECTIONS[5:]]
        title = "EVALUACIÓN MÉDICA PRE-OPERATORIA"
    elif kind == "physical_exam":
        groups = [[("EXAMEN FÍSICO", PHYSICAL_EXAM_FIELDS)]]
        title = "EXAMEN FÍSICO"
    else:
        raise HTTPException(404, "Catálogo no encontrado")
    pages = []
    for page_no, group in enumerate(groups, 1):
        pages.append({"page_number": page_no, "sort_order": page_no, "page_size": "Letter",
                      "orientation": "portrait", "sections": [
                          {"key": f"s{page_no}_{order}", "title": heading.upper(), "sort_order": order,
                           "fields": [_catalog_field(key, label, index) for index, (key, label) in enumerate(fields, 1)]}
                          for order, (heading, fields) in enumerate(group, 1)]})
    return FormDefinition.model_validate({"appearance": {
        "header": title, "doctor_heading": "Dr. Osiris Valdez Tiburcio",
        "specialty_heading": "CARDIÓLOGO - INTERNISTA - ECOCARDIOGRAFISTA",
        "center_heading": "CEMER", "font": "Helvetica", "font_size": 8,
        "density": "compact", "primary_color": "#24415c"}, "pages": pages})
