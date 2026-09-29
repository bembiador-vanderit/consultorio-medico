"""Insurance locking guarantees on an explicitly disposable PostgreSQL DB."""
import os
from concurrent.futures import ThreadPoolExecutor
from datetime import date, time
from threading import Barrier
import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session
from app.db import Base
from app.models import Role, User, Patient, Appointment
from app.models.insurance import InsuranceCompany, PatientInsurance, AppointmentCoverage
from app.schemas.insurance import PatientInsuranceCreate, CoverageWrite
from app.services.bootstrap import seed_identity
from app.services.insurance import save_insurance, save_coverage

@pytest.fixture
def postgres():
    url=os.environ.get('INSURANCE_POSTGRES_URL')
    if not url:
        pytest.skip('Requires disposable insurance_concurrency_test PostgreSQL')
    engine=create_engine(url)
    assert engine.url.database=='insurance_concurrency_test'
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        seed_identity(db)
        role=db.scalar(select(Role).where(Role.code=='admin'))
        user=User(email='insurance@example.test',full_name='Synthetic admin',password_hash='unused',roles=[role])
        patient=Patient(first_name='Synthetic',last_name='Patient',date_of_birth=date(1990,1,1))
        company=InsuranceCompany(name='Synthetic ARS')
        db.add_all([user,patient,company]); db.flush()
        appt=Appointment(patient_id=patient.id,doctor_id=user.id,appointment_date=date(2030,1,1),appointment_time=time(10))
        db.add(appt); db.commit()
        ids=(user.id,patient.id,company.id,appt.id)
    yield engine,ids
    Base.metadata.drop_all(engine); engine.dispose()


def test_concurrent_primary_affiliations_leave_only_one_primary(postgres):
    engine,(uid,pid,cid,_)=postgres
    barrier=Barrier(2)
    def add(index):
        with Session(engine) as db:
            actor=db.get(User,uid); barrier.wait(timeout=30)
            return save_insurance(db,actor,pid,PatientInsuranceCreate(insurance_company_id=cid,member_number=f'SYNTHETIC-{index}')).id
    with ThreadPoolExecutor(max_workers=2) as pool:
        ids=list(pool.map(add,[1,2]))
    assert len(set(ids))==2
    with Session(engine) as db:
        assert len(db.scalars(select(PatientInsurance).where(PatientInsurance.is_primary.is_(True))).all())==1


def test_concurrent_coverage_creation_and_revision_replay(postgres):
    engine,(uid,_,_,aid)=postgres
    def race(revision):
        barrier=Barrier(2)
        def save(_):
            with Session(engine) as db:
                actor=db.get(User,uid); barrier.wait(timeout=30)
                try:
                    save_coverage(db,actor,aid,CoverageWrite(service='Synthetic',base_amount='100',covered_amount='0',patient_copay='100',revision=revision,authorization_status='not_required'))
                    return 200
                except HTTPException as e:
                    db.rollback(); return e.status_code
        with ThreadPoolExecutor(max_workers=2) as pool:
            return list(pool.map(save,[1,2]))
    assert sorted(race(0))==[200,409]
    assert sorted(race(1))==[200,409]
    with Session(engine) as db:
        rows=db.scalars(select(AppointmentCoverage)).all()
        assert len(rows)==1 and rows[0].revision==2
