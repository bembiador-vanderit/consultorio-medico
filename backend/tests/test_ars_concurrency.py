"""PostgreSQL row locks prevent concurrent ARS over-application."""
import os
from concurrent.futures import ThreadPoolExecutor
from datetime import date, time
from threading import Barrier
import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session
from app.db import Base
from app.models import Appointment, CareCenter, Patient, Role, User
from app.models.ars import ArsClaim, ArsRemittance, ArsApplication
from app.models.insurance import AppointmentCoverage, InsuranceCompany
from app.schemas.ars import NewClaim, Transition, RemittanceInput, ApplyInput
from app.services.bootstrap import seed_identity
from app.services import ars


@pytest.fixture
def postgres():
    url = os.environ.get('ARS_POSTGRES_URL')
    if not url:
        pytest.skip('Requires disposable ars_concurrency_test PostgreSQL')
    engine = create_engine(url)
    assert engine.url.database == 'ars_concurrency_test'
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        seed_identity(db)
        role = db.scalar(select(Role).where(Role.code == 'admin'))
        actor = User(email='ars-race@example.test', full_name='Synthetic', password_hash='unused', roles=[role])
        center = CareCenter(name='Synthetic ARS', city='Test')
        company = InsuranceCompany(name='Synthetic ARS')
        patient = Patient(first_name='Synthetic', last_name='ARS', date_of_birth=date(1990,1,1))
        db.add_all([actor, center, company, patient]); db.flush()
        appointment = Appointment(patient_id=patient.id, doctor_id=actor.id, center_id=center.id,
                                  appointment_date=date(2026,10,1), appointment_time=time(10))
        db.add(appointment); db.flush()
        db.add(AppointmentCoverage(appointment_id=appointment.id,
            insurance_snapshot={'company_id': company.id, 'company_name': company.name},
            service='Synthetic', currency='DOP', base_amount=1500, covered_amount=1000,
            patient_copay=500, authorization_status='not_required', revision=1))
        db.commit()
        claim = ars.create_claim(db, actor, NewClaim(appointment_id=appointment.id, coverage_revision=1))
        for state in ('pending', 'sent', 'received'):
            ars.transition(db, actor, claim.id, Transition(state=state))
        rem = ars.create_remittance(db, actor, RemittanceInput(insurance_company_id=company.id,
            center_id=center.id, received_on=date(2026,10,5), reference='RACE-1', amount='1000'))
        ids = actor.id, claim.id, rem.id
    yield engine, ids
    Base.metadata.drop_all(engine)
    engine.dispose()


def test_two_workers_cannot_exceed_remittance_or_claim(postgres):
    engine, (actor_id, claim_id, rem_id) = postgres
    barrier = Barrier(2)

    def apply():
        with Session(engine) as db:
            barrier.wait(timeout=30)
            try:
                ars.apply(db, db.get(User, actor_id), rem_id,
                          ApplyInput(allocations=[{'claim_id': claim_id, 'amount': '700'}]))
                return 200
            except HTTPException as e:
                db.rollback()
                return e.status_code

    with ThreadPoolExecutor(max_workers=2) as pool:
        assert sorted(pool.map(lambda _: apply(), range(2))) == [200, 422]
    with Session(engine) as db:
        assert db.get(ArsClaim, claim_id).paid_amount == 700
        assert db.get(ArsRemittance, rem_id).applied_amount == 700
        assert len(db.scalars(select(ArsApplication)).all()) == 1
