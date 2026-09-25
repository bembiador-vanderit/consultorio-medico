"""Financial HTTP contracts against real tenant sessions, synthetic data only."""
from datetime import date
from uuid import uuid4
from decimal import Decimal
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session
from app.api.routes import finance
from app.models import Appointment, CareCenter, Patient, Role, User, OrganizationMembership, SecretaryCenterScope
from app.models.finance import CashRegister, Invoice, CashMovement
from app.models.administration import SecurityAudit
from test_organization_isolation import tenant_api, sign_in
from test_insurance_6c5 import insurance_api, coverage, path

PREFIX = '/api/v1/finance'


@pytest.fixture
def financial_api(insurance_api):
    c, h, engine, d = insurance_api
    c.app.include_router(finance.router, prefix='/api/v1')
    return c, h, engine, d


def post(c, h, path, body, status=201):
    result = c.post(PREFIX + path, headers=h, json=body)
    assert result.status_code == status, result.text
    return result.json()


def open_cash(c, h, d):
    return post(c, h, '/registers', {'center_id': d['center'], 'opening_amount': '100'})


def payment(register, *amounts):
    return {'request_key': str(uuid4()), 'register_id': register['id'], 'parts': [dict(method=m, amount=a) for m, a in amounts]}


def bill(d, **changes):
    return dict(request_key=str(uuid4()), center_id=d['center'], patient_id=d['patient'], concept='Consulta general', base_amount='1500', **changes)


def test_open_close_difference_and_closed_register(financial_api):
    c, h, engine, d = financial_api
    r = open_cash(c, h, d[1])
    post(c, h, '/registers', {'center_id': d[1]['center'], 'opening_amount': '0'}, 409)
    post(c, h, f"/registers/{r['id']}/close", {'counted_cash': '90'}, 422)
    result = post(c, h, f"/registers/{r['id']}/close", {'counted_cash': '90', 'notes': 'Diferencia sintética'}, 200)
    assert result['difference'] == '-10.00'
    assert result['closed_by'] == r['opened_by'] and result['closed_at']
    post(c, h, '/invoices', bill(d[1], payment=payment(r, ('cash', '50'))), 409)
    with Session(engine) as db:
        assert db.scalar(select(Invoice.id)) is None  # Atomic invoice + payment.
        assert len(db.scalars(select(SecurityAudit).where(SecurityAudit.action.like('finance:%'))).all()) == 2
    assert open_cash(c, h, d[1])['id'] != r['id']


def test_private_mixed_partial_later_payment_and_idempotency(financial_api):
    c, h, engine, d = financial_api
    r = open_cash(c, h, d[1])
    body = bill(d[1], payment=payment(r, ('cash', '200'), ('card', '300')))
    i = post(c, h, '/invoices', body)
    assert (i['paid_amount'], i['balance'], i['ars_amount'], i['state']) == ('500.00', '1000.00', '0.00', 'partial')
    assert post(c, h, '/invoices', body)['id'] == i['id']
    p = payment(r, ('transfer', '1000'))
    saved = post(c, h, f"/invoices/{i['id']}/payments", p, 200)
    assert saved['state'] == 'paid' and saved['balance'] == '0.00'
    assert post(c, h, f"/invoices/{i['id']}/payments", p, 200)['paid_amount'] == '1500.00'
    p['parts'][0]['amount'] = '1'
    post(c, h, f"/invoices/{i['id']}/payments", p, 409)
    detail = c.get(PREFIX + f"/invoices/{i['id']}", headers=h).json()
    assert len(detail['movements']) == 2 and len(detail['movements'][0]['parts']) == 2
    cash = c.get(PREFIX + f"/registers/{r['id']}", headers=h).json()
    assert cash['totals']['expected_cash'] == '300.00'
    assert cash['totals']['collected']['card'] == '300.00'
    assert c.get(PREFIX + '/invoices', params={'center_id': d[1]['center'], 'pending': True}, headers=h).json() == []


def test_insured_snapshot_ars_not_cash_and_clinical_state_independent(financial_api):
    c, h, engine, d = financial_api
    assert c.put(path(d[1]), headers=h, json=coverage(d[1])).status_code == 200
    with Session(engine) as db:
        db.get(Appointment, d[1]['appointment']).status = 'completed'; db.commit()
    r = open_cash(c, h, d[1])
    body = bill(d[1], appointment_id=d[1]['appointment'], coverage_revision=1, payment=payment(r, ('cash', '200')))
    i = post(c, h, '/invoices', body)
    assert (i['ars_amount'], i['patient_amount'], i['balance']) == ('1000.00', '500.00', '300.00')
    post(c, h, '/invoices', bill(d[1], appointment_id=d[1]['appointment'], coverage_revision=1), 409)
    changed = coverage(d[1], revision=1); changed.update(base_amount='1700', patient_copay='700')
    assert c.put(path(d[1]), headers=h, json=changed).status_code == 200
    assert c.get(PREFIX + f"/invoices/{i['id']}", headers=h).json()['base_amount'] == '1500.00'
    with Session(engine) as db:
        assert db.get(Appointment, d[1]['appointment']).status == 'completed'
    s = c.get(PREFIX + '/summary', params={'center_id': d[1]['center'], 'day': date.today().isoformat()}, headers=h).json()
    assert s['ars_expected'] == '1000.00' and s['patient_pending'] == '300.00'
    assert c.get(PREFIX + f"/registers/{r['id']}", headers=h).json()['totals']['collected']['cash'] == '200.00'


def test_pending_invoice_without_cash_and_stale_coverage(financial_api):
    c, h, _, d = financial_api
    i = post(c, h, '/invoices', bill(d[1]))
    assert i['balance'] == '1500.00' and i['state'] == 'pending'
    assert len(c.get(PREFIX + '/invoices', params={'center_id': d[1]['center'], 'pending': True}, headers=h).json()) == 1
    assert c.put(path(d[1]), headers=h, json=coverage(d[1])).status_code == 200
    post(c, h, '/invoices', bill(d[1], appointment_id=d[1]['appointment']), 409)
    body = bill(d[1], appointment_id=d[1]['appointment'], coverage_revision=1); body['base_amount'] = '1'
    post(c, h, '/invoices', body, 409)


def test_reversal_reapplication_adjustment_void_and_audit(financial_api):
    c, h, engine, d = financial_api
    r = open_cash(c, h, d[1])
    i = post(c, h, '/invoices', bill(d[1], payment=payment(r, ('cash', '100'), ('card', '400'))))
    post(c, h, f"/invoices/{i['id']}/void", {'reason': 'Prueba'}, 409)
    detail = c.get(PREFIX + f"/invoices/{i['id']}", headers=h).json(); original = detail['movements'][0]
    post(c, h, f"/registers/{r['id']}/close", {'counted_cash': '200'}, 200)
    new_r = open_cash(c, h, d[1])
    reverse = dict(register_id=new_r['id'], request_key=str(uuid4()), reason='Devolución sintética')
    reversal = post(c, h, f"/movements/{original['id']}/reverse", reverse)
    assert reversal['parts'] == original['parts']
    assert post(c, h, f"/movements/{original['id']}/reverse", reverse)['id'] == reversal['id']
    reverse['request_key'] = str(uuid4())
    post(c, h, f"/movements/{original['id']}/reverse", reverse, 409)
    adjustment = dict(request_key=str(uuid4()), kind='adjustment_in', amount='25', reason='Fondo adicional')
    post(c, h, f"/registers/{new_r['id']}/adjustments", adjustment)
    post(c, h, f"/registers/{new_r['id']}/adjustments", adjustment)
    cash = c.get(PREFIX + f"/registers/{new_r['id']}", headers=h).json()
    assert cash['totals']['expected_cash'] == '25.00'
    # Reapply, then reverse again, and void without deleting any original rows.
    post(c, h, f"/invoices/{i['id']}/payments", payment(new_r, ('check', '500')), 200)
    detail = c.get(PREFIX + f"/invoices/{i['id']}", headers=h).json()
    post(c, h, f"/movements/{detail['movements'][-1]['id']}/reverse", reverse)
    assert post(c, h, f"/invoices/{i['id']}/void", {'reason': 'Duplicado sintético'}, 200)['state'] == 'void'
    with Session(engine) as db:
        assert len(db.scalars(select(CashMovement)).all()) == 5
        audits = db.scalars(select(SecurityAudit).where(SecurityAudit.action.like('finance:%'))).all()
        assert all(a.organization_id == 1 and a.center_id == d[1]['center'] for a in audits)
        assert any('invoice_void' in a.action for a in audits)
        assert sum('reversal' in a.action for a in audits) == 2
    assert c.delete(PREFIX + f"/movements/{original['id']}", headers=h).status_code == 404


@pytest.mark.parametrize('amount', ['-1', 'NaN', 'Infinity', '0.001', '10000000000'])
def test_invalid_money(financial_api, amount):
    c, h, _, d = financial_api
    post(c, h, '/registers', {'center_id': d[1]['center'], 'opening_amount': amount}, 422)
    body = bill(d[1]); body['base_amount'] = amount
    post(c, h, '/invoices', body, 422)


def test_overpayment_duplicate_methods_and_no_extra_tenant_inputs(financial_api):
    c, h, _, d = financial_api
    r = open_cash(c, h, d[1])
    post(c, h, '/invoices', bill(d[1], payment=payment(r, ('cash', '1501'))), 422)
    post(c, h, '/invoices', bill(d[1], payment=payment(r, ('cash', '1'), ('cash', '2'))), 422)
    post(c, h, '/invoices', bill(d[1], payment=payment(r, ('cash', '0'))), 422)
    body = bill(d[1]); body['organization_id'] = 2
    post(c, h, '/invoices', body, 422)


def test_cross_tenant_all_financial_resources(financial_api):
    c, h, _, d = financial_api
    r1 = open_cash(c, h, d[1])
    with TestClient(c.app, base_url='http://two.example.test') as other:
        h2 = sign_in(other); r2 = open_cash(other, h2, d[2])
        i2 = post(other, h2, '/invoices', bill(d[2], payment=payment(r2, ('cash', '10'))))
        m2 = other.get(PREFIX + f"/invoices/{i2['id']}", headers=h2).json()['movements'][0]
    for endpoint in [f"/registers/{r2['id']}", f"/invoices/{i2['id']}", f"/registers?center_id={d[2]['center']}", f"/invoices?center_id={d[2]['center']}&pending=true", f"/summary?center_id={d[2]['center']}&day=2026-10-01", f"/movements?center_id={d[2]['center']}&day=2026-10-01"]:
        assert c.get(PREFIX + endpoint, headers=h).status_code == 404
    post(c, h, '/registers', {'center_id': d[2]['center'], 'opening_amount': '0'}, 404)
    body = bill(d[1]); body['patient_id'] = d[2]['patient']
    post(c, h, '/invoices', body, 404)
    post(c, h, '/invoices', bill(d[1], appointment_id=d[2]['appointment']), 404)
    post(c, h, '/invoices', bill(d[1], payment=payment(r2, ('cash', '1'))), 404)
    post(c, h, f"/invoices/{i2['id']}/payments", payment(r1, ('cash', '1')), 404)
    post(c, h, f"/invoices/{i2['id']}/void", {'reason': 'Prueba'}, 404)
    post(c, h, f"/registers/{r2['id']}/close", {'counted_cash': '0'}, 404)
    post(c, h, f"/movements/{m2['id']}/reverse", dict(register_id=r1['id'], request_key=str(uuid4()), reason='Prueba'), 404)
    assert c.get(PREFIX + '/invoices', params={'center_id': d[1]['center']}, headers=h).json() == []


def test_wrong_center_and_patient_and_staff_permissions(financial_api):
    c, h, engine, d = financial_api
    r = open_cash(c, h, d[1])
    with Session(engine) as db:
        center = CareCenter(name='Other center', city='Synthetic'); db.add(center)
        patient = Patient(first_name='Other', last_name='Synthetic', date_of_birth=date(1990,1,1)); db.add(patient); db.commit()
        center_id, patient_id = center.id, patient.id
    body = bill(d[1], appointment_id=d[1]['appointment']); body['patient_id'] = patient_id
    post(c, h, '/invoices', body, 422)
    body = bill(d[1], payment=payment(r, ('cash', '1'))); body['center_id'] = center_id
    post(c, h, '/invoices', body, 409)
    with Session(engine) as db:
        member = db.scalar(select(OrganizationMembership).where(OrganizationMembership.organization_id == 1))
        member.roles = [db.scalar(select(Role).where(Role.code == 'doctor'))]; db.commit()
    h = sign_in(c)
    assert c.get(PREFIX + '/centers', headers=h).status_code == 403
    post(c, h, '/registers', {'center_id': d[1]['center'], 'opening_amount': '0'}, 403)
    with Session(engine) as db:
        member = db.scalar(select(OrganizationMembership).where(OrganizationMembership.organization_id == 1))
        member.roles = [db.scalar(select(Role).where(Role.code == 'secretary'))]; db.commit()
    h = sign_in(c)
    assert c.get(PREFIX + '/centers', headers=h).status_code == 200
    assert c.get(PREFIX + f'/registers?center_id={center_id}', headers=h).status_code == 404
    post(c, h, f"/registers/{r['id']}/adjustments", dict(request_key=str(uuid4()), kind='adjustment_in', amount='1', reason='Prueba'), 403)
    with Session(engine) as db:
        member = db.scalar(select(OrganizationMembership).where(OrganizationMembership.organization_id == 1))
        member.denied_permissions = ['finance:collect']; db.commit()
    post(c, sign_in(c), f"/registers/{r['id']}/close", {'counted_cash': '100'}, 403)


def test_secretary_collects_only_assigned_cash_and_cannot_reverse(financial_api):
    c, h, engine, d = financial_api
    r = open_cash(c, h, d[1])
    with Session(engine) as db:
        member = db.scalar(select(OrganizationMembership).where(OrganizationMembership.organization_id == 1))
        member.roles = [db.scalar(select(Role).where(Role.code == 'secretary'))]
        db.add(SecretaryCenterScope(organization_id=1, secretary_id=member.user_id, center_id=d[1]['center'], manage_all_doctors=True))
        other = User(email='second.cash@example.test', full_name='Synthetic Cashier', password_hash='unused', memberships=[OrganizationMembership(organization_id=1, roles=[db.scalar(select(Role).where(Role.code == 'secretary'))])])
        db.add(other); db.flush(); other_id = other.id; db.commit()
    h = sign_in(c)
    invoice = post(c, h, '/invoices', bill(d[1], appointment_id=d[1]['appointment'], payment=payment(r, ('cash','10'))))
    detail = c.get(PREFIX + f"/invoices/{invoice['id']}", headers=h).json()
    post(c, h, f"/movements/{detail['movements'][0]['id']}/reverse", dict(register_id=r['id'], request_key=str(uuid4()), reason='Prueba'), 403)
    with Session(engine) as db:
        db.get(CashRegister, r['id']).opened_by = other_id; db.commit()
    post(c, h, f"/invoices/{invoice['id']}/payments", payment(r, ('cash', '1')), 403)


def test_day_totals_use_org_timezone_and_only_patient_payments(financial_api):
    from datetime import datetime
    from app.models import Organization
    c, h, engine, d = financial_api
    assert c.put(path(d[1]), headers=h, json=coverage(d[1])).status_code == 200
    r = open_cash(c, h, d[1])
    i = post(c, h, '/invoices', bill(d[1], appointment_id=d[1]['appointment'], coverage_revision=1, payment=payment(r, ('cash','200'))))
    with Session(engine) as db:
        db.get(Organization, 1).timezone = 'America/Santo_Domingo'
        db.scalar(select(CashMovement)).created_at = datetime(2026, 10, 2, 2, 0)
        db.commit()
    data = c.get(PREFIX + '/summary', params={'center_id': d[1]['center'], 'day':'2026-10-01'}, headers=h).json()
    assert data['collected']['cash'] == '200.00' and data['copays'] == '200.00' and data['ars_expected'] == '1000.00'
    next_day = c.get(PREFIX + '/summary', params={'center_id': d[1]['center'], 'day':'2026-10-02'}, headers=h).json()
    assert next_day['collected']['cash'] == '0.00' and next_day['patient_pending'] == '300.00'
