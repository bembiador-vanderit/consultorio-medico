from datetime import date, time

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.api.routes.appointments import create_appointment, update_appointment
from app.api.routes.clinical_catalog import (
    create_specialty,
    list_specialties,
    manage as manage_specialties,
    update_specialty,
    update_specialty_status,
)
from app.api.routes.clinical_history import complete_clinical_history, create_clinical_history, get_clinical_history
from app.api.routes.users import create_user, update_user_specialties
from app.db import Base
from app.models import CareCenter, Patient, Permission, Role, SecretaryCenterScope, Specialty, User
from app.schemas.appointment import AppointmentCreate
from app.schemas.auth import UserCreate
from app.schemas.clinical_catalog import DoctorProfileCreate, SpecialtyCreate, SpecialtyStatusUpdate, SpecialtyUpdate
from app.schemas.clinical_history import ClinicalHistoryCreate, ClinicalHistoryUpdate
from app.schemas.user import UserSpecialtiesUpdate
from app.services.clinical_specialties import resolve_appointment_specialty, set_doctor_specialties


@pytest.fixture()
def specialty_context():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    db = Session(engine)
    doctor_role = Role(code="doctor", name="Doctor")
    secretary_role = Role(code="secretary", name="Secretaria")
    admin_role = Role(code="admin", name="Administrador", permissions=[Permission(code="users:manage", description="Administrar usuarios")])
    center = CareCenter(name="CEMER", city="Santo Domingo", is_active=True)
    cardiology = Specialty(name="Cardiología", is_active=True)
    pediatrics = Specialty(name="Pediatría", is_active=True)
    internal = Specialty(name="Medicina interna", is_active=True)
    patient = Patient(first_name="Paciente", last_name="Especialidad", date_of_birth=date(1990, 1, 1))
    doctor_one = User(email="one@example.test", full_name="Doctor Uno", password_hash="hash", roles=[doctor_role], centers=[center], is_active=True)
    doctor_multi = User(email="multi@example.test", full_name="Doctora Múltiple", password_hash="hash", roles=[doctor_role], centers=[center], is_active=True)
    secretary = User(email="secretary@example.test", full_name="Secretaria", password_hash="hash", roles=[secretary_role], centers=[center], is_active=True)
    admin = User(email="admin@example.test", full_name="Admin", password_hash="hash", roles=[admin_role], is_active=True)
    db.add_all([cardiology, pediatrics, internal, patient, doctor_one, doctor_multi, secretary, admin])
    db.flush()
    set_doctor_specialties(db, doctor_one, cardiology.id, [cardiology.id])
    set_doctor_specialties(db, doctor_multi, pediatrics.id, [pediatrics.id, cardiology.id])
    db.add(SecretaryCenterScope(secretary_id=secretary.id, center_id=center.id, manage_all_doctors=False, doctors=[doctor_one, doctor_multi]))
    db.commit()
    yield db, patient, center, cardiology, pediatrics, internal, doctor_one, doctor_multi, secretary, admin
    db.close()
    Base.metadata.drop_all(engine)
    engine.dispose()


def appointment_payload(patient_id: int, doctor_id: int, center_id: int, specialty_id: int | None = None):
    return AppointmentCreate(
        patient_id=patient_id,
        doctor_id=doctor_id,
        center_id=center_id,
        specialty_id=specialty_id,
        appointment_date=date(2026, 9, 15),
        appointment_time=time(9),
    )


def test_single_specialty_is_selected_automatically(specialty_context):
    db, patient, center, cardiology, _, _, doctor, _, _, _ = specialty_context
    result = create_appointment(appointment_payload(patient.id, doctor.id, center.id), doctor, db)
    assert result.specialty_id == cardiology.id
    assert result.specialty_name == "Cardiología"


def test_multiple_specialties_require_explicit_selection(specialty_context):
    db, patient, center, cardiology, _, _, _, doctor, _, admin = specialty_context
    with pytest.raises(HTTPException) as error:
        create_appointment(appointment_payload(patient.id, doctor.id, center.id), admin, db)
    assert error.value.status_code == 422
    assert "seleccionar una especialidad" in error.value.detail

    result = create_appointment(appointment_payload(patient.id, doctor.id, center.id, cardiology.id), admin, db)
    assert result.specialty_id == cardiology.id


def test_secretary_can_only_use_assigned_doctor_specialty(specialty_context):
    db, patient, center, cardiology, _, internal, doctor, _, secretary, _ = specialty_context
    result = create_appointment(appointment_payload(patient.id, doctor.id, center.id, cardiology.id), secretary, db)
    assert result.specialty_id == cardiology.id

    with pytest.raises(HTTPException) as error:
        create_appointment(appointment_payload(patient.id, doctor.id, center.id, internal.id), secretary, db)
    assert error.value.status_code == 422
    assert error.value.detail == "La especialidad no está asignada al médico"


def test_doctor_cannot_forge_other_doctor_or_specialty(specialty_context):
    db, patient, center, _, pediatrics, _, doctor, other_doctor, _, _ = specialty_context
    with pytest.raises(HTTPException) as other_error:
        create_appointment(appointment_payload(patient.id, other_doctor.id, center.id, pediatrics.id), doctor, db)
    assert other_error.value.status_code == 403

    with pytest.raises(HTTPException) as specialty_error:
        create_appointment(appointment_payload(patient.id, doctor.id, center.id, pediatrics.id), doctor, db)
    assert specialty_error.value.status_code == 422


def test_consultation_inherits_specialty_and_context_is_immutable(specialty_context):
    db, patient, center, cardiology, _, _, doctor, _, _, _ = specialty_context
    appointment = create_appointment(appointment_payload(patient.id, doctor.id, center.id), doctor, db)
    history = create_clinical_history(
        patient.id,
        ClinicalHistoryCreate(consultation_date=date(2026, 9, 15), appointment_id=appointment.id),
        doctor,
        db,
    )
    assert history.specialty_id == cardiology.id
    assert history.specialty_name == "Cardiología"

    with pytest.raises(ValueError):
        ClinicalHistoryUpdate.model_validate({"consultation_date": "2026-09-15", "specialty_id": 999})

    changed = appointment_payload(patient.id, doctor.id, center.id, cardiology.id)
    changed.reason = "Control actualizado"
    update_appointment(appointment.id, changed, doctor, db)
    assert history.specialty_id == cardiology.id


def test_history_exposes_specialty_doctor_and_center(specialty_context):
    db, patient, center, _, pediatrics, _, _, doctor, _, admin = specialty_context
    appointment = create_appointment(appointment_payload(patient.id, doctor.id, center.id, pediatrics.id), admin, db)
    create_clinical_history(
        patient.id,
        ClinicalHistoryCreate(consultation_date=date(2026, 9, 15), appointment_id=appointment.id),
        doctor,
        db,
    )
    histories = get_clinical_history(patient.id, doctor, db)
    assert histories[0].specialty_name == "Pediatría"
    assert histories[0].doctor_name == doctor.full_name
    assert histories[0].center_name == center.name


def test_specialty_cannot_change_after_consultation_starts_or_completes(specialty_context):
    db, patient, center, cardiology, pediatrics, _, _, doctor, _, admin = specialty_context
    appointment = create_appointment(appointment_payload(patient.id, doctor.id, center.id, pediatrics.id), admin, db)
    history = create_clinical_history(
        patient.id,
        ClinicalHistoryCreate(consultation_date=date(2026, 9, 15), appointment_id=appointment.id),
        doctor,
        db,
    )
    changed = appointment_payload(patient.id, doctor.id, center.id, cardiology.id)
    with pytest.raises(HTTPException) as started_error:
        update_appointment(appointment.id, changed, admin, db)
    assert started_error.value.status_code == 409

    complete_clinical_history(history.id, doctor, db)
    with pytest.raises(HTTPException) as completed_error:
        update_appointment(appointment.id, changed, admin, db)
    assert completed_error.value.status_code == 409
    assert history.specialty_id == pediatrics.id


def test_admin_sets_primary_and_additional_specialties(specialty_context):
    db, _, _, cardiology, pediatrics, _, doctor, _, _, _ = specialty_context
    payload = DoctorProfileCreate(primary_specialty_id=pediatrics.id, specialty_ids=[pediatrics.id, cardiology.id])
    profile = set_doctor_specialties(db, doctor, payload.primary_specialty_id, payload.specialty_ids)
    db.commit()
    assert profile.specialty_id == pediatrics.id
    assert {item.id for item in doctor.specialties} == {pediatrics.id, cardiology.id}


def test_admin_creates_and_edits_doctor_specialties(specialty_context):
    db, _, _, cardiology, pediatrics, _, _, _, _, admin = specialty_context
    created = create_user(
        UserCreate(
            email="new-doctor@example.com",
            full_name="Doctora Nueva",
            password="ClaveSegura123",
            role_codes=["doctor"],
            primary_specialty_id=cardiology.id,
            specialty_ids=[cardiology.id],
        ),
        admin,
        db,
    )
    assert created.primary_specialty_id == cardiology.id
    assert created.specialty_names == ["Cardiología"]

    updated = update_user_specialties(
        created.id,
        UserSpecialtiesUpdate(primary_specialty_id=pediatrics.id, specialty_ids=[pediatrics.id, cardiology.id]),
        admin,
        db,
    )
    assert updated.primary_specialty_id == pediatrics.id
    assert set(updated.specialty_names) == {"Cardiología", "Pediatría"}


def test_only_admin_permission_can_manage_specialty_catalog(specialty_context):
    _, _, _, _, _, _, doctor, _, _, admin = specialty_context
    assert manage_specialties(admin) is admin
    with pytest.raises(HTTPException) as error:
        manage_specialties(doctor)
    assert error.value.status_code == 403


def test_admin_creates_edits_and_rejects_duplicate_specialty(specialty_context):
    db, _, _, cardiology, _, _, doctor, _, _, admin = specialty_context
    created = create_specialty(SpecialtyCreate(name="  Medicina   del Deporte  "), admin, db)
    assert created.name == "Medicina del Deporte"
    assert created.is_active is True

    updated = update_specialty(created.id, SpecialtyUpdate(name="Medicina deportiva"), admin, db)
    assert updated.name == "Medicina deportiva"

    new_doctor = create_user(
        UserCreate(
            email="sports-doctor@example.com",
            full_name="Doctor del Deporte",
            password="ClaveSegura123",
            role_codes=["doctor"],
            primary_specialty_id=created.id,
            specialty_ids=[created.id],
        ),
        admin,
        db,
    )
    assert new_doctor.primary_specialty_id == created.id
    assert new_doctor.specialty_names == ["Medicina deportiva"]

    with pytest.raises(HTTPException) as error:
        create_specialty(SpecialtyCreate(name=cardiology.name.upper()), admin, db)
    assert error.value.status_code == 409


def test_in_use_specialty_can_be_deactivated_but_not_renamed(specialty_context):
    db, patient, center, cardiology, _, _, doctor, _, _, admin = specialty_context
    appointment = create_appointment(appointment_payload(patient.id, doctor.id, center.id), doctor, db)
    history = create_clinical_history(
        patient.id,
        ClinicalHistoryCreate(consultation_date=date(2026, 9, 15), appointment_id=appointment.id),
        doctor,
        db,
    )

    deactivated = update_specialty_status(cardiology.id, SpecialtyStatusUpdate(is_active=False), admin, db)
    assert deactivated.is_active is False
    assert appointment.specialty_id == cardiology.id
    assert history.specialty_id == cardiology.id
    assert history.specialty_name == "Cardiología"
    assert cardiology.id in {item.id for item in doctor.specialties}
    assert cardiology.id not in {item.id for item in list_specialties(admin, db)}

    with pytest.raises(HTTPException) as rename_error:
        update_specialty(cardiology.id, SpecialtyUpdate(name="Cardiología clínica"), admin, db)
    assert rename_error.value.status_code == 409

    with pytest.raises(HTTPException) as appointment_error:
        resolve_appointment_specialty(db, doctor, cardiology.id)
    assert appointment_error.value.status_code == 422

    new_doctor = User(
        email="inactive-specialty@example.test",
        full_name="Doctor sin especialidad",
        password_hash="hash",
        roles=[doctor.roles[0]],
        centers=[center],
        is_active=True,
    )
    db.add(new_doctor)
    db.flush()
    with pytest.raises(HTTPException) as assign_error:
        set_doctor_specialties(db, new_doctor, cardiology.id, [cardiology.id])
    assert assign_error.value.status_code == 422

    # Guardar el perfil existente no elimina silenciosamente la asignación inactiva.
    profile = set_doctor_specialties(db, doctor, cardiology.id, [cardiology.id])
    db.commit()
    assert profile.specialty_id == cardiology.id
    assert {item.id for item in doctor.specialties} == {cardiology.id}

    reactivated = update_specialty_status(cardiology.id, SpecialtyStatusUpdate(is_active=True), admin, db)
    assert reactivated.is_active is True
