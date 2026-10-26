"""Run the full existing CI contract on dedicated disposable PostgreSQL databases."""
import os
import subprocess
import psycopg
from psycopg import sql
from sqlalchemy.engine import make_url

url = make_url(os.environ['DATABASE_URL'])
assert url.database == 'atlas_prepilot', 'Only the disposable pre-pilot stack is allowed'
names = ['administration_security_test', 'patient_security_test', 'clinical_concurrency_test',
         'administration_migration_test', 'access_schedule_migration_test', 'insurance_migration_test',
         'insurance_concurrency_test', 'finance_concurrency_test', 'finance_migration_test',
         'ars_migration_test', 'ars_concurrency_test']
with psycopg.connect(url.set(drivername='postgresql', database='postgres').render_as_string(hide_password=False), autocommit=True) as db:
    for name in names:
        db.execute('SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname=%s AND pid<>pg_backend_pid()', (name,))
        db.execute(sql.SQL('DROP DATABASE IF EXISTS {}').format(sql.Identifier(name)))
        db.execute(sql.SQL('CREATE DATABASE {}').format(sql.Identifier(name)))
env = dict(os.environ, PYTHONPATH='.', DATABASE_URL='sqlite://')
env['INITIAL_ADMIN_EMAIL'] = ''
env['INITIAL_ADMIN_PASSWORD'] = ''
for key, name in [('ADMIN_SECURITY','administration_security_test'), ('PATIENT_SECURITY','patient_security_test'),
                  ('CLINICAL_CONCURRENCY','clinical_concurrency_test'), ('INSURANCE','insurance_concurrency_test'),
                  ('FINANCE','finance_concurrency_test'), ('ARS','ars_concurrency_test')]:
    env[key + '_POSTGRES_URL'] = url.set(database=name).render_as_string(hide_password=False)
def run(args, database=None):
    selected = dict(env)
    if database:
        selected['DATABASE_URL'] = url.set(database=database).render_as_string(hide_password=False)
    print('CHECK', ' '.join(args), database or '', flush=True)
    subprocess.run(args, env=selected, check=True)
for args in [['alembic','upgrade','head'], ['alembic','downgrade','0033_specialty_codes'], ['alembic','upgrade','head']]:
    run(args, 'administration_migration_test')
for label in ['access_schedule','insurance','finance','ars']:
    run(['python',f'scripts/check_{label}_migration.py'], f'{label}_migration_test')
run(['python','-m','pytest','-q','--junitxml=/tmp/prepilot-tests.xml'])
