"""Disposable PostgreSQL only: 0065→0066→0065→0066, historical fingerprints."""
import hashlib
import json
from datetime import date

from alembic import command
from alembic.config import Config
from sqlalchemy import inspect, text

from app.db import engine


def fingerprints():
    with engine.connect() as connection:
        result = {}
        for table in sorted(set(inspect(connection).get_table_names()) - {"alembic_version", "document_templates",
                                                                             "document_template_versions", "document_template_audits"}):
            sql = f'SELECT coalesce(jsonb_agg(to_jsonb(t) ORDER BY to_jsonb(t)::text),\'[]\'::jsonb)::text FROM "{table}" t'
            result[table] = hashlib.sha256(connection.scalar(text(sql)).encode()).hexdigest()
        return result


def main():
    assert engine.dialect.name == "postgresql"
    assert engine.url.host == "atlas-doc66-qa-pg" and engine.url.database == "atlas_doc66_qa"
    cfg = Config("alembic.ini")
    command.upgrade(cfg, "0065_ars_apply_idempotency")
    with engine.begin() as connection:
        connection.execute(text("INSERT INTO organizations (id,slug,name,timezone,is_active,created_at) VALUES (2,'doc66-qa','QA Documento','America/Santo_Domingo',true,now())"))
        connection.execute(text("INSERT INTO care_centers (id,organization_id,name,center_type,city,is_active,created_at) VALUES (1,2,'QA Centro','consultorio','QA',true,now())"))
        connection.execute(text("INSERT INTO patients (id,organization_id,first_name,last_name,date_of_birth,created_at) VALUES (1,2,'QA','Documento','1990-01-01',now())"))
    before = fingerprints()
    assert len(before) >= 90, len(before)
    command.upgrade(cfg, "0066_document_designer")
    assert fingerprints() == before, "Up migration changed historical data"
    with engine.connect() as connection:
        inspector = inspect(connection)
        assert {"document_templates", "document_template_versions", "document_template_audits"}.issubset(inspector.get_table_names())
        assert any(index["name"] == "uq_document_one_draft" and index["unique"] for index in inspector.get_indexes("document_template_versions"))
    command.downgrade(cfg, "0065_ars_apply_idempotency")
    assert fingerprints() == before, "Down migration changed historical data"
    command.upgrade(cfg, "0066_document_designer")
    assert fingerprints() == before, "Reapply changed historical data"
    with engine.connect() as connection:
        revision = connection.scalar(text("SELECT version_num FROM alembic_version"))
    print(json.dumps({"result": "PASS", "previous_tables_preserved": len(before), "final_revision": revision,
                      "new_tables": ["document_templates", "document_template_versions", "document_template_audits"]}))


if __name__ == "__main__":
    main()
