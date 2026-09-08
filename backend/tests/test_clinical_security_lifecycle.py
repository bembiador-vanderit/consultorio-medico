from datetime import date, datetime, time, timedelta

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, func, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.api.deps import current_user
from app.api.routes import appointments, clinical_coverages, clinical_history, diagnoses, follow_ups, patients, prescriptions, vital_signs
from app.db import Base, get_db
from app.models import (
    Appointment,
    AppointmentCoverageTransfer,
    CareCenter,
    ClinicalAuditLog,
    ClinicalCoverage,
    ClinicalHistory,
    Diagnosis,
    FollowUp,
    Patient,
    Prescription,
    Role,
    SecretaryCenterScope,
    Specialty,
    User,
    VitalSigns,
)
from app.services.clinical_coverage import coverage_status, installation_now
from app.models.requested_tests import RequestedTests
from app.schemas.appointment import AppointmentCreate
from app.services import clinical_access as clinical_access_service
from app.services import clinical_coverage as coverage_service
from app.services.clinical_specialties import set_doctor_specialties


@pytest.fixture()
def clinical_app():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    db = Session(engine)

    doctor_role = Role(code="doctor", name="Doctor")
    admin_role = Role(code="admin", name="Administrador")
    center = CareCenter(name="Centro Seguro", city="Santo Domingo", is_active=True)
    specialty = Specialty(name="Medicina familiar", is_active=True)
    doctor_a = User(
        email="doctor-a@example.test", full_name="Doctor A", password_hash="hash",
        roles=[doctor_role], centers=[center], is_active=True,
    )
    doctor_b = User(
        email="doctor-b@example.test", full_name="Doctor B", password_hash="hash",
        roles=[doctor_role], centers=[center], is_active=True,
    )
    admin = User(
        email="admin@example.test", full_name="Admin", password_hash="hash",
        roles=[admin_role], is_active=True,
    )
    patient_a = Patient(first_name="Paciente", last_name="A", date_of_birth=date(1980, 1, 1), phone="8095550101", email="patient-a@example.com")
    patient_b = Patient(first_name="Paciente", last_name="B", date_of_birth=date(1985, 2, 2), phone="8095550202")
    db.add_all([doctor_a, doctor_b, admin, patient_a, patient_b, specialty])
    db.flush()
    set_doctor_specialties(db, doctor_a, specialty.id, [specialty.id])
    set_doctor_specialties(db, doctor_b, specialty.id, [specialty.id])

    appointment_a = Appointment(
        patient_id=patient_a.id, doctor_id=doctor_a.id, center_id=center.id,
        specialty_id=specialty.id, appointment_date=date(2026, 9, 3), appointment_time=time(9), status="scheduled",
    )
    appointment_b = Appointment(
        patient_id=patient_b.id, doctor_id=doctor_b.id, center_id=center.id,
        specialty_id=specialty.id, appointment_date=date(2026, 9, 3), appointment_time=time(10), status="confirmed",
    )
    db.add_all([appointment_a, appointment_b])
    db.flush()
    history_a = ClinicalHistory(
        patient_id=patient_a.id, appointment_id=appointment_a.id, doctor_id=doctor_a.id,
        center_id=center.id, specialty_id=specialty.id, consultation_date=date(2026, 9, 3), status="in_progress",
        reason_for_visit="Control A",
    )
    history_b = ClinicalHistory(
        patient_id=patient_b.id, appointment_id=appointment_b.id, doctor_id=doctor_b.id,
        center_id=center.id, specialty_id=specialty.id, consultation_date=date(2026, 9, 3), status="in_progress",
        reason_for_visit="Control B",
    )
    db.add_all([history_a, history_b])
    db.flush()
    diagnosis_b = Diagnosis(clinical_history_id=history_b.id, description="Diagnóstico B")
    prescription_b = Prescription(clinical_history_id=history_b.id, medication="Medicamento B")
    test_b = RequestedTests(clinical_history_id=history_b.id, test_name="Estudio B")
    vital_b = VitalSigns(clinical_history_id=history_b.id, heart_rate=70)
    prescription_a = Prescription(clinical_history_id=history_a.id, medication="Medicamento A")
    db.add_all([diagnosis_b, prescription_b, test_b, vital_b, prescription_a])
    db.commit()

    active_user = {"value": doctor_a}
    app = FastAPI()
    for router in (
        appointments.router,
        clinical_history.router,
        diagnoses.router,
        prescriptions.router,
        vital_signs.router,
        clinical_coverages.router,
        patients.router,
        follow_ups.router,
    ):
        app.include_router(router, prefix="/api/v1")
    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[clinical_history.access] = lambda: active_user["value"]
    app.dependency_overrides[clinical_history.audit_access] = lambda: active_user["value"]
    app.dependency_overrides[diagnoses.access] = lambda: active_user["value"]
    app.dependency_overrides[prescriptions.access] = lambda: active_user["value"]
    app.dependency_overrides[vital_signs.access] = lambda: active_user["value"]
    app.dependency_overrides[clinical_coverages.access] = lambda: active_user["value"]
    app.dependency_overrides[clinical_coverages.agenda_access] = lambda: active_user["value"]
    app.dependency_overrides[appointments.access] = lambda: active_user["value"]
    app.dependency_overrides[patients.access] = lambda: active_user["value"]
    app.dependency_overrides[current_user] = lambda: active_user["value"]

    yield {
        "client": TestClient(app), "db": db, "active_user": active_user,
        "doctor_a": doctor_a, "doctor_b": doctor_b, "admin": admin,
        "center": center, "specialty": specialty,
        "patient_a": patient_a, "patient_b": patient_b,
        "appointment_a": appointment_a, "appointment_b": appointment_b,
        "history_a": history_a, "history_b": history_b,
        "diagnosis_b": diagnosis_b, "prescription_b": prescription_b,
        "prescription_a": prescription_a, "test_b": test_b, "vital_b": vital_b,
    }
    db.close()


def test_doctor_cannot_read_or_modify_another_doctors_history(clinical_app):
    client = clinical_app["client"]
    history_b = clinical_app["history_b"]
    patient_b = clinical_app["patient_b"]

    assert client.get(f"/api/v1/clinical-history/patients/{patient_b.id}").status_code == 404
    assert client.get(f"/api/v1/clinical-history/{history_b.id}/summary/pdf").status_code == 403
    assert client.get(
        f"/api/v1/clinical-history/appointments/{clinical_app['appointment_b'].id}/context"
    ).status_code == 403
    response = client.put(
        f"/api/v1/clinical-history/{history_b.id}",
        json={"consultation_date": "2026-09-03", "reason_for_visit": "Ataque"},
    )
    assert response.status_code == 403
    clinical_app["db"].refresh(history_b)
    assert history_b.reason_for_visit == "Control B"

    orphan = client.post(
        f"/api/v1/clinical-history/patients/{clinical_app['patient_a'].id}",
        json={"consultation_date": "2026-09-03"},
    )
    assert orphan.status_code == 422


def test_patient_list_and_direct_identity_access_follow_doctor_scope(clinical_app):
    client = clinical_app["client"]
    patient_a = clinical_app["patient_a"]
    patient_b = clinical_app["patient_b"]

    listed = client.get("/api/v1/patients")
    assert listed.status_code == 200
    assert {item["id"] for item in listed.json()} == {patient_a.id}
    assert client.get(f"/api/v1/patients/{patient_b.id}").status_code == 404

    clinical_app["active_user"]["value"] = clinical_app["doctor_b"]
    listed = client.get("/api/v1/patients")
    assert {item["id"] for item in listed.json()} == {patient_b.id}
    assert client.get(f"/api/v1/patients/{patient_a.id}").status_code == 404
    assert client.get("/api/v1/patients/count").json() == {"count": 1}


def test_restricted_identity_search_returns_minimum_without_clinical_data(clinical_app):
    client = clinical_app["client"]
    patient = clinical_app["patient_a"]
    clinical_app["active_user"]["value"] = clinical_app["doctor_b"]

    response = client.get(
        "/api/v1/patients/identity-search",
        params={"date_of_birth": patient.date_of_birth.isoformat(), "phone": patient.phone},
    )
    assert response.status_code == 200
    assert len(response.json()) == 1
    identity = response.json()[0]
    assert set(identity) == {"id", "first_name", "last_name", "date_of_birth", "phone_masked", "email_masked"}
    assert identity["id"] == patient.id
    assert identity["phone_masked"].endswith("0101")
    assert "clinical_history" not in identity
    assert "diagnoses" not in identity


def test_new_own_appointment_grants_patient_context_but_not_other_doctors_history(clinical_app):
    client = clinical_app["client"]
    patient = clinical_app["patient_a"]
    doctor = clinical_app["doctor_b"]
    clinical_app["active_user"]["value"] = doctor
    before_count = clinical_app["db"].scalar(select(func.count()).select_from(Patient))

    created = client.post("/api/v1/appointments", json={
        "patient_id": patient.id,
        "doctor_id": doctor.id,
        "center_id": clinical_app["center"].id,
        "specialty_id": clinical_app["specialty"].id,
        "appointment_date": "2026-09-04",
        "appointment_time": "09:00:00",
        "status": "scheduled",
    })
    assert created.status_code == 201
    assert clinical_app["db"].scalar(select(func.count()).select_from(Patient)) == before_count
    assert patient.id in {item["id"] for item in client.get("/api/v1/patients").json()}

    context = client.get(f"/api/v1/clinical-history/appointments/{created.json()['id']}/context")
    assert context.status_code == 200
    assert context.json()["previous_consultations"] == []

    consultation = client.post(
        f"/api/v1/clinical-history/patients/{patient.id}",
        json={"consultation_date": "2026-09-04", "appointment_id": created.json()["id"]},
    )
    assert consultation.status_code == 201
    assert consultation.json()["doctor_id"] == doctor.id


def test_secretary_identity_search_requires_authorized_center_and_doctor(clinical_app):
    db = clinical_app["db"]
    secretary_role = Role(code="secretary", name="Secretaria")
    secretary = User(
        email="secretary-patient-scope@example.test",
        full_name="Secretaria Scope",
        password_hash="hash",
        roles=[secretary_role],
        centers=[clinical_app["center"]],
        is_active=True,
    )
    db.add(secretary); db.flush()
    db.add(SecretaryCenterScope(
        secretary_id=secretary.id,
        center_id=clinical_app["center"].id,
        manage_all_doctors=False,
        doctors=[clinical_app["doctor_b"]],
    ))
    db.commit()
    clinical_app["active_user"]["value"] = secretary
    patient = clinical_app["patient_a"]
    assert {item["id"] for item in clinical_app["client"].get("/api/v1/patients").json()} == {
        clinical_app["patient_b"].id
    }
    params = {
        "date_of_birth": patient.date_of_birth.isoformat(),
        "phone": patient.phone,
        "center_id": clinical_app["center"].id,
        "doctor_id": clinical_app["doctor_b"].id,
    }
    assert clinical_app["client"].get("/api/v1/patients/identity-search", params=params).status_code == 200
    params["doctor_id"] = clinical_app["doctor_a"].id
    assert clinical_app["client"].get("/api/v1/patients/identity-search", params=params).status_code == 403
    assert clinical_app["client"].get(
        f"/api/v1/clinical-history/patients/{patient.id}"
    ).status_code == 404
    assert clinical_app["client"].get(
        f"/api/v1/clinical-history/appointments/{clinical_app['appointment_a'].id}/context"
    ).status_code == 403


def test_admin_identity_scope_does_not_include_clinical_history(clinical_app):
    clinical_app["active_user"]["value"] = clinical_app["admin"]
    patient = clinical_app["patient_a"]
    assert clinical_app["client"].get("/api/v1/patients").status_code == 200
    identity = clinical_app["client"].get(
        "/api/v1/patients/identity-search",
        params={"date_of_birth": patient.date_of_birth.isoformat(), "email": patient.email},
    )
    assert identity.status_code == 200
    assert identity.json()[0]["id"] == patient.id
    assert clinical_app["client"].get(
        f"/api/v1/clinical-history/patients/{patient.id}"
    ).status_code == 404
    assert clinical_app["client"].get(
        f"/api/v1/clinical-history/appointments/{clinical_app['appointment_a'].id}/context"
    ).status_code == 404


def test_admin_role_does_not_broaden_a_doctors_clinical_scope(clinical_app):
    doctor = clinical_app["doctor_a"]
    doctor.roles.append(clinical_app["admin"].roles[0])
    clinical_app["db"].commit()
    clinical_app["active_user"]["value"] = doctor

    assert clinical_app["client"].get(
        f"/api/v1/clinical-history/patients/{clinical_app['patient_b'].id}"
    ).status_code == 404


def test_follow_up_rejects_patient_and_history_outside_doctor_scope(clinical_app):
    client = clinical_app["client"]
    due_at = (datetime.utcnow() + timedelta(days=2)).isoformat()
    outside_patient = client.post("/api/v1/follow-ups", json={
        "patient_id": clinical_app["patient_b"].id,
        "doctor_id": clinical_app["doctor_a"].id,
        "due_at": due_at,
        "reason": "Intento fuera de alcance",
    })
    assert outside_patient.status_code == 404

    mismatched_history = client.post("/api/v1/follow-ups", json={
        "patient_id": clinical_app["patient_a"].id,
        "doctor_id": clinical_app["doctor_a"].id,
        "clinical_history_id": clinical_app["history_b"].id,
        "due_at": due_at,
        "reason": "Historia ajena",
    })
    assert mismatched_history.status_code == 403
    assert clinical_app["db"].scalar(select(func.count()).select_from(FollowUp)) == 0


def test_exact_identity_duplicate_is_rejected(clinical_app):
    clinical_app["active_user"]["value"] = clinical_app["admin"]
    patient = clinical_app["patient_a"]
    response = clinical_app["client"].post("/api/v1/patients", json={
        "first_name": "Paciente duplicado",
        "last_name": "Prueba",
        "date_of_birth": patient.date_of_birth.isoformat(),
        "phone": patient.phone,
        "email": None,
    })
    assert response.status_code == 409


@pytest.mark.parametrize(
    "path",
    ["vital-signs", "diagnoses", "prescriptions", "requested-tests"],
)
def test_doctor_cannot_read_children_from_another_history(clinical_app, path):
    history_b = clinical_app["history_b"]
    assert clinical_app["client"].get(
        f"/api/v1/clinical-history/{history_b.id}/{path}"
    ).status_code == 403


@pytest.mark.parametrize(
    "path",
    ["summary/pdf", "prescriptions/pdf", "requested-tests/pdf"],
)
def test_doctor_cannot_download_another_doctors_clinical_documents(clinical_app, path):
    history_b = clinical_app["history_b"]
    assert clinical_app["client"].get(
        f"/api/v1/clinical-history/{history_b.id}/{path}"
    ).status_code == 403


def test_doctor_cannot_delete_resources_from_another_history(clinical_app):
    client = clinical_app["client"]
    history_b = clinical_app["history_b"]
    diagnosis_b = clinical_app["diagnosis_b"]
    prescription_b = clinical_app["prescription_b"]
    test_b = clinical_app["test_b"]

    assert client.delete(f"/api/v1/clinical-history/{history_b.id}/diagnoses/{diagnosis_b.id}").status_code == 403
    assert client.delete(f"/api/v1/clinical-history/{history_b.id}/prescriptions/{prescription_b.id}").status_code == 403
    assert client.delete(f"/api/v1/clinical-history/requested-tests/{test_b.id}").status_code == 403
    assert clinical_app["db"].get(Diagnosis, diagnosis_b.id) is not None
    assert clinical_app["db"].get(Prescription, prescription_b.id) is not None
    assert clinical_app["db"].get(RequestedTests, test_b.id) is not None


def test_parent_history_authorization_cannot_be_bypassed_with_child_ids(clinical_app):
    client = clinical_app["client"]
    history_a = clinical_app["history_a"]
    prescription_b = clinical_app["prescription_b"]
    response = client.put(
        f"/api/v1/clinical-history/{history_a.id}/prescriptions/{prescription_b.id}",
        json={"medication": "Manipulado"},
    )
    assert response.status_code == 404
    clinical_app["db"].refresh(prescription_b)
    assert prescription_b.medication == "Medicamento B"


def test_context_fields_are_rejected_and_remain_immutable(clinical_app):
    history_a = clinical_app["history_a"]
    response = clinical_app["client"].put(
        f"/api/v1/clinical-history/{history_a.id}",
        json={
            "consultation_date": "2026-09-03",
            "appointment_id": clinical_app["appointment_b"].id,
            "patient_id": clinical_app["patient_b"].id,
            "doctor_id": clinical_app["doctor_b"].id,
            "center_id": 999,
        },
    )
    assert response.status_code == 422
    clinical_app["db"].refresh(history_a)
    assert history_a.appointment_id == clinical_app["appointment_a"].id
    assert history_a.patient_id == clinical_app["patient_a"].id
    assert history_a.doctor_id == clinical_app["doctor_a"].id


def test_linked_appointment_cannot_change_clinical_context_or_be_deleted(clinical_app):
    appointment = clinical_app["appointment_a"]
    payload = AppointmentCreate(
        patient_id=clinical_app["patient_b"].id,
        doctor_id=clinical_app["doctor_a"].id,
        center_id=clinical_app["center"].id,
        appointment_date=appointment.appointment_date,
        appointment_time=appointment.appointment_time,
        status=appointment.status,
    )

    with pytest.raises(HTTPException) as update_error:
        appointments.update_appointment(
            appointment.id, payload, clinical_app["doctor_a"], clinical_app["db"]
        )
    assert getattr(update_error.value, "status_code", None) == 403

    with pytest.raises(HTTPException) as delete_error:
        appointments.delete_appointment(
            appointment.id, clinical_app["doctor_a"], clinical_app["db"]
        )
    assert getattr(delete_error.value, "status_code", None) == 409

    completed_payload = payload.model_copy(
        update={"patient_id": clinical_app["patient_a"].id, "status": "completed"}
    )
    with pytest.raises(HTTPException) as create_error:
        appointments.create_appointment(
            completed_payload, clinical_app["doctor_a"], clinical_app["db"]
        )
    assert create_error.value.status_code == 409


def test_completed_appointment_context_is_immutable_for_admin(clinical_app):
    appointment = clinical_app["appointment_a"]
    appointment.status = "completed"
    clinical_app["db"].commit()
    payload = AppointmentCreate(
        patient_id=clinical_app["patient_b"].id, doctor_id=clinical_app["doctor_b"].id,
        center_id=clinical_app["center"].id, appointment_date=appointment.appointment_date,
        appointment_time=appointment.appointment_time, status="completed",
    )
    with pytest.raises(HTTPException) as error:
        appointments.update_appointment(
            appointment.id, payload, clinical_app["admin"], clinical_app["db"]
        )
    assert error.value.status_code == 409
    clinical_app["db"].refresh(appointment)
    assert appointment.patient_id == clinical_app["patient_a"].id
    assert appointment.doctor_id == clinical_app["doctor_a"].id

    reopen_payload = AppointmentCreate(
        patient_id=appointment.patient_id,
        doctor_id=appointment.doctor_id,
        center_id=appointment.center_id,
        appointment_date=appointment.appointment_date,
        appointment_time=appointment.appointment_time,
        status="scheduled",
    )
    with pytest.raises(HTTPException) as reopen_error:
        appointments.update_appointment(
            appointment.id, reopen_payload, clinical_app["admin"], clinical_app["db"]
        )
    assert reopen_error.value.status_code == 409


def test_doctor_requires_center_membership_and_consistent_appointment_context(clinical_app):
    client = clinical_app["client"]
    db = clinical_app["db"]
    doctor = clinical_app["doctor_a"]
    history = clinical_app["history_a"]
    appointment = clinical_app["appointment_a"]

    doctor.centers.clear()
    db.commit()
    assert client.get(f"/api/v1/clinical-history/{history.id}/summary/pdf").status_code == 403

    doctor.centers.append(clinical_app["center"])
    appointment.patient_id = clinical_app["patient_b"].id
    db.commit()
    assert client.get(f"/api/v1/clinical-history/{history.id}/summary/pdf").status_code == 403


def test_admin_does_not_receive_clinical_access_automatically(clinical_app):
    clinical_app["active_user"]["value"] = clinical_app["admin"]
    history = clinical_app["history_b"]
    patient = clinical_app["patient_b"]

    listed = clinical_app["client"].get(f"/api/v1/clinical-history/patients/{patient.id}")
    assert listed.status_code == 404
    assert clinical_app["client"].get(f"/api/v1/clinical-history/{history.id}/summary/pdf").status_code == 403
    assert clinical_app["client"].get(f"/api/v1/clinical-history/{history.id}/prescriptions/pdf").status_code == 403
    assert clinical_app["client"].get(f"/api/v1/clinical-history/{history.id}/requested-tests/pdf").status_code == 403


def test_completion_updates_consultation_and_appointment_atomically_and_locks_writes(clinical_app):
    client = clinical_app["client"]
    history = clinical_app["history_a"]
    appointment = clinical_app["appointment_a"]

    response = client.post(f"/api/v1/clinical-history/{history.id}/complete")
    assert response.status_code == 200
    assert response.json()["status"] == "completed"
    clinical_app["db"].refresh(history)
    clinical_app["db"].refresh(appointment)
    assert history.status == "completed"
    assert history.completed_by_id == clinical_app["doctor_a"].id
    assert history.completed_at is not None
    assert appointment.status == "completed"

    assert client.put(
        f"/api/v1/clinical-history/{history.id}",
        json={"consultation_date": "2026-09-03", "clinical_notes": "Cambio tardío"},
    ).status_code == 409
    assert client.post(
        f"/api/v1/clinical-history/{history.id}/diagnoses",
        json={"description": "Cambio tardío"},
    ).status_code == 409
    assert client.put(
        f"/api/v1/clinical-history/{history.id}/vital-signs",
        json={"heart_rate": 75},
    ).status_code == 409
    assert client.post(
        f"/api/v1/clinical-history/{history.id}/prescriptions",
        json={"medication": "Cambio tardío"},
    ).status_code == 409
    assert client.post(
        f"/api/v1/clinical-history/{history.id}/requested-tests",
        json={"test_name": "Cambio tardío"},
    ).status_code == 409
    assert client.delete(
        f"/api/v1/clinical-history/{history.id}/prescriptions/{clinical_app['prescription_a'].id}"
    ).status_code == 409
    assert client.get(f"/api/v1/clinical-history/{history.id}/summary/pdf").status_code == 200
    assert client.get(f"/api/v1/clinical-history/{history.id}/prescriptions/pdf").status_code == 200


def test_completion_rolls_back_both_records_when_commit_fails(clinical_app):
    db = clinical_app["db"]
    history = clinical_app["history_a"]
    appointment = clinical_app["appointment_a"]
    original_commit = db.commit

    def failed_commit():
        raise SQLAlchemyError("forced failure")

    db.commit = failed_commit
    response = clinical_app["client"].post(f"/api/v1/clinical-history/{history.id}/complete")
    db.commit = original_commit
    assert response.status_code == 500
    db.expire_all()
    assert db.get(ClinicalHistory, history.id).status == "in_progress"
    assert db.get(Appointment, appointment.id).status == "scheduled"


@pytest.mark.parametrize("appointment_status", ["cancelled", "no_show", "completed"])
def test_non_attendable_appointment_cannot_open_consultation(clinical_app, appointment_status):
    appointment = clinical_app["appointment_a"]
    appointment.status = appointment_status
    clinical_app["db"].commit()
    response = clinical_app["client"].get(
        f"/api/v1/clinical-history/appointments/{appointment.id}/context"
    )
    assert response.status_code == 409

    create_response = clinical_app["client"].post(
        f"/api/v1/clinical-history/patients/{clinical_app['patient_a'].id}",
        json={
            "appointment_id": appointment.id,
            "consultation_date": "2026-09-03",
            "reason_for_visit": "No debe crearse",
        },
    )
    assert create_response.status_code == 409


def test_denied_and_successful_operations_create_minimal_audit_records(clinical_app):
    client = clinical_app["client"]
    history_a = clinical_app["history_a"]
    history_b = clinical_app["history_b"]
    assert client.get(f"/api/v1/clinical-history/{history_a.id}/vital-signs").status_code == 200
    assert client.get(f"/api/v1/clinical-history/{history_b.id}/vital-signs").status_code == 403

    logs = list(clinical_app["db"].scalars(select(ClinicalAuditLog)).all())
    assert any(log.action == "vital_signs.read" and log.outcome == "success" for log in logs)
    assert any(log.action == "vital_signs.read" and log.outcome == "denied" for log in logs)
    assert all(not (log.context and "clinical_notes" in log.context) for log in logs)


def test_explicit_coverage_grants_only_patient_specific_read_access_and_revocation_removes_it(clinical_app):
    client = clinical_app["client"]
    db = clinical_app["db"]
    doctor_a = clinical_app["doctor_a"]
    doctor_b = clinical_app["doctor_b"]
    center = clinical_app["center"]
    history_a = clinical_app["history_a"]
    now = installation_now()

    unrelated_patient = Patient(first_name="Paciente", last_name="Sin cobertura", date_of_birth=date(1990, 1, 1))
    db.add(unrelated_patient); db.flush()
    unrelated_appointment = Appointment(
        patient_id=unrelated_patient.id, doctor_id=doctor_a.id, center_id=center.id,
        appointment_date=now.date(), appointment_time=time(11), status="scheduled",
    )
    db.add(unrelated_appointment); db.flush()
    unrelated_history = ClinicalHistory(
        patient_id=unrelated_patient.id, appointment_id=unrelated_appointment.id,
        doctor_id=doctor_a.id, center_id=center.id, consultation_date=now.date(), status="in_progress",
    )
    transfer_appointment = Appointment(
        patient_id=clinical_app["patient_a"].id, doctor_id=doctor_a.id, center_id=center.id,
        appointment_date=now.date(), appointment_time=now.time().replace(microsecond=0), status="scheduled",
    )
    prior_requested_test = RequestedTests(clinical_history_id=history_a.id, test_name="Hemograma previo")
    db.add_all([unrelated_history, transfer_appointment, prior_requested_test]); db.commit()

    coverage_response = client.post("/api/v1/clinical-coverages", json={
        "substitute_doctor_id": doctor_b.id,
        "center_id": center.id,
        "starts_at": (now - timedelta(hours=1)).isoformat(),
        "ends_at": (now + timedelta(hours=2)).isoformat(),
    })
    assert coverage_response.status_code == 201
    coverage_id = coverage_response.json()["id"]

    transferred = client.post(
        f"/api/v1/clinical-coverages/{coverage_id}/appointments/{transfer_appointment.id}/transfer"
    )
    assert transferred.status_code == 200
    db.refresh(transfer_appointment)
    assert transfer_appointment.doctor_id == doctor_b.id
    assert transfer_appointment.coverage_transfer.original_doctor_id == doctor_a.id

    clinical_app["active_user"]["value"] = doctor_b
    visible_patient_ids = {item["id"] for item in client.get("/api/v1/patients").json()}
    assert clinical_app["patient_a"].id in visible_patient_ids
    assert unrelated_patient.id not in visible_patient_ids
    context = client.get(
        f"/api/v1/clinical-history/appointments/{transfer_appointment.id}/context"
    )
    assert context.status_code == 200
    assert history_a.id in {item["id"] for item in context.json()["previous_consultations"]}
    assert client.get(f"/api/v1/clinical-history/{history_a.id}/summary/pdf").status_code == 200
    assert client.get(f"/api/v1/clinical-history/{history_a.id}/prescriptions/pdf").status_code == 200
    assert client.get(f"/api/v1/clinical-history/{history_a.id}/requested-tests/pdf").status_code == 200
    assert client.get(f"/api/v1/clinical-history/{history_a.id}/vital-signs").status_code == 200
    assert client.get(f"/api/v1/clinical-history/{history_a.id}/diagnoses").status_code == 200
    assert client.get(f"/api/v1/clinical-history/{history_a.id}/prescriptions").status_code == 200
    assert client.get(f"/api/v1/clinical-history/{history_a.id}/requested-tests").status_code == 200
    assert client.get(f"/api/v1/clinical-history/{unrelated_history.id}/summary/pdf").status_code == 403
    unrelated_list = client.get(f"/api/v1/clinical-history/patients/{unrelated_patient.id}")
    assert unrelated_list.status_code == 404
    assert client.put(
        f"/api/v1/clinical-history/{history_a.id}",
        json={"consultation_date": now.date().isoformat(), "clinical_notes": "No permitido"},
    ).status_code == 403

    created = client.post(
        f"/api/v1/clinical-history/patients/{clinical_app['patient_a'].id}",
        json={"appointment_id": transfer_appointment.id, "consultation_date": now.date().isoformat()},
    )
    assert created.status_code == 201
    assert created.json()["doctor_id"] == doctor_b.id
    db.refresh(history_a)
    assert history_a.doctor_id == doctor_a.id

    # The substitute cannot transfer appointments or expand the grant.
    assert client.post(
        f"/api/v1/clinical-coverages/{coverage_id}/appointments/{unrelated_appointment.id}/transfer"
    ).status_code == 403

    clinical_app["active_user"]["value"] = doctor_a
    assert client.post(f"/api/v1/clinical-coverages/{coverage_id}/revoke").status_code == 200
    db.refresh(transfer_appointment)
    assert transfer_appointment.doctor_id == doctor_b.id
    assert transfer_appointment.coverage_transfer is not None
    clinical_app["active_user"]["value"] = doctor_b
    assert client.get(f"/api/v1/clinical-history/{history_a.id}/summary/pdf").status_code == 403
    assert client.get(
        f"/api/v1/clinical-history/appointments/{transfer_appointment.id}/context"
    ).status_code == 200


def test_revoking_coverage_restores_unstarted_appointment_and_preserves_audit(clinical_app):
    client = clinical_app["client"]
    db = clinical_app["db"]
    doctor_a = clinical_app["doctor_a"]
    doctor_b = clinical_app["doctor_b"]
    center = clinical_app["center"]
    now = installation_now()
    appointment = Appointment(
        patient_id=clinical_app["patient_a"].id,
        doctor_id=doctor_a.id,
        center_id=center.id,
        appointment_date=now.date(),
        appointment_time=now.time().replace(microsecond=0),
        status="scheduled",
    )
    db.add(appointment); db.commit()
    coverage = client.post("/api/v1/clinical-coverages", json={
        "substitute_doctor_id": doctor_b.id,
        "center_id": center.id,
        "starts_at": (now - timedelta(hours=1)).isoformat(),
        "ends_at": (now + timedelta(hours=2)).isoformat(),
    })
    assert coverage.status_code == 201
    coverage_id = coverage.json()["id"]
    assert client.post(
        f"/api/v1/clinical-coverages/{coverage_id}/appointments/{appointment.id}/transfer"
    ).status_code == 200
    db.refresh(appointment)
    assert appointment.doctor_id == doctor_b.id

    assert client.post(f"/api/v1/clinical-coverages/{coverage_id}/revoke").status_code == 200
    db.refresh(appointment)
    assert appointment.doctor_id == doctor_a.id
    assert db.scalar(select(AppointmentCoverageTransfer).where(
        AppointmentCoverageTransfer.appointment_id == appointment.id
    )) is None
    assert client.post(
        f"/api/v1/clinical-coverages/{coverage_id}/appointments/{appointment.id}/transfer"
    ).status_code == 409
    logs = list(db.scalars(select(ClinicalAuditLog).where(
        ClinicalAuditLog.resource_id == appointment.id
    )).all())
    assert any(log.action == "coverage.appointment.transfer" for log in logs)
    assert any(log.action == "coverage.appointment.restore" for log in logs)


def test_transferred_appointment_context_schedule_and_deletion_are_immutable(clinical_app):
    client = clinical_app["client"]
    db = clinical_app["db"]
    doctor_a = clinical_app["doctor_a"]
    doctor_b = clinical_app["doctor_b"]
    center = clinical_app["center"]
    now = installation_now()
    appointment = Appointment(
        patient_id=clinical_app["patient_a"].id,
        doctor_id=doctor_a.id,
        center_id=center.id,
        appointment_date=now.date(),
        appointment_time=now.time().replace(microsecond=0),
        status="scheduled",
    )
    db.add(appointment); db.commit()
    coverage = client.post("/api/v1/clinical-coverages", json={
        "substitute_doctor_id": doctor_b.id,
        "center_id": center.id,
        "starts_at": (now - timedelta(hours=1)).isoformat(),
        "ends_at": (now + timedelta(hours=2)).isoformat(),
    })
    assert coverage.status_code == 201
    assert client.post(
        f"/api/v1/clinical-coverages/{coverage.json()['id']}/appointments/{appointment.id}/transfer"
    ).status_code == 200

    clinical_app["active_user"]["value"] = clinical_app["admin"]
    payload = {
        "patient_id": appointment.patient_id,
        "doctor_id": doctor_b.id,
        "center_id": center.id,
        "appointment_date": (now.date() + timedelta(days=1)).isoformat(),
        "appointment_time": appointment.appointment_time.isoformat(),
        "status": "scheduled",
    }
    assert client.put(f"/api/v1/appointments/{appointment.id}", json=payload).status_code == 409
    assert client.delete(f"/api/v1/appointments/{appointment.id}").status_code == 409


@pytest.mark.parametrize("appointment_status", ["cancelled", "no_show", "completed"])
def test_non_eligible_appointment_status_cannot_be_transferred(clinical_app, appointment_status):
    client = clinical_app["client"]
    db = clinical_app["db"]
    now = installation_now()
    appointment = Appointment(
        patient_id=clinical_app["patient_a"].id,
        doctor_id=clinical_app["doctor_a"].id,
        center_id=clinical_app["center"].id,
        appointment_date=now.date(),
        appointment_time=now.time().replace(microsecond=0),
        status=appointment_status,
    )
    db.add(appointment); db.commit()
    coverage = client.post("/api/v1/clinical-coverages", json={
        "substitute_doctor_id": clinical_app["doctor_b"].id,
        "center_id": clinical_app["center"].id,
        "starts_at": (now - timedelta(hours=1)).isoformat(),
        "ends_at": (now + timedelta(hours=2)).isoformat(),
    })
    assert coverage.status_code == 201
    assert client.post(
        f"/api/v1/clinical-coverages/{coverage.json()['id']}/appointments/{appointment.id}/transfer"
    ).status_code == 409


def test_appointment_with_started_consultation_cannot_be_transferred(clinical_app):
    now = installation_now()
    coverage = clinical_app["client"].post("/api/v1/clinical-coverages", json={
        "substitute_doctor_id": clinical_app["doctor_b"].id,
        "center_id": clinical_app["center"].id,
        "starts_at": (now - timedelta(hours=1)).isoformat(),
        "ends_at": (now + timedelta(hours=2)).isoformat(),
    })
    assert coverage.status_code == 201
    assert clinical_app["client"].post(
        f"/api/v1/clinical-coverages/{coverage.json()['id']}/appointments/{clinical_app['appointment_a'].id}/transfer"
    ).status_code == 409


def test_failed_coverage_transfer_rolls_back_appointment_and_relation(clinical_app):
    client = clinical_app["client"]
    db = clinical_app["db"]
    doctor_a = clinical_app["doctor_a"]
    doctor_b = clinical_app["doctor_b"]
    center = clinical_app["center"]
    now = installation_now()
    appointment = Appointment(
        patient_id=clinical_app["patient_a"].id,
        doctor_id=doctor_a.id,
        center_id=center.id,
        appointment_date=now.date(),
        appointment_time=now.time().replace(microsecond=0),
        status="scheduled",
    )
    db.add(appointment); db.commit()
    coverage = client.post("/api/v1/clinical-coverages", json={
        "substitute_doctor_id": doctor_b.id,
        "center_id": center.id,
        "starts_at": (now - timedelta(hours=1)).isoformat(),
        "ends_at": (now + timedelta(hours=2)).isoformat(),
    })
    assert coverage.status_code == 201
    coverage_id = coverage.json()["id"]
    original_commit = db.commit

    def failed_commit():
        raise SQLAlchemyError("forced transfer failure")

    db.commit = failed_commit
    try:
        with pytest.raises(HTTPException) as error:
            clinical_coverages.transfer_appointment(coverage_id, appointment.id, doctor_a, db)
    finally:
        db.commit = original_commit
    assert error.value.status_code == 500
    db.expire_all()
    assert db.get(Appointment, appointment.id).doctor_id == doctor_a.id
    assert db.scalar(select(AppointmentCoverageTransfer).where(
        AppointmentCoverageTransfer.appointment_id == appointment.id
    )) is None


def test_expired_coverage_cannot_transfer_an_appointment(clinical_app):
    now = installation_now()
    response = clinical_app["client"].post("/api/v1/clinical-coverages", json={
        "substitute_doctor_id": clinical_app["doctor_b"].id,
        "center_id": clinical_app["center"].id,
        "starts_at": (now - timedelta(hours=3)).isoformat(),
        "ends_at": (now - timedelta(hours=2)).isoformat(),
    })
    assert response.status_code == 201
    appointment = clinical_app["appointment_a"]
    assert clinical_app["client"].post(
        f"/api/v1/clinical-coverages/{response.json()['id']}/appointments/{appointment.id}/transfer"
    ).status_code == 409


def test_future_coverage_transfers_now_but_clinical_access_waits_for_start(clinical_app, monkeypatch):
    client = clinical_app["client"]
    db = clinical_app["db"]
    principal = clinical_app["doctor_a"]
    substitute = clinical_app["doctor_b"]
    now = installation_now()
    starts_at = (now + timedelta(days=2)).replace(microsecond=0)
    appointment_at = starts_at + timedelta(hours=2)
    ends_at = starts_at + timedelta(days=5)
    appointment = Appointment(
        patient_id=clinical_app["patient_a"].id,
        doctor_id=principal.id,
        center_id=clinical_app["center"].id,
        specialty_id=clinical_app["specialty"].id,
        appointment_date=appointment_at.date(),
        appointment_time=appointment_at.time(),
        status="confirmed",
    )
    db.add(appointment); db.commit()
    coverage = client.post("/api/v1/clinical-coverages", json={
        "substitute_doctor_id": substitute.id,
        "center_id": clinical_app["center"].id,
        "starts_at": starts_at.isoformat(),
        "ends_at": ends_at.isoformat(),
    })
    assert coverage.status_code == 201
    assert coverage.json()["status"] == "future"

    transferred = client.post(
        f"/api/v1/clinical-coverages/{coverage.json()['id']}/appointments/{appointment.id}/transfer"
    )
    assert transferred.status_code == 200
    db.refresh(appointment)
    assert appointment.doctor_id == substitute.id

    clinical_app["active_user"]["value"] = substitute
    assert appointment.id in {item["id"] for item in client.get("/api/v1/appointments").json()}
    assert client.get(f"/api/v1/clinical-history/appointments/{appointment.id}/context").status_code == 409
    assert client.get(f"/api/v1/clinical-history/{clinical_app['history_a'].id}/summary/pdf").status_code == 403

    active_now = appointment_at
    monkeypatch.setattr(coverage_service, "installation_now", lambda: active_now)
    monkeypatch.setattr(clinical_access_service, "installation_now", lambda: active_now)
    assert client.get(f"/api/v1/clinical-history/appointments/{appointment.id}/context").status_code == 200
    assert client.get(f"/api/v1/clinical-history/{clinical_app['history_a'].id}/summary/pdf").status_code == 200
    created = client.post(
        f"/api/v1/clinical-history/patients/{clinical_app['patient_a'].id}",
        json={"appointment_id": appointment.id, "consultation_date": appointment_at.date().isoformat()},
    )
    assert created.status_code == 201
    substitute_history_id = created.json()["id"]
    assert client.post(f"/api/v1/clinical-history/{substitute_history_id}/complete").status_code == 200

    next_day = active_now + timedelta(days=1)
    monkeypatch.setattr(coverage_service, "installation_now", lambda: next_day)
    monkeypatch.setattr(clinical_access_service, "installation_now", lambda: next_day)
    assert client.get(f"/api/v1/clinical-history/{clinical_app['history_a'].id}/summary/pdf").status_code == 200

    after_expiry = ends_at
    monkeypatch.setattr(coverage_service, "installation_now", lambda: after_expiry)
    monkeypatch.setattr(clinical_access_service, "installation_now", lambda: after_expiry)
    assert client.get(f"/api/v1/clinical-history/{clinical_app['history_a'].id}/summary/pdf").status_code == 403
    own_episode = client.get(f"/api/v1/clinical-history/{substitute_history_id}/summary/pdf")
    assert own_episode.status_code == 200

    clinical_app["active_user"]["value"] = principal
    assert client.get(f"/api/v1/clinical-history/{substitute_history_id}/summary/pdf").status_code == 200
    assert db.get(ClinicalHistory, substitute_history_id).doctor_id == substitute.id


@pytest.mark.parametrize("delta", [timedelta(hours=-1), timedelta(days=5)])
def test_future_coverage_rejects_appointments_outside_its_period(clinical_app, delta):
    now = installation_now()
    starts_at = (now + timedelta(days=2)).replace(microsecond=0)
    ends_at = starts_at + timedelta(days=5)
    appointment_at = starts_at + delta
    appointment = Appointment(
        patient_id=clinical_app["patient_a"].id,
        doctor_id=clinical_app["doctor_a"].id,
        center_id=clinical_app["center"].id,
        specialty_id=clinical_app["specialty"].id,
        appointment_date=appointment_at.date(),
        appointment_time=appointment_at.time(),
        status="scheduled",
    )
    clinical_app["db"].add(appointment); clinical_app["db"].commit()
    coverage = clinical_app["client"].post("/api/v1/clinical-coverages", json={
        "substitute_doctor_id": clinical_app["doctor_b"].id,
        "center_id": clinical_app["center"].id,
        "starts_at": starts_at.isoformat(),
        "ends_at": ends_at.isoformat(),
    })
    assert clinical_app["client"].post(
        f"/api/v1/clinical-coverages/{coverage.json()['id']}/appointments/{appointment.id}/transfer"
    ).status_code == 409


def test_doctor_cannot_grant_coverage_to_self(clinical_app):
    now = installation_now()
    response = clinical_app["client"].post("/api/v1/clinical-coverages", json={
        "substitute_doctor_id": clinical_app["doctor_a"].id,
        "center_id": clinical_app["center"].id,
        "starts_at": now.isoformat(),
        "ends_at": (now + timedelta(hours=1)).isoformat(),
    })
    assert response.status_code == 422


def test_secretary_cannot_create_clinical_coverage(clinical_app):
    secretary_role = Role(code="secretary", name="Secretaria")
    secretary = User(
        email="secretary-coverage@example.test", full_name="Secretaria",
        password_hash="hash", roles=[secretary_role], centers=[clinical_app["center"]], is_active=True,
    )
    clinical_app["db"].add(secretary); clinical_app["db"].commit()
    clinical_app["active_user"]["value"] = secretary
    now = installation_now()
    response = clinical_app["client"].post("/api/v1/clinical-coverages", json={
        "substitute_doctor_id": clinical_app["doctor_b"].id,
        "center_id": clinical_app["center"].id,
        "starts_at": now.isoformat(), "ends_at": (now + timedelta(hours=1)).isoformat(),
    })
    assert response.status_code == 403


def test_authorized_secretary_can_transfer_future_appointment_but_outsider_cannot(clinical_app):
    db = clinical_app["db"]
    client = clinical_app["client"]
    principal = clinical_app["doctor_a"]
    substitute = clinical_app["doctor_b"]
    center = clinical_app["center"]
    now = installation_now()
    starts_at = (now + timedelta(days=2)).replace(microsecond=0)
    appointment_at = starts_at + timedelta(hours=2)
    coverage = client.post("/api/v1/clinical-coverages", json={
        "substitute_doctor_id": substitute.id,
        "center_id": center.id,
        "starts_at": starts_at.isoformat(),
        "ends_at": (starts_at + timedelta(days=2)).isoformat(),
    }).json()
    appointments_to_transfer = [
        Appointment(
            patient_id=clinical_app["patient_a"].id,
            doctor_id=principal.id,
            center_id=center.id,
            specialty_id=clinical_app["specialty"].id,
            appointment_date=appointment_at.date(),
            appointment_time=(appointment_at + timedelta(hours=index)).time(),
            status="scheduled",
        )
        for index in range(2)
    ]
    secretary_role = Role(code="secretary", name="Secretaria")
    authorized = User(
        email="authorized-future-coverage@example.test", full_name="Secretaria Autorizada",
        password_hash="hash", roles=[secretary_role], centers=[center], is_active=True,
    )
    outsider = User(
        email="outside-future-coverage@example.test", full_name="Secretaria Parcial",
        password_hash="hash", roles=[secretary_role], centers=[center], is_active=True,
    )
    db.add_all([authorized, outsider, *appointments_to_transfer]); db.flush()
    db.add_all([
        SecretaryCenterScope(
            secretary_id=authorized.id, center_id=center.id,
            manage_all_doctors=False, doctors=[principal, substitute],
        ),
        SecretaryCenterScope(
            secretary_id=outsider.id, center_id=center.id,
            manage_all_doctors=False, doctors=[principal],
        ),
    ])
    db.commit()

    clinical_app["active_user"]["value"] = authorized
    listed = client.get("/api/v1/clinical-coverages")
    assert listed.status_code == 200
    assert coverage["id"] in {item["id"] for item in listed.json()}
    assert client.post(
        f"/api/v1/clinical-coverages/{coverage['id']}/appointments/{appointments_to_transfer[0].id}/transfer"
    ).status_code == 200

    clinical_app["active_user"]["value"] = outsider
    assert coverage["id"] not in {item["id"] for item in client.get("/api/v1/clinical-coverages").json()}
    assert client.post(
        f"/api/v1/clinical-coverages/{coverage['id']}/appointments/{appointments_to_transfer[1].id}/transfer"
    ).status_code == 403


def test_revoking_future_coverage_restores_transferred_appointment(clinical_app):
    client = clinical_app["client"]
    db = clinical_app["db"]
    now = installation_now()
    starts_at = (now + timedelta(days=2)).replace(microsecond=0)
    appointment_at = starts_at + timedelta(hours=2)
    appointment = Appointment(
        patient_id=clinical_app["patient_a"].id,
        doctor_id=clinical_app["doctor_a"].id,
        center_id=clinical_app["center"].id,
        specialty_id=clinical_app["specialty"].id,
        appointment_date=appointment_at.date(),
        appointment_time=appointment_at.time(),
        status="confirmed",
    )
    db.add(appointment); db.commit()
    coverage = client.post("/api/v1/clinical-coverages", json={
        "substitute_doctor_id": clinical_app["doctor_b"].id,
        "center_id": clinical_app["center"].id,
        "starts_at": starts_at.isoformat(),
        "ends_at": (starts_at + timedelta(days=2)).isoformat(),
    }).json()
    assert client.post(
        f"/api/v1/clinical-coverages/{coverage['id']}/appointments/{appointment.id}/transfer"
    ).status_code == 200

    clinical_app["active_user"]["value"] = clinical_app["doctor_b"]
    assert appointment.id in {item["id"] for item in client.get("/api/v1/appointments").json()}
    clinical_app["active_user"]["value"] = clinical_app["doctor_a"]
    assert client.post(f"/api/v1/clinical-coverages/{coverage['id']}/revoke").status_code == 200
    db.refresh(appointment)
    assert appointment.doctor_id == clinical_app["doctor_a"].id
    assert appointment.coverage_transfer is None
    clinical_app["active_user"]["value"] = clinical_app["doctor_b"]
    assert appointment.id not in {item["id"] for item in client.get("/api/v1/appointments").json()}


def test_coverage_in_another_center_does_not_open_history(clinical_app):
    db = clinical_app["db"]
    now = installation_now()
    other_center = CareCenter(name="Otro centro", city="Santiago", is_active=True)
    clinical_app["doctor_a"].centers.append(other_center)
    clinical_app["doctor_b"].centers.append(other_center)
    db.add(other_center); db.flush()
    appointment = Appointment(
        patient_id=clinical_app["patient_a"].id, doctor_id=clinical_app["doctor_a"].id,
        center_id=other_center.id, appointment_date=now.date(),
        appointment_time=now.time().replace(microsecond=0), status="scheduled",
    )
    db.add(appointment); db.commit()
    coverage = clinical_app["client"].post("/api/v1/clinical-coverages", json={
        "substitute_doctor_id": clinical_app["doctor_b"].id, "center_id": other_center.id,
        "starts_at": (now - timedelta(hours=1)).isoformat(), "ends_at": (now + timedelta(hours=1)).isoformat(),
    })
    assert coverage.status_code == 201
    assert clinical_app["client"].post(
        f"/api/v1/clinical-coverages/{coverage.json()['id']}/appointments/{appointment.id}/transfer"
    ).status_code == 200
    clinical_app["active_user"]["value"] = clinical_app["doctor_b"]
    assert clinical_app["client"].get(
        f"/api/v1/clinical-history/{clinical_app['history_a'].id}/summary/pdf"
    ).status_code == 403


def test_coverage_status_uses_exact_documented_boundaries():
    start = datetime(2026, 9, 3, 23, 21)
    end = datetime(2026, 9, 4, 23, 0)
    coverage = ClinicalCoverage(
        principal_doctor_id=1,
        substitute_doctor_id=2,
        center_id=3,
        starts_at=start,
        ends_at=end,
        created_by_id=1,
    )

    assert coverage_status(coverage, start - timedelta(microseconds=1)) == "future"
    assert coverage_status(coverage, start) == "active"
    assert coverage_status(coverage, start + timedelta(hours=1)) == "active"
    assert coverage_status(coverage, end) == "expired"
    assert coverage_status(coverage, end + timedelta(microseconds=1)) == "expired"

    coverage.revoked_at = start + timedelta(minutes=30)
    assert coverage_status(coverage, start + timedelta(hours=1)) == "revoked"
