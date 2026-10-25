"""Synthetic clinical episode tests; never uses the official DB."""
from datetime import date,time
import pytest
from fastapi import HTTPException
from sqlalchemy import select,func
from app.models import Appointment,ClinicalHistory,FollowUp,Permission,Role,User,SecretaryCenterScope
from app.models.cardiology import CardiologyAssessment,ClinicalFollowUpPlan,FollowUpContactAttempt
from app.models.clinical_audit import ClinicalAuditLog
from app.schemas.cardiology import CardiologyWrite
from app.services import cardiology as service
from app.services import clinical_follow_up as tasks
from app.api.routes import cardiology,clinical_follow_up
from test_clinical_security_lifecycle import clinical_app
from test_organization_isolation import tenant_api,PASSWORD
from test_clinical_sharing import sharing_app,configure,read

@pytest.fixture
def cardio(clinical_app):
 c=clinical_app;db=c["db"];c["specialty"].code="cardiology"
 for code in ("patients:view","patients:access"):
  permission=db.scalar(select(Permission).where(Permission.code==code))
  if permission is None:permission=Permission(code=code,description=code);db.add(permission)
  c["doctor_a"].roles[0].permissions.append(permission)
 secretary_role=Role(code="secretary",name="Secretaria QA",permissions=[db.scalar(select(Permission).where(Permission.code==p)) for p in ("patients:view","patients:access")])
 sec=User(email="cardio-secretary@example.com",full_name="QA secretary",password_hash="unusable",roles=[secretary_role],centers=[c["center"]])
 db.add(sec);db.flush();db.add(SecretaryCenterScope(secretary_id=sec.id,center_id=c["center"].id,manage_all_doctors=True));db.commit()
 c["secretary"]=sec;c["client"].app.include_router(cardiology.router,prefix="/api/v1");c["client"].app.include_router(clinical_follow_up.router,prefix="/api/v1")
 return c

def url(c):return f"/api/v1/clinical-history/{c['history_a'].id}/cardiology"
def save(c,**values):
 body={"expected_revision":0,"symptoms":{"chest_pain":{"present":True,"detail":"QA finding"}},"examination":{"rhythm":"QA rhythm"},"impression":"QA impression","plan":"QA plan",**values}
 r=c["client"].put(url(c),json=body);assert r.status_code==200,r.text
 return r
def finish(c):
 r=c["client"].post(f"/api/v1/clinical-history/{c['history_a'].id}/complete");assert r.status_code==200,r.text
 return c["db"].scalar(select(FollowUp).where(FollowUp.clinical_history_id==c["history_a"].id))

def test_context_narrative_and_structured_fields(cardio):
 c=cardio;client=c["client"];a=c["appointment_a"]
 context=client.get(f"/api/v1/clinical-history/appointments/{a.id}/context").json();assert context["cardiology_enabled"]
 r=save(c,cardiovascular_history={"hypertension":{"present":False}},studies=[{"category":"ecg","status":"reviewed","note":"QA"}])
 assert r.json()["revision"]==1
 assert client.get(url(c)).json()["symptoms"]["chest_pain"]["detail"]=="QA finding"
 assert c["db"].scalar(select(func.count()).select_from(FollowUp))==0
 r=client.put(url(c),json={"expected_revision":0});assert r.status_code==409
 assert client.put(url(c),json={"expected_revision":1,"symptoms":{"invalid":{"present":True}}}).status_code==422
 assert a.reason is None  # administrative reason is unchanged by the clinical plan

@pytest.mark.parametrize("kind,value,expected",[("days",10,date(2026,9,13)),("weeks",2,date(2026,9,17)),("months",1,date(2026,10,3)),("date",None,date(2026,12,1)),("studies",None,None)])
def test_completion_creates_exactly_one_existing_task(cardio,kind,value,expected):
 c=cardio;f={"kind":kind,"reason":"QA return","condition":"QA studies"}
 if value:f["value"]=value
 if kind=="date":f["date"]="2026-12-01"
 save(c,follow_up=f);task=finish(c);assert task is not None
 assert (task.due_at.date() if task.due_at else None)==expected
 service.complete_follow_up(c["db"],c["doctor_a"],c["history_a"]);c["db"].commit()
 assert c["db"].scalar(select(func.count()).select_from(ClinicalFollowUpPlan))==1
 assert c["db"].scalar(select(func.count()).select_from(FollowUp))==1
 assert c["client"].put(url(c),json={"expected_revision":1}).status_code==409
 assert c["client"].post(f"/api/v1/clinical-history/{c['history_a'].id}/complete").status_code==409

def test_no_follow_up_no_task_and_no_fake_signature(cardio):
 save(cardio);assert finish(cardio) is None
 assert cardio["history_a"].status=="completed"

def test_secretary_operations_append_only_and_clinical_denial(cardio):
 c=cardio;save(c,follow_up={"kind":"days","value":10,"reason":"QA return"});task=finish(c)
 c["active_user"]["value"]=c["secretary"]
 assert c["client"].put(url(c),json={"expected_revision":1}).status_code==403
 inbox=c["client"].get("/api/v1/follow-ups/inbox");assert inbox.status_code==200,inbox.text
 assert inbox.json()["items"][0]["id"]==task.id
 base=f"/api/v1/follow-ups/operational/{task.id}/contacts"
 for result in ("no_answer","retry","studies_ready"):
  r=c["client"].post(base,json={"result":result,"note":"QA operational"});assert r.status_code==201,r.text
 assert len(c["client"].get(base).json())==3
 assert c["client"].get("/api/v1/follow-ups/inbox?status=contacted").json()["items"][0]["status"]=="contacted"
 assert c["client"].put(base,json={}).status_code==405
 assert c["client"].post(base,json={"result":"scheduled"}).status_code==409
 c["db"].refresh(task);assert task.reason=="QA return"

def test_booking_uses_existing_agenda_and_context_lock(cardio):
 c=cardio;save(c,follow_up={"kind":"studies","reason":"QA return"});task=finish(c);c["active_user"]["value"]=c["secretary"]
 body={"patient_id":task.patient_id,"doctor_id":task.doctor_id,"center_id":task.center_id,"specialty_id":c["specialty"].id,"appointment_date":"2026-09-20","appointment_time":"10:00","follow_up_id":task.id}
 response=c["client"].post("/api/v1/appointments",json=body);assert response.status_code==201,response.text
 plan=c["db"].scalar(select(ClinicalFollowUpPlan));assert plan.scheduled_appointment_id==response.json()["id"]
 c["db"].refresh(task);assert task.status=="scheduled"
 assert c["client"].post("/api/v1/appointments",json=body).status_code==409
 assert c["client"].post(f"/api/v1/follow-ups/operational/{task.id}/complete").status_code==403

def test_follow_up_booking_conflict_does_not_link_or_audit(cardio):
 c=cardio;save(c,follow_up={"kind":"studies","reason":"QA return"});task=finish(c)
 c["active_user"]["value"]=c["secretary"]
 body={"patient_id":task.patient_id,"doctor_id":task.doctor_id,"center_id":task.center_id,"specialty_id":c["specialty"].id,"appointment_date":"2026-09-20","appointment_time":"10:00"}
 assert c["client"].post("/api/v1/appointments",json=body).status_code==201
 before=c["db"].scalar(select(func.count()).select_from(ClinicalAuditLog))
 response=c["client"].post("/api/v1/appointments",json={**body,"follow_up_id":task.id})
 assert response.status_code==409,response.text
 plan=c["db"].scalar(select(ClinicalFollowUpPlan));assert plan.scheduled_appointment_id is None
 assert c["db"].scalar(select(func.count()).select_from(ClinicalAuditLog))==before

def test_author_center_and_study_context(cardio):
 c=cardio;c["active_user"]["value"]=c["doctor_b"]
 assert c["client"].get(url(c)).status_code==403
 c["active_user"]["value"]=c["doctor_a"]
 assert c["client"].put(url(c),json={"expected_revision":0,"studies":[{"category":"ecg","status":"reviewed","study_order_id":99999}]}).status_code==422
 save(c,follow_up={"kind":"days","value":1,"reason":"QA"});task=finish(c)
 c["doctor_a"].centers=[];c["db"].commit()
 assert c["client"].get("/api/v1/follow-ups/inbox").json()["items"]==[]
 assert c["client"].get(f"/api/v1/follow-ups/operational/{task.id}/contacts").status_code==403

@pytest.mark.parametrize("data",[{"kind":"days","reason":"QA"},{"kind":"date","reason":"QA"},{"kind":"weeks","value":1},{"kind":"months","value":0,"reason":"QA"}])
def test_follow_up_validation(cardio,data):
 assert cardio["client"].put(url(cardio),json={"expected_revision":0,"follow_up":data}).status_code==422

def test_shared_projection_and_audit_do_not_create_relationship_on_read(cardio):
 c=cardio;save(c)
 before=c["db"].scalar(select(func.count()).select_from(ClinicalAuditLog))
 fields=service.shared_fields(c["db"],c["history_a"])
 assert any(f["value"]=="Sí · QA finding" for f in fields)
 assert any(f["label"]=="Impresión clínica" and f["value"]=="QA impression" for f in fields)
 assert c["db"].scalar(select(func.count()).select_from(ClinicalAuditLog))==before

@pytest.mark.parametrize("key",["dyspnea","palpitations","syncope","dizziness","edema","orthopnea","pnd","claudication","fatigue"])
def test_each_structured_symptom_preserves_optional_detail(cardio,key):
 c=cardio;save(c,symptoms={key:{"present":False,"detail":"QA optional detail"}})
 assert c["client"].get(url(c)).json()["symptoms"][key]=={"present":False,"detail":"QA optional detail"}

def test_return_completion_requires_the_linked_completed_episode(cardio):
 from app.api.routes.clinical_follow_up import complete
 c=cardio;save(c,follow_up={"kind":"days","value":1,"reason":"QA return"});task=finish(c);db=c["db"]
 with pytest.raises(HTTPException) as e: complete(task.id,c["doctor_a"],db)
 assert e.value.status_code==409
 returned_appointment=Appointment(patient_id=task.patient_id,doctor_id=task.doctor_id,center_id=task.center_id,specialty_id=c["specialty"].id,appointment_date=date(2026,9,4),appointment_time=time(9),status="completed")
 db.add(returned_appointment);db.flush()
 returned=ClinicalHistory(patient_id=task.patient_id,doctor_id=task.doctor_id,center_id=task.center_id,specialty_id=c["specialty"].id,appointment_id=returned_appointment.id,consultation_date=date(2026,9,4),status="completed")
 db.add(returned);plan=db.scalar(select(ClinicalFollowUpPlan));plan.scheduled_appointment_id=returned_appointment.id;task.status="scheduled";db.commit()
 assert complete(task.id,c["doctor_a"],db)["status"]=="completed"
 assert complete(task.id,c["doctor_a"],db)["status"]=="completed"
 legacy=c["client"].post(f"/api/v1/follow-ups/{task.id}/complete")
 assert legacy.status_code==200,legacy.text
 assert legacy.json()["status"]=="completed"
 assert legacy.json()["completed_at"] is not None

def test_observations_reuse_existing_structured_vitals(cardio):
 from app.services.clinical_observations import vital_observations
 c=cardio
 response=c["client"].put(f"/api/v1/clinical-history/{c['history_a'].id}/vital-signs",json={"systolic_pressure":120,"diastolic_pressure":80,"weight_kg":80,"height_cm":180,"heart_rate":72})
 assert response.status_code==200,response.text
 from app.models import VitalSigns
 values=vital_observations(c["db"].scalar(select(VitalSigns).where(VitalSigns.clinical_history_id==c["history_a"].id)))
 assert any(v["code"]=="bp.systolic" and v["value"]==120 for v in values)
 assert {v["source"] for v in values}=={"vital_signs"}

def test_cardiology_shared_policy_projects_read_only_without_write_grant(sharing_app):
 from sqlalchemy.orm import Session
 from app.api.routes import vital_signs
 c=sharing_app;c["app"].include_router(cardiology.router,prefix="/api/v1")
 c["app"].include_router(vital_signs.router,prefix="/api/v1")
 with Session(c["engine"]) as db:
  h=db.get(ClinicalHistory,c["ids"]["history"])
  db.add(CardiologyAssessment(organization_id=1,clinical_history_id=h.id,updated_by_user_id=c["ids"]["author"],
   symptoms={"chest_pain":{"present":True,"detail":"QA shared detail"}},impression="QA shared impression",plan="QA shared plan"));db.commit()
 configure(c)
 response=read(c);assert response.status_code==200,response.text
 assert response.json()["read_only"] is True
 fields=response.json()["items"][0]["fields"]
 assert any(f["label"]=="Impresión clínica" and f["value"]=="QA shared impression" for f in fields)
 assert any(f["value"]=="Sí · QA shared detail" for f in fields)
 path=f"/api/v1/clinical-history/{c['ids']['history']}/cardiology"
 assert c["client"].put(path,headers=c["headers"],json={"expected_revision":1,"plan":"forbidden"}).status_code==403
 assert c["client"].put(f"/api/v1/clinical-history/{c['ids']['history']}/vital-signs",headers=c["headers"],json={"heart_rate":70}).status_code==403
 with Session(c["engine"]) as db:
  assert db.scalar(select(CardiologyAssessment)).plan=="QA shared plan"
  assert db.scalar(select(ClinicalAuditLog.id).where(ClinicalAuditLog.action=="clinical_sharing.read")) is not None

def test_http_tenant_boundary_for_new_assessment_and_follow_up(tenant_api):
 from fastapi.testclient import TestClient
 from sqlalchemy.orm import Session
 from app.models import CareCenter,OrganizationMembership,Specialty
 app,engine,pids=tenant_api
 for module in (cardiology,clinical_follow_up): app.include_router(module.router,prefix="/api/v1")
 with Session(engine) as db:
  shared=db.scalar(select(User).where(User.email=="shared@example.com"));role=db.scalar(select(Role).where(Role.code=="doctor"));centers=list(db.scalars(select(CareCenter).order_by(CareCenter.id)))
  doctor=User(email="cardio-tenant@example.com",full_name="QA tenant cardiology",password_hash=shared.password_hash,centers=centers,memberships=[OrganizationMembership(organization_id=i,roles=[role]) for i in (1,2)])
  db.add(doctor);db.flush()
  spec=__import__('app.models',fromlist=['Specialty']).Specialty(organization_id=2,name="Cardio QA",code="cardiology",is_active=True);db.add(spec);db.flush()
  appointment=Appointment(organization_id=2,patient_id=pids[2],doctor_id=doctor.id,center_id=centers[1].id,specialty_id=spec.id,appointment_date=date(2030,1,1),appointment_time=time(8),status="completed");db.add(appointment);db.flush()
  h=ClinicalHistory(organization_id=2,patient_id=pids[2],doctor_id=doctor.id,center_id=centers[1].id,specialty_id=spec.id,appointment_id=appointment.id,consultation_date=date(2030,1,1),status="completed");db.add(h);db.flush()
  t=FollowUp(organization_id=2,patient_id=pids[2],doctor_id=doctor.id,center_id=centers[1].id,clinical_history_id=h.id,reason="QA",due_at=None);db.add(t);db.flush()
  db.add(ClinicalFollowUpPlan(organization_id=2,follow_up_id=t.id,clinical_history_id=h.id,kind="studies",created_by_user_id=doctor.id));db.commit();hid=h.id;tid=t.id
 with TestClient(app,base_url="http://one.example.test") as client:
  token=client.post("/api/v1/auth/login",json={"email":"cardio-tenant@example.com","password":PASSWORD}).json()["access_token"]
  headers={"Authorization":"Bearer "+token}
  assert client.get(f"/api/v1/clinical-history/{hid}/cardiology",headers=headers).status_code==404
  assert client.put(f"/api/v1/clinical-history/{hid}/cardiology",headers=headers,json={"expected_revision":0}).status_code==404
  assert client.get(f"/api/v1/follow-ups/operational/{tid}/contacts",headers=headers).status_code==404
  assert client.post(f"/api/v1/follow-ups/operational/{tid}/contacts",headers=headers,json={"result":"retry"}).status_code==404
  assert client.get("/api/v1/follow-ups/inbox",headers=headers).json()["items"]==[]
