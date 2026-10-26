"""Run only on an explicitly disposable PostgreSQL; no official writes or credentials."""
import hashlib
import json
from concurrent.futures import ThreadPoolExecutor
from datetime import date, time
from decimal import Decimal
from threading import Barrier
from secrets import token_urlsafe
from uuid import uuid4
from alembic import command
from alembic.config import Config
from fastapi import FastAPI, Request
from fastapi.testclient import TestClient
from sqlalchemy import inspect, select, text, func
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from app.api.routes import ars, auth
from app.core.security import hash_password
from app.db import engine, get_db
from app.models import Appointment, CareCenter, OrganizationMembership, Patient, Role, Specialty, User
from app.models.insurance import AppointmentCoverage, InsuranceCompany
from app.models.ars import ArsApplication, ArsApplyOperation, ArsClaim, ArsRemittance, ArsClaimEvent
from app.models.administration import SecurityAudit
from app.models.finance import CashMovement, Invoice
from app.schemas.ars import ApplyInput
from app.services import ars as service
from app.services.bootstrap import seed_identity
from app.services.tenancy import resolve_request, bind_scope


def main():
    assert engine.dialect.name == 'postgresql'
    assert engine.url.host == 'atlas-ars65-qa-pg'
    assert engine.url.database == 'atlas_ars65_qa'
    cfg = Config('alembic.ini')
    password = token_urlsafe(32)  # Ephemeral QA authentication; never stored or printed.
    command.upgrade(cfg, '0064_appointment_arrivals')
    with Session(engine) as db:
        seed_identity(db)
        admin_role = db.scalar(select(Role).where(Role.code == 'admin'))
        doctor_role = db.scalar(select(Role).where(Role.code == 'doctor'))
        specialty = db.scalar(select(Specialty).where(Specialty.organization_id == 1))
        center = CareCenter(organization_id=1, name='QA ARS65', city='QA')
        actor = User(email='ars65-admin@example.com', full_name='QA ARS65', password_hash=hash_password(password),
            memberships=[OrganizationMembership(organization_id=1, roles=[admin_role])])
        provider = User(email='ars65-doctor@example.com', full_name='QA ARS65 Doctor', password_hash='unusable',
            centers=[center], specialties=[specialty], memberships=[OrganizationMembership(organization_id=1, roles=[doctor_role])])
        patient = Patient(organization_id=1, first_name='QA', last_name='ARS65', date_of_birth=date(1990,1,1))
        company = InsuranceCompany(organization_id=1, name='QA ARS65')
        db.add_all([center, actor, provider, patient, company]); db.flush()
        appointments = []
        for hour in (7, 8, 9, 10, 11):
            appt = Appointment(organization_id=1, patient_id=patient.id, doctor_id=provider.id, center_id=center.id,
                specialty_id=specialty.id, appointment_date=date(2026,10,18), appointment_time=time(hour))
            db.add(appt); db.flush()
            db.add(AppointmentCoverage(organization_id=1, appointment_id=appt.id,
                insurance_snapshot={'company_id':company.id, 'company_name':company.name}, service='QA', currency='DOP',
                base_amount=1500, covered_amount=1000, patient_copay=500, authorization_status='not_required', revision=1))
            appointments.append(appt.id)
        db.commit()
        actor_id, center_id, company_id = actor.id, center.id, company.id
        legacy_appt = appointments.pop(0)
        cov = db.scalar(select(AppointmentCoverage).where(AppointmentCoverage.appointment_id == legacy_appt))
        db.add(ArsClaim(id=100, organization_id=1, center_id=center_id, patient_id=patient.id,
            appointment_id=legacy_appt, coverage_id=cov.id, insurance_company_id=company_id,
            snapshot={'insurance':{'company_id':company_id,'company_name':'QA ARS65'}}, patient_name='QA legacy', service_date=date(2026,10,18), state='received',
            claimed_amount=1000, paid_amount=100, disputed_amount=0, created_by=actor_id))
        db.commit()

    def fingerprints():
        with engine.connect() as conn:
            result = {}
            for table in sorted(set(inspect(conn).get_table_names()) - {'alembic_version', 'ars_apply_operations'}):
                expr = "to_jsonb(t) - 'operation_id'" if table == 'ars_applications' else 'to_jsonb(t)'
                value = conn.scalar(text(f'SELECT coalesce(jsonb_agg({expr} ORDER BY ({expr})::text),\'[]\'::jsonb)::text FROM "{table}" t'))
                result[table] = hashlib.sha256(value.encode()).hexdigest()
            return result
    # Includes real legacy rows in the table being altered, without fabricating operation identities.
    with engine.begin() as conn:
        conn.execute(text("INSERT INTO ars_remittances (id,organization_id,center_id,insurance_company_id,company_name,received_on,reference,amount,applied_amount,created_by,created_at) VALUES (100,1,:center,:company,'QA',current_date,'QA LEGACY',1000,100,:actor,now())"),
            {'center':center_id, 'company':company_id, 'actor':actor_id})
        conn.execute(text("INSERT INTO ars_applications (id,organization_id,center_id,remittance_id,claim_id,amount,created_by,created_at) VALUES (100,1,:center,100,100,100,:actor,now())"),
            {'center':center_id, 'actor':actor_id})
    with Session(engine) as db:
        bind_scope(db, 'tenant', 1)
        assert service.serialize(db.get(ArsApplication,100))['amount'] == '100.00'
        try: service.apply(db, db.get(User,actor_id),100, ApplyInput(request_key=uuid4(), allocations=[{'claim_id':100,'amount':'10'}]))
        except Exception as exc: assert getattr(exc,'status_code',None) == 503
        else: raise AssertionError('Missing migration must fail closed, not apply money')
    before = fingerprints()
    for target in ('0065_ars_apply_idempotency', '0064_appointment_arrivals', '0065_ars_apply_idempotency'):
        (command.downgrade if target.startswith('0064') else command.upgrade)(cfg, target)
        assert fingerprints() == before, 'Migration altered pre-existing data'
    with engine.connect() as conn:
        constraints = inspect(conn).get_unique_constraints('ars_apply_operations')
        assert any(c['column_names'] == ['organization_id','request_key'] for c in constraints)
    app = FastAPI()
    for router in (auth.router, ars.router): app.include_router(router, prefix='/api/v1')
    def session(request: Request):
        with Session(engine, autoflush=False) as db:
            resolve_request(db, request); yield db
    app.dependency_overrides[get_db] = session
    def client(): return TestClient(app, base_url='http://localhost')
    with client() as c:
        login = c.post('/api/v1/auth/login', json={'email':'ars65-admin@example.com','password':password})
        assert login.status_code == 200, login.text
        headers = {'Authorization':'Bearer ' + login.json()['access_token']}
    def post(path, body, status=200):
        with client() as c:
            r = c.post('/api/v1/ars' + path, headers=headers, json=body)
            assert r.status_code == status, r.text
            return r.json()
    claims = []
    for appt_id in appointments:
        claim = post('/claims', {'appointment_id':appt_id, 'coverage_revision':1}, 201)
        for state in ('pending','sent','received'): post(f"/claims/{claim['id']}/transition", {'state':state})
        claims.append(claim['id'])
    def rem(reference):
        return post('/remittances', {'insurance_company_id':company_id, 'center_id':center_id, 'received_on':'2026-10-18', 'reference':reference, 'amount':'1000'}, 201)['id']
    def payload(cid, amount='250', key=None):
        return {'request_key':key or str(uuid4()), 'allocations':[{'claim_id':cid,'amount':amount}]}
    def stats(rid, cid):
        with Session(engine) as db:
            app_ids = list(db.scalars(select(ArsApplication.id).where(ArsApplication.remittance_id==rid)))
            return {'applications':db.scalar(select(func.count()).select_from(ArsApplication).where(ArsApplication.remittance_id==rid)),
                'paid':str(db.get(ArsClaim,cid).paid_amount), 'balance':str(db.get(ArsClaim,cid).balance),
                'applied':str(db.get(ArsRemittance,rid).applied_amount), 'unapplied':str(db.get(ArsRemittance,rid).unapplied),
                'events':db.scalar(select(func.count()).select_from(ArsClaimEvent).where(ArsClaimEvent.claim_id==cid, ArsClaimEvent.kind=='applied')),
                'audits':db.scalar(select(func.count()).select_from(SecurityAudit).where(SecurityAudit.action.in_([f'ars:application_created:{aid}' for aid in app_ids])))}
    rid = rem('QA LOST RESPONSE'); path = f'/remittances/{rid}/apply'; intent = payload(claims[0])
    first = post(path, intent); first_stats = stats(rid, claims[0])
    with client() as c:
        report_params = {'center_id':center_id, 'from_date':'2026-10-01','to_date':'2026-10-31'}
        summary_before = c.get('/api/v1/ars/reconciliation', headers=headers, params=report_params).json()
        receivables_before = c.get('/api/v1/ars/receivables', headers=headers, params={'center_id':center_id}).json()
    assert post(path, intent) == first and stats(rid,claims[0]) == first_stats
    with client() as c:
        assert c.get('/api/v1/ars/reconciliation', headers=headers, params=report_params).json() == summary_before
        assert c.get('/api/v1/ars/receivables', headers=headers, params={'center_id':center_id}).json() == receivables_before
    assert first_stats['paid'] == '250.00' and first_stats['applications'] == first_stats['events'] == 1
    changed = payload(claims[0], '300', intent['request_key']); post(path, changed, 409)
    changed = payload(claims[1], key=intent['request_key']); post(path, changed, 409)
    post(path, payload(claims[0])); assert stats(rid,claims[0])['paid'] == '500.00'
    assert post(path, intent) == first
    # Race identical keys, real HTTP authentication and separate PostgreSQL transactions.
    rid2 = rem('QA CONCURRENT'); intent2 = payload(claims[1]); path2 = f'/remittances/{rid2}/apply'
    gate = Barrier(2)
    def race(_): gate.wait(timeout=30); return post(path2, intent2)
    with ThreadPoolExecutor(max_workers=2) as pool: results = list(pool.map(race, range(2)))
    assert results[0] == results[1]
    concurrent = stats(rid2, claims[1])
    assert concurrent['applications'] == concurrent['events'] == 1 and concurrent['paid'] == '250.00'
    # Cross-remittance collision exercises UNIQUE fallback, not only the remittance row lock.
    left, right = rem('QA KEY LEFT'), rem('QA KEY RIGHT'); shared = str(uuid4()); gate = Barrier(2)
    def collision(index):
        gate.wait(timeout=30)
        with client() as c:
            r = c.post(f'/api/v1/ars/remittances/{[left,right][index]}/apply', headers=headers, json=payload(claims[2+index], key=shared))
            return r.status_code
    with ThreadPoolExecutor(max_workers=2) as pool: statuses = sorted(pool.map(collision, range(2)))
    assert statuses == [200,409], statuses
    # Force a failure after an application flush; all ledger/audit/intent writes must roll back.
    rid3 = rem('QA ROLLBACK'); failed_intent = payload(claims[0], '10'); baseline = stats(rid3,claims[0])
    original_event = service.event
    def fail(*args, **kwargs): raise RuntimeError('QA injected failure after ledger flush')
    service.event = fail
    try:
        with Session(engine) as db:
            bind_scope(db, 'tenant', 1)
            try: service.apply(db, db.get(User,actor_id), rid3, ApplyInput(**failed_intent))
            except RuntimeError: pass
            else: raise AssertionError('Failure injection not reached')
    finally: service.event = original_event
    assert stats(rid3,claims[0]) == baseline
    with Session(engine) as db:
        assert db.scalar(select(ArsApplyOperation).where(ArsApplyOperation.request_key == failed_intent['request_key'])) is None
    post(f'/remittances/{rid3}/apply', failed_intent)
    # Direct duplicate INSERT must be rejected by PostgreSQL independent of service code.
    with Session(engine) as db:
        saved = db.scalar(select(ArsApplyOperation).where(ArsApplyOperation.request_key == intent['request_key']))
        db.add(ArsApplyOperation(organization_id=1, request_key=saved.request_key, fingerprint=saved.fingerprint,
            remittance_id=rid, created_by=actor_id, response=saved.response))
        try: db.commit()
        except IntegrityError: db.rollback()
        else: raise AssertionError('UNIQUE constraint did not reject duplicate')
    with Session(engine) as db:
        assert db.scalar(select(func.count()).select_from(CashMovement)) == 0
        assert db.scalar(select(func.count()).select_from(Invoice)) == 0
    print(json.dumps({'result':'PASS', 'roundtrip':'0064 -> 0065 -> 0064 -> 0065', 'previous_tables_preserved':len(before),
        'lost_response':first_stats, 'same_key_concurrent':concurrent, 'cross_remittance_concurrent':statuses,
        'new_intention_paid':'500.00', 'rollback':'PASS', 'unique_constraint':'PASS', 'official_used':False}))


if __name__ == '__main__': main()
