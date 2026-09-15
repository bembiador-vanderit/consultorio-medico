"""Concurrency regressions; run only against disposable PostgreSQL."""

import os
from concurrent.futures import ThreadPoolExecutor
from datetime import date, time
from threading import Barrier, Event

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session

from app.api.routes import clinical_history, diagnoses, vital_signs
from app.db import Base
from app.models import (
    Appointment,
    CareCenter,
    ClinicalAuditLog,
    ClinicalHistory,
    Diagnosis,
    Patient,
    Role,
    Specialty,
    User,
    VitalSigns,
)
from app.schemas.clinical_history import ClinicalHistoryCreate, ClinicalHistoryUpdate
from app.schemas.diagnosis import DiagnosisCreate
from app.schemas.vital_signs import VitalSignsUpdate


@pytest.fixture()
def postgres():
    url = os.environ.get("CLINICAL_CONCURRENCY_POSTGRES_URL")
    if not url:
        pytest.skip("Requires disposable PostgreSQL for clinical concurrency regressions")
    engine = create_engine(url, pool_pre_ping=True)
    assert engine.url.database == "clinical_concurrency_test"
    Base.metadata.create_all(engine)
    try:
        yield engine
    finally:
        Base.metadata.drop_all(engine)
        engine.dispose()


@pytest.fixture()
def clinical_ids(postgres):
    with Session(postgres) as db:
        doctor_role = Role(code="doctor", name="Doctor")
        center = CareCenter(name="Centro de concurrencia", city="Santo Domingo", is_active=True)
        specialty = Specialty(name="Especialidad de concurrencia", is_active=True)
        doctor = User(
            email="doctor-concurrency@example.test",
            full_name="Doctor de concurrencia",
            password_hash="test",
            is_active=True,
            roles=[doctor_role],
            centers=[center],
            specialties=[specialty],
        )
        patient = Patient(
            first_name="Paciente",
            last_name="Concurrencia",
            date_of_birth=date(1990, 1, 1),
            phone="8095550199",
        )
        db.add_all([doctor, patient])
        db.flush()
        appointment = Appointment(
            patient_id=patient.id,
            doctor_id=doctor.id,
            center_id=center.id,
            specialty_id=specialty.id,
            appointment_date=date(2026, 9, 20),
            appointment_time=time(9),
            status="scheduled",
        )
        db.add(appointment)
        db.commit()
        return {
            "doctor_id": doctor.id,
            "patient_id": patient.id,
            "appointment_id": appointment.id,
        }


def _create_history(postgres, ids) -> int:
    with Session(postgres) as db:
        history = ClinicalHistory(
            patient_id=ids["patient_id"],
            appointment_id=ids["appointment_id"],
            doctor_id=ids["doctor_id"],
            center_id=db.get(Appointment, ids["appointment_id"]).center_id,
            specialty_id=db.get(Appointment, ids["appointment_id"]).specialty_id,
            consultation_date=date(2026, 9, 20),
        )
        db.add(history)
        db.commit()
        return history.id


def test_concurrent_create_keeps_one_history_per_appointment(postgres, clinical_ids, monkeypatch):
    barrier = Barrier(2)
    original_precheck = clinical_history._ensure_appointment_available

    def synchronized_precheck(appointment_id, db, exclude_history_id=None):
        original_precheck(appointment_id, db, exclude_history_id)
        barrier.wait(timeout=10)

    monkeypatch.setattr(clinical_history, "_ensure_appointment_available", synchronized_precheck)

    def create_one(_index):
        with Session(postgres) as db:
            user = db.get(User, clinical_ids["doctor_id"])
            try:
                clinical_history.create_clinical_history(
                    clinical_ids["patient_id"],
                    ClinicalHistoryCreate(
                        appointment_id=clinical_ids["appointment_id"],
                        consultation_date=date(2026, 9, 20),
                    ),
                    user=user,
                    db=db,
                )
                return "saved"
            except HTTPException as error:
                assert error.status_code == 409
                assert error.detail == clinical_history.DUPLICATE_APPOINTMENT_DETAIL
                return "conflict"

    with ThreadPoolExecutor(max_workers=2) as pool:
        outcomes = list(pool.map(create_one, range(2)))

    assert sorted(outcomes) == ["conflict", "saved"]
    with Session(postgres) as db:
        count = db.scalar(
            select(func.count()).select_from(ClinicalHistory).where(
                ClinicalHistory.appointment_id == clinical_ids["appointment_id"]
            )
        )
        assert count == 1
        assert db.scalar(
            select(func.count()).select_from(ClinicalAuditLog).where(
                ClinicalAuditLog.action == "history.create",
                ClinicalAuditLog.outcome == "conflict",
            )
        ) == 1


def test_stale_revision_cannot_overwrite_committed_content(postgres, clinical_ids):
    history_id = _create_history(postgres, clinical_ids)
    base = {
        "consultation_date": date(2026, 9, 20),
        "expected_revision": 1,
    }
    with Session(postgres) as first_db:
        first = clinical_history.update_clinical_history(
            history_id,
            ClinicalHistoryUpdate(**base, clinical_notes="Versión confirmada"),
            user=first_db.get(User, clinical_ids["doctor_id"]),
            db=first_db,
        )
        assert first.revision == 2

    with Session(postgres) as stale_db:
        with pytest.raises(HTTPException) as error:
            clinical_history.update_clinical_history(
                history_id,
                ClinicalHistoryUpdate(**base, clinical_notes="Versión obsoleta"),
                user=stale_db.get(User, clinical_ids["doctor_id"]),
                db=stale_db,
            )
        assert error.value.status_code == 409
        assert error.value.detail == clinical_history.STALE_REVISION_DETAIL

    with Session(postgres) as db:
        history = db.get(ClinicalHistory, history_id)
        assert history.revision == 2
        assert history.clinical_notes == "Versión confirmada"
        conflict = db.scalar(
            select(ClinicalAuditLog).where(
                ClinicalAuditLog.action == "history.update",
                ClinicalAuditLog.outcome == "conflict",
            )
        )
        assert conflict.context["expected_revision"] == 1
        assert conflict.context["current_revision"] == 2


def test_complete_serializes_before_stale_update(postgres, clinical_ids, monkeypatch):
    history_id = _create_history(postgres, clinical_ids)
    complete_locked = Event()
    update_attempted = Event()
    release_complete = Event()
    original_access = clinical_history.require_history_access

    def gated_access(*args, **kwargs):
        if kwargs.get("action") == "history.update":
            update_attempted.set()
        history = original_access(*args, **kwargs)
        if kwargs.get("action") == "history.complete":
            complete_locked.set()
            assert release_complete.wait(timeout=10)
        return history

    monkeypatch.setattr(clinical_history, "require_history_access", gated_access)

    def complete():
        with Session(postgres) as db:
            clinical_history.complete_clinical_history(
                history_id,
                user=db.get(User, clinical_ids["doctor_id"]),
                db=db,
            )
            return "completed"

    def update():
        with Session(postgres) as db:
            try:
                clinical_history.update_clinical_history(
                    history_id,
                    ClinicalHistoryUpdate(
                        consultation_date=date(2026, 9, 20),
                        clinical_notes="No debe escribirse después del cierre",
                        expected_revision=1,
                    ),
                    user=db.get(User, clinical_ids["doctor_id"]),
                    db=db,
                )
                return "updated"
            except HTTPException as error:
                assert error.status_code == 409
                return "conflict"

    with ThreadPoolExecutor(max_workers=2) as pool:
        complete_future = pool.submit(complete)
        assert complete_locked.wait(timeout=10)
        update_future = pool.submit(update)
        assert update_attempted.wait(timeout=10)
        release_complete.set()
        assert complete_future.result(timeout=10) == "completed"
        assert update_future.result(timeout=10) == "conflict"

    with Session(postgres) as db:
        history = db.get(ClinicalHistory, history_id)
        assert history.status == "completed"
        assert history.revision == 2
        assert history.clinical_notes is None
        assert db.get(Appointment, clinical_ids["appointment_id"]).status == "completed"


def test_complete_serializes_before_diagnosis_create(postgres, clinical_ids, monkeypatch):
    history_id = _create_history(postgres, clinical_ids)
    complete_locked = Event()
    diagnosis_attempted = Event()
    release_complete = Event()
    original_access = clinical_history.require_history_access
    original_diagnosis_access = diagnoses.require_history_access

    def gated_access(*args, **kwargs):
        history = original_access(*args, **kwargs)
        if kwargs.get("action") == "history.complete":
            complete_locked.set()
            assert release_complete.wait(timeout=10)
        return history

    monkeypatch.setattr(clinical_history, "require_history_access", gated_access)

    def diagnosis_access(*args, **kwargs):
        diagnosis_attempted.set()
        return original_diagnosis_access(*args, **kwargs)

    monkeypatch.setattr(diagnoses, "require_history_access", diagnosis_access)

    def complete():
        with Session(postgres) as db:
            clinical_history.complete_clinical_history(
                history_id,
                user=db.get(User, clinical_ids["doctor_id"]),
                db=db,
            )

    def create_diagnosis():
        with Session(postgres) as db:
            try:
                diagnoses.create_diagnosis(
                    history_id,
                    DiagnosisCreate(description="Diagnóstico concurrente"),
                    user=db.get(User, clinical_ids["doctor_id"]),
                    db=db,
                )
                return "saved"
            except HTTPException as error:
                assert error.status_code == 409
                return "conflict"

    with ThreadPoolExecutor(max_workers=2) as pool:
        complete_future = pool.submit(complete)
        assert complete_locked.wait(timeout=10)
        diagnosis_future = pool.submit(create_diagnosis)
        assert diagnosis_attempted.wait(timeout=10)
        release_complete.set()
        complete_future.result(timeout=10)
        assert diagnosis_future.result(timeout=10) == "conflict"

    with Session(postgres) as db:
        assert db.scalar(
            select(func.count()).select_from(Diagnosis).where(
                Diagnosis.clinical_history_id == history_id
            )
        ) == 0


def test_concurrent_first_vital_signs_upserts_keep_one_row(postgres, clinical_ids):
    history_id = _create_history(postgres, clinical_ids)
    barrier = Barrier(2)

    def upsert(heart_rate):
        with Session(postgres) as db:
            barrier.wait(timeout=10)
            result = vital_signs.upsert_vital_signs(
                history_id,
                VitalSignsUpdate(heart_rate=heart_rate),
                user=db.get(User, clinical_ids["doctor_id"]),
                db=db,
            )
            return result.heart_rate

    with ThreadPoolExecutor(max_workers=2) as pool:
        outcomes = list(pool.map(upsert, (70, 80)))

    assert sorted(outcomes) == [70, 80]
    with Session(postgres) as db:
        assert db.scalar(
            select(func.count()).select_from(VitalSigns).where(
                VitalSigns.clinical_history_id == history_id
            )
        ) == 1
        assert db.scalar(
            select(VitalSigns.heart_rate).where(VitalSigns.clinical_history_id == history_id)
        ) in {70, 80}
