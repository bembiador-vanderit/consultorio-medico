from datetime import date, time

import pytest
from fastapi import HTTPException

from app.api.routes.clinical_history import (
    _appointment_context,
    _ensure_appointment_available,
    _resolve_consultation_context,
)
from app.models import Appointment
from app.schemas.clinical_history import ClinicalHistoryCreate


class FakeDB:
    def __init__(self, appointment, existing_history_id=None):
        self.appointment = appointment
        self.existing_history_id = existing_history_id

    def get(self, model, object_id):
        return self.appointment if object_id == self.appointment.id else None

    def scalar(self, _query):
        return self.existing_history_id


def test_consultation_context_is_derived_from_appointment():
    appointment = Appointment(
        id=42,
        patient_id=7,
        doctor_id=11,
        center_id=5,
        appointment_date=date(2026, 9, 10),
        appointment_time=time(9, 30),
        reason="Control general",
    )

    context = _resolve_consultation_context(42, 7, FakeDB(appointment))

    assert context == {
        "appointment_id": 42,
        "doctor_id": 11,
        "center_id": 5,
    }


def test_consultation_without_appointment_has_no_derived_context():
    context = _resolve_consultation_context(None, 7, object())

    assert context == {
        "appointment_id": None,
        "doctor_id": None,
        "center_id": None,
    }


def test_client_cannot_supply_doctor_or_center_context():
    payload = ClinicalHistoryCreate.model_validate(
        {
            "consultation_date": "2026-09-10",
            "appointment_id": 42,
            "doctor_id": 999,
            "center_id": 999,
        }
    )

    assert payload.appointment_id == 42
    assert not hasattr(payload, "doctor_id")
    assert not hasattr(payload, "center_id")


def test_appointment_must_belong_to_patient():
    appointment = Appointment(
        id=42,
        patient_id=8,
        doctor_id=11,
        center_id=5,
        appointment_date=date(2026, 9, 10),
        appointment_time=time(9, 30),
    )

    with pytest.raises(HTTPException) as error:
        _appointment_context(appointment, 7)

    assert error.value.status_code == 400


def test_appointment_cannot_create_more_than_one_consultation():
    db = FakeDB(appointment=None, existing_history_id=51)

    with pytest.raises(HTTPException) as error:
        _ensure_appointment_available(42, db)

    assert error.value.status_code == 409
    assert error.value.detail == "La cita ya tiene una consulta médica registrada"


def test_existing_consultation_can_keep_its_appointment():
    db = FakeDB(appointment=None, existing_history_id=None)

    _ensure_appointment_available(42, db, exclude_history_id=51)
