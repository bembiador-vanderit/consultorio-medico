"""Synthetic host-bound tests; no official DB or implicit grants."""
from datetime import date, datetime, timezone

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select, func
from sqlalchemy.orm import Session

from app.api.routes import clinical_sharing, clinical_history, clinical_patient_documents, patient_safety
from app.models import CareCenter, ClinicalHistory, OrganizationMembership, Patient, Role, User
from app.models.clinical_audit import ClinicalAuditLog
from app.models.clinical_patient_document import PreoperativeEvaluation
from app.models.patient_care import PatientCareRelationship
from app.models.patient_safety import PatientSafetyEntry
from app.services import clinical_sharing as service
from app.services.tenancy import bind_scope
from test_organization_isolation import tenant_api, PASSWORD, sign_in
from test_administration_security import proof

BASE = "/api/v1/clinical-sharing"


@pytest.fixture
def sharing_app(tenant_api):
    app, engine, patients = tenant_api
    for module in (clinical_sharing, clinical_history, clinical_patient_documents, patient_safety):
        app.include_router(module.router, prefix="/api/v1")
    with Session(engine) as db:
        doctor = db.scalar(select(Role).where(Role.code == "doctor"))
        shared = db.scalar(select(User).where(User.email == "shared@example.com"))
        centers = list(db.scalars(select(CareCenter).order_by(CareCenter.id)))
        users = [User(email=f"sharing-{i}@example.com", full_name=f"QA Sharing {i}", password_hash=shared.password_hash,
            centers=centers, memberships=[OrganizationMembership(organization_id=oid, roles=[doctor]) for oid in (1,2)]) for i in range(2)]
        db.add_all(users);db.flush()
        history = ClinicalHistory(organization_id=1,patient_id=patients[1],doctor_id=users[0].id,center_id=centers[0].id,
            consultation_date=date(2030,1,1),status="completed",clinical_notes="Sensitive QA history")
        document = PreoperativeEvaluation(organization_id=1,patient_id=patients[1],doctor_id=users[0].id,center_id=centers[0].id,
            document_date=date(2030,1,1),status="signed",content={"procedimiento":"Sensitive QA document"},
            created_by_user_id=users[0].id,last_updated_by_user_id=users[0].id,signed_by_user_id=users[0].id)
        safety = PatientSafetyEntry(organization_id=1,patient_id=patients[1],entry_type="allergy",substance_or_agent="QA agent",
            reaction_description="Sensitive QA safety",source_type="patient_reported",recorded_by_user_id=users[0].id,updated_by_user_id=users[0].id)
        relation = PatientCareRelationship(organization_id=1,patient_id=patients[1],doctor_id=users[1].id,center_id=centers[0].id,
            relationship_type="treating",origin="administrative_assignment",status="active",started_at=datetime.now(timezone.utc),
            created_by_user_id=shared.id,updated_by_user_id=shared.id)
        db.add_all([history,document,safety,relation]);db.commit()
        ids={"author":users[0].id,"reader":users[1].id,"history":history.id,"document":document.id,
             "relation":relation.id,"center":centers[0].id,"other_center":centers[1].id,"safety":safety.id}
    client=TestClient(app,base_url="http://one.example.test")
    admin_headers=sign_in(client)
    response=client.post("/api/v1/auth/login",json={"email":"sharing-1@example.com","password":PASSWORD})
    assert response.status_code==200,response.text
    headers={"Authorization":f"Bearer {response.json()['access_token']}"}
    yield {"app":app,"engine":engine,"client":client,"patients":patients,"ids":ids,"headers":headers,"admin":admin_headers}
    client.close()


def configure(ctx,**values):
    current=ctx["client"].get(BASE+"/policy",headers=ctx["admin"]).json()
    payload={key:current[key] for key in service.POLICY_FIELDS}
    payload.update(mode="active_relationship",clinical_history=True,clinical_documents=False,patient_safety=False,
                   **{})
    payload.update(values,revision=current["revision"],reason="Synthetic QA policy")
    response=ctx["client"].put(BASE+"/policy",headers=proof(ctx["client"],ctx["admin"],"PUT",BASE+"/policy"),json=payload)
    assert response.status_code==200,response.text
    return response.json()


def read(ctx,resource="clinical_history",patient=None,**params):
    return ctx["client"].get(f"{BASE}/patients/{patient or ctx['patients'][1]}/records/{resource}",headers=ctx["headers"],params=params)


def renew_reader(ctx):
    response=ctx["client"].post("/api/v1/auth/login",json={"email":"sharing-1@example.com","password":PASSWORD})
    assert response.status_code==200
    ctx["headers"]={"Authorization":f"Bearer {response.json()['access_token']}"}


def test_default_is_conservative_and_relationship_is_not_a_grant(sharing_app):
    c=sharing_app
    policy=c["client"].get(BASE+"/policy",headers=c["admin"]).json()
    assert policy["mode"]=="assigned" and policy["revision"]==0
    assert not any(policy[r] for r in service.RESOURCES)
    assert read(c).status_code==404
    assert c["client"].get(f"{BASE}/patients/{c['patients'][1]}/capabilities",headers=c["headers"]).json()["resources"]==[]


@pytest.mark.parametrize("status,allowed",[("active",True),("follow_up",True),("historical",False),("ended",False)])
def test_relationship_policy_requires_active_status(sharing_app,status,allowed):
    c=sharing_app;configure(c)
    with Session(c["engine"]) as db:
        row=db.get(PatientCareRelationship,c["ids"]["relation"]);row.status=status
        row.ended_at=datetime.now(timezone.utc) if status=="ended" else None;db.commit()
    response=read(c)
    assert response.status_code==(200 if allowed else 404),response.text
    if allowed:
        assert response.json()["items"][0]["fields"][-1]["value"]=="Sensitive QA history"
        assert response.json()["read_only"] is True


@pytest.mark.parametrize("mode",["same_center","organization"])
def test_center_and_organization_policies_do_not_require_relationship(sharing_app,mode):
    c=sharing_app
    with Session(c["engine"]) as db:
        row=db.get(PatientCareRelationship,c["ids"]["relation"]);row.status="historical";db.commit()
    configure(c,mode=mode,limit_to_same_center=mode=="same_center")
    assert read(c).status_code==200


def test_resource_separation_safety_and_documents_are_read_only(sharing_app):
    c=sharing_app;configure(c,patient_safety=True)
    assert read(c).status_code==200
    assert read(c,"clinical_documents").status_code==404
    result=read(c,"patient_safety");assert result.status_code==200,result.text
    assert result.json()["items"][0]["fields"][2]["value"]=="Sensitive QA safety"
    configure(c,clinical_documents=True,patient_safety=True)
    assert read(c,"clinical_documents").json()["items"][0]["fields"]==[{"label":"Procedimiento previsto","value":"Sensitive QA document"}]
    # Existing write authorizers must not consume the sharing grant.
    doc=c["client"].put(f"/api/v1/clinical-documents/preoperative/{c['ids']['document']}",headers=c["headers"],json={"expected_revision":0,"values":{"procedimiento":"forbidden"}})
    assert doc.status_code in (403,404),doc.text
    with Session(c["engine"]) as db:
        assert db.get(PreoperativeEvaluation,c["ids"]["document"]).content["procedimiento"]=="Sensitive QA document"


@pytest.mark.parametrize("denial",["clinical:access","patients:view","patients:access"])
def test_denied_permissions_override_policy(sharing_app,denial):
    c=sharing_app;configure(c,mode="organization",limit_to_same_center=False)
    with Session(c["engine"]) as db:
        member=db.scalar(select(OrganizationMembership).where(OrganizationMembership.organization_id==1,OrganizationMembership.user_id==c["ids"]["reader"]))
        member.denied_permissions=[denial];db.commit()
    renew_reader(c)
    assert read(c).status_code==403


@pytest.mark.parametrize("resource,denial",[("clinical_documents","clinical_documents:view"),("patient_safety","patient_safety:view")])
def test_resource_rbac_cannot_be_replaced_by_policy(sharing_app,resource,denial):
    c=sharing_app;configure(c,**{resource:True})
    with Session(c["engine"]) as db:
        member=db.scalar(select(OrganizationMembership).where(OrganizationMembership.organization_id==1,OrganizationMembership.user_id==c["ids"]["reader"]))
        member.denied_permissions=[denial];db.commit()
    renew_reader(c)
    assert read(c,resource).status_code==403


def test_outside_center_cannot_be_spoofed_and_null_center_fails_closed(sharing_app):
    c=sharing_app;configure(c,mode="same_center",patient_safety=True)
    with Session(c["engine"]) as db:
        db.get(User,c["ids"]["reader"]).centers=[db.get(CareCenter,c["ids"]["other_center"])];db.commit()
    renew_reader(c)
    assert read(c).status_code==404
    assert read(c,"patient_safety",center_id=c["ids"]["other_center"]).status_code==404


def test_cross_tenant_and_platform_have_no_shared_access(sharing_app):
    c=sharing_app;configure(c,mode="organization",limit_to_same_center=False)
    assert read(c,patient=c["patients"][2]).status_code==404
    with TestClient(c["app"],base_url="http://two.example.test") as other:
        assert other.get(f"{BASE}/patients/{c['patients'][1]}/records/clinical_history",headers=c["headers"]).status_code==401
    with TestClient(c["app"],base_url="http://admin.example.test") as platform:
        headers=sign_in(platform)
        assert platform.get(f"{BASE}/patients/{c['patients'][1]}/records/clinical_history",headers=headers).status_code==403


def test_access_schedule_and_membership_precede_policy(sharing_app):
    c=sharing_app;configure(c)
    with Session(c["engine"]) as db:
        member=db.scalar(select(OrganizationMembership).where(OrganizationMembership.organization_id==1,OrganizationMembership.user_id==c["ids"]["reader"]))
        member.restrict_outside_schedule=True;member.weekly_schedule=[];db.commit()
    assert read(c).status_code in (401,403)  # Restricted schedule also revokes the old lease.


def test_read_audit_is_separate_deduplicated_and_policy_update_audited(sharing_app):
    c=sharing_app;configure(c,patient_safety=True)
    cap=f"{BASE}/patients/{c['patients'][1]}/capabilities"
    for _ in range(2):assert c["client"].get(cap,headers=c["headers"]).status_code==200
    with Session(c["engine"]) as db:
        assert not db.scalar(select(ClinicalAuditLog.id).where(ClinicalAuditLog.action=="clinical_sharing.read"))
    for _ in range(3):assert read(c).status_code==200
    assert read(c,"patient_safety").status_code==200
    with Session(c["engine"]) as db:
        logs=db.scalars(select(ClinicalAuditLog).where(ClinicalAuditLog.action=="clinical_sharing.read")).all()
        assert len(logs)==2
        assert {r.resource_type for r in logs}=={"shared_clinical_history","shared_patient_safety"}
        assert all(r.user_id==c["ids"]["reader"] and r.context["read_only"] for r in logs)
        assert "Sensitive QA" not in str([r.context for r in logs])
        update=db.scalar(select(ClinicalAuditLog).where(ClinicalAuditLog.action=="clinical_sharing.policy_updated"))
        assert update.context["before"] is None and update.context["after"]["mode"]=="active_relationship"


def test_decision_reasons_and_assigned_context_hook(sharing_app):
    c=sharing_app;configure(c)
    with Session(c["engine"]) as db:
        bind_scope(db,"tenant",1);user=db.get(User,c["ids"]["reader"])
        decision=service.decide(db,user,c["patients"][1],"clinical_history",center_id=c["ids"]["center"])
        assert decision.allowed and decision.reason=="active_care_relationship"
        assert not service.decide(db,user,c["patients"][2],"clinical_history").allowed
        assert service.decide(db,user,c["patients"][1],"clinical_documents").reason=="resource_not_shared"
        assert service.decide(db,user,c["patients"][1],"clinical_history",care_context_id=999).reason=="invalid_context"
    configure(c,mode="assigned")
    with Session(c["engine"]) as db:
        bind_scope(db,"tenant",1);user=db.get(User,c["ids"]["author"])
        assert service.decide(db,user,c["patients"][1],"clinical_history",center_id=c["ids"]["center"],care_context_id=c["ids"]["history"]).reason=="assigned_context"
    assert not service.future_episode_access(doctor_id=1,patient_id=1,organization_id=1,care_context_id=1,resource_type="clinical_history").allowed


def test_configuration_reauth_revision_and_no_non_admin_updates(sharing_app):
    c=sharing_app
    assert c["client"].get(BASE+"/policy",headers=c["headers"]).status_code==403
    assert c["client"].put(BASE+"/policy",headers=c["headers"],json={"revision":0,"reason":"QA policy"}).status_code==403
    assert c["client"].put(BASE+"/policy",headers=c["admin"],json={"revision":0,"reason":"QA policy"}).status_code==428
    configure(c)
    response=c["client"].put(BASE+"/policy",headers=proof(c["client"],c["admin"],"PUT",BASE+"/policy"),json={"revision":0,"reason":"QA stale policy"})
    assert response.status_code==409


def test_shared_endpoint_has_no_write_methods(sharing_app):
    c=sharing_app;configure(c)
    path=f"{BASE}/patients/{c['patients'][1]}/records/clinical_history"
    for method in ("post","put","patch","delete"):
        assert getattr(c["client"],method)(path,headers=c["headers"]).status_code==405


def test_existing_patient_search_discovers_shared_identity_but_never_grants_edit(sharing_app):
    c=sharing_app;pid=c["patients"][1]
    assert c["client"].get("/api/v1/patients",headers=c["headers"]).json()==[]
    configure(c)
    response=c["client"].get("/api/v1/patients",headers=c["headers"])
    assert [r["id"] for r in response.json()]==[pid]
    assert c["client"].get("/api/v1/patients/count",headers=c["headers"]).json()=={"count":1}
    detail=c["client"].get(f"/api/v1/patients/{pid}",headers=c["headers"])
    assert detail.status_code==200 and detail.json()["shared_read_only"] is True
    assert detail.json()["document_number"] is None  # Not expanded demographics.
    response=c["client"].put(f"/api/v1/patients/{pid}",headers=c["headers"],json={"first_name":"Changed","last_name":"QA","date_of_birth":"1990-01-01"})
    assert response.status_code==404
    assert c["client"].get(f"/api/v1/patients/{c['patients'][2]}",headers=c["headers"]).status_code==404


def test_shared_access_never_authorizes_history_or_safety_mutations(sharing_app):
    c=sharing_app;configure(c,patient_safety=True)
    assert read(c).status_code==200
    result=c["client"].put(f"/api/v1/clinical-history/{c['ids']['history']}",headers=c["headers"],json={"consultation_date":"2030-01-01","expected_revision":1,"clinical_notes":"forbidden"})
    assert result.status_code==403,result.text
    result=c["client"].put(f"/api/v1/patient-safety/patients/{c['patients'][1]}/entries/{c['ids']['safety']}",headers=c["headers"],json={"revision":1,"entry_type":"allergy","substance_or_agent":"forbidden","reaction_description":"QA","severity":"mild","status":"active","source_type":"patient_reported"})
    assert result.status_code==404,result.text
    with Session(c["engine"]) as db:
        assert db.get(ClinicalHistory,c["ids"]["history"]).clinical_notes=="Sensitive QA history"
        assert db.get(PatientSafetyEntry,c["ids"]["safety"]).substance_or_agent=="QA agent"


def test_policy_revocation_is_effective_on_next_read_and_discovery(sharing_app):
    c=sharing_app;configure(c);assert read(c).status_code==200
    configure(c,mode="assigned")
    assert read(c).status_code==404
    assert c["client"].get("/api/v1/patients",headers=c["headers"]).json()==[]


def test_missing_staged_schema_does_not_break_existing_authorized_reads(sharing_app):
    c=sharing_app
    from app.models.clinical_sharing import ClinicalSharingPolicy
    ClinicalSharingPolicy.__table__.drop(c["engine"])
    assert c["client"].get(BASE+"/policy",headers=c["admin"]).json()["enabled"] is False
    assert c["client"].get(f"{BASE}/patients/{c['patients'][1]}/capabilities",headers=c["headers"]).json()=={"enabled":False,"resources":[]}
    assert c["client"].get("/api/v1/patients",headers=c["headers"]).status_code==200


def test_episode_and_break_glass_are_not_configurable_grants(sharing_app):
    c=sharing_app
    for mode in ("episode","break_glass"):
        response=c["client"].put(BASE+"/policy",headers=proof(c["client"],c["admin"],"PUT",BASE+"/policy"),json={"revision":0,"reason":"QA no future grants","mode":mode})
        assert response.status_code==422
