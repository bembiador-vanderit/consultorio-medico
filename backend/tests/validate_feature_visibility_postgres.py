"""Explicit disposable PostgreSQL only. Never accepts Atlas official DB/host."""
import hashlib
import json
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, time, timezone
from threading import Barrier
from alembic import command
from alembic.config import Config
from fastapi import HTTPException
from sqlalchemy import func, inspect, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from app.db import engine
from app.models import Appointment, CareCenter, ClinicalHistory, FollowUp, OrganizationMembership, Patient, Role, Specialty, User
from app.models.cardiology import CardiologyAssessment, ClinicalFollowUpPlan, FollowUpContactAttempt
from app.models.clinical_audit import ClinicalAuditLog
from app.models.clinical_patient_document import PreoperativeEvaluation, PhysicalExamination
from app.models.clinical_sharing import ClinicalSharingPolicy
from app.models.feature_visibility import FeatureVisibilitySetting
from app.models.patient_care import PatientCareRelationship
from app.models.patient_safety import PatientSafetyEntry
from app.schemas.feature_visibility import VisibilityUpdate
from app.services import feature_visibility as service
from app.services.bootstrap import seed_identity
from app.services.tenancy import bind_scope


def main():
    assert engine.dialect.name == "postgresql"
    assert (engine.url.host or "").startswith("atlas-0062-visibility-qa-")
    assert engine.url.database == "atlas_0062_qa"
    cfg = Config("/app/alembic.ini")
    command.upgrade(cfg, "0061_cardiology_workspace")
    with Session(engine) as db:
        seed_identity(db)
        roles = list(db.scalars(select(Role).where(Role.code.in_(("doctor", "admin")))))
        center = CareCenter(organization_id=1, name="QA visibility temporary", city="QA")
        patient = Patient(organization_id=1, first_name="QA", last_name="Visibility temporary", date_of_birth=date(1990,1,1))
        doctor = User(full_name="QA visibility clinician", email="visibility-temporary@example.com", password_hash="unusable-qa",
            centers=[center], memberships=[OrganizationMembership(organization_id=1, roles=roles)])
        db.add_all([center, patient, doctor]); db.flush()
        specialty = db.scalar(select(Specialty).where(Specialty.organization_id == 1, Specialty.code == "cardiology"))
        appointment = Appointment(organization_id=1, patient_id=patient.id, doctor_id=doctor.id, center_id=center.id,
            specialty_id=specialty.id, appointment_date=date(2030,1,1), appointment_time=time(9), status="completed")
        db.add(appointment); db.flush()
        history = ClinicalHistory(organization_id=1, patient_id=patient.id, doctor_id=doctor.id, center_id=center.id,
            specialty_id=specialty.id, appointment_id=appointment.id, consultation_date=date(2030,1,1), status="completed")
        db.add(history); db.flush()
        db.add_all([
            PatientSafetyEntry(organization_id=1, patient_id=patient.id, entry_type="allergy", substance_or_agent="QA agent",
                reaction_description="QA unchanged", severity="critical", source_type="patient_reported", recorded_by_user_id=doctor.id, updated_by_user_id=doctor.id),
            PatientCareRelationship(organization_id=1, patient_id=patient.id, doctor_id=doctor.id, center_id=center.id,
                origin="consultation", status="active", started_at=datetime.now(timezone.utc), created_by_user_id=doctor.id, updated_by_user_id=doctor.id),
            ClinicalSharingPolicy(organization_id=1, updated_by_user_id=doctor.id),
            ClinicalAuditLog(organization_id=1, user_id=doctor.id, action="qa.preserved", resource_type="patient", resource_id=patient.id, outcome="success"),
            CardiologyAssessment(organization_id=1, clinical_history_id=history.id, updated_by_user_id=doctor.id),
        ])
        for model in (PreoperativeEvaluation, PhysicalExamination):
            db.add(model(organization_id=1, patient_id=patient.id, doctor_id=doctor.id, center_id=center.id,
                document_date=date(2030,1,1), status="signed", content={"otros":"QA unchanged"}, created_by_user_id=doctor.id, last_updated_by_user_id=doctor.id))
        task = FollowUp(organization_id=1, patient_id=patient.id, doctor_id=doctor.id, center_id=center.id,
            clinical_history_id=history.id, due_at=datetime(2030,1,11), reason="QA follow-up")
        db.add(task); db.flush()
        db.add_all([ClinicalFollowUpPlan(organization_id=1, follow_up_id=task.id, clinical_history_id=history.id,
            kind="days", timeframe_value=10, created_by_user_id=doctor.id),
            FollowUpContactAttempt(organization_id=1, follow_up_id=task.id, recorded_by_user_id=doctor.id, result="no_answer")])
        db.commit(); ids = {"doctor": doctor.id, "center": center.id}

    tables = sorted(set(inspect(engine).get_table_names()) - {"alembic_version"})
    def fingerprints(*, exclude_visibility_audits=False):
        with engine.connect() as conn:
            result = {}
            for table in tables:
                where = " WHERE action != 'feature_visibility.updated'" if exclude_visibility_audits and table == "clinical_audit_logs" else ""
                result[table] = hashlib.sha256(conn.scalar(text(f'SELECT coalesce(jsonb_agg(to_jsonb(t) ORDER BY to_jsonb(t)::text),\'[]\'::jsonb)::text FROM "{table}" t{where}')).encode()).hexdigest()
            return result
    before = fingerprints()
    for target in ("0062_feature_visibility", "0061_cardiology_workspace", "0062_feature_visibility"):
        (command.downgrade if target.startswith("0061") else command.upgrade)(cfg, target)
        assert fingerprints() == before, "Historical records changed"
    inspector = inspect(engine)
    assert len(inspector.get_foreign_keys("feature_visibility_settings")) == 3
    indexes = {i["name"]: i for i in inspector.get_indexes("feature_visibility_settings")}
    assert indexes["uq_feature_visibility_org"]["unique"] and indexes["uq_feature_visibility_center"]["unique"]
    assert "center_id IS NULL" in str(indexes["uq_feature_visibility_org"]["dialect_options"]["postgresql_where"])
    assert "center_id IS NOT NULL" in str(indexes["uq_feature_visibility_center"]["dialect_options"]["postgresql_where"])

    def row(**changes):
        return FeatureVisibilitySetting(organization_id=1, center_id=None, feature_code="clinical_safety_full", context_code="ambulatory",
            audience="doctor", visibility_mode="visible", updated_by_user_id=ids["doctor"], reason="QA constraints", **changes)
    with Session(engine) as db:
        db.add(row()); db.commit()
    checks = 0
    for mode, revision in (("visible",1),("invalid",1),("hidden",0)):
        with Session(engine) as db:
            candidate=row(); candidate.visibility_mode=mode; candidate.revision=revision
            db.add(candidate)
            try:
                db.commit()
            except IntegrityError:
                db.rollback(); checks += 1
            else:
                raise AssertionError("Constraint did not reject invalid/duplicate configuration")
    # Same key at a center is legal; a second center override is not.
    with Session(engine) as db:
        candidate=row(); candidate.center_id=ids["center"]; db.add(candidate); db.commit()
    with Session(engine) as db:
        candidate=row(); candidate.center_id=ids["center"]; db.add(candidate)
        try:
            db.commit()
        except IntegrityError:
            db.rollback(); checks += 1
        else:
            raise AssertionError("Center unique index did not enforce uniqueness")

    barrier = Barrier(2)
    def race(_):
        with Session(engine) as db:
            bind_scope(db, "tenant", 1)
            user = db.get(User, ids["doctor"])
            barrier.wait(timeout=30)
            try:
                service.update(db, user, None, VisibilityUpdate(changes=[{
                    "feature_code":"clinical_safety_critical_alert", "audience":"doctor", "visibility_mode":"visible", "revision":0}], reason="QA concurrent visibility"))
                return 200
            except HTTPException as error:
                db.rollback(); return error.status_code
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = sorted(pool.map(race, range(2)))
    assert results == [200,409], results
    with Session(engine) as db:
        assert db.scalar(select(func.count()).select_from(FeatureVisibilitySetting).where(FeatureVisibilitySetting.feature_code == "clinical_safety_critical_alert")) == 1
        assert db.scalar(select(func.count()).select_from(ClinicalAuditLog).where(ClinicalAuditLog.action == "feature_visibility.updated")) == 1
        persisted = db.scalar(select(FeatureVisibilitySetting).where(FeatureVisibilitySetting.feature_code == "clinical_safety_critical_alert"))
        audit = db.scalar(select(ClinicalAuditLog).where(ClinicalAuditLog.action == "feature_visibility.updated"))
        assert audit.context["revision"] == persisted.revision == 1
        assert audit.context["previous_revision"] == 0
        assert audit.resource_id == persisted.id and audit.user_id == ids["doctor"]
        assert audit.organization_id == 1 and audit.center_id is None and audit.created_at
        assert audit.context["feature_code"] == persisted.feature_code
        assert audit.context["context_code"] == persisted.context_code == "ambulatory"
        assert audit.context["audience"] == persisted.audience == "doctor"
        assert audit.context["before"] is None and audit.context["after"] == "visible"

    def write(mode, revision):
        with Session(engine) as db:
            bind_scope(db, "tenant", 1)
            user = db.get(User, ids["doctor"])
            try:
                service.update(db, user, None, VisibilityUpdate(changes=[{
                    "feature_code":"clinical_safety_critical_alert", "audience":"doctor", "visibility_mode":mode, "revision":revision}], reason="QA audit revision trace"))
                return 200
            except HTTPException as error:
                db.rollback(); return error.status_code

    assert write("visible", 1) == 200  # unchanged: no successful-change audit
    assert write("hidden", 0) == 409
    with Session(engine) as db:
        bind_scope(db, "tenant", 1)
        service.settings_view(db, None)  # reading must not create modifications
        assert db.scalar(select(func.count()).select_from(ClinicalAuditLog).where(ClinicalAuditLog.action == "feature_visibility.updated")) == 1
    assert write("hidden", 1) == 200
    with Session(engine) as db:
        persisted = db.scalar(select(FeatureVisibilitySetting).where(FeatureVisibilitySetting.feature_code == "clinical_safety_critical_alert"))
        audit = db.scalar(select(ClinicalAuditLog).where(ClinicalAuditLog.action == "feature_visibility.updated").order_by(ClinicalAuditLog.id.desc()))
        assert audit.context["revision"] == persisted.revision == 2
        assert audit.context["previous_revision"] == 1
    assert write(None, 2) == 200  # removal: local revision is 0, inherit unchanged
    with Session(engine) as db:
        audits = list(db.scalars(select(ClinicalAuditLog).where(ClinicalAuditLog.action == "feature_visibility.updated").order_by(ClinicalAuditLog.id)))
        assert [(a.context["previous_revision"], a.context["revision"]) for a in audits] == [(0,1),(1,2),(2,0)]
        assert db.scalar(select(FeatureVisibilitySetting).where(FeatureVisibilitySetting.feature_code == "clinical_safety_critical_alert")) is None
    assert fingerprints(exclude_visibility_audits=True) == before, "Previous data changed during audit validation"
    print(json.dumps({"RESULT":"PASS", "roundtrip":"0061 -> 0062 -> 0061 -> 0062", "preserved_tables":len(tables),
        "constraints_rejected":checks, "concurrent_statuses":results, "concurrent_audit_events":1,
        "audit_revision_trace":[1,2,0], "previous_revision_trace":[0,1,2], "read_noop_stale_no_new_audit":True,
        "official_database_used":False}))


if __name__ == "__main__":
    main()
