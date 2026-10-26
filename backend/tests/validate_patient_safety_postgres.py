"""Explicit disposable-PostgreSQL validation. Never run against the official DB."""
import hashlib
import json
from datetime import date, time

from alembic import command
from alembic.config import Config
from fastapi import HTTPException
from sqlalchemy import inspect, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db import engine
from app.models import Appointment, CareCenter, ClinicalHistory, Organization, OrganizationMembership, Patient, Role, Specialty, User
from app.models.clinical_audit import ClinicalAuditLog
from app.models.clinical_patient_document import PhysicalExamination, PreoperativeEvaluation
from app.models.patient_safety import PatientSafetyEntry
from app.schemas.patient_safety import SafetyCreate, SafetyUpdate
from app.services import patient_safety as safety
from app.services.bootstrap import seed_identity
from app.services.tenancy import bind_scope


def main():
    assert engine.dialect.name == "postgresql"
    assert (engine.url.host or "").startswith("atlas-0058-safety-qa-")
    assert engine.url.database == "atlas_0058_qa"
    cfg = Config("/app/alembic.ini")
    command.upgrade(cfg, "0057_clinical_draft_identity")
    with Session(engine) as db:
        seed_identity(db)
        assert not safety.available(db)
        role = db.scalar(select(Role).where(Role.code == "doctor"))
        assert "patient_safety:view" not in {p.code for p in role.permissions}
        org = Organization(slug="safety_qa_two", name="QA Safety Two")
        db.add(org);db.flush()
        centers = [CareCenter(organization_id=oid, name="QA Safety Center", city="QA") for oid in (1,org.id)]
        patients = [Patient(organization_id=oid, first_name="QA Safety", last_name=f"Patient {i}", date_of_birth=date(1990,1,1)) for i,oid in enumerate((1,org.id))]
        doctors = [User(email=f"qa-safety-{i}@example.com", full_name=f"QA Safety Doctor {i}", password_hash="synthetic-unusable",
            roles=[role], centers=[centers[i]], memberships=[OrganizationMembership(organization_id=oid, roles=[role])]) for i,oid in enumerate((1,org.id))]
        db.add_all([*centers,*patients,*doctors]);db.flush()
        specialties = [Specialty(organization_id=oid, name="QA Safety", is_active=True) for oid in (1,org.id)]
        db.add_all(specialties);db.flush()
        specialty = specialties[0]
        appointment = Appointment(organization_id=1, patient_id=patients[0].id, doctor_id=doctors[0].id, center_id=centers[0].id,
            specialty_id=specialty.id, appointment_date=date(2030,1,1), appointment_time=time(9), schedule_mode="timed", status="scheduled")
        db.add(appointment);db.flush()
        histories = [ClinicalHistory(organization_id=oid, patient_id=patients[i].id, doctor_id=doctors[i].id,
            center_id=centers[i].id, consultation_date=date(2030,1,1), allergies="Historical synthetic QA text",
                appointment_id=appointment.id if i==0 else None, specialty_id=specialties[i].id) for i,oid in enumerate((1,org.id))]
        db.add_all(histories);db.flush()
        for model in (PreoperativeEvaluation,PhysicalExamination):
            db.add(model(organization_id=1, patient_id=patients[0].id, doctor_id=doctors[0].id, center_id=centers[0].id,
                appointment_id=appointment.id, clinical_history_id=histories[0].id, document_date=date(2030,1,1),
                content={"qa":"preserve"}, created_by_user_id=doctors[0].id, last_updated_by_user_id=doctors[0].id))
        db.commit()
        ids = dict(patient=patients[0].id, foreign_patient=patients[1].id, doctor=doctors[0].id,
                   foreign_doctor=doctors[1].id, history=histories[0].id, org_two=org.id)

    def fingerprints():
        result={}
        with engine.connect() as conn:
            for table in ("patients","appointments","clinical_histories","preoperative_evaluations","physical_examinations"):
                value=conn.scalar(text(f"SELECT coalesce(jsonb_agg(to_jsonb(t) ORDER BY id),'[]'::jsonb)::text FROM {table} t"))
                result[table]={"count":len(json.loads(value)),"sha256":hashlib.sha256(value.encode()).hexdigest()}
        return result

    before=fingerprints()
    for target in ("0058_patient_safety","0057_clinical_draft_identity","0058_patient_safety"):
        (command.downgrade if target.startswith("0057") else command.upgrade)(cfg,target)
        assert fingerprints()==before
    inspector=inspect(engine)
    assert {"ix_safety_patient_status","ix_patient_safety_entries_organization_id"}.issubset({i["name"] for i in inspector.get_indexes("patient_safety_entries")})
    assert len(inspector.get_foreign_keys("patient_safety_entries"))==5
    assert len(inspector.get_check_constraints("patient_safety_entries"))==6
    with Session(engine) as db:
        seed_identity(db)
        doctor=db.get(User,ids["doctor"])
        assert {safety.VIEW,safety.EDIT}.issubset({p.code for p in doctor.roles[0].permissions})
    with Session(engine) as db:
        bind_scope(db,"tenant",1)
        row=safety.create(db,db.get(User,ids["doctor"]),ids["patient"],SafetyCreate(entry_type="allergy",substance_or_agent="QA agent",
            reaction_description="Synthetic reaction",severity="critical",source_type="patient_reported",clinical_history_id=ids["history"]))
        entry_id=row.id
        assert row.recorded_by_user_id==ids["doctor"]
        assert db.scalar(select(ClinicalAuditLog).where(ClinicalAuditLog.resource_type=="patient_safety_entry")).context["after"]["severity"]=="critical"
    assert fingerprints()==before
    with Session(engine) as db:
        bind_scope(db,"tenant",ids["org_two"])
        actor=db.get(User,ids["foreign_doctor"])
        safety.authorize(db,actor,ids["foreign_patient"])
        assert db.get(PatientSafetyEntry,entry_id) is None
        assert db.scalar(select(ClinicalAuditLog).where(ClinicalAuditLog.resource_type=="patient_safety_entry")) is None
        try:
            safety.update(db,actor,ids["foreign_patient"],entry_id,SafetyUpdate(entry_type="allergy",substance_or_agent="QA",
                reaction_description="QA",source_type="patient_reported",revision=1))
        except HTTPException as error:
            assert error.status_code==404
        else:
            raise AssertionError("Cross-tenant safety update succeeded")
    checks={"entry_type":"'bad'","severity":"'bad'","status":"'bad'","source_type":"'bad'","revision":"0",
            "substance_or_agent":"' '","patient_id":"99999999","clinical_history_id":"99999999","recorded_by_user_id":"99999999"}
    with engine.begin() as conn:
        for field,value in checks.items():
            nested=conn.begin_nested()
            try:
                conn.execute(text(f"UPDATE patient_safety_entries SET {field}={value} WHERE id=:id"),{"id":entry_id})
            except IntegrityError:
                nested.rollback()
            else:
                nested.rollback();raise AssertionError(f"Constraint missing: {field}")
    try:
        command.downgrade(cfg,"0057_clinical_draft_identity")
    except RuntimeError as error:
        assert "Downgrade blocked" in str(error)
    else:
        raise AssertionError("Populated safety data was deleted by downgrade")
    with engine.connect() as conn:
        assert conn.scalar(text("SELECT version_num FROM alembic_version"))=="0058_patient_safety"
        assert conn.scalar(text("SELECT count(*) FROM patient_safety_entries"))==1
    print(json.dumps({"RESULT":"PASS","roundtrip":"0057 -> 0058 -> 0057 -> 0058","preserved":before,
        "foreign_keys":5,"check_constraints":6,"invalid_writes_rejected":len(checks),
        "tenant_isolation":"PASS","populated_downgrade":"blocked safely","new_safety_entries":1}))


if __name__=="__main__":
    main()
