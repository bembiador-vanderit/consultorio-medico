"""Synthetic host-bound visibility tests. No official database mutations."""
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select, func
from sqlalchemy.orm import Session
from app.api.routes import feature_visibility, patient_safety
from app.models import CareCenter, OrganizationMembership, Role, User
from app.models.feature_visibility import FeatureVisibilitySetting
from app.models.clinical_audit import ClinicalAuditLog
from app.models.patient_safety import PatientSafetyEntry
from app.services import feature_visibility as service
from app.services.administration import effective_permissions
from app.services.tenancy import bind_scope
from test_organization_isolation import tenant_api, sign_in, PASSWORD
from test_administration_security import proof
from test_clinical_sharing import sharing_app, configure, read

BASE = "/api/v1/feature-visibility"


@pytest.fixture
def visibility(tenant_api):
    app, engine, patients = tenant_api
    app.include_router(feature_visibility.router, prefix="/api/v1")
    app.include_router(patient_safety.router, prefix="/api/v1")
    ids = {}
    with Session(engine) as db:
        original = db.scalar(select(User).where(User.email == "shared@example.com"))
        center = db.scalar(select(CareCenter).where(CareCenter.organization_id == 1))
        for role in ("doctor", "secretary"):
            user = User(email=f"visibility-{role}@example.com", full_name=f"QA {role}", password_hash=original.password_hash,
                centers=[center], memberships=[OrganizationMembership(organization_id=1, roles=[db.scalar(select(Role).where(Role.code == role))])])
            db.add(user); db.flush(); ids[role] = user.id
        ids["center"] = center.id
        ids["other_center"] = db.scalar(select(CareCenter.id).where(CareCenter.organization_id == 2))
        db.commit()
    client = TestClient(app, base_url="http://one.example.test")
    headers = {"admin": sign_in(client)}
    for role in ("doctor", "secretary"):
        response = client.post("/api/v1/auth/login", json={"email": f"visibility-{role}@example.com", "password": PASSWORD})
        assert response.status_code == 200
        headers[role] = {"Authorization": f"Bearer {response.json()['access_token']}"}
    yield {"client": client, "engine": engine, "ids": ids, "headers": headers, "patients": patients}
    client.close()


def save(c, *, feature="clinical_safety_full", audience="doctor", mode="visible", center=None, revision=None):
    params = {"center_id": center} if center else {}
    if revision is None:
        items = c["client"].get(BASE + "/settings", headers=c["headers"]["admin"], params=params).json()["items"]
        revision = next(i["revision"] for i in items if i["feature_code"] == feature and i["audience"] == audience)
    body = {"changes": [{"feature_code": feature, "audience": audience, "visibility_mode": mode, "revision": revision}], "reason": "QA visibility test"}
    return c["client"].put(BASE + "/settings", params=params,
        headers=proof(c["client"], c["headers"]["admin"], "PUT", BASE + "/settings"), json=body)


@pytest.mark.parametrize("audience", ["doctor", "secretary"])
def test_ambulatory_defaults_both_hidden(visibility, audience):
    c = visibility
    response = c["client"].get(BASE + "/resolved", headers=c["headers"][audience])
    assert response.status_code == 200
    assert response.headers["Cache-Control"] == "no-store"
    assert response.json()["audience"] == audience
    assert response.json()["features"] == {key: False for key in service.FEATURES}


def test_admin_visible_hidden_and_audiences_independent(visibility):
    c = visibility
    assert save(c).status_code == 200
    assert c["client"].get(BASE + "/resolved", headers=c["headers"]["doctor"]).json()["features"]["clinical_safety_full"]
    assert not c["client"].get(BASE + "/resolved", headers=c["headers"]["secretary"]).json()["features"]["clinical_safety_full"]
    assert save(c, mode="hidden").status_code == 200
    assert not c["client"].get(BASE + "/resolved", headers=c["headers"]["doctor"]).json()["features"]["clinical_safety_full"]


def test_critical_is_independent_and_read_does_not_modify_audit(visibility):
    c = visibility
    assert save(c, feature="clinical_safety_critical_alert").status_code == 200
    with Session(c["engine"]) as db:
        before = db.scalar(select(func.count()).select_from(ClinicalAuditLog))
    result = c["client"].get(BASE + "/resolved", headers=c["headers"]["doctor"]).json()["features"]
    assert result == {"clinical_safety_full": False, "clinical_safety_critical_alert": True}
    with Session(c["engine"]) as db:
        assert db.scalar(select(func.count()).select_from(ClinicalAuditLog)) == before
        audit = db.scalar(select(ClinicalAuditLog).where(ClinicalAuditLog.action == "feature_visibility.updated"))
        assert audit.user_id and audit.organization_id == 1 and audit.created_at
        assert audit.context == {"feature_code": "clinical_safety_critical_alert", "context_code": "ambulatory",
            "audience": "doctor", "before": None, "after": "visible", "previous_revision": 0,
            "revision": 1, "reason": "QA visibility test"}


def test_center_org_default_precedence_and_inheritance(visibility):
    c = visibility; center = c["ids"]["center"]
    assert save(c).status_code == 200
    assert save(c, center=center, mode="hidden").status_code == 200
    h = c["headers"]["doctor"]
    assert not c["client"].get(BASE + "/resolved", headers=h, params={"center_id": center}).json()["features"]["clinical_safety_full"]
    assert c["client"].get(BASE + "/resolved", headers=h).json()["features"]["clinical_safety_full"]
    assert save(c, center=center, mode=None).status_code == 200
    assert c["client"].get(BASE + "/resolved", headers=h, params={"center_id": center}).json()["features"]["clinical_safety_full"]
    assert save(c, mode=None).status_code == 200
    assert not c["client"].get(BASE + "/resolved", headers=h).json()["features"]["clinical_safety_full"]


def test_visibility_never_changes_permissions_or_grants_secretary_safety(visibility):
    c = visibility
    with Session(c["engine"]) as db:
        bind_scope(db, "tenant", 1)
        before = {r: effective_permissions(db.get(User, c["ids"][r])) for r in ("doctor", "secretary")}
    assert save(c, audience="secretary").status_code == 200
    assert c["client"].get(f"/api/v1/patient-safety/patients/{c['patients'][1]}", headers=c["headers"]["secretary"]).status_code == 403
    assert save(c, mode="hidden").status_code == 200
    with Session(c["engine"]) as db:
        bind_scope(db, "tenant", 1)
        assert {r: effective_permissions(db.get(User, c["ids"][r])) for r in ("doctor", "secretary")} == before


def test_tenant_isolation_and_center_boundary(visibility):
    c = visibility
    assert save(c).status_code == 200
    with TestClient(c["client"].app, base_url="http://two.example.test") as other:
        headers = sign_in(other)
        assert not any(i["visible"] for i in other.get(BASE + "/settings", headers=headers).json()["items"])
        assert other.get(BASE + "/settings", headers=c["headers"]["admin"]).status_code == 401
        assert other.get(BASE + "/settings", headers=headers, params={"center_id": c["ids"]["center"]}).status_code == 404
    assert c["client"].get(BASE + "/resolved", headers=c["headers"]["doctor"], params={"center_id": c["ids"]["other_center"]}).status_code == 404
    assert save(c, center=c["ids"]["other_center"], revision=0).status_code == 404


@pytest.mark.parametrize("audience", ["doctor", "secretary"])
def test_non_admin_cannot_configure(visibility, audience):
    c = visibility
    assert c["client"].get(BASE + "/settings", headers=c["headers"][audience]).status_code == 403
    assert c["client"].put(BASE + "/settings", headers=c["headers"][audience], json={"changes": [], "reason": "QA reason"}).status_code == 403


@pytest.mark.parametrize("field,value", [("feature_code", "internal_messaging"), ("context_code", "emergency"), ("audience", "unknown"), ("visibility_mode", "entitled")])
def test_invalid_or_unimplemented_codes_rejected(visibility, field, value):
    c = visibility
    body = {"changes": [{"feature_code": "clinical_safety_full", "context_code": "ambulatory", "audience": "doctor", "visibility_mode": "visible", "revision": 0, field: value}], "reason": "QA invalid code"}
    assert c["client"].put(BASE + "/settings", headers=proof(c["client"], c["headers"]["admin"], "PUT", BASE + "/settings"), json=body).status_code == 422
    assert c["client"].get(BASE + "/resolved", headers=c["headers"]["doctor"], params={"context_code": "emergency"}).status_code == 422


def test_revision_and_noop_audit(visibility):
    c = visibility
    assert save(c).status_code == 200
    def assert_single_event():
        with Session(c["engine"]) as db:
            row = db.scalar(select(FeatureVisibilitySetting))
            audits = list(db.scalars(select(ClinicalAuditLog).where(ClinicalAuditLog.action == "feature_visibility.updated")))
            assert len(audits) == 1
            assert audits[0].context["revision"] == row.revision == 1
            assert audits[0].context["previous_revision"] == 0
            assert db.scalar(select(func.count()).select_from(FeatureVisibilitySetting)) == 1
    assert_single_event()
    assert save(c, revision=0).status_code == 409
    assert_single_event()
    assert save(c).status_code == 200
    assert_single_event()


@pytest.mark.parametrize("center_override", [False, True])
def test_audit_snapshots_resulting_revision_for_update_and_removal(visibility, center_override):
    c = visibility
    center = c["ids"]["center"] if center_override else None
    assert save(c, center=center).status_code == 200
    with Session(c["engine"]) as db:
        created = db.scalar(select(ClinicalAuditLog).where(ClinicalAuditLog.action == "feature_visibility.updated"))
        assert created.context["revision"] == 1
    assert save(c, center=center, mode="hidden").status_code == 200
    with Session(c["engine"]) as db:
        row = db.scalar(select(FeatureVisibilitySetting))
        updated = db.scalar(select(ClinicalAuditLog).where(ClinicalAuditLog.action == "feature_visibility.updated").order_by(ClinicalAuditLog.id.desc()))
        assert updated.context["revision"] == row.revision == 2
        assert updated.context["previous_revision"] == 1
    response = save(c, center=center, mode=None)
    assert response.status_code == 200
    local = next(i for i in response.json()["items"] if i["feature_code"] == "clinical_safety_full" and i["audience"] == "doctor")
    with Session(c["engine"]) as db:
        audits = list(db.scalars(select(ClinicalAuditLog).where(ClinicalAuditLog.action == "feature_visibility.updated").order_by(ClinicalAuditLog.id)))
        assert [(a.context["previous_revision"], a.context["revision"]) for a in audits] == [(0,1),(1,2),(2,0)]
        assert all(a.center_id == center for a in audits)
        assert audits[-1].context["after"] is None
        assert audits[-1].context["revision"] == local["revision"] == 0
        assert db.scalar(select(FeatureVisibilitySetting)) is None
        # Earlier immutable audit JSON still names its original revision.
        assert audits[0].context["revision"] == 1


def test_stale_batch_rolls_back_earlier_change_and_its_audit(visibility):
    c = visibility
    assert save(c, feature="clinical_safety_critical_alert").status_code == 200
    response = c["client"].put(BASE + "/settings",
        headers=proof(c["client"], c["headers"]["admin"], "PUT", BASE + "/settings"),
        json={"reason":"QA atomic stale batch", "changes":[
            {"feature_code":"clinical_safety_full", "audience":"doctor", "visibility_mode":"visible", "revision":0},
            {"feature_code":"clinical_safety_critical_alert", "audience":"doctor", "visibility_mode":"hidden", "revision":0}]})
    assert response.status_code == 409
    with Session(c["engine"]) as db:
        rows = list(db.scalars(select(FeatureVisibilitySetting)))
        audits = list(db.scalars(select(ClinicalAuditLog).where(ClinicalAuditLog.action == "feature_visibility.updated")))
        assert len(rows) == len(audits) == 1
        assert rows[0].feature_code == "clinical_safety_critical_alert"
        assert rows[0].visibility_mode == "visible"
        assert audits[0].context["revision"] == rows[0].revision == 1


def test_config_write_requires_existing_reauthentication(visibility):
    c = visibility
    response = c["client"].put(BASE + "/settings", headers=c["headers"]["admin"], json={"changes": [
        {"feature_code": "clinical_safety_full", "audience": "doctor", "visibility_mode": "visible", "revision": 0}], "reason": "QA secure configuration"})
    assert response.status_code == 428


def test_multi_role_uses_effective_membership_doctor_category(visibility):
    c = visibility
    with Session(c["engine"]) as db:
        member = db.scalar(select(OrganizationMembership).where(OrganizationMembership.organization_id == 1,
            OrganizationMembership.user_id == c["ids"]["doctor"]))
        member.roles.append(db.scalar(select(Role).where(Role.code == "admin")))
        db.commit()
    response = c["client"].post("/api/v1/auth/login", json={"email": "visibility-doctor@example.com", "password": PASSWORD})
    headers = {"Authorization": f"Bearer {response.json()['access_token']}"}
    assert c["client"].get(BASE + "/resolved", headers=headers).json()["audience"] == "doctor"


def test_hidden_does_not_revoke_shared_permission_or_modify_safety(sharing_app):
    c = sharing_app; c["app"].include_router(feature_visibility.router, prefix="/api/v1")
    configure(c, patient_safety=True)
    with Session(c["engine"]) as db:
        before = dict(db.get(PatientSafetyEntry, c["ids"]["safety"]).__dict__)
    resolved = c["client"].get(BASE + "/resolved", headers=c["headers"]).json()["features"]
    assert not any(resolved.values())
    assert read(c, "patient_safety").status_code == 200  # visibility is not API authorization
    with Session(c["engine"]) as db:
        after = dict(db.get(PatientSafetyEntry, c["ids"]["safety"]).__dict__)
    before.pop("_sa_instance_state"); after.pop("_sa_instance_state")
    assert before == after


def test_staged_schema_uses_safe_defaults_without_querying_missing_table(visibility, monkeypatch):
    c = visibility
    monkeypatch.setattr(service, "available", lambda db: False)
    assert not any(c["client"].get(BASE + "/resolved", headers=c["headers"]["doctor"]).json()["features"].values())
    assert c["client"].get(BASE + "/settings", headers=c["headers"]["admin"]).json()["enabled"] is False
    assert save(c, revision=0).status_code == 503
