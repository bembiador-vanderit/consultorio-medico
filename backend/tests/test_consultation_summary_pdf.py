from datetime import date

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.routes import clinical_history
from app.db import get_db
from app.models.center import CareCenter
from app.models.clinical_history import ClinicalHistory
from app.models.diagnosis import Diagnosis
from app.models.identity import User
from app.models.patient import Patient
from app.models.prescription import Prescription
from app.models.requested_tests import RequestedTests
from app.models.vital_signs import VitalSigns
from app.services.clinical_documents import (
    DiagnosisLine,
    PrescriptionLine,
    build_consultation_summary_pdf,
)


class FakeDB:
    def __init__(self, *, with_history: bool = True):
        self.history = ClinicalHistory(
            id=17,
            patient_id=3,
            appointment_id=19,
            doctor_id=5,
            center_id=7,
            consultation_date=date(2026, 9, 2),
            reason_for_visit="Dolor torácico",
            current_illness="Síntomas de dos días de evolución",
            allergies="Ninguna conocida",
            clinical_notes="Paciente estable",
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
        self.diagnoses = [
            Diagnosis(
                id=21,
                clinical_history_id=17,
                description="Diagnóstico de prueba",
                icd10_code="R07.9",
                is_primary=True,
            )
        ]
        self.prescriptions = [
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
        self.tests = [RequestedTests(id=31, clinical_history_id=17, test_name="Electrocardiograma")]
        self.vital_signs = VitalSigns(
            id=41,
            clinical_history_id=17,
            systolic_pressure=120,
            diastolic_pressure=80,
            heart_rate=72,
            respiratory_rate=16,
            temperature_c=36.7,
            oxygen_saturation=98,
            weight_kg=70.5,
            height_cm=170,
        )
        self.with_history = with_history

    def get(self, model, object_id):
        records = {
            (ClinicalHistory, 17): self.history if self.with_history else None,
            (Patient, 3): self.patient,
            (User, 5): self.doctor,
            (CareCenter, 7): self.center,
        }
        return records.get((model, object_id))

    def scalars(self, query):
        entity = query.column_descriptions[0].get("entity")
        return {
            Diagnosis: self.diagnoses,
            Prescription: self.prescriptions,
            RequestedTests: self.tests,
        }.get(entity, [])

    def scalar(self, query):
        entity = query.column_descriptions[0].get("entity")
        return self.vital_signs if entity is VitalSigns else None


def build_client(db: FakeDB) -> TestClient:
    app = FastAPI()
    app.include_router(clinical_history.router, prefix="/api/v1")
    app.dependency_overrides[clinical_history.access] = lambda: None
    app.dependency_overrides[get_db] = lambda: db
    return TestClient(app)


def test_consultation_summary_pdf_uses_the_complete_clinical_context():
    response = build_client(FakeDB()).get("/api/v1/clinical-history/17/summary/pdf")

    assert response.status_code == 200
    assert response.headers["content-type"] == "application/pdf"
    assert response.headers["content-disposition"] == 'attachment; filename="resumen-consulta-17.pdf"'
    assert response.content.startswith(b"%PDF")
    assert len(response.content) > 2_000


def test_consultation_summary_pdf_rejects_an_unknown_history():
    response = build_client(FakeDB(with_history=False)).get(
        "/api/v1/clinical-history/17/summary/pdf"
    )

    assert response.status_code == 404
    assert response.json()["detail"] == "Registro de historia clínica no encontrado"


def test_consultation_summary_builder_escapes_all_clinical_text():
    content = build_consultation_summary_pdf(
        history_id=17,
        appointment_id=19,
        consultation_date=date(2026, 9, 2),
        patient_name="Ana <Pérez>",
        doctor_name="Dra. María & Asociados",
        center_name="Centro <Norte>",
        center_address="Calle A & B",
        vital_signs=[("Presión <arterial>", "120/80 & estable")],
        clinical_fields=[("Motivo", "Dolor <intenso> & mareo")],
        diagnosis_lines=[DiagnosisLine(description="Diagnóstico <principal>", is_primary=True)],
        prescription_lines=[
            PrescriptionLine(
                medication="Medicamento <especial>",
                instructions="Tomar con agua & alimentos",
            )
        ],
        test_names=["Prueba <especial> & control"],
    )

    assert content.startswith(b"%PDF")
    assert len(content) > 2_000
