from datetime import date

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.routes import prescriptions
from app.db import get_db
from app.models.center import CareCenter
from app.models.clinical_history import ClinicalHistory
from app.models.identity import User
from app.models.patient import Patient
from app.models.prescription import Prescription
from app.services.clinical_documents import PrescriptionLine, build_prescription_pdf


class FakeDB:
    def __init__(self, *, with_prescriptions: bool = True):
        self.history = ClinicalHistory(
            id=17,
            patient_id=3,
            doctor_id=5,
            center_id=7,
            consultation_date=date(2026, 9, 2),
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
        self.prescriptions = (
            [
                Prescription(
                    id=11,
                    clinical_history_id=17,
                    medication="Medicamento de prueba",
                    presentation="Tabletas 500 mg",
                    dose="1 tableta",
                    route="Oral",
                    frequency="Cada 8 horas",
                    duration="5 días",
                    quantity=15,
                    instructions="Tomar después de alimentos",
                )
            ]
            if with_prescriptions
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
        return self.prescriptions


def build_client(db: FakeDB) -> TestClient:
    app = FastAPI()
    app.include_router(prescriptions.router, prefix="/api/v1")
    app.dependency_overrides[prescriptions.access] = lambda: None
    app.dependency_overrides[get_db] = lambda: db
    return TestClient(app)


def test_prescription_pdf_is_generated_from_clinical_history_id():
    response = build_client(FakeDB()).get("/api/v1/clinical-history/17/prescriptions/pdf")

    assert response.status_code == 200
    assert response.headers["content-type"] == "application/pdf"
    assert response.headers["content-disposition"] == 'attachment; filename="receta-17.pdf"'
    assert response.content.startswith(b"%PDF")
    assert len(response.content) > 1_000


def test_prescription_pdf_rejects_an_empty_prescription():
    response = build_client(FakeDB(with_prescriptions=False)).get(
        "/api/v1/clinical-history/17/prescriptions/pdf"
    )

    assert response.status_code == 422
    assert response.json()["detail"] == "La consulta no tiene medicamentos recetados"


def test_prescription_pdf_builder_escapes_clinical_text():
    content = build_prescription_pdf(
        history_id=17,
        consultation_date=date(2026, 9, 2),
        patient_name="Ana <Pérez>",
        doctor_name="Dra. María & Asociados",
        center_name="Centro <Norte>",
        center_address="Calle A & B",
        prescription_lines=[
            PrescriptionLine(
                medication="Medicamento <especial>",
                instructions="Tomar con agua & alimentos",
            )
        ],
    )

    assert content.startswith(b"%PDF")
    assert len(content) > 1_000
