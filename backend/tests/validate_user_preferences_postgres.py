"""Disposable PostgreSQL only: validate 0069→0070→0069→0070."""
import hashlib
import json

from alembic import command
from alembic.config import Config
from sqlalchemy import inspect, select, text
from sqlalchemy.orm import Session

from app.db import engine
from app.models import User, UserPreference


def historical_fingerprints():
    with engine.connect() as connection:
        result = {}
        for table in sorted(set(inspect(connection).get_table_names()) - {"alembic_version", "user_preferences"}):
            content = connection.scalar(text(
                f'SELECT coalesce(jsonb_agg(to_jsonb(t) ORDER BY to_jsonb(t)::text),\'[]\'::jsonb)::text FROM "{table}" t'))
            result[table] = hashlib.sha256(content.encode()).hexdigest()
        return result


def main():
    assert engine.dialect.name == "postgresql"
    assert engine.url.host == "atlas-userprefs70-qa-pg" and engine.url.database == "atlas_pref70_qa"
    cfg = Config("alembic.ini")
    command.upgrade(cfg, "0069_print_job_contract")
    with Session(engine) as db:
        db.add(User(email="prefs70-qa@example.test", full_name="QA Preferences", password_hash="synthetic-not-login"))
        db.commit()
    before = historical_fingerprints()
    command.upgrade(cfg, "0070_user_preferences")
    assert historical_fingerprints() == before
    with engine.connect() as connection:
        inspector = inspect(connection)
        assert "user_preferences" in inspector.get_table_names()
        assert any(item["name"] == "uq_user_preferences_user_id" for item in inspector.get_unique_constraints("user_preferences"))
        assert any(item["referred_table"] == "users" and item["options"].get("ondelete") == "CASCADE"
                   for item in inspector.get_foreign_keys("user_preferences"))
        assert any(item["name"] == "ix_user_preferences_user_id" for item in inspector.get_indexes("user_preferences"))
        assert connection.scalar(text("SELECT count(*) FROM user_preferences")) == 0
    with Session(engine) as db:
        user = db.scalar(select(User).where(User.email == "prefs70-qa@example.test"))
        db.add(UserPreference(user_id=user.id, gestion_menu_order=["patients"],
                              dashboard_widget_order=["agenda"], accent_theme="indigo"))
        db.commit()
        assert db.scalar(select(UserPreference).where(UserPreference.user_id == user.id)).accent_theme == "indigo"
        db.query(UserPreference).delete()
        db.commit()
    command.downgrade(cfg, "0069_print_job_contract")
    assert historical_fingerprints() == before
    command.upgrade(cfg, "0070_user_preferences")
    assert historical_fingerprints() == before
    with engine.connect() as connection:
        assert connection.scalar(text("SELECT version_num FROM alembic_version")) == "0070_user_preferences"
        assert connection.scalar(text("SELECT count(*) FROM user_preferences")) == 0
    print(json.dumps({"result": "PASS", "historical_tables_preserved": len(before),
                      "roundtrip": "0069->0070->0069->0070", "new_table_empty": True}))


if __name__ == "__main__":
    main()
