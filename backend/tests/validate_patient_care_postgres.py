"""Explicitly guarded, disposable PostgreSQL roundtrip/concurrency validation."""
import hashlib
import json
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, time, timedelta, timezone
from threading import Barrier

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
from app.models.patient_care import PatientCareRelationship as Relationship
from app.models.patient_safety import PatientSafetyEntry
from app.schemas.patient_care import RelationshipCreate
from app.schemas.patient_safety import SafetyCreate
from app.services import patient_care as care, patient_safety as safety
from app.services.bootstrap import seed_identity
from app.services.tenancy import bind_scope


def main():
    assert engine.dialect.name=="postgresql"
    assert (engine.url.host or "").startswith("atlas-0059-care-qa-")
    assert engine.url.database=="atlas_0059_qa"
    cfg=Config("/app/alembic.ini")
    command.upgrade(cfg,"0058_patient_safety")
    with Session(engine) as db:
        seed_identity(db)
        assert not care.available(db)
        doctor_role=db.scalar(select(Role).where(Role.code=="doctor"))
        admin_role=db.scalar(select(Role).where(Role.code=="admin"))
        org=Organization(slug="care_qa_two",name="QA Care Two");db.add(org);db.flush()
        org_ids=[1,org.id]
        centers=[CareCenter(organization_id=oid,name="QA Care Center",city="QA") for oid in org_ids]
        patients=[Patient(organization_id=oid,first_name="QA Care",last_name=f"Patient {i}",date_of_birth=date(1990,1,1)) for i,oid in enumerate(org_ids)]
        specialties=[Specialty(organization_id=oid,name="QA Care Specialty",is_active=True) for oid in org_ids]
        doctors=[User(email=f"qa-care-{i}@example.com",full_name=f"QA Care Doctor {i}",password_hash="synthetic-unusable",roles=[doctor_role],
            centers=[centers[i]],specialties=[specialties[i]],memberships=[OrganizationMembership(organization_id=oid,roles=[doctor_role])]) for i,oid in enumerate(org_ids)]
        admin=User(email="qa-care-admin@example.com",full_name="QA Care Admin",password_hash="synthetic-unusable",roles=[admin_role],
            memberships=[OrganizationMembership(organization_id=oid,roles=[admin_role]) for oid in org_ids])
        other_doctor=User(email="qa-care-other@example.com",full_name="QA Second Related Doctor",password_hash="synthetic-unusable",
            roles=[doctor_role],centers=[centers[0]],memberships=[OrganizationMembership(organization_id=1,roles=[doctor_role])])
        db.add_all([*centers,*patients,*specialties,*doctors,other_doctor,admin]);db.flush()
        now=datetime.now(timezone.utc)
        histories=[]
        for index in range(2):
            appointment=Appointment(organization_id=1,patient_id=patients[0].id,doctor_id=doctors[0].id,center_id=centers[0].id,
                specialty_id=specialties[0].id,appointment_date=date(2030,1,index+1),appointment_time=time(9),schedule_mode="timed",status="completed")
            db.add(appointment);db.flush()
            history=ClinicalHistory(organization_id=1,patient_id=patients[0].id,doctor_id=doctors[0].id,center_id=centers[0].id,
                specialty_id=specialties[0].id,appointment_id=appointment.id,consultation_date=appointment.appointment_date,
                status="completed",completed_at=now-timedelta(minutes=2-index),completed_by_id=doctors[0].id,allergies="Historical QA text, unchanged")
            db.add(history);db.flush();histories.append(history)
        for model in (PreoperativeEvaluation,PhysicalExamination):
            db.add(model(organization_id=1,patient_id=patients[0].id,doctor_id=doctors[0].id,center_id=centers[0].id,
                appointment_id=histories[0].appointment_id,clinical_history_id=histories[0].id,document_date=date(2030,1,1),
                content={"qa":"preserve"},created_by_user_id=doctors[0].id,last_updated_by_user_id=doctors[0].id))
        db.commit()
        ids={"patient":patients[0].id,"doctor":doctors[0].id,"patient_two":patients[1].id,"doctor_two":doctors[1].id,
             "org_two":org.id,"admin":admin.id,"other_doctor":other_doctor.id,"history":histories[0].id,"history_next":histories[1].id}
    with Session(engine) as db:
        bind_scope(db,"tenant",1)
        safety.create(db,db.get(User,ids["doctor"]),ids["patient"],SafetyCreate(entry_type="allergy",substance_or_agent="QA agent",
            reaction_description="QA preserve",source_type="patient_reported"))

    def fingerprints():
        result={}
        with engine.connect() as c:
            for table in ("patients","appointments","clinical_histories","preoperative_evaluations","physical_examinations","patient_safety_entries","clinical_audit_logs"):
                where=" WHERE resource_type!='patient_care_relationship'" if table=="clinical_audit_logs" else ""
                raw=c.scalar(text(f"SELECT coalesce(jsonb_agg(to_jsonb(t) ORDER BY id),'[]'::jsonb)::text FROM {table} t{where}"))
                result[table]={"count":len(json.loads(raw)),"sha256":hashlib.sha256(raw.encode()).hexdigest()}
        return result

    before=fingerprints()
    for target in ("0059_patient_care","0058_patient_safety","0059_patient_care"):
        (command.downgrade if target.startswith("0058") else command.upgrade)(cfg,target)
        assert fingerprints()==before
    i=inspect(engine)
    assert len(i.get_foreign_keys("patient_care_relationships"))==9
    assert len(i.get_check_constraints("patient_care_relationships"))==6
    indexes=[index for index in i.get_indexes("patient_care_relationships") if not index.get("duplicates_constraint")]
    assert {index["name"] for index in indexes}=={
        "ix_patient_care_relationships_organization_id","ix_patient_care_patient_status","ix_patient_care_doctor_status"}
    assert i.get_unique_constraints("patient_care_relationships")[0]["column_names"]==["organization_id","patient_id","doctor_id"]
    with Session(engine) as db:
        seed_identity(db)

    barrier=Barrier(2)
    def observe():
        with Session(engine) as db:
            bind_scope(db,"tenant",1)
            actor=db.get(User,ids["doctor"]);history=db.get(ClinicalHistory,ids["history"])
            barrier.wait(timeout=20)
            row=care.observe_completed_consultation(db,actor,history);db.commit()
            return row.id
    with ThreadPoolExecutor(max_workers=2) as pool:
        auto_results=list(pool.map(lambda _:observe(),range(2)))
    assert len(set(auto_results))==1
    with Session(engine) as db:
        bind_scope(db,"tenant",1)
        first=db.get(Relationship,auto_results[0])
        assert first.origin=="consultation" and first.status=="active"
        assert db.scalar(select(ClinicalAuditLog).where(ClinicalAuditLog.resource_type=="patient_care_relationship")).action=="patient_care.created"
        care.observe_completed_consultation(db,db.get(User,ids["doctor"]),db.get(ClinicalHistory,ids["history_next"]));db.commit()
        assert first.last_clinical_history_id==ids["history_next"]
        assert first.created_from_clinical_history_id==ids["history"]
        assert care.utc(first.last_seen_at)>care.utc(first.first_seen_at)
        try:
            care.assign(db,db.get(User,ids["admin"]),ids["patient"],RelationshipCreate(doctor_id=ids["doctor_two"],reason="QA cross tenant denied"))
        except HTTPException as error:
            assert error.status_code==404
        else:raise AssertionError("Foreign doctor accepted")
    barrier=Barrier(2)
    def manual():
        with Session(engine) as db:
            bind_scope(db,"tenant",ids["org_two"])
            actor=db.get(User,ids["admin"])
            barrier.wait(timeout=20)
            row,created=care.assign(db,actor,ids["patient_two"],RelationshipCreate(doctor_id=ids["doctor_two"],reason="QA concurrent assignment"))
            db.commit();return {"id":row.id,"created":created}
    with ThreadPoolExecutor(max_workers=2) as pool:
        manual_results=list(pool.map(lambda _:manual(),range(2)))
    assert len({x["id"] for x in manual_results})==1
    assert sorted(x["created"] for x in manual_results)==[False,True]
    with Session(engine) as db:
        bind_scope(db,"tenant",ids["org_two"])
        assert db.get(Relationship,auto_results[0]) is None
        assert db.scalar(select(Relationship.id).where(Relationship.patient_id==ids["patient"])) is None
    with Session(engine) as db:
        bind_scope(db,"tenant",1)
        actor=db.get(User,ids["admin"])
        another,created=care.assign(db,actor,ids["patient"],RelationshipCreate(doctor_id=ids["other_doctor"],reason="QA second related physician"))
        assert created and another.patient_id==ids["patient"]
        assert {row.doctor_id for row in care.list_related(db,actor,ids["patient"])}=={ids["doctor"],ids["other_doctor"]}
    checks={"relationship_type":"'bad'","origin":"'bad'","status":"'bad'","revision":"0","doctor_id":"9999999","ended_at":"now()","first_seen_at":"NULL"}
    with engine.begin() as c:
        for field,value in checks.items():
            nested=c.begin_nested()
            try:c.execute(text(f"UPDATE patient_care_relationships SET {field}={value} WHERE id=:id"),{"id":auto_results[0]})
            except IntegrityError:nested.rollback()
            else:nested.rollback();raise AssertionError(f"Missing constraint {field}")
        nested=c.begin_nested()
        try:
            c.execute(text("INSERT INTO patient_care_relationships SELECT id+100,organization_id,patient_id,doctor_id,center_id,specialty_id,relationship_type,origin,status,started_at,first_seen_at,last_seen_at,ended_at,created_from_clinical_history_id,last_clinical_history_id,created_by_user_id,updated_by_user_id,created_at,updated_at,revision FROM patient_care_relationships WHERE id=:id"),{"id":auto_results[0]})
        except IntegrityError:nested.rollback()
        else:nested.rollback();raise AssertionError("Duplicate relationship accepted")
    assert fingerprints()==before
    with engine.connect() as c:
        count=c.scalar(text("SELECT count(*) FROM clinical_audit_logs WHERE action='patient_care.created'"))
        assert count==1
        assert c.scalar(text("SELECT count(*) FROM patient_care_relationships"))==3
    try:command.downgrade(cfg,"0058_patient_safety")
    except RuntimeError as error:assert "Downgrade blocked" in str(error)
    else:raise AssertionError("Populated relationships were lost")
    print(json.dumps({"RESULT":"PASS","roundtrip":"0058 -> 0059 -> 0058 -> 0059","preserved":before,
        "foreign_keys":9,"checks":6,"indexes":3,"automatic_concurrency":auto_results,"manual_concurrency":manual_results,
        "automatic_created_audits":count,"multiple_doctors_same_patient":"PASS","tenant_isolation":"PASS","populated_downgrade":"blocked safely"}))


if __name__=="__main__":main()
