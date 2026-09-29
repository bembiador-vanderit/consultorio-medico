"""Run only against an EMPTY disposable PostgreSQL database, never a pilot database."""
import subprocess

from sqlalchemy import create_engine, inspect, text
from app.core.config import get_settings

engine = create_engine(get_settings().database_url)
if inspect(engine).get_table_names():
    raise SystemExit("This check requires an empty disposable database")


def migrate(*args):
    subprocess.run(["alembic", *args], check=True)


migrate("upgrade", "0035_organizations")
with engine.begin() as db:
    db.execute(text("INSERT INTO organizations (id, slug, name, is_active, created_at) VALUES (2, 'migration-test', 'Synthetic tenant', true, CURRENT_TIMESTAMP)"))
    db.execute(text("INSERT INTO users (id, email, full_name, password_hash, is_active, denied_permissions, created_at) VALUES (999, 'migration@example.test', 'Synthetic user', 'not-a-usable-password-hash', true, '[]', CURRENT_TIMESTAMP)"))
    db.execute(text("INSERT INTO organization_memberships (user_id, organization_id, state, denied_permissions, created_at) VALUES (999, 1, 'active', '[]', CURRENT_TIMESTAMP), (999, 2, 'active', '[]', CURRENT_TIMESTAMP)"))
    original_version = db.scalar(text("SELECT session_version FROM users WHERE id=999"))
migrate("upgrade", "head")
with engine.connect() as db:
    assert dict(db.execute(text("SELECT slug, timezone FROM organizations")).all()) == {"pilot": "America/Santo_Domingo", "migration-test": "UTC"}
    assert db.execute(text("SELECT restrict_outside_schedule, weekly_schedule, schedule_version FROM organization_memberships")).all() == [(False, [], 0), (False, [], 0)]
    assert db.scalar(text("SELECT session_version FROM users WHERE id=999")) == original_version
migrate("downgrade", "0035_organizations")
migrate("upgrade", "head")
with engine.connect() as db:
    assert db.scalar(text("SELECT count(*) FROM organization_memberships")) == 2
    assert db.scalar(text("SELECT count(*) FROM organization_memberships WHERE restrict_outside_schedule")) == 0
print("6C4C PostgreSQL backfill, preserved sessions, downgrade and re-upgrade: passed")
