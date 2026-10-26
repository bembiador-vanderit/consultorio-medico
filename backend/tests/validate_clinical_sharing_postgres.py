"""Run explicitly against an isolated disposable PostgreSQL, NEVER official data."""
import hashlib
import json
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timezone
from threading import Barrier

from alembic import command
from alembic.config import Config
from fastapi import Response
from sqlalchemy import inspect, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db import engine
from app.models import CareCenter, ClinicalHistory, OrganizationMembership, Patient, Role, Specialty, User
from app.models.clinical_audit import ClinicalAuditLog
from app.models.clinical_patient_document import PreoperativeEvaluation
from app.models.patient_care import PatientCareRelationship
from app.models.patient_safety import PatientSafetyEntry
from app.api.routes.clinical_sharing import read_records
from app.schemas.clinical_sharing import PolicyUpdate
from app.services import clinical_sharing as sharing
from app.services.bootstrap import seed_identity
from app.services.tenancy import bind_scope


def main():
    assert engine.dialect.name == "postgresql"
    assert (engine.url.host or "").startswith("atlas-0060-sharing-qa-")
    assert engine.url.database == "atlas_0060_qa"
    cfg = Config("/app/alembic.ini")
    command.upgrade(cfg, "0059_patient_care")
    with Session(engine) as db:
        seed_identity(db)
        role = db.scalar(select(Role).where(Role.code == "doctor"))
        admin = db.scalar(select(User).where(User.email == "qa-sharing-admin@example.com"))
        assert admin is not None
        center = CareCenter(organization_id=1,name="QA shared temporary center",city="QA")
        patient = Patient(organization_id=1,first_name="QA shared",last_name="temporary",date_of_birth=date(1990,1,1))
        specialty = Specialty(organization_id=1,name="QA shared specialty",is_active=True)
        doctors = [User(full_name=f"QA sharing doctor {i}",email=f"qa-sharing-{i}@example.com",password_hash="unusable-qa",
            centers=[center],memberships=[OrganizationMembership(organization_id=1,roles=[role])]) for i in range(2)]
        db.add_all([center,patient,specialty,*doctors]);db.flush()
        history=ClinicalHistory(organization_id=1,patient_id=patient.id,doctor_id=doctors[0].id,center_id=center.id,
            specialty_id=specialty.id,consultation_date=date(2030,1,1),status="completed",clinical_notes="QA preserved")
        relationship=PatientCareRelationship(organization_id=1,patient_id=patient.id,doctor_id=doctors[1].id,center_id=center.id,
            relationship_type="treating",origin="administrative_assignment",status="active",started_at=datetime.now(timezone.utc),
            created_by_user_id=admin.id,updated_by_user_id=admin.id)
        safety=PatientSafetyEntry(organization_id=1,patient_id=patient.id,entry_type="allergy",substance_or_agent="QA agent",
            reaction_description="QA preserved",source_type="patient_reported",recorded_by_user_id=doctors[0].id,updated_by_user_id=doctors[0].id)
        document=PreoperativeEvaluation(organization_id=1,patient_id=patient.id,doctor_id=doctors[0].id,center_id=center.id,
            document_date=date(2030,1,1),status="signed",content={"procedimiento":"QA preserved"},
            created_by_user_id=doctors[0].id,last_updated_by_user_id=doctors[0].id)
        db.add_all([history,relationship,safety,document]);db.commit()
        ids={"reader":doctors[1].id,"admin":admin.id,"patient":patient.id,"center":center.id}

    tables=sorted(set(inspect(engine).get_table_names())-{"alembic_version"})
    def fingerprints():
        with engine.connect() as conn:
            return {table:hashlib.sha256(conn.scalar(text(f'SELECT coalesce(jsonb_agg(to_jsonb(t) ORDER BY to_jsonb(t)::text),\'[]\'::jsonb)::text FROM "{table}" t')).encode()).hexdigest() for table in tables}
    before=fingerprints()
    for target in ("0060_clinical_sharing","0059_patient_care","0060_clinical_sharing"):
        (command.downgrade if target.startswith("0059") else command.upgrade)(cfg,target)
        assert fingerprints()==before
    inspector=inspect(engine)
    assert len(inspector.get_foreign_keys("clinical_sharing_policies"))==2
    assert len(inspector.get_check_constraints("clinical_sharing_policies"))==2
    assert inspector.get_unique_constraints("clinical_sharing_policies")[0]["column_names"]==["organization_id"]
    assert "ix_clinical_shared_read_audit" in {i["name"] for i in inspector.get_indexes("clinical_audit_logs")}
    with Session(engine) as db:
        bind_scope(db,"tenant",1)
        assert sharing.policy_view(db)["mode"]=="assigned"
        assert not sharing.decide(db,db.get(User,ids["reader"]),ids["patient"],"clinical_history",center_id=ids["center"]).allowed
        sharing.update_policy(db,db.get(User,ids["admin"]),PolicyUpdate(mode="active_relationship",clinical_history=True,revision=0,reason="QA temporary opt in"))
    for sql in (
        "UPDATE clinical_sharing_policies SET mode='unsafe'",
        "UPDATE clinical_sharing_policies SET revision=0",
        "INSERT INTO clinical_sharing_policies SELECT id+100,organization_id,mode,limit_to_same_center,clinical_history,clinical_documents,patient_safety,revision,updated_by_user_id,created_at,updated_at FROM clinical_sharing_policies",
    ):
        try:
            with engine.begin() as conn: conn.execute(text(sql))
        except IntegrityError: pass
        else: raise AssertionError("Constraint accepted invalid policy")
    barrier=Barrier(2)
    def read():
        with Session(engine) as db:
            bind_scope(db,"tenant",1)
            user=db.get(User,ids["reader"])
            barrier.wait(timeout=20)
            return read_records(ids["patient"],"clinical_history",Response(),None,25,0,user,db)
    with ThreadPoolExecutor(max_workers=2) as pool:
        results=list(pool.map(lambda _:read(),range(2)))
    assert all(r["read_only"] and len(r["items"])==1 for r in results)
    with Session(engine) as db:
        logs=db.scalars(select(ClinicalAuditLog).where(ClinicalAuditLog.action=="clinical_sharing.read")).all()
        assert len(logs)==1
        assert logs[0].user_id==ids["reader"] and logs[0].context["policy_revision"]==1
        assert db.scalar(text("select count(*) from patients"))==1
    # Only the newly expected read/policy audit rows changed after opt-in.
    final=fingerprints()
    assert all(final[t]==before[t] for t in tables if t!="clinical_audit_logs")
    print(json.dumps({"result":"PASS","roundtrip":"0059 -> 0060 -> 0059 -> 0060","preserved_tables":len(tables),
        "constraints":"PASS","default_deny":True,"concurrent_shared_reads":len(results),"read_audits":len(logs)}))


if __name__ == "__main__":
    main()
