from datetime import date

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.routes import clinical_history
from app.db import get_db
from app.models.center import CareCenter
from app.models.clinical_history import ClinicalHistory
from app.models.identity import User
from app.models.patient import Patient
from app.models.requested_tests import RequestedTests
from app.services.clinical_documents import build_requested_tests_pdf


class FakeDB:
    def __init__(self, *, with_tests: bool = True):
        self.history = ClinicalHistory(
            id=17,
            patient_id=3,
            doctor_id=5,
            center_id=7,
            consultation_date=date(2026, 9, 1),
        )
        self.patient = Patient(
            id=3,
            first_name="Ana",
            last_name="Pérez",
            date_of_birth=date(1990, 1, 1),
        )
        self.doctor = User(
            id=5,
            email="doctor@example.test",
            full_name="Dra. María Gómez",
            password_hash="not-a-real-hash",
        )
        self.center = CareCenter(id=7, name="Centro Norte", city="Santiago", address="Calle Principal 1")
        self.tests = (
            [RequestedTests(id=11, clinical_history_id=17, test_name="Hemograma completo")]
            if with_tests
            else []
        )

    def get(self, model, object_id):
        records = {
            (ClinicalHistory, 17): self.history,
            (Patient, 3): self.patient,
            (User, 5): self.doctor,
            (CareCenter, 7): self.center,
        }
        return records.get((model, object_id))

    def scalars(self, _query):
        return self.tests


def build_client(db: FakeDB) -> TestClient:
    app = FastAPI()
    app.include_router(clinical_history.router, prefix="/api/v1")
    app.dependency_overrides[clinical_history.access] = lambda: None
    app.dependency_overrides[get_db] = lambda: db
    return TestClient(app)


def test_requested_tests_pdf_is_generated_from_clinical_context():
    response = build_client(FakeDB()).get("/api/v1/clinical-history/17/requested-tests/pdf")

    assert response.status_code == 200
    assert response.headers["content-type"] == "application/pdf"
    assert response.headers["content-disposition"] == 'attachment; filename="orden-estudios-17.pdf"'
    assert response.content.startswith(b"%PDF")
    assert len(response.content) > 1_000


def test_requested_tests_pdf_rejects_an_empty_order():
    response = build_client(FakeDB(with_tests=False)).get(
        "/api/v1/clinical-history/17/requested-tests/pdf"
    )

    assert response.status_code == 422
    assert response.json()["detail"] == "La consulta no tiene estudios solicitados"


def test_pdf_builder_escapes_clinical_text():
    content = build_requested_tests_pdf(
        history_id=17,
        consultation_date=date(2026, 9, 1),
        patient_name="Ana <Pérez>",
        doctor_name="Dra. María & Asociados",
        center_name="Centro <Norte>",
        center_address="Calle A & B",
        test_names=["Perfil <especial> & control"],
    )

    assert content.startswith(b"%PDF")
    assert len(content) > 1_000
