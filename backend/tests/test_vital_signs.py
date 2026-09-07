from datetime import date, datetime

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.routes import vital_signs
from app.db import get_db
from app.models.clinical_history import ClinicalHistory
from app.models.clinical_audit import ClinicalAuditLog
from app.models.identity import Role, User


class FakeDB:
    def __init__(self, *, with_history: bool = True):
        self.history = ClinicalHistory(id=17, patient_id=3, consultation_date=date(2026, 9, 2))
        self.with_history = with_history
        self.record = None
        self.added = 0

    def get(self, model, object_id):
        if model is ClinicalHistory and object_id == 17 and self.with_history:
            return self.history
        return None

    def scalar(self, _query):
        return self.record

    def add(self, record):
        if isinstance(record, ClinicalAuditLog):
            return
        self.record = record
        self.added += 1

    def commit(self):
        pass

    def flush(self):
        pass

    def refresh(self, record):
        if record.id is None:
            record.id = 1
        now = datetime(2026, 9, 2, 10, 30)
        if record.created_at is None:
            record.created_at = now
        record.updated_at = now


def build_client(db: FakeDB) -> TestClient:
    app = FastAPI()
    app.include_router(vital_signs.router, prefix="/api/v1")
    app.dependency_overrides[vital_signs.access] = lambda: User(
        id=1, full_name="Admin", roles=[Role(code="admin", name="Administrador")]
    )
    app.dependency_overrides[get_db] = lambda: db
    return TestClient(app)


def test_vital_signs_can_be_created_and_updated_for_one_consultation():
    db = FakeDB()
    client = build_client(db)

    created = client.put(
        "/api/v1/clinical-history/17/vital-signs",
        json={
            "systolic_pressure": 120,
            "diastolic_pressure": 80,
            "heart_rate": 72,
            "temperature_c": 36.7,
            "oxygen_saturation": 98,
            "weight_kg": 70.5,
            "height_cm": 170,
        },
    )

    assert created.status_code == 200
    assert created.json()["clinical_history_id"] == 17
    assert created.json()["systolic_pressure"] == 120
    assert created.json()["temperature_c"] == 36.7
    assert db.added == 1

    updated = client.put(
        "/api/v1/clinical-history/17/vital-signs",
        json={"systolic_pressure": 118, "diastolic_pressure": 76},
    )

    assert updated.status_code == 200
    assert updated.json()["systolic_pressure"] == 118
    assert updated.json()["diastolic_pressure"] == 76
    assert updated.json()["heart_rate"] is None
    assert db.added == 1


def test_vital_signs_returns_null_when_the_consultation_has_no_measurements():
    response = build_client(FakeDB()).get("/api/v1/clinical-history/17/vital-signs")

    assert response.status_code == 200
    assert response.json() is None


def test_vital_signs_rejects_empty_or_inconsistent_measurements():
    client = build_client(FakeDB())

    empty = client.put("/api/v1/clinical-history/17/vital-signs", json={})
    invalid_pressure = client.put(
        "/api/v1/clinical-history/17/vital-signs",
        json={"systolic_pressure": 70, "diastolic_pressure": 90},
    )
    invalid_saturation = client.put(
        "/api/v1/clinical-history/17/vital-signs",
        json={"oxygen_saturation": 120},
    )

    assert empty.status_code == 422
    assert invalid_pressure.status_code == 422
    assert invalid_saturation.status_code == 422


def test_vital_signs_rejects_an_unknown_clinical_history():
    response = build_client(FakeDB(with_history=False)).get(
        "/api/v1/clinical-history/17/vital-signs"
    )

    assert response.status_code == 404
    assert response.json()["detail"] == "Registro de historia clínica no encontrado"
