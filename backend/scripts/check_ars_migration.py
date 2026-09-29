"""Check 6C7 additive migration and a real PostgreSQL ARS payment cycle."""
import subprocess
from datetime import date, time
from sqlalchemy import create_engine, inspect, select, text
from sqlalchemy.orm import Session
from app.core.config import get_settings

engine = create_engine(get_settings().database_url)
if engine.dialect.name != 'postgresql' or inspect(engine).get_table_names():
    raise SystemExit('Requires an empty disposable PostgreSQL database')


def migrate(*args):
    subprocess.run(['alembic', *args], check=True)


migrate('upgrade', '0038_cash_billing')
with engine.begin() as db:
    db.execute(text("INSERT INTO patients (id,organization_id,first_name,last_name,date_of_birth,created_at) VALUES (9911,1,'Synthetic','ARS','1990-01-01',CURRENT_TIMESTAMP)"))
    db.execute(text("INSERT INTO users (id,email,full_name,password_hash,is_active,created_at,session_version,is_platform_admin) VALUES (9911,'ars-migration@example.test','Synthetic ARS','unused',true,CURRENT_TIMESTAMP,0,false)"))
    db.execute(text("INSERT INTO specialties (id,organization_id,name,code,is_active,created_at) VALUES (9911,1,'Synthetic ARS','synthetic_ars',true,CURRENT_TIMESTAMP)"))
    db.execute(text("INSERT INTO appointments (id,organization_id,patient_id,doctor_id,specialty_id,appointment_date,appointment_time,status,created_at,updated_at) VALUES (9911,1,9911,9911,9911,'2026-10-01','10:00','completed',CURRENT_TIMESTAMP,CURRENT_TIMESTAMP)"))
    prior = db.execute(text('SELECT id,patient_id,status FROM appointments WHERE id=9911')).one()
for cycle in range(2):
    migrate('upgrade', 'head')
    with engine.connect() as db:
        assert db.execute(text('SELECT id,patient_id,status FROM appointments WHERE id=9911')).one() == prior
        for table in ('ars_claims', 'ars_claim_events', 'ars_remittances', 'ars_applications'):
            assert db.scalar(text(f'SELECT count(*) FROM {table}')) == 0
        assert db.scalar(text("SELECT count(*) FROM permissions WHERE code LIKE 'ars:%'")) == 7
    if cycle == 0:
        migrate('downgrade', '0038_cash_billing')

from app.models import User, Role, CareCenter, Appointment
from app.models.insurance import InsuranceCompany, AppointmentCoverage
from app.schemas.ars import NewClaim, Transition, RemittanceInput, ApplyInput, ReverseInput
from app.services.bootstrap import seed_identity
from app.services import ars

with Session(engine) as db:
    seed_identity(db)
    actor = db.get(User, 9911)
    actor.roles = [db.scalar(select(Role).where(Role.code == 'admin'))]
    center = CareCenter(name='Synthetic ARS migration', city='Test')
    company = InsuranceCompany(name='Synthetic ARS migration')
    db.add_all([center, company]); db.flush()
    appointment = db.get(Appointment, 9911)
    appointment.center_id = center.id
    coverage = AppointmentCoverage(appointment_id=appointment.id,
        insurance_snapshot={'company_id': company.id, 'company_name': company.name},
        service='Consulta sintética', currency='DOP', base_amount=1500, covered_amount=1000,
        patient_copay=500, authorization_status='not_required', revision=1)
    db.add(coverage); db.commit()
    claim = ars.create_claim(db, actor, NewClaim(appointment_id=9911, coverage_revision=1))
    assert claim.balance == 1000
    for state in ('pending', 'sent', 'received'):
        ars.transition(db, actor, claim.id, Transition(state=state))
    rem = ars.create_remittance(db, actor, RemittanceInput(insurance_company_id=company.id,
        center_id=center.id, received_on=date(2026, 10, 5), reference='SYN-ARS-MIGRATION', amount='1000'))
    ars.apply(db, actor, rem.id, ApplyInput(allocations=[{'claim_id': claim.id, 'amount': '600'}]))
    assert claim.balance == 400 and rem.unapplied == 400
    from app.models.ars import ArsApplication
    application = db.scalar(select(ArsApplication).where(ArsApplication.claim_id == claim.id))
    ars.reverse(db, actor, application.id, ReverseInput(reason='Prueba de migración'))
    assert claim.balance == 1000 and rem.unapplied == 1000
print('6C7 PostgreSQL: preservation, empty backfill, downgrade/reapply, payment and reversal passed')
