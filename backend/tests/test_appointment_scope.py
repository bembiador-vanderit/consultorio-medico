import pytest
from fastapi import HTTPException

from app.api.routes.appointments import ensure_appointment_access, list_appointments
from app.models import Appointment, Role, User


def _user(user_id: int, role_code: str) -> User:
    return User(
        id=user_id,
        full_name=f"Usuario {user_id}",
        roles=[Role(code=role_code, name=role_code)],
    )


class QueryCaptureDB:
    def scalars(self, query):
        self.query = query
        return self

    def all(self):
        return []


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
