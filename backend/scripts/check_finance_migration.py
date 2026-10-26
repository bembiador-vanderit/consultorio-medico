"""Preserve a synthetic 6C5 coverage; require an empty disposable PostgreSQL DB."""
import subprocess
from sqlalchemy import create_engine, inspect, select, text
from app.core.config import get_settings
engine = create_engine(get_settings().database_url)
if engine.dialect.name != 'postgresql' or inspect(engine).get_table_names():
    raise SystemExit('Requires an empty disposable PostgreSQL database')


def migrate(*args):
    subprocess.run(['alembic', *args], check=True)


migrate('upgrade', '0037_insurance_coverage')
with engine.begin() as db:
    db.execute(text("INSERT INTO patients (id,organization_id,first_name,last_name,date_of_birth,created_at) VALUES (9901,1,'Synthetic','Migration','1990-01-01',CURRENT_TIMESTAMP)"))
    db.execute(text("INSERT INTO users (id,email,full_name,password_hash,is_active,created_at,session_version,is_platform_admin) VALUES (9901,'synthetic@example.test','Synthetic','unused',true,CURRENT_TIMESTAMP,0,false)"))
    db.execute(text("INSERT INTO specialties (id,organization_id,name,code,is_active,created_at) VALUES (9901,1,'Synthetic finance','synthetic_finance',true,CURRENT_TIMESTAMP)"))
    db.execute(text("INSERT INTO appointments (id,organization_id,patient_id,doctor_id,specialty_id,appointment_date,appointment_time,status,created_at,updated_at) VALUES (9901,1,9901,9901,9901,'2030-01-01','10:00','completed',CURRENT_TIMESTAMP,CURRENT_TIMESTAMP)"))
    db.execute(text("INSERT INTO appointment_insurance_coverages (id,organization_id,appointment_id,insurance_snapshot,service,currency,base_amount,covered_amount,patient_copay,authorization_status,revision,updated_at) VALUES (9901,1,9901,'{}','Synthetic','DOP',100,0,100,'not_required',1,CURRENT_TIMESTAMP)"))
    original = db.execute(text('SELECT * FROM appointment_insurance_coverages')).all()
for cycle in range(2):
    migrate('upgrade', 'head')
    with engine.connect() as db:
        assert db.execute(text('SELECT * FROM appointment_insurance_coverages')).all() == original
        for table in ('cash_registers','financial_invoices','cash_movements'):
            assert db.scalar(text(f'SELECT count(*) FROM {table}')) == 0
        assert db.scalar(text("SELECT count(*) FROM permissions WHERE code IN ('finance:read','finance:collect','finance:manage')")) == 3
        assert db.scalar(text("SELECT status FROM appointments WHERE id=9901")) == 'completed'
    if cycle == 0:
        migrate('downgrade', '0037_insurance_coverage')
print('6C6 PostgreSQL: previous coverage preserved, no seeded payments, downgrade and re-upgrade passed')

# Exercise the migrated schema itself, not only ORM create_all fixtures.
from uuid import uuid4
from sqlalchemy.orm import Session
from app.models import User, Role, CareCenter, Appointment
from app.schemas.finance import OpenRegister, CloseRegister, NewInvoice, Payment
from app.services.bootstrap import seed_identity
from app.services import finance
with Session(engine) as db:
    seed_identity(db)
    actor = db.get(User, 9901)
    actor.roles = [db.scalar(select(Role).where(Role.code == 'admin'))]
    center = CareCenter(name='Synthetic migration cash', city='Test')
    db.add(center); db.flush()
    db.get(Appointment, 9901).center_id = center.id
    db.commit()
    register = finance.open_register(db, actor, OpenRegister(center_id=center.id, opening_amount='100'))
    invoice = finance.create_invoice(db, actor, NewInvoice(request_key=uuid4(), center_id=center.id, patient_id=9901,
        appointment_id=9901, coverage_revision=1, concept='Synthetic', base_amount='100',
        payment=Payment(request_key=uuid4(), register_id=register.id, parts=[{'method':'cash','amount':'40'}, {'method':'card','amount':'10'}])))
    assert invoice.balance == 50 and invoice.paid_amount == 50
    result = finance.close_register(db, actor, register.id, CloseRegister(counted_cash='140'))
    assert result.difference == 0
print('6C6 actual migrated schema: mixed partial payment and cash close passed')
