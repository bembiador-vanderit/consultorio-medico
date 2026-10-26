from datetime import date, time

from app.api.routes.communications import appointment_message
from app.models import Appointment, CareCenter, Patient, User


def test_appointment_message_contains_patient_and_visit_details():
    patient = Patient(first_name="Ana", last_name="Pérez", date_of_birth=date(1990, 1, 1))
    doctor = User(email="doctor@example.com", full_name="María López", password_hash="hash")
    center = CareCenter(name="Centro Principal", city="La Romana", is_active=True)
    appointment = Appointment(
        patient=patient,
        doctor=doctor,
        center=center,
        appointment_date=date(2026, 9, 10),
        appointment_time=time(9, 30),
        reason="Control general",
    )

    message = appointment_message(appointment)

    assert "Ana Pérez" in message
    assert "10/09/2026" in message
    assert "09:30 AM" in message
    assert "María López" in message
    assert "Centro Principal (La Romana)" in message
    assert "Control general" in message
