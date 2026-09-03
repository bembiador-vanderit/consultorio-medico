from datetime import date, datetime, time

import pytest
from fastapi import HTTPException

from app.api.routes import appointments as appointment_routes
from app.api.routes.appointments import (
    create_appointment,
    ensure_appointment_access,
    list_appointments,
    update_appointment,
    validate_appointment_assignment,
)
from app.models import Appointment, CareCenter, Patient, Role, User
from app.schemas.appointment import AppointmentCreate


def _user(user_id: int, role_code: str, *, active: bool = True, centers=None) -> User:
    return User(
        id=user_id,
        full_name=f"Usuario {user_id}",
        is_active=active,
        roles=[Role(code=role_code, name=role_code)],
        centers=centers or [],
    )


def _center(center_id: int, *, active: bool = True) -> CareCenter:
    return CareCenter(id=center_id, name=f"Centro {center_id}", city="Santo Domingo", is_active=active)


def _payload(doctor_id: int | None, center_id: int | None) -> AppointmentCreate:
    return AppointmentCreate(
        patient_id=7,
        doctor_id=doctor_id,
        center_id=center_id,
        appointment_date=date(2026, 9, 10),
        appointment_time=time(9, 30),
    )


class QueryCaptureDB:
    def scalars(self, query):
        self.query = query
        return self

    def all(self):
        return []


class AppointmentDB:
    def __init__(self, users, centers, appointment=None):
        self.patient = Patient(id=7, first_name="Paciente", last_name="Prueba", date_of_birth=date(1990, 1, 1))
        self.users = {user.id: user for user in users}
        self.centers = {center.id: center for center in centers}
        self.appointment = appointment
        self.added = None

    def get(self, model, object_id):
        if model is Patient:
            return self.patient if object_id == self.patient.id else None
        if model is User:
            return self.users.get(object_id)
        if model is CareCenter:
            return self.centers.get(object_id)
        if model is Appointment:
            return self.appointment if self.appointment and object_id == self.appointment.id else None
        return None

    def scalar(self, _query):
        return None

    def add(self, appointment):
        self.added = appointment

    def commit(self):
        pass

    def refresh(self, appointment):
        appointment.id = 100
        appointment.patient = self.patient
        appointment.doctor = self.users[appointment.doctor_id]
        appointment.center = self.centers[appointment.center_id]
        appointment.created_at = datetime(2026, 9, 3, 10, 0)
        appointment.updated_at = datetime(2026, 9, 3, 10, 0)


def test_doctor_can_access_own_appointment():
    appointment = Appointment(id=42, doctor_id=11, center_id=5)

    ensure_appointment_access(_user(11, "doctor"), appointment)


def test_doctor_cannot_access_another_doctors_appointment():
    appointment = Appointment(id=42, doctor_id=11, center_id=5)

    with pytest.raises(HTTPException) as error:
        ensure_appointment_access(_user(12, "doctor"), appointment)

    assert error.value.status_code == 403
    assert error.value.detail == "No tiene acceso a esta cita"


def test_admin_can_access_any_appointment():
    appointment = Appointment(id=42, doctor_id=11, center_id=5)

    ensure_appointment_access(_user(1, "admin"), appointment)


def test_doctor_appointment_list_is_filtered_by_current_user():
    db = QueryCaptureDB()

    assert list_appointments(user=_user(11, "doctor"), db=db) == []

    compiled_query = str(db.query.compile(compile_kwargs={"literal_binds": True}))
    assert "appointments.doctor_id = 11" in compiled_query


def test_doctor_creates_appointment_for_self():
    center = _center(5)
    doctor = _user(11, "doctor", centers=[center])
    db = AppointmentDB([doctor], [center])

    result = create_appointment(_payload(doctor.id, center.id), user=doctor, db=db)

    assert result.doctor_id == doctor.id
    assert db.added.doctor_id == doctor.id


def test_doctor_can_select_same_center_substitute_and_backend_preserves_it():
    center = _center(5)
    current_doctor = _user(11, "doctor", centers=[center])
    substitute = _user(12, "doctor", centers=[center])
    db = AppointmentDB([current_doctor, substitute], [center])

    result = create_appointment(_payload(substitute.id, center.id), user=current_doctor, db=db)

    assert result.doctor_id == substitute.id
    assert db.added.doctor_id == substitute.id


def test_doctor_can_update_own_appointment_to_same_center_substitute():
    center = _center(5)
    current_doctor = _user(11, "doctor", centers=[center])
    substitute = _user(12, "doctor", centers=[center])
    appointment = Appointment(id=42, patient_id=7, doctor_id=current_doctor.id, center_id=center.id)
    db = AppointmentDB([current_doctor, substitute], [center], appointment)

    result = update_appointment(appointment.id, _payload(substitute.id, center.id), user=current_doctor, db=db)

    assert result.doctor_id == substitute.id
    assert appointment.doctor_id == substitute.id


def test_secretary_creates_appointment_for_valid_doctor_in_assigned_center():
    center = _center(5)
    secretary = _user(21, "secretary", centers=[center])
    doctor = _user(11, "doctor", centers=[center])
    db = AppointmentDB([secretary, doctor], [center])

    result = create_appointment(_payload(doctor.id, center.id), user=secretary, db=db)

    assert result.doctor_id == doctor.id
    assert result.center_id == center.id


def test_admin_creates_appointment_for_valid_doctor():
    center = _center(5)
    admin = _user(1, "admin")
    doctor = _user(11, "doctor", centers=[center])
    db = AppointmentDB([admin, doctor], [center])

    result = create_appointment(_payload(doctor.id, center.id), user=admin, db=db)

    assert result.doctor_id == doctor.id


@pytest.mark.parametrize(
    ("doctor", "expected_detail"),
    [
        (None, "Médico inválido"),
        (_user(11, "doctor", active=False), "Médico inválido"),
        (_user(11, "secretary"), "Médico inválido"),
        (_user(11, "admin"), "Médico inválido"),
    ],
)
def test_manipulated_request_rejects_missing_inactive_or_non_doctor_user(doctor, expected_detail):
    center = _center(5)
    admin = _user(1, "admin")
    users = [admin] + ([doctor] if doctor else [])
    db = AppointmentDB(users, [center])

    with pytest.raises(HTTPException) as error:
        validate_appointment_assignment(db, admin, 11, center.id, date(2026, 9, 10))

    assert error.value.status_code == 422
    assert error.value.detail == expected_detail


def test_request_rejects_doctor_not_assigned_to_selected_center():
    selected_center = _center(5)
    other_center = _center(6)
    admin = _user(1, "admin")
    doctor = _user(11, "doctor", centers=[other_center])
    db = AppointmentDB([admin, doctor], [selected_center, other_center])

    with pytest.raises(HTTPException) as error:
        validate_appointment_assignment(db, admin, doctor.id, selected_center.id, date(2026, 9, 10))

    assert error.value.status_code == 422
    assert error.value.detail == "El médico no está asignado a este centro"


@pytest.mark.parametrize("role_code", ["doctor", "secretary"])
def test_non_admin_cannot_use_unassigned_center(role_code):
    assigned_center = _center(5)
    other_center = _center(6)
    current_user = _user(20, role_code, centers=[assigned_center])
    doctor = _user(11, "doctor", centers=[other_center])
    db = AppointmentDB([current_user, doctor], [assigned_center, other_center])

    with pytest.raises(HTTPException) as error:
        validate_appointment_assignment(db, current_user, doctor.id, other_center.id, date(2026, 9, 10))

    assert error.value.status_code == 403
    assert error.value.detail == "No tiene acceso a este centro"


def test_request_rejects_unavailable_doctor(monkeypatch):
    center = _center(5)
    admin = _user(1, "admin")
    doctor = _user(11, "doctor", centers=[center])
    db = AppointmentDB([admin, doctor], [center])
    monkeypatch.setattr(appointment_routes, "doctor_is_available", lambda *_args: False)

    with pytest.raises(HTTPException) as error:
        validate_appointment_assignment(db, admin, doctor.id, center.id, date(2026, 9, 10))

    assert error.value.status_code == 409
    assert error.value.detail == "El médico no está disponible en esta fecha para este centro"
