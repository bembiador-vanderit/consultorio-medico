"""Synthetic-only validation of the two independent clinical documents."""
from datetime import date

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.deps import current_user
from app.api.routes import clinical_patient_documents as routes
from app.db import get_db
from app.models import Appointment, CareCenter, ClinicalHistory, Patient, Permission, QueueTicket, Role, SecretaryDocumentGrant, User
from app.models.clinical_audit import ClinicalAuditLog
from app.models.clinical_patient_document import PhysicalExamination, PreoperativeEvaluation
from app.schemas.clinical_patient_document import DocumentCreate, DocumentLink, DocumentTransition, DocumentUpdate
from app.services import clinical_patient_documents as documents
from app.services.clinical_patient_document_fields import PHYSICAL_KEYS, PREOPERATIVE_KEYS
from app.services.clinical_patient_document_pdf import build_document_pdf
from app.services.patient_scope import doctor_has_patient_relationship, issue_patient_selection_token, patient_in_identity_scope
from test_queue_arrivals import queue_db, scoped


@pytest.fixture
def document_db(queue_db):
    engine, ids, day = queue_db
    with Session(engine) as db:
        role_codes = {
            "admin": ("patients:access", "clinical_documents:create", "clinical_documents:view", "clinical_documents:prepare"),
            "secretary": ("patients:access", "clinical_documents:create", "clinical_documents:view", "clinical_documents:prepare"),
            "doctor": ("patients:access", "clinical:access", "clinical_documents:create", "clinical_documents:view",
                       "clinical_documents:prepare", "clinical_documents:edit_clinical", "clinical_documents:sign"),
        }
        all_codes = {name for codes in role_codes.values() for name in codes}
        permission_by_code = {name: Permission(code=name, description=name) for name in all_codes}
        db.add_all(permission_by_code.values())
        for code, permissions in role_codes.items():
            role = db.scalar(select(Role).where(Role.code == code))
            role.permissions = [permission_by_code[name] for name in permissions]
        # 0056 no longer grants document initiation to all secretaries. These
        # legacy-flow tests explicitly opt this synthetic secretary in.
        db.add(SecretaryDocumentGrant(organization_id=1, user_id=ids["secretary"],
                                      start_preoperative=True, start_physical_exam=True,
                                      prepare_administrative=True, updated_by_user_id=ids["admin"]))
        db.commit()
    return engine, ids, day


def appointment_payload(db, ids, appointment_id=None, **overrides):
    appointment = db.get(Appointment, appointment_id or ids["appointments"][0])
    return DocumentCreate(patient_id=appointment.patient_id, doctor_id=appointment.doctor_id,
                          center_id=appointment.center_id, appointment_id=appointment.id, **overrides)


def rejects(code, callback):
    with pytest.raises(HTTPException) as error:
        callback()
    assert error.value.status_code == code


def test_draft_identity_distinguishes_consultations_and_explicitly_links_standalone(document_db):
    engine, ids, day = document_db
    with scoped(engine) as db:
        doctor = db.get(User, ids["doctor"])
        secretary = db.get(User, ids["secretary"])
        first_appointment = db.get(Appointment, ids["appointments"][0])
        second_appointment = db.get(Appointment, ids["tomorrow"])
        second_appointment.appointment_date = day
        db.commit()
        standalone = DocumentCreate(patient_id=first_appointment.patient_id, doctor_id=doctor.id,
                                    center_id=ids["center"], patient_selection_token="qa-proof")
        # Synthetic secretary starts a patient-linked draft without a consultation.
        from unittest.mock import patch
        with patch("app.services.clinical_patient_documents.require_patient_selection"):
            prepared, created = documents.create(db, secretary, "preoperative", standalone)
        assert created and prepared.appointment_id is None
        with patch("app.services.clinical_patient_documents.require_patient_selection"):
            same, created = documents.create(db, secretary, "preoperative", standalone)
        assert not created and same.id == prepared.id

        context = DocumentCreate(patient_id=first_appointment.patient_id, appointment_id=first_appointment.id)
        first, created = documents.create(db, doctor, "preoperative", context)
        assert created and first.id != prepared.id and first.doctor_id == doctor.id and first.center_id == ids["center"]
        same, created = documents.create(db, doctor, "preoperative", context)
        assert not created and same.id == first.id
        other, created = documents.create(db, doctor, "preoperative", context.model_copy(update={"appointment_id": second_appointment.id}))
        assert created and other.id not in {prepared.id, first.id}
        assert other.document_date == first.document_date
        rejects(409, lambda: documents.link_context(db, doctor, "preoperative", prepared.id,
                                                     DocumentLink(expected_revision=0, appointment_id=first_appointment.id)))
        exam, created = documents.create(db, doctor, "physical_exam", context)
        assert created and exam.appointment_id == first_appointment.id
        prepared.status = "signed"
        db.commit()
        with patch("app.services.clinical_patient_documents.require_patient_selection"):
            fresh, created = documents.create(db, secretary, "preoperative", standalone)
        assert created and fresh.id != prepared.id
        rejects(404, lambda: documents.create(db, doctor, "physical_exam",
                                               context.model_copy(update={"doctor_id": ids["secretary"]})))


def test_prepared_draft_links_only_on_explicit_doctor_action(document_db):
    engine, ids, _ = document_db
    with scoped(engine) as db:
        doctor, secretary = (db.get(User, ids[key]) for key in ("doctor", "secretary"))
        appointment = db.get(Appointment, ids["appointments"][0])
        from unittest.mock import patch
        with patch("app.services.clinical_patient_documents.require_patient_selection"):
            row, _ = documents.create(db, secretary, "physical_exam", DocumentCreate(
                patient_id=appointment.patient_id, center_id=appointment.center_id,
                doctor_id=appointment.doctor_id, patient_selection_token="qa-proof"))
        rejects(403, lambda: documents.link_context(db, secretary, "physical_exam", row.id,
                                                     DocumentLink(expected_revision=0, appointment_id=appointment.id)))
        linked = documents.link_context(db, doctor, "physical_exam", row.id,
                                        DocumentLink(expected_revision=0, appointment_id=appointment.id))
        assert linked["id"] == row.id and linked["appointment_id"] == appointment.id and linked["revision"] == 1
        same, created = documents.create(db, doctor, "physical_exam", DocumentCreate(
            patient_id=appointment.patient_id, appointment_id=appointment.id))
        assert not created and same.id == row.id
        audit = db.scalar(select(ClinicalAuditLog).where(ClinicalAuditLog.resource_type == "physical_exam",
                                                       ClinicalAuditLog.resource_id == row.id,
                                                       ClinicalAuditLog.action == "clinical_document:linked_to_consultation"))
        assert audit and audit.user_id == doctor.id
    with scoped(engine, 2) as db:
        admin = db.get(User, ids["admin"])
        rejects(404, lambda: documents.link_context(db, admin, "physical_exam", row.id,
                                                     DocumentLink(expected_revision=1, appointment_id=appointment.id)))


def test_doctor_without_context_needs_center_only_when_multi_center(document_db):
    engine, ids, _ = document_db
    with scoped(engine) as db:
        doctor = db.get(User, ids["doctor"])
        appointment = db.get(Appointment, ids["appointments"][0])
        extra = CareCenter(organization_id=1, name="Segundo centro QA", city="Prueba")
        doctor.centers.append(extra)
        db.commit()
        rejects(422, lambda: documents.create(db, doctor, "physical_exam",
                                               DocumentCreate(patient_id=appointment.patient_id)))
        row, created = documents.create(db, doctor, "physical_exam",
                                        DocumentCreate(patient_id=appointment.patient_id, center_id=appointment.center_id))
        assert created and row.doctor_id == doctor.id and row.center_id == appointment.center_id


def test_history_without_appointment_is_its_own_open_context(document_db):
    engine, ids, day = document_db
    with scoped(engine) as db:
        doctor = db.get(User, ids["doctor"])
        appointment = db.get(Appointment, ids["appointments"][0])
        histories = [ClinicalHistory(organization_id=1, patient_id=appointment.patient_id,
                                     doctor_id=doctor.id, center_id=ids["center"],
                                     consultation_date=day, status="in_progress") for _ in range(2)]
        db.add_all(histories)
        db.commit()
        first, created = documents.create(db, doctor, "preoperative", DocumentCreate(
            patient_id=appointment.patient_id, clinical_history_id=histories[0].id))
        assert created and first.appointment_id is None
        same, created = documents.create(db, doctor, "preoperative", DocumentCreate(
            patient_id=appointment.patient_id, clinical_history_id=histories[0].id))
        assert not created and same.id == first.id
        second, created = documents.create(db, doctor, "preoperative", DocumentCreate(
            patient_id=appointment.patient_id, clinical_history_id=histories[1].id))
        assert created and second.id != first.id


def test_independent_documents_lifecycle_audit_and_unchanged_operational_data(document_db):
    engine, ids, _ = document_db
    with scoped(engine) as db:
        doctor, secretary, admin = (db.get(User, ids[key]) for key in ("doctor", "secretary", "admin"))
        appointment = db.get(Appointment, ids["appointments"][0])
        original = (appointment.status, appointment.appointment_time)
        patient_count = db.scalar(select(func.count(Patient.id)))
        appointment_count = db.scalar(select(func.count(Appointment.id)))
        queue_count = db.scalar(select(func.count(QueueTicket.id)))
        history_count = db.scalar(select(func.count(ClinicalHistory.id)))

        preop, created = documents.create(db, secretary, "preoperative", appointment_payload(db, ids))
        assert created and preop.status == "draft" and preop.clinical_history_id is None
        same, created = documents.create(db, doctor, "preoperative", appointment_payload(db, ids))
        assert not created and same.id == preop.id
        exam, created = documents.create(db, doctor, "physical_exam", appointment_payload(db, ids))
        assert created and exam.id == 1 and exam.patient_id == preop.patient_id
        assert documents.get(db, doctor, "preoperative", preop.id)["patient_profile"]["patient_name"].startswith("Paciente")
        assert documents.get(db, secretary, "preoperative", preop.id)["values"] == {}

        admin_value = documents.update(db, secretary, "preoperative", preop.id, DocumentUpdate(expected_revision=0, values={"procedimiento": "Procedimiento sintético"}))
        assert admin_value["revision"] == 1
        assert admin_value["values"] == {"procedimiento": "Procedimiento sintético"}
        rejects(403, lambda: documents.update(db, secretary, "preoperative", preop.id, DocumentUpdate(expected_revision=1, values={"hepatitis": "Sí"})))
        rejects(403, lambda: documents.transition(db, secretary, "preoperative", preop.id, "complete", DocumentTransition(expected_revision=1)))
        rejects(403, lambda: documents.transition(db, secretary, "preoperative", preop.id, "sign", DocumentTransition(expected_revision=1)))
        submitted = documents.transition(db, secretary, "preoperative", preop.id, "submit", DocumentTransition(expected_revision=1))
        assert submitted["status"] == "pending_evaluation"
        updated = documents.update(db, doctor, "preoperative", preop.id, DocumentUpdate(expected_revision=2, values={
            "hepatitis": "No", "enfermedades_otros": "Ninguna", "glicemia": "Dato sintético",
            "creatinina": "Dato sintético", "pcb": "Anotación médica", "ivy": "Anotación médica",
        }))
        assert set(updated["values"]) >= {"procedimiento", "hepatitis", "glicemia", "creatinina", "pcb", "ivy"}
        assert "pcb" in PREOPERATIVE_KEYS and "pcb" in PHYSICAL_KEYS
        rejects(409, lambda: documents.update(db, doctor, "preoperative", preop.id, DocumentUpdate(expected_revision=2, values={"ta": "120/80"})))
        completed = documents.transition(db, doctor, "preoperative", preop.id, "complete", DocumentTransition(expected_revision=3))
        rejects(403, lambda: documents.transition(db, admin, "preoperative", preop.id, "sign",
                                                  DocumentTransition(expected_revision=4)))
        signed = documents.transition(db, doctor, "preoperative", preop.id, "sign", DocumentTransition(expected_revision=4))
        assert completed["status"] == "completed" and signed["status"] == "signed"
        assert signed["signed_by_user_id"] == doctor.id and signed["signed_at"]
        assert signed["patient_profile"] == completed["patient_profile"]
        assert build_document_pdf(signed).startswith(b"%PDF")
        rejects(409, lambda: documents.update(db, doctor, "preoperative", preop.id, DocumentUpdate(expected_revision=5, values={"ta": "changed"})))
        blocked = db.scalar(select(ClinicalAuditLog).where(
            ClinicalAuditLog.resource_type == "preoperative", ClinicalAuditLog.resource_id == preop.id,
            ClinicalAuditLog.action == "clinical_document:update_blocked"))
        assert blocked and blocked.user_id == doctor.id and blocked.outcome == "conflict"
        assert blocked.context == {"status": "signed", "reason": "document_locked"}

        exam_update = documents.update(db, doctor, "physical_exam", exam.id, DocumentUpdate(expected_revision=0, values={"ta": "120/80"}))
        assert exam_update["values"] == {"ta": "120/80"}
        assert documents.get(db, doctor, "preoperative", preop.id)["values"] != exam_update["values"]
        assert len(documents.list_for_patient(db, doctor, appointment.patient_id)) == 2
        actions = list(db.scalars(select(ClinicalAuditLog.action).where(ClinicalAuditLog.resource_type == "preoperative")))
        assert actions.count("clinical_document:created") == 1
        assert "clinical_document:updated" in actions and "clinical_document:sign" in actions
        db.refresh(appointment)
        assert (appointment.status, appointment.appointment_time) == original
        assert db.scalar(select(func.count(Patient.id))) == patient_count
        assert db.scalar(select(func.count(Appointment.id))) == appointment_count
        assert db.scalar(select(func.count(QueueTicket.id))) == queue_count
        assert db.scalar(select(func.count(ClinicalHistory.id))) == history_count


def test_consultation_linkage_scope_permissions_and_tenant_isolation(document_db):
    engine, ids, day = document_db
    with scoped(engine) as db:
        doctor, secretary = db.get(User, ids["doctor"]), db.get(User, ids["secretary"])
        appointment = db.get(Appointment, ids["appointments"][0])
        history = ClinicalHistory(patient_id=appointment.patient_id, doctor_id=doctor.id, center_id=ids["center"],
                                  appointment_id=appointment.id, consultation_date=day)
        db.add(history); db.commit()
        row, created = documents.create(db, doctor, "preoperative", appointment_payload(db, ids, clinical_history_id=history.id))
        assert created and row.clinical_history_id == history.id
        rejects(403, lambda: documents.create(db, secretary, "physical_exam", appointment_payload(db, ids, clinical_history_id=history.id)))
        history.status = "completed"
        db.commit()
        rejects(409, lambda: documents.create(db, doctor, "physical_exam", appointment_payload(db, ids, clinical_history_id=history.id)))
        rejects(404, lambda: documents.create(db, doctor, "physical_exam", DocumentCreate(
            patient_id=999999, doctor_id=doctor.id, center_id=ids["center"], appointment_id=appointment.id)))
        rejects(404, lambda: documents.create(db, doctor, "physical_exam", DocumentCreate(patient_id=appointment.patient_id,
                doctor_id=doctor.id, center_id=ids["foreign_center"])))
        secretary.denied_permissions = ["clinical_documents:create"]
        db.commit()
        rejects(403, lambda: documents.create(db, secretary, "physical_exam", appointment_payload(db, ids)))
        row_id, patient_id = row.id, appointment.patient_id
    with scoped(engine, 2) as db:
        admin = db.get(User, ids["admin"])
        rejects(404, lambda: documents.get(db, admin, "preoperative", row_id))
        rejects(404, lambda: documents.list_for_patient(db, admin, patient_id))


def test_document_without_consultation_is_patient_linked_and_signed_snapshot_is_immutable(document_db):
    engine, ids, _ = document_db
    with scoped(engine) as db:
        admin, doctor = db.get(User, ids["admin"]), db.get(User, ids["doctor"])
        patient = Patient(first_name="Sin cita", last_name="QA", date_of_birth=date(1988, 6, 1), phone="809-111-1111")
        db.add(patient); db.commit()
        row, _ = documents.create(db, admin, "physical_exam", DocumentCreate(
            patient_id=patient.id, doctor_id=doctor.id, center_id=ids["center"]))
        assert row.appointment_id is None and row.clinical_history_id is None
        assert doctor_has_patient_relationship(db, doctor, patient.id)
        assert patient_in_identity_scope(db, doctor, patient.id)
        updated = documents.update(db, doctor, "physical_exam", row.id, DocumentUpdate(expected_revision=0, values={"corazon": "Exploración sintética"}))
        documents.transition(db, doctor, "physical_exam", row.id, "complete", DocumentTransition(expected_revision=updated["revision"]))
        signed = documents.transition(db, doctor, "physical_exam", row.id, "sign", DocumentTransition(expected_revision=2))
        snapshot = signed["patient_profile"]
        db.get(Patient, patient.id).phone = "809-000-0000"
        db.commit()
        assert documents.get(db, doctor, "physical_exam", row.id)["patient_profile"] == snapshot


def test_secretary_can_prepare_selected_patient_before_appointment_without_clinical_leak(document_db):
    engine, ids, _ = document_db
    with scoped(engine) as db:
        secretary = db.get(User, ids["secretary"])
        patient = Patient(first_name="QA", last_name="Nuevo", date_of_birth=date(1990, 1, 1))
        db.add(patient); db.commit()
        token = issue_patient_selection_token(secretary, patient.id, center_id=ids["center"], doctor_id=ids["doctor"])
        row, created = documents.create(db, secretary, "preoperative", DocumentCreate(
            patient_id=patient.id, doctor_id=ids["doctor"], center_id=ids["center"], patient_selection_token=token))
        assert created and row.appointment_id is None
        assert len(documents.list_for_patient(db, secretary, patient.id)) == 1
        assert documents.get(db, secretary, "preoperative", row.id)["values"] == {}
        assert patient_in_identity_scope(db, secretary, patient.id)
        exam, created = documents.create(db, secretary, "physical_exam", DocumentCreate(
            patient_id=patient.id, doctor_id=ids["doctor"], center_id=ids["center"]))
        assert created and exam.patient_id == patient.id


def test_document_api_response_and_pdf_authorization(document_db):
    engine, ids, _ = document_db
    with scoped(engine) as db:
        active = {"id": ids["doctor"]}
        app = FastAPI()
        app.include_router(routes.router, prefix="/api/v1")
        app.dependency_overrides[current_user] = lambda: db.get(User, active["id"])
        app.dependency_overrides[get_db] = lambda: db
        client = TestClient(app)
        appointment = db.get(Appointment, ids["appointments"][0])
        payload = {"patient_id": appointment.patient_id, "doctor_id": appointment.doctor_id,
                   "center_id": appointment.center_id, "appointment_id": appointment.id}
        created = client.post("/api/v1/clinical-documents/preoperative", json=payload)
        assert created.status_code == 201
        document_id = created.json()["id"]
        assert client.post("/api/v1/clinical-documents/preoperative", json=payload).status_code == 200
        assert client.put(f"/api/v1/clinical-documents/preoperative/{document_id}", json={
            "expected_revision": 0, "values": {"ta": "120/80"}}).status_code == 200
        printed = client.get(f"/api/v1/clinical-documents/preoperative/{document_id}/pdf")
        assert printed.status_code == 200 and printed.content.startswith(b"%PDF")
        active["id"] = ids["secretary"]
        assert client.get(f"/api/v1/clinical-documents/preoperative/{document_id}/pdf").status_code == 403
        read = client.get(f"/api/v1/clinical-documents/preoperative/{document_id}")
        assert read.status_code == 200 and "ta" not in read.json()["values"]


def test_api_explicitly_links_prepared_draft_without_changing_patient(document_db):
    engine, ids, _ = document_db
    with scoped(engine) as db:
        app = FastAPI()
        app.include_router(routes.router, prefix="/api/v1")
        app.dependency_overrides[current_user] = lambda: db.get(User, ids["doctor"])
        app.dependency_overrides[get_db] = lambda: db
        client = TestClient(app)
        appointment = db.get(Appointment, ids["appointments"][0])
        created = client.post("/api/v1/clinical-documents/preoperative", json={
            "patient_id": appointment.patient_id})
        assert created.status_code == 201
        row_id = created.json()["id"]
        assert created.json()["doctor_id"] == ids["doctor"]
        assert created.json()["center_id"] == ids["center"]
        assert created.json()["appointment_id"] is None
        assert client.put(f"/api/v1/clinical-documents/preoperative/{row_id}", json={
            "patient_id": ids["appointments"][1], "expected_revision": 0, "values": {}
        }).status_code == 422
        linked = client.post(f"/api/v1/clinical-documents/preoperative/{row_id}/link-context", json={
            "expected_revision": 0, "appointment_id": appointment.id})
        assert linked.status_code == 200
        assert linked.json()["id"] == row_id and linked.json()["patient_id"] == appointment.patient_id
        assert linked.json()["appointment_id"] == appointment.id
        same = client.post("/api/v1/clinical-documents/preoperative", json={
            "patient_id": appointment.patient_id, "appointment_id": appointment.id})
        assert same.status_code == 200 and same.json()["id"] == row_id


def test_synthetic_api_handoff_reopen_sign_and_independent_exam(document_db):
    engine, ids, _ = document_db
    with scoped(engine) as db:
        active = {"id": ids["secretary"]}
        app = FastAPI()
        app.include_router(routes.router, prefix="/api/v1")
        app.dependency_overrides[current_user] = lambda: db.get(User, active["id"])
        app.dependency_overrides[get_db] = lambda: db
        client = TestClient(app)
        appointment = db.get(Appointment, ids["appointments"][0])
        payload = {"patient_id": appointment.patient_id, "doctor_id": appointment.doctor_id,
                   "center_id": appointment.center_id, "appointment_id": appointment.id}
        created = client.post("/api/v1/clinical-documents/preoperative", json=payload)
        assert created.status_code == 201
        document_id = created.json()["id"]
        saved = client.put(f"/api/v1/clinical-documents/preoperative/{document_id}", json={
            "expected_revision": 0, "values": {"procedimiento": "Procedimiento QA"}})
        assert saved.status_code == 200 and saved.json()["values"] == {"procedimiento": "Procedimiento QA"}
        assert client.post("/api/v1/clinical-documents/preoperative", json=payload).json()["id"] == document_id
        assert client.get(f"/api/v1/clinical-documents/preoperative/{document_id}").json()["values"] == {
            "procedimiento": "Procedimiento QA"}
        submitted = client.post(f"/api/v1/clinical-documents/preoperative/{document_id}/submit", json={
            "expected_revision": 1})
        assert submitted.status_code == 200 and submitted.json()["status"] == "pending_evaluation"
        assert client.post(f"/api/v1/clinical-documents/preoperative/{document_id}/complete", json={
            "expected_revision": 2}).status_code == 403

        active["id"] = ids["doctor"]
        assert client.get(f"/api/v1/clinical-documents/preoperative/{document_id}").json()["values"] == {
            "procedimiento": "Procedimiento QA"}
        updated = client.put(f"/api/v1/clinical-documents/preoperative/{document_id}", json={
            "expected_revision": 2, "values": {"hepatitis": "No", "glicemia": "QA 90", "ta": "120/80"}})
        assert updated.status_code == 200 and updated.json()["values"]["hepatitis"] == "No"
        completed = client.post(f"/api/v1/clinical-documents/preoperative/{document_id}/complete", json={
            "expected_revision": 3})
        signed = client.post(f"/api/v1/clinical-documents/preoperative/{document_id}/sign", json={
            "expected_revision": 4})
        assert completed.json()["status"] == "completed" and signed.json()["status"] == "signed"
        assert signed.json()["signed_by_user_id"] == ids["doctor"] and signed.json()["signed_at"]
        assert client.put(f"/api/v1/clinical-documents/preoperative/{document_id}", json={
            "expected_revision": 5, "values": {"ta": "cambio bloqueado"}}).status_code == 409
        assert client.get(f"/api/v1/clinical-documents/preoperative/{document_id}/pdf").content.startswith(b"%PDF")

        exam = client.post("/api/v1/clinical-documents/physical_exam", json=payload)
        assert exam.status_code == 201 and exam.json()["kind"] == "physical_exam"
        assert client.put(f"/api/v1/clinical-documents/physical_exam/{exam.json()['id']}", json={
            "expected_revision": 0, "values": {"ta": "110/70"}}).status_code == 200
        assert client.post(f"/api/v1/clinical-documents/physical_exam/{exam.json()['id']}/complete", json={
            "expected_revision": 1}).json()["status"] == "completed"
        assert client.post(f"/api/v1/clinical-documents/physical_exam/{exam.json()['id']}/sign", json={
            "expected_revision": 2}).json()["status"] == "signed"
        assert client.get(f"/api/v1/clinical-documents/physical_exam/{exam.json()['id']}/pdf").content.startswith(b"%PDF")
        assert client.get(f"/api/v1/clinical-documents/preoperative/{document_id}").json()["values"]["ta"] == "120/80"
        history = client.get(f"/api/v1/clinical-documents/patients/{appointment.patient_id}")
        assert history.status_code == 200 and {item["kind"] for item in history.json()} == {
            "preoperative", "physical_exam"}
