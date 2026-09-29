"""Run only against a disposable PostgreSQL DB named patient_security_test."""
import os
from concurrent.futures import ThreadPoolExecutor
from datetime import date
from threading import Barrier

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session

from app.api.routes.patients import create_patient, update_patient
from app.db import Base
from app.models import Organization, Patient, Role, User
from app.schemas.patient import PatientCreate, PatientUpdate


@pytest.fixture()
def postgres():
    url = os.environ.get("PATIENT_SECURITY_POSTGRES_URL")
    if not url:
        pytest.skip("Requires disposable PostgreSQL for advisory-lock regression")
    engine = create_engine(url)
    assert engine.url.database == "patient_security_test"
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        db.add(Organization(id=1, slug="pilot", name="Organización inicial"))
        db.commit()
    try:
        yield engine
    finally:
        Base.metadata.drop_all(engine)
        engine.dispose()


@pytest.mark.parametrize("operation", ["create_create", "create_update"])
def test_concurrent_writes_cannot_commit_same_dob_identifier(postgres, operation):
    with Session(postgres) as db:
        patient = Patient(first_name="Anterior", last_name="Ficticio", date_of_birth=date(1991, 1, 1), phone="8095550000")
        db.add(patient)
        db.commit()
        patient_id = patient.id
    barrier = Barrier(2)
    target = {"first_name": "Paciente", "last_name": "Ficticio", "date_of_birth": "1990-01-01", "phone": "8095559999"}
    def write(index):
        with Session(postgres) as db:
            user = User(id=1, roles=[Role(code="admin", name="Admin")], is_active=True)
            barrier.wait(timeout=10)
            try:
                if index == 1 and operation == "create_update":
                    update_patient(patient_id, PatientUpdate(**target), user=user, db=db)
                else:
                    create_patient(PatientCreate(**target), user=user, db=db)
                return "saved"
            except HTTPException as error:
                db.rollback()
                assert error.status_code == 409
                return "conflict"
    with ThreadPoolExecutor(max_workers=2) as pool:
        outcomes = list(pool.map(write, range(2)))
    assert sorted(outcomes) == ["conflict", "saved"]
    with Session(postgres) as db:
        assert db.scalar(select(func.count()).select_from(Patient).where(Patient.date_of_birth == date(1990, 1, 1), Patient.phone == "8095559999")) == 1


@pytest.mark.parametrize("operation", ["create_create", "create_update", "update_update"])
def test_concurrent_document_writes_are_unique_without_contact(postgres, operation):
    with Session(postgres) as db:
        originals = [Patient(first_name="Previo", last_name="Ficticio", date_of_birth=date(1991, 1, 1)) for _ in range(2)]
        db.add_all(originals)
        db.commit()
        ids = [item.id for item in originals]
    barrier = Barrier(2)
    def write(index):
        with Session(postgres) as db:
            user = User(id=1, roles=[Role(code="admin", name="Admin")], is_active=True)
            target = {"first_name": "Paciente", "last_name": "Ficticio", "date_of_birth": f"199{index}-01-01",
                      "document_type": "passport", "document_number": " test-123 " if index == 0 else "TEST123"}
            barrier.wait(timeout=10)
            try:
                if operation == "update_update" or (operation == "create_update" and index == 1):
                    update_patient(ids[index], PatientUpdate(**target), user=user, db=db)
                else:
                    create_patient(PatientCreate(**target), user=user, db=db)
                return "saved"
            except HTTPException as error:
                db.rollback()
                assert error.status_code == 409
                assert error.detail == "Ya existe un paciente con ese documento"
                return "conflict"
    with ThreadPoolExecutor(max_workers=2) as pool:
        assert sorted(pool.map(write, range(2))) == ["conflict", "saved"]
    with Session(postgres) as db:
        assert db.scalar(select(func.count()).select_from(Patient).where(Patient.document_number == "TEST123")) == 1
