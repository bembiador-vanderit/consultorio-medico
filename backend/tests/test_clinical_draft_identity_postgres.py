"""Opt-in concurrency checks; only the disposable 0057 PostgreSQL database."""

import os
from concurrent.futures import ThreadPoolExecutor
from datetime import date, time
from threading import Barrier
from uuid import uuid4

import pytest
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db import engine
from app.models import Appointment, Patient, Permission, Role, Specialty, User
from app.models.clinical_patient_document import PhysicalExamination, PreoperativeEvaluation
from app.schemas.clinical_patient_document import DocumentCreate
from app.services import clinical_patient_documents as documents
from app.services.tenancy import bind_scope


pytestmark = pytest.mark.skipif(os.environ.get("ATLAS_0057_PG_VALIDATION") != "1",
                                reason="Requires the disposable atlas-0057-clinical-qa PostgreSQL database")


def test_concurrent_same_and_distinct_consultations():
    assert engine.dialect.name == "postgresql"
    assert engine.url.host == "atlas-0057-clinical-qa"
    assert engine.url.database == "atlas_0057_qa"
    with Session(engine) as db:
        role = db.scalar(select(Role).where(Role.code == "doctor"))
        for code in ("clinical:access", "patients:access"):
            permission = db.scalar(select(Permission).where(Permission.code == code))
            if permission is None:
                permission = Permission(code=code, description=code)
                db.add(permission)
            if permission not in role.permissions:
                role.permissions.append(permission)
        doctor = db.scalar(select(User).where(User.email == "doctor-0057@example.test"))
        specialty = db.scalars(select(Specialty)).first()
        patient = Patient(organization_id=1, first_name="Concurrencia", last_name=f"QA {uuid4().hex[:8]}",
                          date_of_birth=date(1990, 1, 1))
        db.add(patient)
        db.flush()
        appointments = [Appointment(organization_id=1, patient_id=patient.id, doctor_id=doctor.id,
                                    center_id=doctor.centers[0].id, specialty_id=specialty.id,
                                    appointment_date=date(2030, 10, 15), appointment_time=time(10, minute),
                                    schedule_mode="timed", status="scheduled") for minute in (0, 15, 30)]
        db.add_all(appointments)
        db.commit()
        doctor_id, patient_id, appointment_ids = doctor.id, patient.id, tuple(item.id for item in appointments)

    def race(kind: str, appointment_ids: tuple[int, int]):
        gate = Barrier(2)

        def create_one(appointment_id: int):
            with Session(engine) as db:
                bind_scope(db, "tenant", 1)
                doctor = db.get(User, doctor_id)
                gate.wait(timeout=20)
                row, created = documents.create(db, doctor, kind,
                                                DocumentCreate(patient_id=patient_id, appointment_id=appointment_id))
                return row.id, created, row.appointment_id

        with ThreadPoolExecutor(max_workers=2) as pool:
            return list(pool.map(create_one, appointment_ids))

    same = race("preoperative", (appointment_ids[0], appointment_ids[0]))
    assert len({row_id for row_id, _, _ in same}) == 1
    assert sorted(created for _, created, _ in same) == [False, True]

    distinct = race("physical_exam", (appointment_ids[1], appointment_ids[2]))
    assert len({row_id for row_id, _, _ in distinct}) == 2
    assert all(created for _, created, _ in distinct)
    assert {appointment_id for _, _, appointment_id in distinct} == set(appointment_ids[1:])
    with Session(engine) as db:
        assert db.scalar(select(func.count(PreoperativeEvaluation.id)).where(
            PreoperativeEvaluation.appointment_id == appointment_ids[0])) == 1
        assert db.scalar(select(func.count(PhysicalExamination.id)).where(
            PhysicalExamination.appointment_id.in_(appointment_ids[1:]))) == 2
        original = db.scalar(select(PreoperativeEvaluation).where(
            PreoperativeEvaluation.appointment_id == appointment_ids[0]))
        duplicate = PreoperativeEvaluation(organization_id=1, patient_id=patient_id,
                                           doctor_id=doctor_id, center_id=original.center_id,
                                           appointment_id=appointment_ids[0], document_date=original.document_date,
                                           status="draft", content={}, created_by_user_id=doctor_id,
                                           last_updated_by_user_id=doctor_id)
        db.add(duplicate)
        with pytest.raises(IntegrityError):
            db.commit()
        db.rollback()
