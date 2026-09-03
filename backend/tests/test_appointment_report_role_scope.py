from datetime import date, time

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.api.routes.appointments import (
    appointment_scope_options,
    list_appointments,
    list_available_doctors,
    validate_appointment_assignment,
)
from app.api.routes import reports as report_routes
from app.api.routes.centers import unassign_user
from app.api.routes.users import update_secretary_scopes
from app.db import Base
from app.models import Appointment, CareCenter, Patient, Role, SecretaryCenterScope, User
from app.schemas.user import SecretaryDoctorScopesUpdate


@pytest.fixture
def scoped_db():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        admin_role = Role(code="admin", name="Administrador")
        doctor_role = Role(code="doctor", name="Doctor")
        secretary_role = Role(code="secretary", name="Secretaria")
        center_one = CareCenter(name="CEMER", city="Santo Domingo", center_type="consultorio", is_active=True)
        center_two = CareCenter(name="Centro Norte", city="Santiago", center_type="clinica", is_active=True)
        doctor_one = User(email="one@example.com", full_name="Doctora Uno", password_hash="hash", is_active=True, roles=[doctor_role], centers=[center_one])
        doctor_two = User(email="two@example.com", full_name="Doctor Dos", password_hash="hash", is_active=True, roles=[doctor_role], centers=[center_one])
        doctor_three = User(email="three@example.com", full_name="Doctora Tres", password_hash="hash", is_active=True, roles=[doctor_role], centers=[center_two])
        admin = User(email="admin@example.com", full_name="Admin", password_hash="hash", is_active=True, roles=[admin_role])
        secretary = User(email="secretary@example.com", full_name="Secretaria", password_hash="hash", is_active=True, roles=[secretary_role], centers=[center_one, center_two])
        secretary_all = User(email="all@example.com", full_name="Secretaria Todo", password_hash="hash", is_active=True, roles=[secretary_role], centers=[center_one])
        outsider = User(email="outside@example.com", full_name="Sin Rol", password_hash="hash", is_active=True)
        inactive = User(email="inactive@example.com", full_name="Inactiva", password_hash="hash", is_active=False, roles=[secretary_role], centers=[center_one])
        patient = Patient(first_name="Paciente", last_name="Prueba", date_of_birth=date(1990, 1, 1))
        db.add_all([admin, doctor_one, doctor_two, doctor_three, secretary, secretary_all, outsider, inactive, patient])
        db.flush()
        db.add_all([
            SecretaryCenterScope(secretary_id=secretary.id, center_id=center_one.id, manage_all_doctors=False, doctors=[doctor_one]),
            SecretaryCenterScope(secretary_id=secretary.id, center_id=center_two.id, manage_all_doctors=False, doctors=[doctor_three]),
            SecretaryCenterScope(secretary_id=secretary_all.id, center_id=center_one.id, manage_all_doctors=True),
            SecretaryCenterScope(secretary_id=inactive.id, center_id=center_one.id, manage_all_doctors=True),
            Appointment(patient_id=patient.id, doctor_id=doctor_one.id, center_id=center_one.id, appointment_date=date(2026, 9, 10), appointment_time=time(9, 0)),
            Appointment(patient_id=patient.id, doctor_id=doctor_two.id, center_id=center_one.id, appointment_date=date(2026, 9, 10), appointment_time=time(10, 0)),
            Appointment(patient_id=patient.id, doctor_id=doctor_three.id, center_id=center_two.id, appointment_date=date(2026, 9, 11), appointment_time=time(11, 0)),
        ])
        db.commit()
        yield db, admin, doctor_one, doctor_two, doctor_three, secretary, secretary_all, outsider, inactive, center_one, center_two
    Base.metadata.drop_all(engine)
    engine.dispose()


def test_admin_has_global_agenda_access(scoped_db):
    db, admin, *_ = scoped_db
    assert len(list_appointments(user=admin, db=db)) == 3


def test_doctor_only_sees_own_agenda_and_report(scoped_db):
    db, _, doctor_one, doctor_two, *_ = scoped_db
    own = list_appointments(user=doctor_one, db=db)
    assert {item.doctor_id for item in own} == {doctor_one.id}
    assert not list_appointments(doctor_id=doctor_two.id, user=doctor_one, db=db)
    rows = report_routes.get_appointment_rows(
        start=None, end=None, appointment_status=None, doctor_id=None,
        center_id=None, search=None, user=doctor_one, db=db,
    )
    assert {item.doctor_id for item in rows} == {doctor_one.id}


def test_secretary_specific_scope_spans_centers_and_is_not_creator_based(scoped_db):
    db, _, doctor_one, doctor_two, doctor_three, secretary, *_ = scoped_db
    items = list_appointments(user=secretary, db=db)
    assert {item.doctor_id for item in items} == {doctor_one.id, doctor_three.id}
    assert doctor_two.id not in {item.doctor_id for item in items}


def test_secretary_all_doctors_scope_is_limited_to_its_center(scoped_db):
    db, _, doctor_one, doctor_two, doctor_three, _, secretary_all, *_ = scoped_db
    items = list_appointments(user=secretary_all, db=db)
    assert {item.doctor_id for item in items} == {doctor_one.id, doctor_two.id}
    assert doctor_three.id not in {item.doctor_id for item in items}


def test_manipulated_filters_cannot_escape_secretary_scope(scoped_db):
    db, _, _, doctor_two, doctor_three, secretary, *_, center_one, center_two = scoped_db
    assert list_appointments(center_id=center_one.id, doctor_id=doctor_two.id, user=secretary, db=db) == []
    allowed = list_appointments(center_id=center_two.id, doctor_id=doctor_three.id, user=secretary, db=db)
    assert len(allowed) == 1


def test_secretary_new_appointment_doctor_options_and_validation_are_scoped(scoped_db):
    db, _, doctor_one, doctor_two, _, secretary, *_, center_one, _ = scoped_db
    available = list_available_doctors(center_one.id, date(2026, 9, 10), user=secretary, db=db)
    assert [doctor["id"] for doctor in available] == [doctor_one.id]
    with pytest.raises(HTTPException) as error:
        validate_appointment_assignment(db, secretary, doctor_two.id, center_one.id, date(2026, 9, 10))
    assert error.value.status_code == 403


def test_doctor_can_still_select_same_center_substitute(scoped_db):
    db, _, doctor_one, doctor_two, *_, center_one, _ = scoped_db
    selected, _ = validate_appointment_assignment(db, doctor_one, doctor_two.id, center_one.id, date(2026, 9, 10))
    assert selected.id == doctor_two.id


def test_scope_options_do_not_require_admin_catalog_endpoints(scoped_db):
    db, _, doctor_one, doctor_two, doctor_three, secretary, *_, center_one, center_two = scoped_db
    options = appointment_scope_options(user=secretary, db=db)
    assert {center["id"] for center in options["centers"]} == {center_one.id, center_two.id}
    assert {doctor["id"] for doctor in options["doctors"]} == {doctor_one.id, doctor_three.id}
    assert doctor_two.id not in {doctor["id"] for doctor in options["doctors"]}


def test_pdf_and_report_delivery_use_the_same_server_side_scope(scoped_db, monkeypatch):
    db, _, doctor_one, doctor_two, doctor_three, secretary, *_ = scoped_db
    captured = []

    def fake_pdf(appointments, _start, _end):
        captured.extend(appointment.doctor_id for appointment in appointments)
        return b"%PDF-test"

    monkeypatch.setattr(report_routes, "build_appointment_report_pdf", fake_pdf)
    monkeypatch.setattr(report_routes, "send_email_with_attachment", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(report_routes, "send_whatsapp_document", lambda *_args, **_kwargs: "https://wa.me/test")
    monkeypatch.setattr(report_routes, "get_settings", lambda: type("Settings", (), {
        "smtp_host": "smtp.test",
        "smtp_from": "atlas@example.com",
        "whatsapp_access_token": "token",
        "whatsapp_phone_number_id": "phone-id",
    })())
    report_routes.appointment_report_pdf(
        start=None, end=None, status=None, doctor_id=None,
        center_id=None, search=None, user=secretary, db=db,
    )
    assert set(captured) == {doctor_one.id, doctor_three.id}
    assert doctor_two.id not in captured

    captured.clear()
    report_routes.appointment_report_email(
        to="audit@example.com", start=None, end=None, appointment_status=None,
        doctor_id=None, center_id=None, search=None, user=secretary, db=db,
    )
    assert set(captured) == {doctor_one.id, doctor_three.id}

    captured.clear()
    report_routes.appointment_report_whatsapp(
        phone="18095550101", start=None, end=None, appointment_status=None,
        doctor_id=None, center_id=None, search=None, user=secretary, db=db,
    )
    assert set(captured) == {doctor_one.id, doctor_three.id}


def test_inactive_and_unauthorized_roles_are_rejected(scoped_db):
    db, *_, outsider, inactive, _, _ = scoped_db
    for user in (outsider, inactive):
        with pytest.raises(HTTPException) as error:
            list_appointments(user=user, db=db)
        assert error.value.status_code == 403


def test_admin_updates_specific_and_all_doctor_scopes(scoped_db):
    db, admin, doctor_one, doctor_two, _, secretary, *_, center_one, _ = scoped_db
    result = update_secretary_scopes(
        secretary.id,
        SecretaryDoctorScopesUpdate(scopes=[{
            "center_id": center_one.id,
            "manage_all_doctors": False,
            "doctor_ids": [doctor_two.id],
        }]),
        admin,
        db,
    )
    assert result.secretary_scopes[0].doctor_ids == [doctor_two.id]

    result = update_secretary_scopes(
        secretary.id,
        SecretaryDoctorScopesUpdate(scopes=[{
            "center_id": center_one.id,
            "manage_all_doctors": True,
            "doctor_ids": [],
        }]),
        admin,
        db,
    )
    assert result.secretary_scopes[0].manage_all_doctors is True


def test_scope_update_rejects_doctor_from_another_center(scoped_db):
    db, admin, _, _, doctor_three, secretary, *_, center_one, _ = scoped_db
    with pytest.raises(HTTPException) as error:
        update_secretary_scopes(
            secretary.id,
            SecretaryDoctorScopesUpdate(scopes=[{
                "center_id": center_one.id,
                "manage_all_doctors": False,
                "doctor_ids": [doctor_three.id],
            }]),
            admin,
            db,
        )
    assert error.value.status_code == 422


def test_unassigning_secretary_from_center_removes_stale_scope(scoped_db):
    db, admin, doctor_one, _, doctor_three, secretary, *_, center_one, _ = scoped_db
    unassign_user(center_one.id, secretary.id, admin, db)
    assert {item.doctor_id for item in list_appointments(user=secretary, db=db)} == {doctor_three.id}

    secretary.centers.append(center_one)
    db.commit()
    assert {item.doctor_id for item in list_appointments(user=secretary, db=db)} == {doctor_three.id}
    assert doctor_one.id not in {item.doctor_id for item in list_appointments(user=secretary, db=db)}
