from datetime import datetime

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.routes import prescriptions
from app.db import get_db
from app.models.clinical_history import ClinicalHistory
from app.models.prescription import Prescription


class FakeDB:
    def __init__(self):
        self.histories = {10: object(), 20: object()}
        self.prescriptions: dict[int, Prescription] = {}
        self.next_id = 1

    def get(self, model, object_id):
        if model is ClinicalHistory:
            return self.histories.get(object_id)
        if model is Prescription:
            return self.prescriptions.get(object_id)
        return None

    def scalars(self, _query):
        return sorted(self.prescriptions.values(), key=lambda item: item.id)

    def add(self, prescription):
        prescription.id = self.next_id
        prescription.created_at = datetime(2026, 9, 1, 9, 0)
        prescription.updated_at = prescription.created_at
        self.prescriptions[prescription.id] = prescription
        self.next_id += 1

    def commit(self):
        return None

    def refresh(self, prescription):
        prescription.updated_at = datetime(2026, 9, 1, 9, 5)

    def delete(self, prescription):
        del self.prescriptions[prescription.id]


def build_client(db: FakeDB) -> TestClient:
    app = FastAPI()
    app.include_router(prescriptions.router, prefix="/api/v1")
    app.dependency_overrides[prescriptions.access] = lambda: None
    app.dependency_overrides[get_db] = lambda: db
    return TestClient(app)


def test_prescription_crud_uses_clinical_history_id():
    db = FakeDB()
    client = build_client(db)
    base_url = "/api/v1/clinical-history/10/prescriptions"

    create_response = client.post(
        base_url,
        json={"medication": "Medicamento de prueba", "dose": "1 tableta", "quantity": 10},
    )
    assert create_response.status_code == 201
    created = create_response.json()
    assert created["clinical_history_id"] == 10
    assert created["medication"] == "Medicamento de prueba"

    list_response = client.get(base_url)
    assert list_response.status_code == 200
    assert [item["id"] for item in list_response.json()] == [created["id"]]

    update_response = client.put(
        f"{base_url}/{created['id']}",
        json={"medication": "Medicamento actualizado", "route": "Oral", "quantity": 5},
    )
    assert update_response.status_code == 200
    assert update_response.json()["medication"] == "Medicamento actualizado"
    assert update_response.json()["clinical_history_id"] == 10

    delete_response = client.delete(f"{base_url}/{created['id']}")
    assert delete_response.status_code == 204
    assert db.prescriptions == {}


def test_prescription_cannot_be_changed_from_another_history():
    db = FakeDB()
    client = build_client(db)
    created = client.post(
        "/api/v1/clinical-history/10/prescriptions",
        json={"medication": "Medicamento de prueba"},
    ).json()

    update_response = client.put(
        f"/api/v1/clinical-history/20/prescriptions/{created['id']}",
        json={"medication": "Cambio no permitido"},
    )
    delete_response = client.delete(
        f"/api/v1/clinical-history/20/prescriptions/{created['id']}"
    )

    assert update_response.status_code == 404
    assert delete_response.status_code == 404
    assert db.prescriptions[created["id"]].clinical_history_id == 10


def test_main_app_registers_prescription_routes():
    from app.main import app

    paths = {route.path for route in app.routes}
    assert "/api/v1/clinical-history/{history_id}/prescriptions" in paths
    assert "/api/v1/clinical-history/{history_id}/prescriptions/{prescription_id}" in paths
