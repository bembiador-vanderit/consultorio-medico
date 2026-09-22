from datetime import date, time
import importlib.util
from pathlib import Path

import pytest
from alembic.migration import MigrationContext
from alembic.operations import Operations
from fastapi import HTTPException
from sqlalchemy import create_engine, select, text
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.api.routes.clinical_catalog import create_specialty
from app.api.routes.clinical_history import create_clinical_history, get_consultation_context
from app.db import Base
from app.models import (
    Appointment,
    CareCenter,
    ClinicalHistory,
    DoctorProfile,
    Patient,
    Role,
    Specialty,
    SpecialtyTemplate,
    SpecialtyTemplateModule,
    User,
)
from app.schemas.clinical_catalog import SpecialtyCreate
from app.schemas.clinical_history import ClinicalHistoryCreate, ClinicalHistoryUpdate
from app.services.specialty_templates import (
    DEFAULT_MODULE_KEYS,
    create_base_specialty_template,
    publish_specialty_template,
    resolve_specialty_template,
    validate_template_module_keys,
)


@pytest.fixture()
def workspace_context():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    db = Session(engine)
    doctor_role = Role(code="doctor", name="Doctor")
    center = CareCenter(name="Centro de prueba", city="Santo Domingo", is_active=True)
    cardiology = Specialty(name="Cardiología", is_active=True)
    pediatrics = Specialty(name="Pediatría", is_active=True)
    patient = Patient(
        first_name="Paciente",
        last_name="Plantilla",
        date_of_birth=date(2010, 4, 3),
        phone="8095550101",
    )
    doctor = User(
        email="multi-template@example.test",
        full_name="Doctora Multi Especialidad",
        password_hash="hash",
        is_active=True,
        roles=[doctor_role],
        centers=[center],
        specialties=[cardiology, pediatrics],
    )
    other_doctor = User(
        email="other-template@example.test",
        full_name="Doctor Fuera de Alcance",
        password_hash="hash",
        is_active=True,
        roles=[doctor_role],
        centers=[center],
        specialties=[cardiology],
    )
    db.add_all([patient, doctor, other_doctor])
    db.flush()
    db.add(DoctorProfile(user_id=doctor.id, specialty_id=cardiology.id))
    db.add(DoctorProfile(user_id=other_doctor.id, specialty_id=cardiology.id))
    cardiology_template = create_base_specialty_template(db, cardiology)
    pediatrics_template = create_base_specialty_template(db, pediatrics)
    db.commit()
    yield db, patient, center, cardiology, pediatrics, doctor, other_doctor, cardiology_template, pediatrics_template
    db.close()
    Base.metadata.drop_all(engine)
    engine.dispose()


def add_appointment(db, patient, center, doctor, specialty, hour=9):
    appointment = Appointment(
        patient_id=patient.id,
        doctor_id=doctor.id,
        center_id=center.id,
        specialty_id=specialty.id,
        appointment_date=date(2026, 9, 21),
        appointment_time=time(hour),
        status="scheduled",
    )
    db.add(appointment)
    db.commit()
    db.refresh(appointment)
    return appointment


def draft_template(specialty, version, keys):
    return SpecialtyTemplate(
        specialty_id=specialty.id,
        version=version,
        status="draft",
        modules=[
            SpecialtyTemplateModule(module_key=key, position=position)
            for position, key in enumerate(keys, start=1)
        ],
    )


def test_base_template_has_known_modules_in_current_workspace_order(workspace_context):
    db, _, _, cardiology, _, _, _, template, _ = workspace_context
    resolved = resolve_specialty_template(db, cardiology.id)

    assert resolved.id == template.id
    assert resolved.status == "published"
    assert [item.module_key for item in resolved.modules] == list(DEFAULT_MODULE_KEYS)
    assert [item.position for item in resolved.modules] == [1, 2, 3, 4, 5]


def test_unknown_or_duplicate_module_keys_cannot_be_published(workspace_context):
    db, _, _, cardiology, _, _, _, _, _ = workspace_context
    unknown = draft_template(cardiology, 2, ["core.anamnesis", "cardiology.not-installed"])
    db.add(unknown)
    db.flush()
    with pytest.raises(HTTPException) as error:
        publish_specialty_template(db, unknown)
    assert error.value.status_code == 422
    assert "desconocidos" in error.value.detail

    with pytest.raises(HTTPException) as duplicate:
        validate_template_module_keys(["core.anamnesis", "core.anamnesis"])
    assert duplicate.value.status_code == 422


def test_draft_is_never_resolved_and_publish_retires_previous_template(workspace_context):
    db, _, _, cardiology, _, _, _, first, _ = workspace_context
    second = draft_template(cardiology, 2, reversed(DEFAULT_MODULE_KEYS))
    db.add(second)
    db.flush()

    assert resolve_specialty_template(db, cardiology.id).id == first.id
    publish_specialty_template(db, second)
    db.commit()

    assert first.status == "retired"
    assert resolve_specialty_template(db, cardiology.id).id == second.id
    assert [item.module_key for item in second.modules] == list(reversed(DEFAULT_MODULE_KEYS))


def test_new_specialty_gets_published_base_template(workspace_context):
    db, _, _, _, _, _, _, _, _ = workspace_context
    created = create_specialty(SpecialtyCreate(name="Medicina familiar"), User(), db)
    template = resolve_specialty_template(db, created.id)

    assert template.version == 1
    assert template.status == "published"
    assert [item.module_key for item in template.modules] == list(DEFAULT_MODULE_KEYS)


def test_same_doctor_resolves_each_appointment_specialty_without_primary_override(workspace_context):
    db, patient, center, cardiology, pediatrics, doctor, _, cardio_template, pediatric_template = workspace_context
    cardiology_appointment = add_appointment(db, patient, center, doctor, cardiology, 9)
    pediatrics_appointment = add_appointment(db, patient, center, doctor, pediatrics, 10)

    cardiology_context = get_consultation_context(cardiology_appointment.id, doctor, db)
    pediatrics_context = get_consultation_context(pediatrics_appointment.id, doctor, db)

    assert doctor.doctor_profile.specialty_id == cardiology.id
    assert cardiology_context.workspace.template_id == cardio_template.id
    assert cardiology_context.workspace.specialty_id == cardiology.id
    assert pediatrics_context.workspace.template_id == pediatric_template.id
    assert pediatrics_context.workspace.specialty_id == pediatrics.id


def test_new_history_snapshots_template_and_context_keeps_it_after_new_publish(workspace_context):
    db, patient, center, cardiology, _, doctor, _, first, _ = workspace_context
    appointment = add_appointment(db, patient, center, doctor, cardiology)
    history = create_clinical_history(
        patient.id,
        ClinicalHistoryCreate(consultation_date=date(2026, 9, 21), appointment_id=appointment.id),
        doctor,
        db,
    )
    assert history.specialty_template_id == first.id

    second = draft_template(cardiology, 2, reversed(DEFAULT_MODULE_KEYS))
    db.add(second)
    db.flush()
    publish_specialty_template(db, second)
    db.commit()

    context = get_consultation_context(appointment.id, doctor, db)
    assert context.workspace.template_id == first.id
    assert context.workspace.template_version == 1
    assert [item.key for item in context.workspace.modules] == list(DEFAULT_MODULE_KEYS)
    assert resolve_specialty_template(db, cardiology.id).id == second.id

    with pytest.raises(ValueError):
        ClinicalHistoryCreate.model_validate({
            "consultation_date": "2026-09-21",
            "appointment_id": appointment.id,
            "specialty_template_id": second.id,
        })
    with pytest.raises(ValueError):
        ClinicalHistoryUpdate.model_validate({
            "consultation_date": "2026-09-21",
            "expected_revision": history.revision,
            "specialty_template_id": second.id,
        })


def test_completed_and_legacy_histories_remain_readable(workspace_context):
    db, patient, center, cardiology, _, doctor, _, template, _ = workspace_context
    completed_appointment = add_appointment(db, patient, center, doctor, cardiology, 9)
    completed = ClinicalHistory(
        patient_id=patient.id,
        appointment_id=completed_appointment.id,
        doctor_id=doctor.id,
        center_id=center.id,
        specialty_id=cardiology.id,
        specialty_template_id=template.id,
        consultation_date=date(2026, 9, 20),
        status="completed",
    )
    legacy_appointment = add_appointment(db, patient, center, doctor, cardiology, 10)
    legacy = ClinicalHistory(
        patient_id=patient.id,
        appointment_id=legacy_appointment.id,
        doctor_id=doctor.id,
        center_id=center.id,
        specialty_id=cardiology.id,
        specialty_template_id=None,
        consultation_date=date(2025, 1, 1),
        status="completed",
    )
    db.add_all([completed, legacy])
    db.commit()

    completed_context = get_consultation_context(completed_appointment.id, doctor, db)
    legacy_context = get_consultation_context(legacy_appointment.id, doctor, db)
    assert completed_context.workspace.template_id == template.id
    assert legacy_context.workspace.template_id is None
    assert [item.key for item in legacy_context.workspace.modules] == list(DEFAULT_MODULE_KEYS)


def test_existing_clinical_permissions_still_reject_another_doctor(workspace_context):
    db, patient, center, cardiology, _, doctor, other_doctor, _, _ = workspace_context
    appointment = add_appointment(db, patient, center, doctor, cardiology)

    with pytest.raises(HTTPException) as error:
        get_consultation_context(appointment.id, other_doctor, db)
    assert error.value.status_code == 403


def test_migration_seeds_templates_and_only_backfills_valid_specialties(tmp_path):
    migration_path = Path(__file__).parents[1] / "alembic/versions/0032_specialty_workspace_templates.py"
    spec = importlib.util.spec_from_file_location("specialty_template_migration", migration_path)
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)
    engine = create_engine(f"sqlite:///{tmp_path / 'legacy.db'}")

    with engine.begin() as connection:
        connection.execute(text("CREATE TABLE specialties (id INTEGER PRIMARY KEY, name VARCHAR(120), is_active BOOLEAN, created_at DATETIME)"))
        connection.execute(text("CREATE TABLE clinical_histories (id INTEGER PRIMARY KEY, specialty_id INTEGER NULL)"))
        connection.execute(text("INSERT INTO specialties (id, name, is_active) VALUES (1, 'Cardiología', 1), (2, 'Pediatría', 1)"))
        connection.execute(text("INSERT INTO clinical_histories (id, specialty_id) VALUES (10, 1), (11, 2), (12, NULL), (13, 999)"))
        context = MigrationContext.configure(connection)
        with Operations.context(context):
            migration.upgrade()

        templates = connection.execute(text("SELECT specialty_id, version, status FROM specialty_templates ORDER BY specialty_id")).all()
        modules = connection.execute(text("SELECT template_id, module_key, position FROM specialty_template_modules ORDER BY template_id, position")).all()
        histories = connection.execute(text("SELECT id, specialty_template_id FROM clinical_histories ORDER BY id")).all()

    assert templates == [(1, 1, "published"), (2, 1, "published")]
    assert len(modules) == 10
    assert [row[1] for row in modules[:5]] == list(DEFAULT_MODULE_KEYS)
    assert histories[0][1] is not None and histories[1][1] is not None
    assert histories[2][1] is None and histories[3][1] is None
