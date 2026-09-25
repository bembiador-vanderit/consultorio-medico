"""6C5 HTTP contracts, tenant boundaries, capabilities and durable snapshots."""
from datetime import date, time
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session
from app.api.routes import insurance, appointments
from app.models import Appointment, CareCenter, Patient, Role, User, OrganizationMembership, SecretaryCenterScope
from app.models.insurance import InsuranceCompany, InsurancePlan, PatientInsurance, AppointmentCoverage
from app.models.administration import SecurityAudit
from test_organization_isolation import tenant_api, sign_in, PASSWORD

@pytest.fixture
def insurance_api(tenant_api):
    app, engine, ids = tenant_api
    app.include_router(insurance.router, prefix='/api/v1')
    app.include_router(appointments.router, prefix='/api/v1')
    data = {}
    with Session(engine) as db:
        actor = db.scalar(select(User).where(User.email == 'shared@example.com'))
        for org in (1, 2):
            company = InsuranceCompany(organization_id=org, name='ARS de prueba', code='SYNTHETIC')
            db.add(company); db.flush()
            plan = InsurancePlan(organization_id=org, insurance_company_id=company.id, name='Plan prueba')
            db.add(plan); db.flush()
            policy = PatientInsurance(organization_id=org, patient_id=ids[org], insurance_company_id=company.id,
                plan_id=plan.id, plan_name=plan.name, member_number='SYNTHETIC', is_primary=True, valid_from=date(2026,1,1), valid_until=date(2026,12,31))
            center = db.scalar(select(CareCenter).where(CareCenter.organization_id == org))
            appt = Appointment(organization_id=org, patient_id=ids[org], doctor_id=actor.id, center_id=center.id,
                appointment_date=date(2026,10,1), appointment_time=time(10))
            db.add_all([policy, appt]); db.flush()
            data[org] = dict(company=company.id, plan=plan.id, policy=policy.id, appointment=appt.id, center=center.id, patient=ids[org])
        db.commit()
    with TestClient(app, base_url='http://one.example.test') as client:
        yield client, sign_in(client), engine, data


def coverage(d, **changes):
    return dict(patient_insurance_id=d['policy'], service='Consulta general', base_amount='1500.00', covered_amount='1000.00', patient_copay='500.00', **changes)


def path(d):
    return f"/api/v1/insurance/appointments/{d['appointment']}/coverage"


def affiliate(d, **changes):
    return {"insurance_company_id": d['company'], "plan_id": d['plan'], "member_number": "SYNTHETIC", **changes}


def authorized(client, headers, method, url):
    proof = client.post('/api/v1/administration/reauthenticate', headers=headers, json={'password': PASSWORD, 'method': method, 'path': url})
    assert proof.status_code == 200, proof.text
    return {**headers, 'X-Reauthentication': proof.json()['proof']}


def test_catalogs_and_patient_lists_are_tenant_scoped(insurance_api):
    c,h,_,d = insurance_api
    assert [x['id'] for x in c.get('/api/v1/insurance/companies', headers=h).json()] == [d[1]['company']]
    assert [x['id'] for x in c.get('/api/v1/insurance/plans', headers=h).json()] == [d[1]['plan']]
    assert c.get(f"/api/v1/insurance/plans?insurance_company_id={d[2]['company']}", headers=h).status_code == 404
    assert c.get(f"/api/v1/insurance/patients/{d[2]['patient']}", headers=h).status_code == 404
    assert c.get(path(d[2]), headers=h).status_code == 404
    assert c.put(path(d[2]), headers=h, json=coverage(d[1])).status_code == 404


@pytest.mark.parametrize('field', ['company','plan'])
def test_foreign_affiliation_relations_rejected(insurance_api, field):
    c,h,_,d = insurance_api
    body = affiliate(d[1]); body['insurance_company_id' if field=='company' else 'plan_id'] = d[2][field]
    assert c.post(f"/api/v1/insurance/patients/{d[1]['patient']}", headers=h, json=body).status_code == 422


def test_cross_tenant_catalog_writes_and_foreign_patient_insurance_rejected(insurance_api):
    c,h,_,d = insurance_api
    url = f"/api/v1/insurance/companies/{d[2]['company']}"
    assert c.put(url, headers=authorized(c,h,'PUT',url), json={'name':'Invisible'}).status_code == 404
    url = f"/api/v1/insurance/plans/{d[2]['plan']}"
    assert c.put(url, headers=authorized(c,h,'PUT',url), json={'name':'Invisible','insurance_company_id':d[1]['company']}).status_code == 404
    url = '/api/v1/insurance/plans'
    assert c.post(url, headers=authorized(c,h,'POST',url), json={'name':'Invisible','insurance_company_id':d[2]['company']}).status_code == 422
    assert c.put(path(d[1]), headers=h, json=coverage(d[2])).status_code == 422
    url = f"/api/v1/insurance/patients/{d[1]['patient']}/{d[2]['policy']}"
    assert c.put(url, headers=h, json=affiliate(d[1])).status_code == 404
    assert c.delete(url, headers=h).status_code == 404


def test_same_tenant_wrong_patient_policy_rejected(insurance_api):
    c,h,engine,d = insurance_api
    with Session(engine) as db:
        other = Patient(organization_id=1, first_name='Other',last_name='Synthetic',date_of_birth=date(1990,1,1)); db.add(other); db.flush()
        row = db.get(PatientInsurance,d[1]['policy']); row.patient_id=other.id; db.commit()
    assert c.put(path(d[1]), headers=h, json=coverage(d[1])).status_code == 422


def test_snapshot_survives_affiliation_plan_and_company_edits(insurance_api):
    c,h,engine,d = insurance_api
    saved = c.put(path(d[1]), headers=h, json=coverage(d[1]))
    assert saved.status_code == 200, saved.text
    original = saved.json()
    assert original['expected_insurer_balance'] == '1000.00'
    url = f"/api/v1/insurance/patients/{d[1]['patient']}/{d[1]['policy']}"
    response = c.put(url, headers=h, json=affiliate(d[1],member_number='CHANGED',policy_holder='Titular sintético'))
    assert response.status_code == 200, response.text
    with Session(engine) as db:
        db.get(InsurancePlan,d[1]['plan']).name='Renamed'
        db.get(InsuranceCompany,d[1]['company']).name='Renamed ARS'; db.commit()
    assert c.delete(url, headers=h).status_code == 204
    response = c.put(path(d[1]), headers=h, json=coverage(d[1],revision=1,authorization_status='authorized',authorization_number='TEST-AUTH'))
    assert response.status_code == 200, response.text
    assert response.json()['insurance_snapshot'] == original['insurance_snapshot']
    assert response.json()['revision'] == 2
    assert c.put(path(d[1]), headers=h, json=coverage(d[1],revision=1)).status_code == 409
    assert c.delete(f"/api/v1/appointments/{d[1]['appointment']}",headers=h).status_code == 409
    with Session(engine) as db:
        logs = db.scalars(select(SecurityAudit).where(SecurityAudit.action.like('insurance:%'))).all()
        assert logs and all(row.organization_id==1 for row in logs)
        assert any(row.center_id==d[1]['center'] and 'authorization_authorized' in row.action for row in logs)
        assert all('TEST-AUTH' not in row.action and 'SYNTHETIC' not in row.action for row in logs)


@pytest.mark.parametrize('change', [dict(base_amount='-1'),dict(patient_copay='501'),dict(covered_amount='NaN'),dict(base_amount='1.001'),dict(authorized_amount='-1'),dict(authorization_status='unknown'),dict(authorization_status='authorized'),dict(authorized_at='2026-01-01T10:00:00')])
def test_invalid_financial_and_authorization_values(insurance_api,change):
    c,h,_,d = insurance_api
    body=coverage(d[1]); body.update(change)
    assert c.put(path(d[1]),headers=h,json=body).status_code==422
    assert c.get(path(d[1]),headers=h).json() is None


def test_expiration_primary_and_legacy_update_permissions(insurance_api):
    c,h,engine,d=insurance_api
    url=f"/api/v1/insurance/patients/{d[1]['patient']}"
    assert c.post(url,headers=h,json=affiliate(d[1],valid_from='2026-12-31',valid_until='2026-01-01')).status_code==422
    assert c.post(url,headers=h,json=affiliate(d[1],valid_until='2026-01-01')).status_code==201
    policies=c.get(url,headers=h).json()
    assert sum(p['is_primary'] for p in policies)==1
    newest=next(p for p in policies if p['is_primary'])
    body=coverage(d[1]); body['patient_insurance_id']=newest['id']
    assert c.put(path(d[1]),headers=h,json=body).status_code==422
    with Session(engine) as db:
        member=db.scalar(select(OrganizationMembership).where(OrganizationMembership.organization_id==1))
        member.roles=[db.scalar(select(Role).where(Role.code=='doctor'))]; db.commit()
    h=sign_in(c)
    assert c.get(url,headers=h).status_code==200
    assert c.get(path(d[1]),headers=h).status_code==200
    assert c.post(url,headers=h,json=affiliate(d[1])).status_code==403
    assert c.put(path(d[1]),headers=h,json=coverage(d[1])).status_code==403
    assert c.put(f"/api/v1/patients/{d[1]['patient']}",headers=h,json={'first_name':'One','last_name':'Patient','date_of_birth':'1990-01-01','has_insurance':False}).status_code==403


def test_secretary_scope_and_individual_denials(insurance_api):
    c,h,engine,d=insurance_api
    with Session(engine) as db:
        member=db.scalar(select(OrganizationMembership).where(OrganizationMembership.organization_id==1))
        member.roles=[db.scalar(select(Role).where(Role.code=='secretary'))]
        db.add(SecretaryCenterScope(organization_id=1,secretary_id=member.user_id,center_id=d[1]['center'],manage_all_doctors=True))
        db.commit()
    h=sign_in(c)
    assert c.put(path(d[1]),headers=h,json=coverage(d[1])).status_code==200
    with Session(engine) as db:
        member=db.scalar(select(OrganizationMembership).where(OrganizationMembership.organization_id==1))
        member.denied_permissions=['insurance:manage']; db.commit()
    h=sign_in(c)
    assert c.put(path(d[1]),headers=h,json=coverage(d[1],revision=1)).status_code==403
    assert c.get(path(d[1]),headers=h).status_code==200
    with Session(engine) as db:
        member=db.scalar(select(OrganizationMembership).where(OrganizationMembership.organization_id==1))
        member.denied_permissions=[]
        scope=db.scalar(select(SecretaryCenterScope)); scope.manage_all_doctors=False; db.commit()
    h=sign_in(c)
    assert c.get(path(d[1]),headers=h).status_code==403


def test_private_coverage_and_completed_affiliation_lock(insurance_api):
    c,h,engine,d=insurance_api
    body=coverage(d[1]); body.update(patient_insurance_id=None,covered_amount='0',patient_copay='1500',authorization_status='not_required')
    response=c.put(path(d[1]),headers=h,json=body)
    assert response.status_code==200,response.text
    assert response.json()['insurance_snapshot']=={}
    with Session(engine) as db:
        db.get(Appointment,d[1]['appointment']).status='completed'; db.commit()
    assert c.put(path(d[1]),headers=h,json=coverage(d[1],revision=1)).status_code==409
