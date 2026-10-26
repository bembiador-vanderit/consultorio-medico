"""Run only on disposable atlas-slot-guard-qa-* PostgreSQL; never official data."""
import hashlib
import json
from concurrent.futures import ThreadPoolExecutor
from datetime import date, time
from threading import Barrier

from alembic import command
from alembic.config import Config
from fastapi import FastAPI, Request
from fastapi.testclient import TestClient
from sqlalchemy import inspect, select, text
from sqlalchemy.orm import Session

from app.api.routes import appointments, auth, clinical_coverages
from app.core.security import hash_password
from app.db import engine, get_db
from app.models import Appointment, CareCenter, OrganizationMembership, Patient, Role, Specialty, User
from app.models.agenda_schedule import DoctorAgendaSetting
from app.models.clinical_form import ClinicalFormTemplate, ClinicalFormVersion, ClinicalFormAssignment
from app.models.clinical_sharing import ClinicalSharingPolicy
from app.models.feature_visibility import FeatureVisibilitySetting
from app.models.finance import CashRegister
from app.models.insurance import InsuranceCompany
from app.services.appointment_slots import slot_write
from app.services.bootstrap import seed_identity
from app.services.tenancy import resolve_request


def main():
    assert engine.dialect.name == "postgresql"
    assert (engine.url.host or "").startswith("atlas-slot-guard-qa-")
    assert engine.url.database == "atlas_slot_qa"
    cfg = Config("/app/alembic.ini")
    command.upgrade(cfg, "0062_feature_visibility")
    with Session(engine) as db:
        seed_identity(db)
        roles = {r.code:r for r in db.scalars(select(Role))}
        center = CareCenter(organization_id=1, name="QA CEMER", city="QA")
        specialty = db.scalar(select(Specialty).where(Specialty.organization_id==1).limit(1))
        assert specialty is not None
        admin = User(full_name="QA slot administrator",email="slot-admin@example.com",password_hash=hash_password("SyntheticSlotOnly123"),
            memberships=[OrganizationMembership(organization_id=1, roles=[roles["admin"]])])
        doctor = User(full_name="QA slot doctor",email="slot-doctor@example.com",password_hash=hash_password("SyntheticSlotOnly123"),
            centers=[center],specialties=[specialty],memberships=[OrganizationMembership(organization_id=1,roles=[roles["doctor"]])])
        substitute = User(full_name="QA slot substitute",email="slot-substitute@example.com",password_hash="unusable",
            centers=[center],specialties=[specialty],memberships=[OrganizationMembership(organization_id=1,roles=[roles["doctor"]])])
        secretary = User(full_name="QA slot secretary",email="slot-secretary@example.com",password_hash="unusable",
            centers=[center],memberships=[OrganizationMembership(organization_id=1,roles=[roles["secretary"]])])
        db.add_all([admin,doctor,secretary,substitute,
            Patient(id=19,organization_id=1,first_name="QA",last_name="Piloto A",date_of_birth=date(1990,1,1)),
            Patient(id=20,organization_id=1,first_name="QA",last_name="Piloto B",date_of_birth=date(1991,2,2))]);db.flush()
        db.add_all([DoctorAgendaSetting(organization_id=1,doctor_id=doctor.id,center_id=center.id,
            base_mode="timed",allowed_timed=True,allowed_queue=False,default_mode="timed"),
            InsuranceCompany(organization_id=1,name="QA ARS",code="QA-SLOT"),
            CashRegister(organization_id=1,center_id=center.id,opened_by=secretary.id,opening_amount=2000),
            ClinicalSharingPolicy(organization_id=1,updated_by_user_id=admin.id),
            FeatureVisibilitySetting(organization_id=1,feature_code="clinical_safety_full",context_code="ambulatory",
                audience="doctor",visibility_mode="hidden",updated_by_user_id=admin.id,reason="QA preserved")])
        template = ClinicalFormTemplate(organization_id=1,name="QA template",code="qa-slot-preserved",document_type="physical_exam",created_by_user_id=admin.id)
        db.add(template);db.flush()
        version = ClinicalFormVersion(organization_id=1,template_id=template.id,version=1,definition={"qa":"preserved"},created_by_user_id=admin.id)
        db.add(version);db.flush()
        template.current_version_id=version.id
        db.add(ClinicalFormAssignment(organization_id=1,template_id=template.id,document_type="physical_exam",scope_key="org",created_by_user_id=admin.id))
        db.commit()
        ids = {"doctor":doctor.id,"center":center.id,"specialty":specialty.id,"substitute":substitute.id}

    app=FastAPI();app.include_router(appointments.router,prefix="/api/v1");app.include_router(auth.router,prefix="/api/v1")
    app.include_router(clinical_coverages.router,prefix="/api/v1")
    def session(request:Request):
        with Session(engine,autoflush=False) as db:
            resolve_request(db,request);yield db
    app.dependency_overrides[get_db]=session
    def client():return TestClient(app,base_url="http://localhost")
    with client() as c:
        login=c.post("/api/v1/auth/login",json={"email":"slot-admin@example.com","password":"SyntheticSlotOnly123"})
        assert login.status_code==200,login.text
        headers={"Authorization":"Bearer "+login.json()["access_token"]}
    def payload(pid,day):return {"patient_id":pid,"doctor_id":ids["doctor"],"center_id":ids["center"],
        "specialty_id":ids["specialty"],"appointment_date":day,"appointment_time":"08:00","schedule_mode":"timed"}
    def http_race(day):
        gate=Barrier(2)
        def attempt(pid):
            with client() as c:
                gate.wait(timeout=30)
                r=c.post("/api/v1/appointments",headers=headers,json=payload(pid,day))
                assert r.status_code in (201,409),r.text
                return r.status_code
        with ThreadPoolExecutor(max_workers=2) as pool:result=sorted(pool.map(attempt,[19,20]))
        assert result==[201,409],result
        with engine.connect() as c:
            assert c.scalar(text("SELECT count(*) FROM appointments WHERE appointment_date=:day AND status IN ('scheduled','confirmed')"),{"day":day})==1
        return result
    # Before official activation the already-existing center row lock + guard
    # must protect normal HTTP requests even on schema 0062.
    pre_index_race=http_race("2030-10-20")
    # A historical collision must abort migration, without choosing a survivor.
    with Session(engine) as db:
        duplicate=Appointment(organization_id=1,patient_id=20,doctor_id=ids["doctor"],center_id=ids["center"],
            specialty_id=ids["specialty"],appointment_date=date(2030,10,20),appointment_time=time(8),status="confirmed")
        db.add(duplicate);db.commit();duplicate_id=duplicate.id
    try:command.upgrade(cfg,"0063_appointment_slot_guard")
    except RuntimeError as error:assert "duplicadas" in str(error)
    else:raise AssertionError("Migration accepted historical collisions")
    with engine.begin() as c:
        assert c.scalar(text("SELECT version_num FROM alembic_version"))=="0062_feature_visibility"
        assert c.scalar(text("SELECT count(*) FROM appointments"))==2
        c.execute(text("DELETE FROM appointments WHERE id=:id"),{"id":duplicate_id})
    def fingerprints():
        with engine.connect() as c:
            return {table:hashlib.sha256(c.scalar(text(
                'SELECT coalesce(jsonb_agg(to_jsonb(t) ORDER BY to_jsonb(t)::text),\'[]\'::jsonb)::text FROM "'+table+'" t')).encode()).hexdigest()
                for table in sorted(set(inspect(c).get_table_names())-{"alembic_version"})}
    before=fingerprints()
    for target in ("0063_appointment_slot_guard","0062_feature_visibility","0063_appointment_slot_guard"):
        (command.downgrade if target.startswith("0062") else command.upgrade)(cfg,target)
        assert fingerprints()==before,"Migration rewrote existing data"
    with engine.connect() as c:
        index=c.scalar(text("SELECT indexdef FROM pg_indexes WHERE indexname='uq_appointments_active_timed_slot'"))
        assert "NULLS NOT DISTINCT" in index and "timed" in index and "confirmed" in index
    post_index_race=http_race("2030-10-21")
    # Deliberately bypass SELECT/domain locks to exercise the DB unique index
    # and the same narrow IntegrityError -> 409 mapping used by the route.
    gate=Barrier(2)
    @slot_write
    def insert_direct(pid,db):
        db.add(Appointment(organization_id=1,patient_id=pid,doctor_id=ids["doctor"],center_id=ids["center"],
            specialty_id=ids["specialty"],appointment_date=date(2030,10,22),appointment_time=time(8),status="confirmed"))
        gate.wait(timeout=30);db.commit();return 201
    def direct_attempt(pid):
        from fastapi import HTTPException
        with Session(engine) as db:
            try:return insert_direct(pid,db)
            except HTTPException as error:return error.status_code
    with ThreadPoolExecutor(max_workers=2) as pool:direct_race=sorted(pool.map(direct_attempt,[19,20]))
    assert direct_race==[201,409],direct_race
    with engine.connect() as c:
        assert c.scalar(text("SELECT count(*) FROM appointments WHERE appointment_date='2030-10-22'"))==1
    # Exercise nullable legacy center keys: NULL must not open an index bypass.
    with engine.begin() as c:
        values={"p":19,"d":ids["doctor"],"s":ids["specialty"]}
        sql=text("INSERT INTO appointments (organization_id,patient_id,doctor_id,center_id,specialty_id,appointment_date,appointment_time,schedule_mode,status,created_at,updated_at) VALUES (1,:p,:d,NULL,:s,'2030-10-23','08:00','timed','scheduled',now(),now())")
        c.execute(sql,values)
    from sqlalchemy.exc import IntegrityError
    try:
        with engine.begin() as c:c.execute(sql,{**values,"p":20})
    except IntegrityError as error:
        assert error.orig.diag.constraint_name=="uq_appointments_active_timed_slot"
    else:raise AssertionError("NULL center duplicate accepted")
    # Coverage transfer/restoration also change the doctor portion of a slot.
    with client() as c:
        r=c.post("/api/v1/auth/login",json={"email":"slot-doctor@example.com","password":"SyntheticSlotOnly123"})
        assert r.status_code==200,r.text
        doctor_headers={"Authorization":"Bearer "+r.json()["access_token"]}
        p=payload(19,"2030-10-24")
        a=c.post("/api/v1/appointments",headers=headers,json=p);assert a.status_code==201,a.text
        b=c.post("/api/v1/appointments",headers=headers,json={**p,"patient_id":20,"doctor_id":ids["substitute"]});assert b.status_code==201,b.text
        r=c.post("/api/v1/clinical-coverages",headers=doctor_headers,json={"center_id":ids["center"],
            "substitute_doctor_id":ids["substitute"],"starts_at":"2030-10-24T00:00:00","ends_at":"2030-10-25T00:00:00"})
        assert r.status_code==201,r.text
        coverage_id=r.json()["id"];base=f"/api/v1/clinical-coverages/{coverage_id}"
        transfer_url=base+f"/appointments/{a.json()['id']}/transfer"
        with engine.connect() as conn:audits=conn.scalar(text("SELECT count(*) FROM clinical_audit_logs"))
        assert c.post(transfer_url,headers=doctor_headers).status_code==409
        with engine.connect() as conn:
            assert conn.scalar(text("SELECT count(*) FROM appointment_coverage_transfers"))==0
            assert conn.scalar(text("SELECT count(*) FROM clinical_audit_logs"))==audits
        r=c.put(f"/api/v1/appointments/{b.json()['id']}",headers=headers,json={**p,"patient_id":20,"doctor_id":ids["substitute"],"status":"cancelled"});assert r.status_code==200,r.text
        r=c.post(transfer_url,headers=doctor_headers);assert r.status_code==200,r.text
        occupied=c.post("/api/v1/appointments",headers=headers,json={**p,"patient_id":20});assert occupied.status_code==201,occupied.text
        with engine.connect() as conn:audits=conn.scalar(text("SELECT count(*) FROM clinical_audit_logs"))
        r=c.post(base+"/revoke",headers=doctor_headers);assert r.status_code==409,r.text
        with engine.connect() as conn:
            assert conn.scalar(text("SELECT revoked_at FROM clinical_coverages WHERE id=:id"),{"id":coverage_id}) is None
            assert conn.scalar(text("SELECT count(*) FROM clinical_audit_logs"))==audits
        r=c.put(f"/api/v1/appointments/{occupied.json()['id']}",headers=headers,json={**p,"patient_id":20,"status":"cancelled"});assert r.status_code==200,r.text
        r=c.post(base+"/revoke",headers=doctor_headers);assert r.status_code==200,r.text
    print(json.dumps({"RESULT":"PASS","roundtrip":"0062 -> 0063 -> 0062 -> 0063",
        "preserved_tables":len(before),"http_race_0062":pre_index_race,"http_race_0063":post_index_race,
        "direct_index_race":direct_race,"null_center_guard":"PASS","historical_collision_abort":"PASS",
        "coverage_transfer_restore_conflicts_no_partial_audit":"PASS","patients":[19,20]}))


if __name__=="__main__":main()
