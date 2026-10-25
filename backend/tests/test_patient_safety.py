"""Synthetic HTTP tests for the longitudinal safety profile."""
from datetime import date

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.routes import patient_safety
from app.models import CareCenter, ClinicalHistory, Permission, Role, User
from app.models.clinical_audit import ClinicalAuditLog
from app.models.patient_safety import PatientSafetyEntry
from app.services.bootstrap import seed_identity
from test_patient_security import patient_app
from test_organization_isolation import tenant_api, sign_in


@pytest.fixture
def safety_app(patient_app):
    ctx = patient_app
    ctx["client"].app.include_router(patient_safety.router, prefix="/api/v1")
    db = ctx["db"]
    for code in ("patient_safety:view", "patient_safety:edit"):
        permission = Permission(code=code, description=code)
        ctx["roles"]["doctor"].permissions.append(permission)
    db.commit()
    return ctx


def payload(**changes):
    return {"entry_type": "allergy", "substance_or_agent": "Agente sintético QA",
            "reaction_description": "Reacción sintética QA", "severity": "unknown",
            "source_type": "patient_reported", **changes}


def path(ctx, patient=None):
    return f"/api/v1/patient-safety/patients/{(patient or ctx['a']).id}"


@pytest.mark.parametrize("kind", ["allergy", "adverse_reaction", "contraindication", "intolerance_avoid"])
def test_create_all_safety_types_and_patient_ownership(safety_app, kind):
    ctx = safety_app
    response = ctx["client"].post(path(ctx), json=payload(entry_type=kind))
    assert response.status_code == 201
    row = response.json()
    assert row["patient_id"] == ctx["a"].id and row["organization_id"] == ctx["a"].organization_id
    assert row["source_type"] == "patient_reported" and row["severity"] == "unknown"
    assert row["recorded_by_user_id"] == ctx["doctor"].id
    assert row["recorded_by_name"] == ctx["doctor"].full_name
    assert row["clinical_history_id"] is None
    assert ctx["client"].get(path(ctx)).json()[0]["id"] == row["id"]
    event = ctx["db"].scalar(select(ClinicalAuditLog).where(ClinicalAuditLog.resource_type == "patient_safety_entry"))
    assert event.context["before"] is None
    assert event.context["after"]["entry_type"] == kind
    assert event.user_id == ctx["doctor"].id


@pytest.mark.parametrize("changes", [{"severity":"invented"}, {"source_type":"confirmed"}, {"source_type":None}, {"substance_or_agent":" "}, {"entry_type":"unknown"}, {"reaction_description":""}, {"recorded_by_user_id":99}, {"organization_id":2}])
def test_validation_never_infers_or_accepts_forged_metadata(safety_app, changes):
    assert safety_app["client"].post(path(safety_app), json=payload(**changes)).status_code == 422


@pytest.mark.parametrize("actor", ["secretary", "admin", "no_permission"])
def test_non_clinical_users_cannot_read_or_write_even_with_demographic_edit(safety_app, actor):
    ctx = safety_app
    ctx["active"]["user"] = ctx[actor]
    assert ctx["client"].get(path(ctx)).status_code == 403
    assert ctx["client"].post(path(ctx), json=payload()).status_code == 403


@pytest.mark.parametrize("denied", ["patient_safety:edit", "patient_safety:view", "clinical:access", "patients:view"])
def test_specific_denials_and_view_only(safety_app, denied):
    ctx = safety_app
    ctx["doctor"].denied_permissions = [denied]
    ctx["db"].commit()
    assert ctx["client"].get(path(ctx)).status_code == (200 if denied == "patient_safety:edit" else 403)
    assert ctx["client"].post(path(ctx), json=payload()).status_code == 403


def test_update_noop_states_reasons_revision_and_no_delete(safety_app):
    ctx = safety_app
    client, db = ctx["client"], ctx["db"]
    before_history = db.scalar(select(func.count()).select_from(ClinicalHistory))
    row = client.post(path(ctx), json=payload()).json()
    url = f"{path(ctx)}/entries/{row['id']}"
    assert client.get(path(ctx)).status_code == 200
    unchanged = payload(revision=1)
    assert client.put(url, json=unchanged).status_code == 200
    assert db.scalar(select(func.count()).select_from(ClinicalAuditLog)) == 1
    response = client.put(url, json=payload(revision=1, severity="critical", notes="QA observación"))
    assert response.status_code == 200
    assert response.json()["revision"] == 2
    assert client.put(url, json=payload(revision=1)).status_code == 409
    assert client.put(url, json=payload(revision=2, status="inactive")).status_code == 422
    response = client.put(url, json=payload(revision=2, status="inactive", change_reason="Motivo sintético"))
    assert response.status_code == 200
    response = client.put(url, json=payload(revision=3, status="entered_in_error", change_reason="Corrección QA"))
    assert response.status_code == 200
    assert client.delete(url).status_code == 405
    assert client.put(url, json=payload(revision=4)).status_code == 409
    events = client.get(f"{url}/history").json()
    assert len(events) == 4
    assert events[0]["at"].endswith("+00:00") or events[0]["at"].endswith("Z")
    assert events[1]["context"]["before"]["severity"] == "unknown"
    assert events[1]["context"]["after"]["severity"] == "critical"
    assert events[-1]["action"] == "patient_safety.entered_in_error"
    assert events[-1]["context"]["reason"] == "Corrección QA"
    assert db.scalar(select(func.count()).select_from(ClinicalHistory)) == before_history
    # A doctor with administrative audit permission still cannot leak safety
    # payloads through the generic administrative listing.
    ctx["roles"]["doctor"].permissions.append(db.scalar(select(Permission).where(Permission.code == "users:manage")))
    db.commit()
    assert not [e for e in client.get("/api/v1/clinical-history/audit-logs").json() if e["resource_type"] == "patient_safety_entry"]


def test_context_provenance_is_optional_patient_bound_and_does_not_own_entry(safety_app):
    ctx = safety_app
    db = ctx["db"]
    history = ClinicalHistory(patient_id=ctx["a"].id, doctor_id=ctx["doctor"].id,
        center_id=ctx["centers"][0].id, consultation_date=date(2030,1,1), allergies="Texto histórico QA")
    foreign = ClinicalHistory(patient_id=ctx["b"].id, doctor_id=ctx["other"].id,
        center_id=ctx["centers"][1].id, consultation_date=date(2030,1,1))
    db.add_all([history,foreign]);db.commit()
    response = ctx["client"].post(path(ctx), json=payload(clinical_history_id=history.id))
    assert response.status_code == 201 and response.json()["clinical_history_id"] == history.id
    assert ctx["client"].post(path(ctx), json=payload(clinical_history_id=foreign.id)).status_code == 404
    assert history.allergies == "Texto histórico QA"
    # Another authorized physician can consume the same longitudinal record.
    db.add(ClinicalHistory(patient_id=ctx["a"].id, doctor_id=ctx["other"].id,
        center_id=ctx["centers"][0].id, consultation_date=date(2030,1,2)))
    db.commit();ctx["active"]["user"] = ctx["other"]
    assert ctx["client"].get(path(ctx)).json()[0]["id"] == response.json()["id"]


def test_cross_patient_scope_and_entry_id_cannot_be_substituted(safety_app):
    ctx = safety_app
    row = ctx["client"].post(path(ctx), json=payload()).json()
    assert ctx["client"].get(path(ctx, ctx["b"])).status_code == 404
    assert ctx["client"].post(path(ctx, ctx["b"]), json=payload()).status_code == 404
    assert ctx["client"].put(f"{path(ctx,ctx['b'])}/entries/{row['id']}", json=payload(revision=1)).status_code == 404
    assert ctx["client"].get(f"{path(ctx,ctx['b'])}/entries/{row['id']}/history").status_code == 404
    ctx["db"].add(ClinicalHistory(patient_id=ctx["b"].id, doctor_id=ctx["doctor"].id,
        center_id=ctx["centers"][0].id, consultation_date=date(2030,1,1)))
    ctx["db"].commit()
    assert ctx["client"].get(path(ctx,ctx["b"])).json() == []
    assert ctx["client"].put(f"{path(ctx,ctx['b'])}/entries/{row['id']}", json=payload(revision=1)).status_code == 404


def test_bootstrap_safety_grants_only_doctors_and_preserves_withdrawn_edit(safety_app):
    ctx = safety_app
    db = ctx["db"]
    ctx["roles"]["doctor"].permissions = [p for p in ctx["roles"]["doctor"].permissions if p.code != "patient_safety:edit"]
    db.commit();seed_identity(db)
    assert "patient_safety:edit" not in {p.code for p in ctx["roles"]["doctor"].permissions}
    for role in ("admin", "secretary"):
        assert not {"patient_safety:view", "patient_safety:edit"}.intersection({p.code for p in ctx["roles"][role].permissions})


def test_host_bound_organization_isolation_including_audit_and_platform(tenant_api):
    app, engine, ids = tenant_api
    app.include_router(patient_safety.router, prefix="/api/v1")
    with Session(engine) as db:
        actor = db.scalar(select(User).where(User.email == "shared@example.com"))
        doctor = db.scalar(select(Role).where(Role.code == "doctor"))
        for membership in actor.memberships:
            membership.roles.append(doctor)
            center = db.scalar(select(CareCenter).where(CareCenter.organization_id == membership.organization_id))
            db.add(ClinicalHistory(organization_id=membership.organization_id, patient_id=ids[membership.organization_id],
                doctor_id=actor.id, center_id=center.id, consultation_date=date(2030,1,1)))
        db.commit()
    with TestClient(app, base_url="http://one.example.test") as one, TestClient(app, base_url="http://two.example.test") as two, TestClient(app, base_url="http://admin.example.test") as platform:
        h1, h2, hp = sign_in(one), sign_in(two), sign_in(platform)
        root = "/api/v1/patient-safety/patients"
        created = one.post(f"{root}/{ids[1]}", headers=h1, json=payload())
        assert created.status_code == 201
        entry_id = created.json()["id"]
        assert two.get(f"{root}/{ids[2]}", headers=h2).json() == []
        assert two.get(f"{root}/{ids[1]}", headers=h2).status_code == 404
        assert two.post(f"{root}/{ids[1]}", headers=h2, json=payload()).status_code == 404
        assert two.put(f"{root}/{ids[2]}/entries/{entry_id}", headers=h2, json=payload(revision=1)).status_code == 404
        assert two.get(f"{root}/{ids[2]}/entries/{entry_id}/history", headers=h2).status_code == 404
        assert platform.get(f"{root}/{ids[1]}", headers=hp).status_code == 403
        assert one.get(f"{root}/{ids[1]}/entries/{entry_id}/history", headers=h1).status_code == 200
