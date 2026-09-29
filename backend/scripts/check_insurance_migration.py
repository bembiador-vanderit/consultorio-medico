"""Synthetic migration preservation test: run ONLY on an empty disposable DB."""
import subprocess
from sqlalchemy import create_engine, inspect, text
from app.core.config import get_settings
engine = create_engine(get_settings().database_url)
if inspect(engine).get_table_names():
    raise SystemExit('Requires an empty disposable database')
def migrate(*args):
    subprocess.run(['alembic', *args], check=True)
migrate('upgrade', '0036_access_schedules')
with engine.begin() as db:
    db.execute(text("INSERT INTO patients (id, organization_id, first_name, last_name, date_of_birth, created_at) VALUES (9901, 1, 'Synthetic', 'Migration', '1990-01-01', CURRENT_TIMESTAMP)"))
    db.execute(text("INSERT INTO insurance_companies (id, organization_id, name, code, is_active, created_at) VALUES (9901, 1, 'Synthetic ARS', 'SYNTHETIC', true, CURRENT_TIMESTAMP)"))
    db.execute(text("INSERT INTO patient_insurances (id, organization_id, patient_id, insurance_company_id, member_number, plan_name, is_primary, is_active, created_at) VALUES (9901, 1, 9901, 9901, 'SYNTHETIC', 'Legacy plan', true, true, CURRENT_TIMESTAMP)"))
    original = db.execute(text('SELECT id, organization_id, patient_id, insurance_company_id, member_number, plan_name, is_primary, is_active, created_at FROM patient_insurances')).all()
for cycle in range(2):
    migrate('upgrade', 'head')
    with engine.connect() as db:
        assert db.execute(text('SELECT id, organization_id, patient_id, insurance_company_id, member_number, plan_name, is_primary, is_active, created_at FROM patient_insurances')).all() == original
        assert db.scalar(text('SELECT count(*) FROM insurance_plans')) == 0
        assert db.scalar(text('SELECT count(*) FROM appointment_insurance_coverages')) == 0
        assert db.scalar(text('SELECT plan_id FROM patient_insurances WHERE id=9901')) is None
        assert db.scalar(text('SELECT count(*) FROM patients')) == 1
    if cycle == 0:
        migrate('downgrade', '0036_access_schedules')
print('6C5 PostgreSQL upgrade, preserved legacy affiliation, empty catalogs, rollback and re-upgrade: passed')
