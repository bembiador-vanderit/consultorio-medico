"""Fictional identities only; preserve PR #32 authorization and transactions."""
import importlib.util
from datetime import date
from pathlib import Path

import pytest
import sqlalchemy as sa
from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy.exc import IntegrityError

from app.models import Country, Locality, Patient, RegionalSettings, TerritorialLevel, TerritorialUnit
from test_patient_security import patient_app, identity_payload


def payload(**values):
    return {"first_name": "Identidad", "last_name": "Ficticia", "date_of_birth": "2001-01-01", **values}


def test_legacy_and_extended_create_edit_preserve_insurance(patient_app):
    ctx = patient_app
    client = ctx["client"]
    ctx["active"]["user"] = ctx["admin"]
    for _ in range(2):
        old = client.post("/api/v1/patients", json=payload())
        assert old.status_code == 201
        assert old.json()["document_number"] is None
    data = payload(document_type="passport", document_number=" ab - 12 ", phone=" 5550001 ", home_phone=" 5550002 ",
                   blood_type="AB-", registered_sex="female", address="Calle ficticia", province="Provincia ficticia",
                   nationality="Nacionalidad ficticia", occupation="Profesión ficticia", emergency_contact_name="Contacto ficticio",
                   emergency_contact_relationship="Familiar", emergency_contact_mobile="5550003", emergency_contact_home_phone="5550004",
                   guardian_name="Tutor ficticio", guardian_relationship="Responsable", guardian_mobile="5550005", guardian_home_phone="5550006")
    result = client.post("/api/v1/patients", json=data)
    assert result.status_code == 201, result.text
    saved = result.json()
    assert saved["document_number"] == "AB12"
    assert saved["phone"] == "5550001" and saved["home_phone"] == "5550002"
    assert saved["selection_token"] and "age" not in saved
    # Old clients omit new fields; they must survive a full identity PUT.
    updated = client.put(f"/api/v1/patients/{saved['id']}", json=payload(phone="5550001"))
    assert updated.status_code == 200
    for key in data.keys() - {"document_number", "phone", "home_phone"}:
        assert updated.json()[key] == saved[key]
    assert updated.json()["document_number"] == "AB12"
    cleared = client.put(f"/api/v1/patients/{saved['id']}", json=payload(document_type=None, document_number=None, home_phone=None))
    assert cleared.status_code == 200
    assert cleared.json()["document_type"] is None and cleared.json()["home_phone"] is None
    a = ctx["a"]
    updated = client.put(f"/api/v1/patients/{a.id}", json=identity_payload(a, home_phone="5550099", blood_type="O+"))
    assert updated.status_code == 200
    ctx["db"].refresh(ctx["policy"])
    assert ctx["policy"].is_primary and ctx["policy"].is_active


@pytest.mark.parametrize("document_type", ["cedula", "passport", "other"])
def test_normalized_document_duplicates_generic_and_same_patient_edit(patient_app, document_type):
    ctx = patient_app
    client = ctx["client"]
    ctx["active"]["user"] = ctx["admin"]
    first = client.post("/api/v1/patients", json=payload(document_type=document_type, document_number=" ab-123 "))
    assert first.status_code == 201
    duplicate = client.post("/api/v1/patients", json=payload(document_type=document_type, document_number="ＡＢ 123", date_of_birth="1980-01-01"))
    assert duplicate.status_code == 409
    assert duplicate.json() == {"detail": "Ya existe un paciente con ese documento"}
    same = client.put(f"/api/v1/patients/{first.json()['id']}", json=payload(document_type=document_type, document_number="ab123"))
    assert same.status_code == 200
    a = ctx["a"]
    conflict = client.put(f"/api/v1/patients/{a.id}", json=identity_payload(a, document_type=document_type, document_number="ab123", has_insurance=False))
    assert conflict.status_code == 409
    ctx["db"].refresh(ctx["policy"])
    assert ctx["policy"].is_active


@pytest.mark.parametrize("values", [
    {"blood_type": "confirmed"}, {"registered_sex": "invalid"}, {"document_type": "invalid", "document_number": "123"},
    {"document_type": "passport"}, {"document_number": "123"}, {"document_type": "other", "document_number": "---"},
    {"document_type": "other", "document_number": "a" * 101}, {"locality_id": 999999}, {"home_phone": "1" * 31},
    {"document_type": "other", "document_number": "ab\u000012"},
])
def test_invalid_demographics_rejected(patient_app, values):
    assert patient_app["client"].post("/api/v1/patients", json=payload(**values)).status_code == 422


@pytest.mark.parametrize("blood_type", [None, "A+", "A-", "B+", "B-", "AB+", "AB-", "O+", "O-"])
def test_all_blood_types_optional(patient_app, blood_type):
    assert patient_app["client"].post("/api/v1/patients", json=payload(blood_type=blood_type)).status_code == 201


def test_locality_existing_catalog_and_inactive_preservation(patient_app):
    ctx = patient_app
    locality = Locality(name="Localidad ficticia", is_active=True)
    ctx["db"].add(locality)
    ctx["db"].commit()
    client, a = ctx["client"], ctx["a"]
    assert client.get("/api/v1/patients/localities").json()[0]["id"] == locality.id
    response = client.put(f"/api/v1/patients/{a.id}", json=identity_payload(a, locality_id=locality.id))
    assert response.status_code == 200 and response.json()["locality_name"] == locality.name
    locality.is_active = False
    ctx["db"].commit()
    assert client.get("/api/v1/patients/localities").json() == []
    assert client.put(f"/api/v1/patients/{a.id}", json=identity_payload(a, locality_id=locality.id)).status_code == 200
    assert client.post("/api/v1/patients", json=payload(locality_id=locality.id)).status_code == 422


def test_country_territory_catalog_and_patient_legacy_compatibility(patient_app):
    ctx = patient_app
    db = ctx["db"]
    country = Country(code="DO", name="República Dominicana", is_active=True)
    province = TerritorialLevel(country_code="DO", position=1, key="province", display_label="Provincia", is_required=True, is_active=True)
    db.add_all([country, province]); db.flush()
    municipality = TerritorialLevel(country_code="DO", position=2, key="municipality", display_label="Municipio", is_required=True, is_active=True)
    db.add(municipality); db.flush()
    root = TerritorialUnit(country_code="DO", territorial_level_id=province.id, name="La Romana", is_active=True)
    db.add(root); db.flush()
    child = TerritorialUnit(country_code="DO", territorial_level_id=municipality.id, parent_id=root.id, name="Villa Hermosa", is_active=True)
    db.add_all([child, RegionalSettings(id=1, default_country_code="DO")]); db.commit()
    client = ctx["client"]
    assert client.get("/api/v1/regional/countries").json() == [{"code": "DO", "name": "República Dominicana"}]
    assert [item["display_label"] for item in client.get("/api/v1/regional/countries/DO/levels").json()] == ["Provincia", "Municipio"]
    assert client.get("/api/v1/regional/territories", params={"country_code":"DO", "level":province.id}).json()[0]["name"] == "La Romana"
    assert client.get("/api/v1/regional/territories", params={"country_code":"DO", "level":municipality.id, "parent_id":root.id}).json()[0]["name"] == "Villa Hermosa"
    created = client.post("/api/v1/patients", json=payload(country_code="DO", territorial_unit_id=child.id, sector_locality="Villa Verde"))
    assert created.status_code == 201, created.text
    assert [item["name"] for item in created.json()["territorial_path"]] == ["La Romana", "Villa Hermosa"]
    assert created.json()["sector_locality"] == "Villa Verde"
    assert client.post("/api/v1/patients", json=payload(country_code="DO")).status_code == 422
    assert client.post("/api/v1/patients", json=payload(country_code="DO", territorial_unit_id=root.id)).status_code == 422
    assert client.post("/api/v1/patients", json=payload(country_code="DO", territorial_unit_id=root.id + 999)).status_code == 422
    puerto_rico = Country(code="PR", name="Puerto Rico", is_active=True)
    pr_level = TerritorialLevel(country_code="PR", position=1, key="municipality", display_label="Municipio", is_required=True, is_active=True)
    db.add_all([puerto_rico, pr_level]); db.flush()
    pr_unit = TerritorialUnit(country_code="PR", territorial_level_id=pr_level.id, name="San Juan", is_active=True)
    db.add(pr_unit); db.commit()
    ctx["active"]["user"] = ctx["admin"]
    assert client.put(f"/api/v1/patients/{created.json()['id']}", json=payload(country_code="PR", territorial_unit_id=child.id)).status_code == 422
    updated = client.put(f"/api/v1/patients/{created.json()['id']}", json=payload(country_code="PR", territorial_unit_id=pr_unit.id))
    assert updated.status_code == 200 and updated.json()["country_code"] == "PR" and updated.json()["territorial_path"][-1]["name"] == "San Juan"
    # An older client can still perform a full identity PUT without clearing territory.
    retained = client.put(f"/api/v1/patients/{created.json()['id']}", json=payload())
    assert retained.status_code == 200 and retained.json()["territorial_unit_id"] == pr_unit.id
    legacy = client.post("/api/v1/patients", json=payload(province="Legacy", date_of_birth="2002-01-01"))
    assert legacy.status_code == 201 and legacy.json()["province"] == "Legacy" and legacy.json()["territorial_path"] == []


def test_regional_settings_requires_manage_permission(patient_app):
    ctx = patient_app
    client = ctx["client"]
    assert client.get("/api/v1/regional/settings").status_code == 503
    country = Country(code="DO", name="República Dominicana", is_active=True)
    ctx["db"].add(country)
    ctx["db"].flush()
    ctx["db"].add(RegionalSettings(id=1, default_country_code="DO"))
    ctx["db"].commit()
    assert client.get("/api/v1/regional/settings").json()["default_country_code"] == "DO"
    assert client.put("/api/v1/regional/settings", json={"default_country_code": "DO"}).status_code == 403
    ctx["active"]["user"] = ctx["admin"]
    assert client.put("/api/v1/regional/settings", json={"default_country_code": "do"}).status_code == 428
    # Fixture supplies identity directly; create a real, actor/action-bound proof.
    from datetime import datetime, timedelta
    from hashlib import sha256
    from app.models.administration import ReauthenticationGrant
    ctx["db"].add(ReauthenticationGrant(id=sha256(b"fixture-proof").hexdigest(), user_id=ctx["admin"].id,
        session_version=ctx["admin"].session_version, action="PUT /api/v1/regional/settings",
        expires_at=datetime.utcnow() + timedelta(minutes=1)))
    ctx["db"].commit()
    response = client.put("/api/v1/regional/settings", json={"default_country_code": "do"}, headers={"X-Reauthentication": "fixture-proof"})
    assert response.status_code == 200 and response.json()["default_country_code"] == "DO"


@pytest.mark.parametrize("role", ["doctor", "secretary", "admin"])
def test_least_privilege_document_search_and_detail_scope(patient_app, role):
    ctx = patient_app
    for patient, number in [(ctx["a"], "VISIBLE123"), (ctx["b"], "OTHER456")]:
        patient.document_type = "other"
        patient.document_number = number
        patient.address = "Dirección privada ficticia"
        patient.blood_type = "B+"
    ctx["db"].commit()
    ctx["active"]["user"] = ctx[role]
    client = ctx["client"]
    minimal_fields = {"id", "first_name", "last_name", "date_of_birth", "phone", "email", "created_at"}
    listed = client.get("/api/v1/patients", params={"query": "visible-123"}).json()
    assert len(listed) == 1 and set(listed[0]) == minimal_fields
    assert client.get("/api/v1/patients", params={"query": "other456"}).json() == ([] if role != "admin" else [next(item for item in client.get("/api/v1/patients").json() if item["id"] == ctx["b"].id)])
    detail = client.get(f"/api/v1/patients/{ctx['a'].id}")
    assert detail.json()["document_number"] == "VISIBLE123"
    foreign = client.get(f"/api/v1/patients/{ctx['b'].id}")
    assert foreign.status_code == (200 if role == "admin" else 404)
    searched = client.get("/api/v1/patients/identity-search", params={"date_of_birth": "1991-01-01", "phone": ctx["b"].phone, "center_id": ctx["centers"][0].id, "doctor_id": ctx["doctor"].id})
    assert searched.status_code == 200
    assert set(searched.json()[0]) == {"id", "first_name", "last_name", "date_of_birth", "phone_masked", "email_masked", "selection_token"}
    if role != "admin":
        assert client.get(f"/api/v1/patients/{ctx['b'].id}").status_code == 404


def test_no_permission_rejected(patient_app):
    ctx = patient_app
    ctx["active"]["user"] = ctx["no_permission"]
    for url in ["/api/v1/patients", "/api/v1/patients/localities", f"/api/v1/patients/{ctx['a'].id}"]:
        assert ctx["client"].get(url).status_code == 403
    assert ctx["client"].post("/api/v1/patients", json=payload()).status_code == 403


def test_clinical_context_demographics_and_historical_birth_require_existing_authorization(patient_app):
    ctx = patient_app
    ctx["a"].blood_type = "AB+"
    ctx["db"].commit()
    client = ctx["client"]
    url = f"/api/v1/clinical-history/appointments/{ctx['own'].id}/context"
    context = client.get(url)
    assert context.status_code == 200
    assert context.json()["patient_blood_type"] == "AB+"
    assert "document_number" not in context.json() and "address" not in context.json()
    history = client.post(f"/api/v1/clinical-history/patients/{ctx['a'].id}", json={
        "appointment_id": ctx["own"].id, "consultation_date": "2020-12-31",
    })
    assert history.status_code == 201, history.text
    assert history.json()["patient_date_of_birth"] == "1990-01-01"
    assert history.json()["consultation_date"] == "2020-12-31"
    for role in ("admin", "secretary", "other"):
        ctx["active"]["user"] = ctx[role]
        assert client.get(url).status_code in (403, 404)
        assert client.get(f"/api/v1/clinical-history/patients/{ctx['a'].id}").status_code in (403, 404)


def test_migration_preserves_legacy_rows_and_enforces_nullable_unique_document():
    path = Path(__file__).parents[1] / "alembic/versions/0030_patient_demographics.py"
    spec = importlib.util.spec_from_file_location("demographics_migration", path)
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)
    engine = sa.create_engine("sqlite://")
    with engine.begin() as connection:
        connection.execute(sa.text("CREATE TABLE localities (id INTEGER PRIMARY KEY)"))
        connection.execute(sa.text("CREATE TABLE patients (id INTEGER PRIMARY KEY, first_name VARCHAR(100), phone VARCHAR(30))"))
        connection.execute(sa.text("INSERT INTO patients VALUES (1, 'Ficticio', '5550001'), (2, 'Legacy', NULL)"))
        with Operations.context(MigrationContext.configure(connection)):
            migration.upgrade()
        rows = connection.execute(sa.text("SELECT first_name, phone, document_number, home_phone FROM patients ORDER BY id")).all()
        assert rows == [("Ficticio", "5550001", None, None), ("Legacy", None, None, None)]
        connection.execute(sa.text("UPDATE patients SET document_type='other', document_number='TEST123' WHERE id=1"))
        with pytest.raises(IntegrityError):
            connection.execute(sa.text("UPDATE patients SET document_type='other', document_number='TEST123' WHERE id=2"))
        connection.execute(sa.text("UPDATE patients SET document_type='passport', document_number='TEST123' WHERE id=2"))
        assert connection.execute(sa.text("SELECT count(*) FROM patients")).scalar() == 2



def test_country_territory_migration_preserves_existing_patients_and_seeds_full_rd_catalog():
    migrations = Path(__file__).parents[1] / "alembic/versions"
    def load(name):
        spec = importlib.util.spec_from_file_location(name, migrations / name)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module
    demographics = load("0030_patient_demographics.py")
    territory = load("0031_country_territory.py")
    engine = sa.create_engine("sqlite://")
    with engine.begin() as connection:
        connection.execute(sa.text("CREATE TABLE localities (id INTEGER PRIMARY KEY)"))
        connection.execute(sa.text("CREATE TABLE patients (id INTEGER PRIMARY KEY, first_name VARCHAR(100), phone VARCHAR(30))"))
        connection.execute(sa.text("INSERT INTO patients VALUES (1, 'Legacy', '5550001')"))
        with Operations.context(MigrationContext.configure(connection)):
            demographics.upgrade()
            territory.upgrade()
        legacy = connection.execute(sa.text("SELECT first_name, country_code, territorial_unit_id, sector_locality FROM patients")).one()
        assert legacy == ("Legacy", None, None, None)
        assert connection.execute(sa.text("SELECT count(*) FROM countries WHERE code = 'DO'")).scalar() == 1
        assert connection.execute(sa.text("SELECT count(*) FROM territorial_levels WHERE country_code = 'DO'")).scalar() == 2
        assert connection.execute(sa.text("SELECT count(*) FROM territorial_units WHERE country_code = 'DO' AND territorial_level_id = 2")).scalar() == 158
        assert connection.execute(sa.text("SELECT count(*) FROM territorial_units WHERE name = 'Villa Hermosa' AND parent_id = 12")).scalar() == 1
