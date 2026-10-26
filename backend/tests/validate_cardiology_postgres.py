"""Explicit disposable-PostgreSQL validation. Refuses the official host/database."""
import hashlib
import json
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, time, timezone
from threading import Barrier

from alembic import command
from alembic.config import Config
from fastapi import HTTPException
from sqlalchemy import inspect, select, text, func
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db import engine
from app.models import (Appointment, CareCenter, ClinicalHistory, FollowUp,
    OrganizationMembership, Patient, Role, Specialty, User)
from app.models.cardiology import CardiologyAssessment, ClinicalFollowUpPlan
from app.models.clinical_audit import ClinicalAuditLog
from app.models.clinical_patient_document import PreoperativeEvaluation
from app.models.clinical_sharing import ClinicalSharingPolicy
from app.models.patient_care import PatientCareRelationship
from app.models.patient_safety import PatientSafetyEntry
from app.api.routes.clinical_history import complete_clinical_history
from app.api.routes.cardiology import save_assessment
from app.schemas.cardiology import CardiologyWrite
from app.services.bootstrap import seed_identity
from app.services.clinical_specialties import set_doctor_specialties
from app.services.tenancy import bind_scope


def main():
    assert engine.dialect.name == "postgresql"
    assert (engine.url.host or "").startswith("atlas-0061-cardio-qa-")
    assert engine.url.database == "atlas_0061_qa"
    cfg = Config("/app/alembic.ini")
    command.upgrade(cfg, "0060_clinical_sharing")
    with Session(engine) as db:
        seed_identity(db)
        role = db.scalar(select(Role).where(Role.code == "doctor"))
        center = CareCenter(organization_id=1, name="QA cardiology temporary", city="QA")
        patient = Patient(organization_id=1, first_name="QA cardio", last_name="temporary", date_of_birth=date(1990,1,1))
        specialties = list(db.scalars(select(Specialty).where(Specialty.organization_id==1, Specialty.code=="cardiology")))
        assert len(specialties)==1, "Expected exactly one seeded cardiology specialty"
        specialty = specialties[0]
        doctor = User(full_name="QA cardiology doctor", email="cardio-temporary@example.test", password_hash="unusable-qa",
            centers=[center], memberships=[OrganizationMembership(organization_id=1, roles=[role])])
        db.add_all([center, patient, specialty, doctor]); db.flush()
        set_doctor_specialties(db,doctor,specialty.id,[specialty.id])
        appointment = Appointment(organization_id=1, patient_id=patient.id, doctor_id=doctor.id, center_id=center.id,
            specialty_id=specialty.id, appointment_date=date(2030,1,1), appointment_time=time(9), status="scheduled")
        db.add(appointment); db.flush()
        history = ClinicalHistory(organization_id=1, patient_id=patient.id, doctor_id=doctor.id, center_id=center.id,
            specialty_id=specialty.id, appointment_id=appointment.id, consultation_date=date(2030,1,1),
            status="in_progress", clinical_notes="QA preserved", reason_for_visit="QA reason")
        relationship = PatientCareRelationship(organization_id=1, patient_id=patient.id, doctor_id=doctor.id, center_id=center.id,
            relationship_type="treating", origin="administrative_assignment", status="active", started_at=datetime.now(timezone.utc),
            created_by_user_id=doctor.id, updated_by_user_id=doctor.id)
        safety = PatientSafetyEntry(organization_id=1, patient_id=patient.id, entry_type="allergy", substance_or_agent="QA agent",
            reaction_description="QA preserved", source_type="patient_reported", recorded_by_user_id=doctor.id, updated_by_user_id=doctor.id)
        document = PreoperativeEvaluation(organization_id=1, patient_id=patient.id, doctor_id=doctor.id, center_id=center.id,
            document_date=date(2030,1,1), status="signed", content={"procedimiento":"QA preserved"},
            created_by_user_id=doctor.id, last_updated_by_user_id=doctor.id)
        policy = ClinicalSharingPolicy(organization_id=1, updated_by_user_id=doctor.id)
        audit = ClinicalAuditLog(organization_id=1, user_id=doctor.id, action="qa.preserved", resource_type="patient", resource_id=patient.id, outcome="success")
        db.add_all([history, relationship, safety, document, policy, audit]); db.flush()
        legacy = FollowUp(organization_id=1, patient_id=patient.id, doctor_id=doctor.id, center_id=center.id,
            due_at=datetime(2030,2,1), reason="QA preserved legacy")
        db.add(legacy); db.commit()
        ids = {"history":history.id, "doctor":doctor.id, "patient":patient.id}

    tables = sorted(set(inspect(engine).get_table_names()) - {"alembic_version"})
    def fingerprints():
        with engine.connect() as conn:
            return {table:hashlib.sha256(conn.scalar(text(f'SELECT coalesce(jsonb_agg(to_jsonb(t) ORDER BY to_jsonb(t)::text),\'[]\'::jsonb)::text FROM "{table}" t')).encode()).hexdigest() for table in tables}
    before = fingerprints()
    for target in ("0061_cardiology_workspace", "0060_clinical_sharing", "0061_cardiology_workspace"):
        (command.downgrade if target.startswith("0060") else command.upgrade)(cfg, target)
        assert fingerprints() == before, "Historical data changed during migration"
    inspector = inspect(engine)
    assert next(c for c in inspector.get_columns("follow_ups") if c["name"]=="due_at")["nullable"]
    for table, fks in (("cardiology_assessments",3),("clinical_follow_up_plans",5),("follow_up_contact_attempts",3)):
        assert len(inspector.get_foreign_keys(table)) == fks
        assert any(i["column_names"]==["organization_id"] for i in inspector.get_indexes(table))

    def race(operation):
        barrier = Barrier(2)
        def run(_):
            with Session(engine) as db:
                bind_scope(db,"tenant",1)
                user = db.get(User,ids["doctor"])
                barrier.wait(timeout=30)
                try:
                    operation(db,user)
                    return 200
                except HTTPException as error:
                    db.rollback()
                    return error.status_code
        with ThreadPoolExecutor(max_workers=2) as pool:
            return sorted(pool.map(run,range(2)))

    payload = CardiologyWrite(expected_revision=0, symptoms={"chest_pain":{"present":True,"detail":"QA"}},
        follow_up={"kind":"studies","reason":"QA Holter","condition":"QA report"})
    writes = race(lambda db,user:save_assessment(ids["history"],payload,user,db))
    assert writes == [200,409], writes
    finishes = race(lambda db,user:complete_clinical_history(ids["history"],user,db))
    assert finishes == [200,409], finishes
    with Session(engine) as db:
        bind_scope(db,"tenant",1)
        assert db.scalar(select(func.count()).select_from(CardiologyAssessment)) == 1
        assert db.scalar(select(func.count()).select_from(ClinicalFollowUpPlan)) == 1
        task = db.scalar(select(FollowUp).where(FollowUp.clinical_history_id==ids["history"]))
        assert task.status == "pending" and task.due_at is None
        assert db.get(ClinicalHistory,ids["history"]).status == "completed"
        assert db.scalar(select(func.count()).select_from(Patient)) == 1
        assert db.scalar(select(func.count()).select_from(PatientCareRelationship)) == 1
        assert db.scalar(select(func.count()).select_from(ClinicalAuditLog).where(ClinicalAuditLog.action=="follow_up.indicated")) == 1
        task_id=task.id
    # Real DB checks, each in an isolated rollback transaction.
    invalid = [
        "UPDATE cardiology_assessments SET revision=0",
        "UPDATE clinical_follow_up_plans SET kind='unsafe'",
        "UPDATE clinical_follow_up_plans SET timeframe_value=0",
        "UPDATE clinical_follow_up_plans SET scheduled_appointment_id=999999",
        "INSERT INTO clinical_follow_up_plans SELECT id+100,organization_id,follow_up_id,clinical_history_id,kind,timeframe_value,condition,scheduled_appointment_id,created_by_user_id,revision,created_at FROM clinical_follow_up_plans",
    ]
    for sql in invalid:
        try:
            with engine.begin() as conn: conn.execute(text(sql))
        except IntegrityError: pass
        else: raise AssertionError("Constraint accepted invalid input")
    print(json.dumps({"result":"PASS", "roundtrip":"0060 -> 0061 -> 0060 -> 0061",
        "preserved_tables":len(tables),"constraints":"PASS","concurrent_assessment":writes,
        "concurrent_completion":finishes,"follow_up_id":task_id,"follow_ups_from_completion":1,
        "patients":1,"relationships":1,"indication_audits":1}))


if __name__ == "__main__": main()
