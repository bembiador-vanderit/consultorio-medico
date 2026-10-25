"""0056 synthetic tests; never access the official local database."""
from datetime import date

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Permission, Role, SecretaryDocumentGrant, Specialty, User
from app.models.clinical_audit import ClinicalAuditLog
from app.api.deps import current_user
from app.api.routes import clinical_forms as form_routes
from app.db import get_db
from app.schemas.clinical_form import FormDefinition
from app.schemas.clinical_patient_document import DocumentTransition, DocumentUpdate
from app.services import clinical_forms as forms, clinical_patient_documents as documents
from app.services.bootstrap import seed_identity
from app.services.clinical_form_pdf import build_form_pdf
from test_clinical_patient_documents import appointment_payload, document_db, rejects
from test_queue_arrivals import queue_db, scoped


@pytest.fixture
def designer_db(document_db):
    engine, ids, day = document_db
    # Base.metadata intentionally excludes the future columns: 0055 remains
    # writable before activation. A migrated SQLite test database adds them.
    with engine.begin() as connection:
        for table in ("preoperative_evaluations", "physical_examinations"):
            connection.exec_driver_sql(f"ALTER TABLE {table} ADD COLUMN template_id INTEGER")
            connection.exec_driver_sql(f"ALTER TABLE {table} ADD COLUMN template_version_id INTEGER")
    with Session(engine) as db:
        admin_role = db.scalar(select(Role).where(Role.code == "admin"))
        codes = ("clinical_forms:view", "clinical_forms:create", "clinical_forms:edit_draft",
                 "clinical_forms:publish", "clinical_forms:retire", "clinical_forms:assign")
        permissions = [Permission(code=code, description=code) for code in codes]
        db.add_all(permissions)
        admin_role.permissions.extend(permissions)
        db.commit()
    return engine, ids, day


def test_cemer_catalog_versions_assignment_snapshot_and_pdf(designer_db):
    engine, ids, _ = designer_db
    with scoped(engine) as db:
        admin = db.get(User, ids["admin"])
        doctor = db.get(User, ids["doctor"])
        definition = forms.cemer_definition("preoperative")
        assert len(definition.pages) == 2
        assert forms.field_keys(definition.model_dump()) >= {"hepatitis", "glicemia", "creatinina", "pcb", "ivy"}
        assert [page.page_number for page in definition.pages] == [1, 2]
        template = forms.create_template(db, admin, name="Evaluación CEMER", code="cemer_preop_test",
                                         description="QA", document_type="preoperative", definition=definition)
        assert template["draft_version_id"] and template["current_version_id"] is None
        rejects(409, lambda: forms.assign(db, admin, template["id"], center_id=ids["center"], specialty_id=None, doctor_id=None))
        published = forms.publish(db, admin, template["id"], template["draft_version_id"])
        assert published["status"] == "published" and published["current_version"] == 1
        rejects(409, lambda: forms.update_draft(db, admin, template["id"], published["current_version_id"], definition))
        assigned = forms.assign(db, admin, template["id"], center_id=ids["center"], specialty_id=None, doctor_id=doctor.id)
        assert assigned.doctor_id == doctor.id
        row, created = documents.create(db, doctor, "preoperative", appointment_payload(db, ids))
        assert created
        first = documents.get(db, doctor, "preoperative", row.id)
        assert first["template_version_id"] == published["current_version_id"]
        assert first["template_source"] == "versioned"
        updated = documents.update(db, doctor, "preoperative", row.id,
                                   DocumentUpdate(expected_revision=0, values={"hepatitis": "no", "peso": "80.5"}))
        assert updated["values"]["peso"] == "80.5"
        rejects(422, lambda: documents.update(db, doctor, "preoperative", row.id,
                                               DocumentUpdate(expected_revision=1, values={"hepatitis": "maybe"})))
        documents.transition(db, doctor, "preoperative", row.id, "complete", DocumentTransition(expected_revision=1))
        signed = documents.transition(db, doctor, "preoperative", row.id, "sign", DocumentTransition(expected_revision=2))
        assert signed["status"] == "signed" and signed["template_version_id"] == first["template_version_id"]
        pdf = build_form_pdf(signed["template_definition"], values=signed["values"],
                             profile=signed["patient_profile"], document_date=str(signed["document_date"]),
                             status=signed["status"], signed_at=signed["signed_at"])
        assert pdf.startswith(b"%PDF") and pdf.count(b"/Type /Page\n") == 2
        fork = forms.fork_draft(db, admin, template["id"])
        definition2 = FormDefinition.model_validate(fork["definition"])
        definition2.pages[0].sections[0].title = "ENCABEZADO V2"
        forms.update_draft(db, admin, template["id"], fork["draft_version_id"], definition2)
        forms.publish(db, admin, template["id"], fork["draft_version_id"])
        assert documents.get(db, doctor, "preoperative", row.id)["template_version_id"] == first["template_version_id"]
        assert documents.get(db, doctor, "preoperative", row.id)["template_definition"]["pages"][0]["sections"][0]["title"] != "ENCABEZADO V2"
        rejects(409, lambda: documents.update(db, doctor, "preoperative", row.id,
                                               DocumentUpdate(expected_revision=3, values={"peso": "90"})))


def test_versioned_completion_checks_only_template_required_fields(designer_db):
    engine, ids, _ = designer_db
    with scoped(engine) as db:
        admin = db.get(User, ids["admin"])
        doctor = db.get(User, ids["doctor"])
        optional = forms.cemer_definition("preoperative")
        assert not any(field.required for page in optional.pages for section in page.sections for field in section.fields)
        template = forms.create_template(db, admin, name="Preoperatoria opcional QA", code="preop_optional_qa",
                                         description="QA", document_type="preoperative", definition=optional)
        forms.publish(db, admin, template["id"], template["draft_version_id"])
        forms.assign(db, admin, template["id"], center_id=ids["center"], specialty_id=None, doctor_id=doctor.id)
        row, created = documents.create(db, doctor, "preoperative", appointment_payload(db, ids))
        assert created and documents.get(db, doctor, "preoperative", row.id)["template_source"] == "versioned"
        completed = documents.transition(db, doctor, "preoperative", row.id, "complete",
                                         DocumentTransition(expected_revision=0))
        assert completed["status"] == "completed" and completed["values"] == {}

        required = forms.cemer_definition("physical_exam")
        ta = next(field for page in required.pages for section in page.sections for field in section.fields if field.key == "ta")
        ta.required = True
        exam_template = forms.create_template(db, admin, name="Examen requerido QA", code="exam_required_qa",
                                              description="QA", document_type="physical_exam", definition=required)
        forms.publish(db, admin, exam_template["id"], exam_template["draft_version_id"])
        forms.assign(db, admin, exam_template["id"], center_id=ids["center"], specialty_id=None, doctor_id=doctor.id)
        exam, created = documents.create(db, doctor, "physical_exam", appointment_payload(db, ids))
        assert created
        rejects(422, lambda: documents.transition(db, doctor, "physical_exam", exam.id, "complete",
                                                  DocumentTransition(expected_revision=0)))
        documents.update(db, doctor, "physical_exam", exam.id,
                         DocumentUpdate(expected_revision=0, values={"ta": "120/80"}))
        assert documents.transition(db, doctor, "physical_exam", exam.id, "complete",
                                    DocumentTransition(expected_revision=1))["status"] == "completed"


def test_synthetic_secretary_doctor_handoff_preserves_one_versioned_document(designer_db):
    engine, ids, _ = designer_db
    with scoped(engine) as db:
        admin, secretary, doctor = (db.get(User, ids[key]) for key in ("admin", "secretary", "doctor"))
        definition = forms.cemer_definition("preoperative")
        template = forms.create_template(db, admin, name="Preoperatoria de traspaso QA", code="preop_handoff_qa",
                                         description="QA", document_type="preoperative", definition=definition)
        published = forms.publish(db, admin, template["id"], template["draft_version_id"])
        forms.assign(db, admin, template["id"], center_id=ids["center"], specialty_id=None, doctor_id=doctor.id)
        forms.set_secretary_capabilities(db, admin, secretary.id, {
            "start_preoperative": True, "start_physical_exam": True, "prepare_administrative": True,
        })

        preop, created = documents.create(db, secretary, "preoperative", appointment_payload(db, ids))
        assert created and preop.status == "draft" and preop.appointment_id == ids["appointments"][0]
        saved = documents.update(db, secretary, "preoperative", preop.id,
                                 DocumentUpdate(expected_revision=0, values={"procedimiento": "Procedimiento QA"}))
        assert saved["last_updated_by_user_id"] == secretary.id
        assert saved["template_version_id"] == published["current_version_id"]
        again, created = documents.create(db, doctor, "preoperative", appointment_payload(db, ids))
        assert not created and again.id == preop.id
        submitted = documents.transition(db, secretary, "preoperative", preop.id, "submit",
                                         DocumentTransition(expected_revision=1))
        assert submitted["status"] == "pending_evaluation"
        rejects(403, lambda: documents.transition(db, secretary, "preoperative", preop.id, "complete",
                                                  DocumentTransition(expected_revision=2)))
        rejects(403, lambda: documents.transition(db, secretary, "preoperative", preop.id, "sign",
                                                  DocumentTransition(expected_revision=2)))
        reopened = documents.get(db, doctor, "preoperative", preop.id)
        assert reopened["id"] == preop.id and reopened["values"]["procedimiento"] == "Procedimiento QA"
        assert reopened["template_version_id"] == published["current_version_id"]
        documents.update(db, doctor, "preoperative", preop.id, DocumentUpdate(expected_revision=2, values={
            "hepatitis": "no", "glicemia": "QA 90", "creatinina": "QA 1.0", "corazon": "Examen QA",
        }))
        completed = documents.transition(db, doctor, "preoperative", preop.id, "complete",
                                         DocumentTransition(expected_revision=3))
        signed = documents.transition(db, doctor, "preoperative", preop.id, "sign",
                                      DocumentTransition(expected_revision=4))
        assert completed["status"] == "completed" and signed["status"] == "signed"
        assert signed["signed_by_user_id"] == doctor.id and signed["signed_at"]
        assert signed["values"]["hepatitis"] == "no" and signed["values"]["corazon"] == "Examen QA"
        pdf = build_form_pdf(signed["template_definition"], values=signed["values"],
                             profile=signed["patient_profile"], document_date=str(signed["document_date"]),
                             status=signed["status"], signed_at=signed["signed_at"])
        assert pdf.startswith(b"%PDF") and pdf.count(b"/Type /Page\n") == 2

        exam, created = documents.create(db, doctor, "physical_exam", appointment_payload(db, ids))
        assert created and exam.patient_id == preop.patient_id
        documents.update(db, doctor, "physical_exam", exam.id,
                         DocumentUpdate(expected_revision=0, values={"ta": "120/80"}))
        assert documents.get(db, doctor, "physical_exam", exam.id)["values"] == {"ta": "120/80"}
        assert documents.get(db, doctor, "preoperative", preop.id)["values"] == signed["values"]
        rows = db.scalars(select(ClinicalAuditLog).where(ClinicalAuditLog.resource_type == "preoperative",
                                                        ClinicalAuditLog.resource_id == preop.id)).all()
        assert {"clinical_document:created", "clinical_document:updated", "clinical_document:submit",
                "clinical_document:complete", "clinical_document:sign"} <= {row.action for row in rows}
        assert next(row for row in rows if row.action == "clinical_document:submit").user_id == secretary.id
        assert next(row for row in rows if row.action == "clinical_document:complete").user_id == doctor.id


def test_validation_duplicate_retire_and_tenant_scope(designer_db):
    engine, ids, _ = designer_db
    with scoped(engine) as db:
        admin = db.get(User, ids["admin"])
        draft = forms.create_template(db, admin, name="Vacía", code="qa_empty_form", description="",
                                      document_type="physical_exam")
        rejects(422, lambda: forms.publish(db, admin, draft["id"], draft["draft_version_id"]))
        definition = forms.cemer_definition("physical_exam")
        forms.update_draft(db, admin, draft["id"], draft["draft_version_id"], definition)
        forms.publish(db, admin, draft["id"], draft["draft_version_id"])
        copy = forms.duplicate(db, admin, draft["id"], name="Copia", code="qa_exam_copy")
        assert copy["status"] == "draft" and copy["definition"] == definition.model_dump(mode="json")
        forms.retire(db, admin, draft["id"])
        rejects(409, lambda: forms.assign(db, admin, draft["id"], center_id=None, specialty_id=None, doctor_id=None))
        item_id = copy["id"]
    with scoped(engine, 2) as db:
        rejects(404, lambda: forms._template(db, item_id))


def test_secretary_grants_are_independent_and_legacy_document_fallback(designer_db):
    engine, ids, _ = designer_db
    with scoped(engine) as db:
        admin, secretary, doctor = (db.get(User, ids[key]) for key in ("admin", "secretary", "doctor"))
        existing = db.scalar(select(SecretaryDocumentGrant).where(SecretaryDocumentGrant.user_id == secretary.id))
        db.delete(existing); db.commit()
        assert not any(forms.secretary_capabilities(db, secretary).values())
        rejects(403, lambda: documents.create(db, secretary, "preoperative", appointment_payload(db, ids)))
        forms.set_secretary_capabilities(db, admin, secretary.id, {
            "start_preoperative": True, "start_physical_exam": False, "prepare_administrative": True})
        row, created = documents.create(db, secretary, "preoperative", appointment_payload(db, ids))
        assert created and documents.get(db, doctor, "preoperative", row.id)["template_source"] == "legacy_0055"
        rejects(403, lambda: documents.create(db, secretary, "physical_exam", appointment_payload(db, ids)))
        item = documents.update(db, secretary, "preoperative", row.id,
                                DocumentUpdate(expected_revision=0, values={"procedimiento": "QA"}))
        assert item["values"] == {"procedimiento": "QA"}
        rejects(403, lambda: documents.update(db, secretary, "preoperative", row.id,
                                               DocumentUpdate(expected_revision=1, values={"hepatitis": "no"})))


def test_schema_rejects_duplicate_keys_and_unsafe_binding():
    definition = forms.cemer_definition("physical_exam").model_dump(mode="json")
    definition["pages"][0]["sections"][0]["fields"].append(definition["pages"][0]["sections"][0]["fields"][0])
    with pytest.raises(ValueError):
        FormDefinition.model_validate(definition)
    definition = forms.cemer_definition("physical_exam").model_dump(mode="json")
    definition["pages"][0]["sections"][0]["fields"][0]["type"] = "date"
    definition["pages"][0]["sections"][0]["fields"][0]["default_value"] = "not-a-date"
    with pytest.raises(ValueError):
        FormDefinition.model_validate(definition)


def test_assignment_precedence_and_independent_physical_exam(designer_db):
    engine, ids, _ = designer_db
    with scoped(engine) as db:
        admin = db.get(User, ids["admin"])
        doctor = db.get(User, ids["doctor"])
        specialty = Specialty(name="Cardiología QA")
        db.add(specialty)
        doctor.specialties.append(specialty)
        db.commit()
        assigned = []
        for suffix in ("org", "center", "specialty", "doctor"):
            item = forms.create_template(db, admin, name=f"QA {suffix}", code=f"qa_preop_{suffix}",
                                         description="", document_type="preoperative",
                                         definition=forms.cemer_definition("preoperative"))
            forms.publish(db, admin, item["id"], item["draft_version_id"])
            assigned.append(item["id"])
        scopes = ((None, None, None), (ids["center"], None, None),
                  (ids["center"], specialty.id, None), (ids["center"], None, doctor.id))
        for index, scope in enumerate(scopes):
            forms.assign(db, admin, assigned[index], center_id=scope[0], specialty_id=scope[1], doctor_id=scope[2])
            resolved = forms.resolve(db, "preoperative", center_id=ids["center"], doctor_id=doctor.id)
            assert resolved[0].id == assigned[index]
        assert forms.resolve(db, "physical_exam", center_id=ids["center"], doctor_id=doctor.id) is None
        exam = forms.create_template(db, admin, name="Examen QA", code="qa_exam_independent",
                                     description="", document_type="physical_exam",
                                     definition=forms.cemer_definition("physical_exam"))
        forms.publish(db, admin, exam["id"], exam["draft_version_id"])
        forms.assign(db, admin, exam["id"], center_id=ids["center"], specialty_id=None, doctor_id=None)
        assert forms.resolve(db, "physical_exam", center_id=ids["center"], doctor_id=doctor.id)[0].id == exam["id"]
    definition = forms.cemer_definition("physical_exam").model_dump(mode="json")
    definition["pages"][0]["sections"][0]["fields"][0]["data_binding"] = "__import__('os').system('x')"
    with pytest.raises(ValueError):
        FormDefinition.model_validate(definition)


def test_template_api_preview_and_permissions(designer_db):
    engine, ids, _ = designer_db
    with scoped(engine) as db:
        current = {"id": ids["admin"]}
        app = FastAPI()
        app.include_router(form_routes.router, prefix="/api/v1")
        app.dependency_overrides[current_user] = lambda: db.get(User, current["id"])
        app.dependency_overrides[get_db] = lambda: db
        client = TestClient(app)
        assert client.get("/api/v1/clinical-forms/templates").status_code == 200
        response = client.post("/api/v1/clinical-forms/catalog/preoperative")
        assert response.status_code == 201
        template_id = response.json()["id"]
        assert len(response.json()["definition"]["pages"]) == 2
        preview = client.get(f"/api/v1/clinical-forms/templates/{template_id}/preview/pdf")
        assert preview.status_code == 200 and preview.content.startswith(b"%PDF")
        assert preview.content.count(b"/Type /Page\n") == 2
        current["id"] = ids["doctor"]
        assert client.get("/api/v1/clinical-forms/templates").status_code == 403
        assert client.post("/api/v1/clinical-forms/catalog/physical_exam").status_code == 403


def test_bootstrap_preserves_0056_admin_permissions_without_secretary_auto_grants(designer_db):
    engine, ids, _ = designer_db
    with Session(engine) as db:
        seed_identity(db)
    with scoped(engine) as db:
        admin = db.get(User, ids["admin"])
        secretary = db.get(User, ids["secretary"])
        from app.services.administration import effective_permissions
        admin_permissions = effective_permissions(admin)
        secretary_permissions = effective_permissions(secretary)
        assert "clinical_forms:view" in admin_permissions
        assert "clinical_forms:publish" in admin_permissions
        assert "clinical_forms:assign" in admin_permissions
        assert "clinical_documents:view" in secretary_permissions
        assert "clinical_documents:create" not in secretary_permissions
        assert "clinical_documents:prepare" not in secretary_permissions
