"""6C7 ARS workflow, balances, permissions and tenant isolation."""
from datetime import date, time
from uuid import uuid4
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session
from app.api.routes import ars, finance
from app.models import Appointment, OrganizationMembership, Role
from app.models.ars import ArsClaim, ArsApplication, ArsRemittance
from app.models.administration import SecurityAudit
from test_insurance_6c5 import insurance_api, coverage, path
from test_organization_isolation import sign_in, tenant_api

PREFIX = '/api/v1/ars'


def post(c, h, url, data, status=200):
    r = c.post(PREFIX + url, headers=h, json=data)
    assert r.status_code == status, r.text
    return r.json()


def setup(insurance_api):
    c, h, engine, d = insurance_api
    c.app.include_router(finance.router, prefix='/api/v1')
    c.app.include_router(ars.router, prefix='/api/v1')
    return c, h, engine, d


def make_claim(c, h, d):
    result = c.put(path(d), headers=h, json=coverage(d))
    assert result.status_code == 200, result.text
    return post(c, h, '/claims', {'appointment_id': d['appointment'], 'coverage_revision': 1}, 201)


def prepare(c, h, claim):
    for state in ('pending', 'sent', 'received'):
        claim = post(c, h, f"/claims/{claim['id']}/transition", {'state': state})
    return claim


def remittance(c, h, d, amount='1000', reference='SYN-1'):
    return post(c, h, '/remittances', {'insurance_company_id': d['company'], 'center_id': d['center'],
        'received_on': '2026-10-05', 'reference': reference, 'amount': amount}, 201)


def test_creation_snapshot_workflow_glosa_correction_and_audit(insurance_api):
    c, h, engine, d = setup(insurance_api)
    assert c.put(path(d[1]), headers=h, json=coverage(d[1])).status_code == 200
    choices = c.get(PREFIX + '/eligible-appointments', headers=h,
                    params={'center_id': d[1]['center'], 'q': 'One'}).json()
    assert [item['id'] for item in choices] == [d[1]['appointment']]
    assert choices[0]['coverage_revision'] == 1
    claim = post(c, h, '/claims', {'appointment_id': d[1]['appointment'], 'coverage_revision': 1}, 201)
    assert claim['claimed_amount'] == '1000.00' and claim['balance'] == '1000.00'
    assert claim['snapshot']['insurance']['company_id'] == d[1]['company']
    assert c.get(PREFIX + '/eligible-appointments', headers=h,
                 params={'center_id': d[1]['center'], 'q': 'One'}).json() == []
    post(c, h, f"/claims/{claim['id']}/transition", {'state': 'received'}, 409)
    prepare(c, h, claim)
    glosed = post(c, h, f"/claims/{claim['id']}/glosa", {'kind': 'glosed', 'amount': '200', 'code': 'SYN', 'note': 'Prueba'})
    assert glosed['balance'] == '800.00' and glosed['display_state'] == 'glosed'
    corrected = post(c, h, f"/claims/{claim['id']}/correction", {'approved_amount': '900', 'note': 'Corrección de prueba'})
    assert corrected['balance'] == '900.00' and corrected['disputed_amount'] == '100.00'
    resent = post(c, h, f"/claims/{claim['id']}/transition", {'state': 'resent'})
    assert resent['submitted_at']
    detail = c.get(PREFIX + f"/claims/{claim['id']}", headers=h).json()
    assert [e['kind'] for e in detail['events']] == ['created', 'pending', 'sent', 'received', 'glosed', 'corrected', 'resent']
    with Session(engine) as db:
        audits = db.scalars(select(SecurityAudit).where(SecurityAudit.action.like('ars:%'))).all()
        assert len(audits) == 7 and all(a.organization_id == 1 and a.center_id == d[1]['center'] for a in audits)


def test_partial_full_multiple_application_reverse_and_aging(insurance_api):
    c, h, engine, d = setup(insurance_api)
    first = prepare(c, h, make_claim(c, h, d[1]))
    with Session(engine) as db:
        original = db.get(Appointment, d[1]['appointment'])
        second = Appointment(organization_id=1, patient_id=original.patient_id, doctor_id=original.doctor_id,
            center_id=original.center_id, appointment_date=date(2026, 10, 2), appointment_time=time(11))
        db.add(second); db.commit(); second_id = second.id
    d_second = {**d[1], 'appointment': second_id}
    second = prepare(c, h, make_claim(c, h, d_second))
    rem = remittance(c, h, d[1], '1500')
    post(c, h, f"/remittances/{rem['id']}/apply", {'allocations': [
        {'claim_id': first['id'], 'amount': '1000'}, {'claim_id': second['id'], 'amount': '500'}]})
    detail = c.get(PREFIX + f"/remittances/{rem['id']}", headers=h).json()
    assert detail['unapplied'] == '0.00' and len(detail['applications']) == 2
    assert c.get(PREFIX + f"/claims/{first['id']}", headers=h).json()['display_state'] == 'paid'
    assert c.get(PREFIX + f"/claims/{second['id']}", headers=h).json()['display_state'] == 'partial'
    post(c, h, f"/claims/{first['id']}/transition", {'state': 'cancelled', 'note': 'Prueba'}, 409)
    post(c, h, f"/remittances/{rem['id']}/apply", {'allocations': [{'claim_id': second['id'], 'amount': '1'}]}, 422)
    cx = c.get(PREFIX + '/receivables', headers=h, params={'center_id': d[1]['center'], 'as_of': '2026-11-10'}).json()
    assert len(cx) == 1 and cx[0]['balance'] == '500.00' and cx[0]['aging_bucket'] == '31-60'
    post(c, h, f"/applications/{detail['applications'][0]['id']}/reverse", {'reason': 'Prueba'})
    again = c.get(PREFIX + f"/claims/{first['id']}", headers=h).json()
    assert again['balance'] == '1000.00'
    post(c, h, f"/applications/{detail['applications'][0]['id']}/reverse", {'reason': 'Prueba'}, 409)
    summary = c.get(PREFIX + '/reconciliation', headers=h, params={'from_date': '2026-10-01', 'to_date': '2026-10-31', 'center_id': d[1]['center']}).json()[0]
    assert summary['claimed'] == '2000.00' and summary['paid'] == '500.00' and summary['pending'] == '1500.00'
    with Session(engine) as db:
        assert db.get(ArsApplication, detail['applications'][0]['id']).reversed_at is not None


def test_claim_uses_invoiced_ars_history_after_coverage_edit(insurance_api):
    c, h, _, d = setup(insurance_api)
    assert c.put(path(d[1]), headers=h, json=coverage(d[1])).status_code == 200
    invoice = c.post('/api/v1/finance/invoices', headers=h, json={
        'request_key': str(uuid4()), 'center_id': d[1]['center'], 'patient_id': d[1]['patient'],
        'appointment_id': d[1]['appointment'], 'coverage_revision': 1,
        'concept': 'Consulta general', 'base_amount': '1500'})
    assert invoice.status_code == 201, invoice.text
    changed = coverage(d[1], revision=1)
    changed.update(base_amount='1700', covered_amount='700', patient_copay='1000')
    assert c.put(path(d[1]), headers=h, json=changed).status_code == 200
    choices = c.get(PREFIX + '/eligible-appointments', headers=h,
                    params={'center_id': d[1]['center'], 'q': 'One'}).json()
    assert choices[0]['coverage_revision'] == 1 and choices[0]['ars_amount'] == '1000.00'
    claim = post(c, h, '/claims', {'appointment_id': d[1]['appointment'], 'coverage_revision': 1}, 201)
    assert claim['claimed_amount'] == '1000.00' and claim['snapshot']['invoice_id'] == invoice.json()['id']
    assert c.post(f"/api/v1/finance/invoices/{invoice.json()['id']}/void", headers=h,
                  json={'reason': 'Cambio sintético'}).status_code == 409
    post(c, h, f"/claims/{claim['id']}/transition", {'state': 'cancelled', 'note': 'Cambio sintético'})
    assert c.post(f"/api/v1/finance/invoices/{invoice.json()['id']}/void", headers=h,
                  json={'reason': 'Cambio sintético'}).status_code == 200


def test_later_invoice_cannot_change_claimed_ars(insurance_api):
    c, h, _, d = setup(insurance_api)
    make_claim(c, h, d[1])
    changed = coverage(d[1], revision=1)
    changed.update(base_amount='1700', covered_amount='700', patient_copay='1000')
    assert c.put(path(d[1]), headers=h, json=changed).status_code == 200
    invoice = c.post('/api/v1/finance/invoices', headers=h, json={
        'request_key': str(uuid4()), 'center_id': d[1]['center'], 'patient_id': d[1]['patient'],
        'appointment_id': d[1]['appointment'], 'coverage_revision': 2,
        'concept': 'Consulta general', 'base_amount': '1700'})
    assert invoice.status_code == 409, invoice.text


def test_cross_tenant_claims_payments_applications_and_reports(insurance_api):
    c, h, engine, d = setup(insurance_api)
    one = prepare(c, h, make_claim(c, h, d[1]))
    with TestClient(c.app, base_url='http://two.example.test') as other:
        h2 = sign_in(other)
        two = prepare(other, h2, make_claim(other, h2, d[2]))
        pay2 = remittance(other, h2, d[2], '1000')
        post(other, h2, f"/remittances/{pay2['id']}/apply", {'allocations': [{'claim_id': two['id'], 'amount': '100'}]})
        application_id = other.get(PREFIX + f"/remittances/{pay2['id']}", headers=h2).json()['applications'][0]['id']
    for url in (f"/claims/{two['id']}", f"/remittances/{pay2['id']}"):
        assert c.get(PREFIX + url, headers=h).status_code == 404
    for url in ('/claims', '/receivables', '/remittances'):
        assert c.get(PREFIX + url, headers=h, params={'center_id': d[2]['center']}).status_code == 404
    assert c.get(PREFIX + '/eligible-appointments', headers=h,
                 params={'center_id': d[2]['center'], 'q': 'Two'}).status_code == 404
    assert c.get(PREFIX + '/reconciliation', headers=h, params={'center_id': d[2]['center'], 'from_date': '2026-10-01', 'to_date': '2026-10-31'}).status_code == 404
    post(c, h, '/claims', {'appointment_id': d[2]['appointment'], 'coverage_revision': 1}, 404)
    post(c, h, f"/remittances/{pay2['id']}/apply", {'allocations': [{'claim_id': one['id'], 'amount': '10'}]}, 404)
    post(c, h, f"/applications/{application_id}/reverse", {'reason': 'Prueba'}, 404)
    post(c, h, '/remittances', {'insurance_company_id': d[2]['company'], 'center_id': d[1]['center'], 'received_on': '2026-10-05', 'reference': 'BAD', 'amount': '1'}, 404)


def test_doctor_has_no_ars_permissions(insurance_api):
    c, h, engine, d = setup(insurance_api)
    with Session(engine) as db:
        member = db.scalar(select(OrganizationMembership).where(OrganizationMembership.organization_id == 1))
        member.roles = [db.scalar(select(Role).where(Role.code == 'doctor'))]
        db.commit()
    h = sign_in(c)
    assert c.get(PREFIX + '/claims', headers=h).status_code == 403
    post(c, h, '/claims', {'appointment_id': d[1]['appointment'], 'coverage_revision': 1}, 403)
    assert c.get(PREFIX + '/receivables', headers=h).status_code == 403
