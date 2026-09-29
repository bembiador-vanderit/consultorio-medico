import importlib.util
from pathlib import Path

import pytest
from alembic.migration import MigrationContext
from alembic.operations import Operations
from pydantic import ValidationError
from sqlalchemy import create_engine, inspect, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.api.routes.clinical_catalog import create_specialty, update_specialty
from app.db import Base
from app.models import Specialty, SpecialtyTemplate, User
from app.schemas.clinical_catalog import SpecialtyCreate, SpecialtyResponse, SpecialtyUpdate


@pytest.fixture()
def specialty_db():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    db = Session(engine)
    yield db
    db.close()
    Base.metadata.drop_all(engine)
    engine.dispose()


def test_backend_generates_unique_codes_and_rename_keeps_identity(specialty_db):
    first = create_specialty(
        SpecialtyCreate(name="Medicina Física"),
        User(),
        specialty_db,
    )
    second = create_specialty(
        SpecialtyCreate(name="Medicina Fisica"),
        User(),
        specialty_db,
    )

    assert first.code == "medicina-fisica"
    assert second.code == "medicina-fisica-2"
    assert specialty_db.scalar(
        select(SpecialtyTemplate).where(SpecialtyTemplate.specialty_id == first.id)
    ) is not None

    original_code = first.code
    renamed = update_specialty(
        first.id,
        SpecialtyUpdate(name="Medicina física y rehabilitación"),
        User(),
        specialty_db,
    )
    assert renamed.name == "Medicina física y rehabilitación"
    assert renamed.code == original_code
    assert SpecialtyResponse.model_validate(renamed).code == original_code


def test_database_rejects_duplicate_specialty_code(specialty_db):
    created = create_specialty(
        SpecialtyCreate(name="Cardiología"),
        User(),
        specialty_db,
    )

    with pytest.raises(IntegrityError):
        with specialty_db.begin_nested():
            specialty_db.add(
                Specialty(name="Especialidad ficticia", code=created.code, is_active=True)
            )
            specialty_db.flush()


def test_specialty_write_contract_rejects_client_supplied_code():
    with pytest.raises(ValidationError):
        SpecialtyCreate.model_validate({"name": "Neurología", "code": "chosen-by-client"})
    with pytest.raises(ValidationError):
        SpecialtyUpdate.model_validate({"name": "Neurología clínica", "code": "changed"})


def test_0033_migration_backfills_codes_without_losing_references(tmp_path):
    migration_path = Path(__file__).parents[1] / "alembic/versions/0033_specialty_codes.py"
    spec = importlib.util.spec_from_file_location("specialty_code_migration", migration_path)
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)
    engine = create_engine(f"sqlite:///{tmp_path / 'legacy-specialties.db'}")

    with engine.begin() as connection:
        connection.execute(text(
            "CREATE TABLE specialties ("
            "id INTEGER PRIMARY KEY, name VARCHAR(120) NOT NULL UNIQUE, "
            "is_active BOOLEAN NOT NULL, created_at DATETIME)"
        ))
        connection.execute(text(
            "CREATE TABLE doctor_profiles (id INTEGER PRIMARY KEY, specialty_id INTEGER NOT NULL "
            "REFERENCES specialties(id))"
        ))
        connection.execute(text(
            "CREATE TABLE appointments (id INTEGER PRIMARY KEY, specialty_id INTEGER NOT NULL "
            "REFERENCES specialties(id))"
        ))
        connection.execute(text(
            "CREATE TABLE specialty_templates (id INTEGER PRIMARY KEY, specialty_id INTEGER NOT NULL "
            "REFERENCES specialties(id), version INTEGER NOT NULL, status VARCHAR(20) NOT NULL)"
        ))
        connection.execute(text(
            "CREATE TABLE clinical_histories (id INTEGER PRIMARY KEY, specialty_id INTEGER NOT NULL "
            "REFERENCES specialties(id))"
        ))
        connection.execute(text(
            "CREATE TABLE medical_study_specialties (medical_study_id INTEGER NOT NULL, "
            "specialty_id INTEGER NOT NULL REFERENCES specialties(id), "
            "PRIMARY KEY (medical_study_id, specialty_id))"
        ))
        connection.execute(text(
            "INSERT INTO specialties (id, name, is_active) VALUES "
            "(1, 'Cardiología', 1), (2, 'Pediatría', 1), "
            "(3, 'Medicina Física', 1), (4, 'Medicina Fisica', 1)"
        ))
        connection.execute(text("INSERT INTO doctor_profiles VALUES (10, 1)"))
        connection.execute(text("INSERT INTO appointments VALUES (20, 1)"))
        connection.execute(text("INSERT INTO specialty_templates VALUES (30, 1, 1, 'published')"))
        connection.execute(text("INSERT INTO clinical_histories VALUES (40, 1)"))
        connection.execute(text("INSERT INTO medical_study_specialties VALUES (50, 1)"))

        context = MigrationContext.configure(connection)
        with Operations.context(context):
            migration.upgrade()

        codes = connection.execute(
            text("SELECT id, code FROM specialties ORDER BY id")
        ).all()
        references = (
            connection.scalar(text("SELECT specialty_id FROM doctor_profiles WHERE id=10")),
            connection.scalar(text("SELECT specialty_id FROM appointments WHERE id=20")),
            connection.scalar(text("SELECT specialty_id FROM specialty_templates WHERE id=30")),
            connection.scalar(text("SELECT specialty_id FROM clinical_histories WHERE id=40")),
            connection.scalar(text(
                "SELECT specialty_id FROM medical_study_specialties WHERE medical_study_id=50"
            )),
        )

    assert codes == [
        (1, "cardiology"),
        (2, "pediatrics"),
        (3, "medicina-fisica"),
        (4, "medicina-fisica-2"),
    ]
    assert len({code for _, code in codes}) == len(codes)
    assert references == (1, 1, 1, 1, 1)

    columns = {column["name"]: column for column in inspect(engine).get_columns("specialties")}
    unique_constraints = {
        item["name"] for item in inspect(engine).get_unique_constraints("specialties")
    }
    assert columns["code"]["nullable"] is False
    assert "uq_specialties_code" in unique_constraints

    with pytest.raises(IntegrityError):
        with engine.begin() as connection:
            connection.execute(text(
                "INSERT INTO specialties (id, name, code, is_active) "
                "VALUES (5, 'Otra especialidad', 'cardiology', 1)"
            ))

    engine.dispose()
