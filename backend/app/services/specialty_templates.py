from dataclasses import dataclass
from datetime import datetime

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, selectinload

from app.models import Specialty, SpecialtyTemplate, SpecialtyTemplateModule


@dataclass(frozen=True)
class ClinicalModuleDefinition:
    key: str
    label: str
    required: bool


CLINICAL_MODULE_REGISTRY: dict[str, ClinicalModuleDefinition] = {
    definition.key: definition
    for definition in (
        ClinicalModuleDefinition("core.anamnesis", "Historia de la consulta", True),
        ClinicalModuleDefinition("core.vital-signs", "Signos vitales", True),
        ClinicalModuleDefinition("core.diagnoses", "Diagnósticos", True),
        ClinicalModuleDefinition("core.prescriptions", "Recetas", True),
        ClinicalModuleDefinition("core.clinical-orders", "Órdenes clínicas", True),
    )
}
DEFAULT_MODULE_KEYS = tuple(CLINICAL_MODULE_REGISTRY)


def validate_template_module_keys(module_keys: list[str]) -> None:
    unknown = sorted(set(module_keys) - set(CLINICAL_MODULE_REGISTRY))
    if unknown:
        raise HTTPException(
            status_code=422,
            detail=f"La plantilla contiene módulos clínicos desconocidos: {', '.join(unknown)}",
        )
    if len(module_keys) != len(set(module_keys)):
        raise HTTPException(status_code=422, detail="Los módulos de la plantilla no pueden repetirse")


def create_base_specialty_template(db: Session, specialty: Specialty) -> SpecialtyTemplate:
    existing = db.scalar(
        select(SpecialtyTemplate).where(SpecialtyTemplate.specialty_id == specialty.id).limit(1)
    )
    if existing is not None:
        raise HTTPException(status_code=409, detail="La especialidad ya tiene una plantilla clínica")
    template = SpecialtyTemplate(
        specialty=specialty,
        version=1,
        status="published",
        published_at=datetime.utcnow(),
        modules=[
            SpecialtyTemplateModule(module_key=module_key, position=index)
            for index, module_key in enumerate(DEFAULT_MODULE_KEYS, start=1)
        ],
    )
    db.add(template)
    db.flush()
    return template


def create_specialty_with_base_template(db: Session, name: str) -> Specialty:
    specialty = Specialty(name=name, is_active=True)
    db.add(specialty)
    db.flush()
    create_base_specialty_template(db, specialty)
    return specialty


def resolve_specialty_template(db: Session, specialty_id: int) -> SpecialtyTemplate:
    query = (
        select(SpecialtyTemplate)
        .options(selectinload(SpecialtyTemplate.modules), selectinload(SpecialtyTemplate.specialty))
        .where(
            SpecialtyTemplate.specialty_id == specialty_id,
            SpecialtyTemplate.status == "published",
        )
        .order_by(SpecialtyTemplate.version.desc())
    )
    template = db.scalar(query)
    if template is not None:
        validate_template_module_keys([module.module_key for module in template.modules])
        return template

    specialty = db.get(Specialty, specialty_id)
    if specialty is None:
        raise HTTPException(status_code=409, detail="La cita no tiene una especialidad clínica válida")
    has_any_template = db.scalar(
        select(SpecialtyTemplate.id).where(SpecialtyTemplate.specialty_id == specialty_id).limit(1)
    )
    if has_any_template is not None:
        raise HTTPException(status_code=409, detail="La especialidad no tiene una plantilla clínica publicada")

    # Compatibilidad para bases creadas directamente por fixtures o instalaciones
    # que aún no ejecutaron la migración. La ruta administrativa también usa el
    # mismo creador central al registrar especialidades nuevas.
    try:
        with db.begin_nested():
            return create_base_specialty_template(db, specialty)
    except IntegrityError:
        # Otra transacción pudo inicializar la plantilla base al mismo tiempo.
        # El savepoint conserva la transacción clínica exterior.
        db.expire_all()
        template = db.scalar(query)
        if template is not None:
            validate_template_module_keys([module.module_key for module in template.modules])
            return template
        raise


def publish_specialty_template(db: Session, template: SpecialtyTemplate) -> SpecialtyTemplate:
    if template.status != "draft":
        raise HTTPException(status_code=409, detail="Solo una plantilla en borrador puede publicarse")
    validate_template_module_keys([module.module_key for module in template.modules])
    db.scalar(select(Specialty).where(Specialty.id == template.specialty_id).with_for_update())
    current = db.scalar(
        select(SpecialtyTemplate).where(
            SpecialtyTemplate.specialty_id == template.specialty_id,
            SpecialtyTemplate.status == "published",
        )
    )
    if current is not None:
        current.status = "retired"
    template.status = "published"
    template.published_at = datetime.utcnow()
    db.flush()
    return template


def module_descriptor(module: SpecialtyTemplateModule) -> dict[str, object]:
    definition = CLINICAL_MODULE_REGISTRY[module.module_key]
    return {
        "key": definition.key,
        "label": definition.label,
        "position": module.position,
        "required": definition.required,
    }


def default_module_descriptors() -> list[dict[str, object]]:
    return [
        {
            "key": definition.key,
            "label": definition.label,
            "position": position,
            "required": definition.required,
        }
        for position, definition in enumerate(CLINICAL_MODULE_REGISTRY.values(), start=1)
    ]
