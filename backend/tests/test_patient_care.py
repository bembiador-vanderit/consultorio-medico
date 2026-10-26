"""Synthetic HTTP regression tests: discovery must never imply clinical access."""
from datetime import date, datetime, timedelta, timezone

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.api.routes import patient_care
from app.models import Appointment, CareCenter, ClinicalHistory, Organization, Permission, Role, User
from app.models.clinical_audit import ClinicalAuditLog
from app.models.patient_care import PatientCareRelationship as Relationship
from app.services import patient_care as care
from app.services.bootstrap import seed_identity
from test_patient_security import patient_app
from test_organization_isolation import tenant_api, sign_in


@pytest.fixture
def care_app(patient_app):
    ctx = patient_app
    db = ctx["db"]
    if db.get(Organization,1) is None:
        db.add(Organization(id=1,slug="pilot",name="QA Organization"))
    view,manage = Permission(code=care.VIEW,description="QA view"), Permission(code=care.MANAGE,description="QA manage")
    ctx["roles"]["doctor"].permissions.append(view)
    ctx["roles"]["admin"].permissions.extend([view,manage])
    db.commit()
    ctx["client"].app.include_router(patient_care.router,prefix="/api/v1")
    return ctx


def path(ctx,patient=None):
    return f"/api/v1/patient-care/patients/{(patient or ctx['a']).id}/relationships"


def payload(ctx,**changes):
    return {"doctor_id":ctx["doctor"].id,"reason":"Asignación sintética QA",**changes}


def assign(ctx,**changes):
    ctx["active"]["user"] = ctx["admin"]
    response = ctx["client"].post(path(ctx),json=payload(ctx,**changes))
    assert response.status_code==201,response.text
    return response.json()


@pytest.mark.parametrize("kind",["treating","consultant","specialist_followup","primary"])
def test_valid_manual_assignment_optional_context_and_not_actual_care(care_app,kind):
    ctx = care_app
    row = assign(ctx,relationship_type=kind)
    assert row["patient_id"]==ctx["a"].id and row["doctor_id"]==ctx["doctor"].id
    assert row["organization_id"]==1 and row["origin"]=="administrative_assignment"
    assert row["first_seen_at"] is row["last_seen_at"] is None
    assert row["center_id"] is row["specialty_id"] is None
    assert row["created_by_user_id"]==ctx["admin"].id
    assert row["status"]=="active"


def test_repeat_assign_is_idempotent_no_reopen_no_rewrite_origin(care_app):
    ctx=care_app
    row=assign(ctx,status="ended")
    assert row["ended_at"] is not None
    second=ctx["client"].post(path(ctx),json=payload(ctx,status="active"))
    assert second.status_code==200 and second.json()["id"]==row["id"]
    assert second.json()["status"]=="ended"
    assert ctx["db"].scalar(select(func.count()).select_from(Relationship))==1
    assert ctx["db"].scalar(select(func.count()).select_from(ClinicalAuditLog))==1


@pytest.mark.parametrize("state",["active","follow_up","historical","ended"])
def test_states_reasons_revision_and_audit(care_app,state):
    ctx=care_app
    row=assign(ctx)
    url=f"{path(ctx)}/{row['id']}"
    body={"revision":1,"status":state,"relationship_type":"consultant","reason":"Cambio QA controlado"}
    response=ctx["client"].put(url,json=body)
    assert response.status_code==200,response.text
    assert response.json()["status"]==state
    assert bool(response.json()["ended_at"])==(state=="ended")
    assert ctx["client"].put(url,json=body).status_code==409
    assert ctx["client"].put(url,json={**body,"revision":2,"reason":" "}).status_code==422
    before=ctx["db"].scalar(select(func.count()).select_from(ClinicalAuditLog))
    assert ctx["client"].put(url,json={**body,"revision":2}).status_code==200
    assert ctx["db"].scalar(select(func.count()).select_from(ClinicalAuditLog))==before
    events=ctx["client"].get(url+"/history").json()
    assert events[0]["action"]=="patient_care.manual_assigned"
    assert events[1]["context"]["before"]["relationship_type"]=="treating"
    assert events[1]["context"]["after"]["relationship_type"]=="consultant"
    assert events[1]["context"]["reason"]=="Cambio QA controlado"
    assert ctx["client"].delete(url).status_code==405


def test_manual_reactivation_keeps_same_identity_and_first_origin(care_app):
    ctx=care_app
    row=assign(ctx,status="ended")
    result=ctx["client"].put(f"{path(ctx)}/{row['id']}",json={"revision":1,"status":"follow_up","reason":"Reactivar QA"})
    assert result.status_code==200 and result.json()["ended_at"] is None
    assert result.json()["origin"]==row["origin"] and result.json()["started_at"]==row["started_at"]
    assert ctx["client"].get(f"{path(ctx)}/{row['id']}/history").json()[-1]["action"]=="patient_care.reactivated"


@pytest.mark.parametrize("role",["doctor","secretary","no_permission"])
def test_only_explicit_admin_can_assign_or_modify(care_app,role):
    ctx=care_app
    row=assign(ctx)
    ctx["active"]["user"]=ctx[role]
    assert ctx["client"].post(path(ctx),json=payload(ctx)).status_code==403
    assert ctx["client"].put(f"{path(ctx)}/{row['id']}",json={"revision":1,"reason":"QA denegado"}).status_code==403
    if role!="doctor":
        assert ctx["client"].get(path(ctx)).status_code==403


@pytest.mark.parametrize("denial",[care.VIEW,care.MANAGE,"patients:view","users:manage"])
def test_denials_preserved(care_app,denial):
    ctx=care_app
    ctx["admin"].denied_permissions=[denial]
    ctx["db"].commit();ctx["active"]["user"]=ctx["admin"]
    assert ctx["client"].post(path(ctx),json=payload(ctx)).status_code==403


@pytest.mark.parametrize("changes",[{"origin":"consultation"},{"organization_id":2},{"patient_id":2},{"last_seen_at":"2030-01-01"},{"relationship_type":"historical"},{"status":"invented"},{"created_by_user_id":1}])
def test_no_forged_origin_context_or_actors(care_app,changes):
    ctx=care_app;ctx["active"]["user"]=ctx["admin"]
    assert ctx["client"].post(path(ctx),json=payload(ctx,**changes)).status_code==422


def test_assignment_checks_doctor_center_and_specialty(care_app):
    ctx=care_app
    own=ctx["db"].scalar(select(Appointment).where(Appointment.doctor_id==ctx["doctor"].id))
    row=assign(ctx,center_id=own.center_id,specialty_id=own.specialty_id)
    assert row["center_name"] and row["specialty_name"]
    for changes in ({"doctor_id":ctx["secretary"].id},{"center_id":99999},{"specialty_id":99999}):
        assert ctx["client"].post(path(ctx),json=payload(ctx,**changes)).status_code==404


def test_own_list_discovery_is_not_clinical_or_safety_access(care_app):
    ctx=care_app
    # B has only the other physician's appointments. A manual association must
    # not grant the authenticated doctor access to its existing clinical record.
    ctx["active"]["user"]=ctx["admin"]
    created=ctx["client"].post(path(ctx,ctx["b"]),json=payload(ctx,status="follow_up"))
    assert created.status_code==201
    ctx["active"]["user"]=ctx["doctor"]
    mine=ctx["client"].get("/api/v1/patient-care/my-patients?status=follow_up")
    assert mine.status_code==200 and len(mine.json())==1
    assert mine.json()[0]["patient"]["id"]==ctx["b"].id
    assert mine.json()[0]["clinical_access_granted"] is False
    assert ctx["client"].get("/api/v1/patient-care/my-patients?status=active").json()==[]
    assert ctx["client"].get("/api/v1/patient-care/my-patients?center_id=99999").status_code==403
    assert ctx["client"].get(f"/api/v1/patients/{ctx['b'].id}").status_code==404
    assert ctx["client"].get(f"/api/v1/clinical-history/patients/{ctx['b'].id}").status_code==404
    with pytest.raises(HTTPException) as error:
        # No new relationship is ever consulted by clinical scope.
        from app.services.patient_scope import require_patient_clinical_scope
        require_patient_clinical_scope(ctx["db"],ctx["doctor"],ctx["b"].id)
    assert error.value.status_code==404
    assert ctx["client"].get(path(ctx,ctx["b"])).status_code==404


def test_cross_patient_id_and_audit_scoping(care_app):
    ctx=care_app;row=assign(ctx)
    assert ctx["client"].get(f"{path(ctx,ctx['b'])}/{row['id']}/history").status_code==404
    assert ctx["client"].put(f"{path(ctx,ctx['b'])}/{row['id']}",json={"revision":1,"reason":"QA cross-patient"}).status_code==404
    assert not [r for r in ctx["client"].get("/api/v1/clinical-history/audit-logs").json() if r["resource_type"]=="patient_care_relationship"]


def clinical_history(ctx):
    appointment=ctx["db"].scalar(select(Appointment).where(Appointment.doctor_id==ctx["doctor"].id))
    row=ClinicalHistory(patient_id=appointment.patient_id,doctor_id=appointment.doctor_id,center_id=appointment.center_id,
        specialty_id=appointment.specialty_id,appointment_id=appointment.id,consultation_date=date(2030,1,1))
    ctx["db"].add(row);ctx["db"].commit()
    return row,appointment


def test_only_valid_completion_creates_relationship_and_reads_do_not(care_app):
    ctx=care_app
    row,appointment=clinical_history(ctx)
    assert ctx["client"].get(f"/api/v1/patients/{ctx['a'].id}").status_code==200
    assert ctx["client"].get(path(ctx)).json()==[]
    assert ctx["db"].scalar(select(func.count()).select_from(Relationship))==0
    response=ctx["client"].post(f"/api/v1/clinical-history/{row.id}/complete")
    assert response.status_code==200,response.text
    relation=ctx["client"].get(path(ctx)).json()[0]
    assert relation["origin"]=="consultation" and relation["status"]=="active"
    assert relation["created_from_clinical_history_id"]==row.id
    assert relation["last_seen_at"] and relation["first_seen_at"]
    before=ctx["db"].scalar(select(func.count()).select_from(ClinicalAuditLog))
    care.observe_completed_consultation(ctx["db"],ctx["doctor"],row);ctx["db"].commit()
    assert ctx["db"].scalar(select(func.count()).select_from(ClinicalAuditLog))==before


def test_cancelled_appointment_and_in_progress_history_do_not_create(care_app):
    ctx=care_app
    row,appointment=clinical_history(ctx)
    with pytest.raises(HTTPException):
        care.observe_completed_consultation(ctx["db"],ctx["doctor"],row)
    appointment.status="cancelled";ctx["db"].commit()
    assert ctx["client"].post(f"/api/v1/clinical-history/{row.id}/complete").status_code==409
    assert ctx["db"].scalar(select(func.count()).select_from(Relationship))==0


def test_next_consultation_updates_monotonic_seen_context_and_preserves_origin(care_app):
    ctx=care_app
    relation=assign(ctx,status="follow_up",relationship_type="specialist_followup")
    ctx["active"]["user"]=ctx["doctor"]
    first,_=clinical_history(ctx)
    first.status="completed";first.completed_at=datetime.now(timezone.utc);ctx["db"].commit()
    care.observe_completed_consultation(ctx["db"],ctx["doctor"],first);ctx["db"].commit()
    second=ClinicalHistory(patient_id=first.patient_id,doctor_id=first.doctor_id,center_id=ctx["centers"][1].id,
        specialty_id=None,consultation_date=date(2030,1,2),status="completed",completed_at=datetime.now(timezone.utc)+timedelta(days=1))
    ctx["db"].add(second);ctx["db"].commit()
    care.observe_completed_consultation(ctx["db"],ctx["doctor"],second);ctx["db"].commit()
    current=ctx["db"].get(Relationship,relation["id"])
    assert current.origin=="administrative_assignment" and current.relationship_type=="specialist_followup"
    assert current.status=="follow_up" and current.center_id==second.center_id
    assert care.utc(current.last_seen_at)==care.utc(second.completed_at)
    assert care.utc(current.first_seen_at)==care.utc(first.completed_at)
    assert ctx["db"].scalar(select(func.count()).select_from(Relationship))==1


@pytest.mark.parametrize("previous_status",["ended","historical"])
def test_new_attention_reactivates_but_delayed_old_attention_does_not(care_app,previous_status):
    ctx=care_app
    assigned=assign(ctx,status=previous_status)
    relation=ctx["db"].get(Relationship,assigned["id"])
    boundary=care.utc(relation.updated_at)
    first,_=clinical_history(ctx)
    first.status="completed";first.completed_at=boundary-timedelta(minutes=1);ctx["db"].commit()
    care.observe_completed_consultation(ctx["db"],ctx["doctor"],first);ctx["db"].commit()
    assert relation.status==previous_status
    second=ClinicalHistory(patient_id=first.patient_id,doctor_id=first.doctor_id,
        consultation_date=date(2030,1,2),status="completed",completed_at=datetime.now(timezone.utc)+timedelta(minutes=1))
    ctx["db"].add(second);ctx["db"].commit()
    care.observe_completed_consultation(ctx["db"],ctx["doctor"],second);ctx["db"].commit()
    assert relation.status=="active" and relation.ended_at is None
    assert relation.id==assigned["id"] and relation.origin=="administrative_assignment"
    assert care.utc(relation.first_seen_at)==care.utc(first.completed_at)
    assert care.utc(relation.last_seen_at)==care.utc(second.completed_at)
    events=ctx["db"].scalars(select(ClinicalAuditLog).where(ClinicalAuditLog.resource_type=="patient_care_relationship")).all()
    assert events[-1].action=="patient_care.reactivated"
    revision=relation.revision
    care.observe_completed_consultation(ctx["db"],ctx["doctor"],first);ctx["db"].commit()
    assert relation.revision==revision and relation.last_clinical_history_id==second.id


def test_relationship_sql_failure_rolls_back_clinical_completion(care_app,monkeypatch):
    ctx=care_app
    history,appointment=clinical_history(ctx)
    original_status,original_revision=appointment.status,history.revision
    original_audit=care.audit
    def fail_after_relation_insert(*args,**kwargs):
        original_audit(*args,**kwargs)
        raise SQLAlchemyError("Synthetic failure, no sensitive payload")
    monkeypatch.setattr(care,"audit",fail_after_relation_insert)
    response=ctx["client"].post(f"/api/v1/clinical-history/{history.id}/complete")
    assert response.status_code==500
    ctx["db"].refresh(history);ctx["db"].refresh(appointment)
    assert history.status=="in_progress" and history.completed_at is None
    assert history.revision==original_revision and appointment.status==original_status
    assert ctx["db"].scalar(select(func.count()).select_from(Relationship))==0
    assert ctx["db"].scalar(select(func.count()).select_from(ClinicalAuditLog).where(
        ClinicalAuditLog.resource_type=="patient_care_relationship"))==0


def test_staged_schema_absence_does_not_break_clinical_completion(care_app):
    ctx=care_app
    row,_=clinical_history(ctx)
    Relationship.__table__.drop(ctx["db"].get_bind())
    assert ctx["client"].get("/api/v1/patient-care/capabilities").json()["enabled"] is False
    response=ctx["client"].post(f"/api/v1/clinical-history/{row.id}/complete")
    assert response.status_code==200 and response.json()["status"]=="completed"


def test_bootstrap_preserves_withdrawn_care_permissions(care_app):
    ctx=care_app
    ctx["roles"]["doctor"].permissions=[p for p in ctx["roles"]["doctor"].permissions if p.code!=care.VIEW]
    ctx["roles"]["admin"].permissions=[p for p in ctx["roles"]["admin"].permissions if p.code!=care.MANAGE]
    ctx["db"].commit();seed_identity(ctx["db"])
    assert care.VIEW not in {p.code for p in ctx["roles"]["doctor"].permissions}
    assert care.MANAGE not in {p.code for p in ctx["roles"]["admin"].permissions}
    assert not {care.VIEW,care.MANAGE}.intersection({p.code for p in ctx["roles"]["secretary"].permissions})


def test_host_bound_tenant_isolation_for_create_read_update_and_history(tenant_api):
    app,engine,ids=tenant_api
    app.include_router(patient_care.router,prefix="/api/v1")
    with Session(engine) as db:
        actor=db.scalar(select(User).where(User.email=="shared@example.com"))
        doctor=db.scalar(select(Role).where(Role.code=="doctor"))
        for membership in actor.memberships:membership.roles.append(doctor)
        actor_id=actor.id;db.commit()
    with TestClient(app,base_url="http://one.example.test") as one,TestClient(app,base_url="http://two.example.test") as two,TestClient(app,base_url="http://admin.example.test") as platform:
        h1,h2,hp=sign_in(one),sign_in(two),sign_in(platform)
        root="/api/v1/patient-care/patients"
        body={"doctor_id":actor_id,"reason":"QA tenant assignment"}
        created=one.post(f"{root}/{ids[1]}/relationships",json=body,headers=h1)
        assert created.status_code==201,created.text
        rel_id=created.json()["id"]
        assert two.get(f"{root}/{ids[2]}/relationships",headers=h2).json()==[]
        assert two.get(f"{root}/{ids[1]}/relationships",headers=h2).status_code==404
        assert two.post(f"{root}/{ids[1]}/relationships",json=body,headers=h2).status_code==404
        assert two.put(f"{root}/{ids[2]}/relationships/{rel_id}",json={"revision":1,"reason":"QA denied"},headers=h2).status_code==404
        assert two.get(f"{root}/{ids[2]}/relationships/{rel_id}/history",headers=h2).status_code==404
        assert platform.get(f"{root}/{ids[1]}/relationships",headers=hp).status_code==403
