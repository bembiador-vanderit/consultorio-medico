"""Authenticated replay contracts; fixtures are isolated, never official data."""
from uuid import uuid4
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select, func
from sqlalchemy.orm import Session
from app.models import Role
from app.models.ars import ArsApplyOperation, ArsApplication, ArsClaimEvent
from test_ars_6c7 import setup, make_claim, prepare, remittance, post, PREFIX
from test_insurance_6c5 import insurance_api, shared_membership
from test_organization_isolation import tenant_api, sign_in


def body(claim, amount='250', key=None):
    return {'request_key': key or str(uuid4()), 'allocations': [{'claim_id': claim['id'], 'amount': amount}]}


def ready(fixture):
    c, h, engine, d = setup(fixture)
    claim = prepare(c, h, make_claim(c, h, d[1]))
    rem = remittance(c, h, d[1])
    return c, h, engine, d, claim, rem, f"/remittances/{rem['id']}/apply"


def test_lost_response_retry_returns_original_and_new_intent_is_valid(insurance_api):
    c, h, engine, d, claim, rem, url = ready(insurance_api)
    intent = body(claim)
    first = post(c, h, url, intent)
    assert first['applied_amount'] == '250.00' and first['unapplied'] == '750.00'
    assert post(c, h, url, intent) == first  # Lost response / double click.
    post(c, h, url, body(claim))  # Deliberate identical amount, different key.
    assert post(c, h, url, intent) == first  # Immutable result, not later totals.
    detail = c.get(PREFIX + f"/claims/{claim['id']}", headers=h).json()
    assert detail['paid_amount'] == '500.00' and detail['balance'] == '500.00'
    assert len(detail['applications']) == 2
    with Session(engine) as db:
        assert db.scalar(select(func.count()).select_from(ArsApplyOperation)) == 2
        assert db.scalar(select(func.count()).select_from(ArsClaimEvent).where(ArsClaimEvent.kind == 'applied')) == 2
        assert all(a.operation_id for a in db.scalars(select(ArsApplication)))
    app_id = detail['applications'][0]['id']
    post(c, h, f'/applications/{app_id}/reverse', {'reason': 'QA reverse'})
    assert post(c, h, url, intent) == first  # Replay never re-applies a reversed operation.
    assert c.get(PREFIX + f"/claims/{claim['id']}", headers=h).json()['paid_amount'] == '250.00'


@pytest.mark.parametrize('change', ['amount', 'claim', 'remittance'])
def test_same_key_different_intent_conflicts(insurance_api, change):
    c, h, engine, d, claim, rem, url = ready(insurance_api)
    intent = body(claim)
    post(c, h, url, intent)
    altered = body(claim, key=intent['request_key'])
    if change == 'amount': altered['allocations'][0]['amount'] = '300'
    if change == 'claim': altered['allocations'][0]['claim_id'] += 1000
    if change == 'remittance':
        other = remittance(c, h, d[1], reference='OTHER')
        url = f"/remittances/{other['id']}/apply"
    post(c, h, url, altered, 409)
    with Session(engine) as db:
        assert db.scalar(select(func.count()).select_from(ArsApplication)) == 1


def test_failed_multi_allocation_rolls_back_intent_balances_and_audit(insurance_api):
    c, h, engine, d, claim, rem, url = ready(insurance_api)
    intent = body(claim)
    intent['allocations'].append({'claim_id': 999999, 'amount': '1'})
    post(c, h, url, intent, 404)
    with Session(engine) as db:
        assert db.scalar(select(func.count()).select_from(ArsApplyOperation)) == 0
        assert db.scalar(select(func.count()).select_from(ArsApplication)) == 0
        assert db.scalar(select(func.count()).select_from(ArsClaimEvent).where(ArsClaimEvent.kind == 'applied')) == 0
    assert c.get(PREFIX + f"/claims/{claim['id']}", headers=h).json()['paid_amount'] == '0.00'
    intent['allocations'].pop()
    post(c, h, url, intent)  # Rolled back key is not consumed.


def test_key_is_tenant_scoped_and_retry_still_requires_permission(insurance_api):
    c, h, engine, d, claim, rem, url = ready(insurance_api)
    intent = body(claim)
    post(c, h, url, intent)
    with TestClient(c.app, base_url='http://two.example.test') as other:
        h2 = sign_in(other)
        two = prepare(other, h2, make_claim(other, h2, d[2]))
        rem2 = remittance(other, h2, d[2])
        post(other, h2, f"/remittances/{rem2['id']}/apply", body(two, key=intent['request_key']))
        post(other, h2, url, intent, 404)
    with Session(engine) as db:
        shared_membership(db).roles = [db.scalar(select(Role).where(Role.code == 'doctor'))]
        db.commit()
    post(c, sign_in(c), url, intent, 403)


def test_key_required_and_amount_canonicalization(insurance_api):
    c, h, engine, d, claim, rem, url = ready(insurance_api)
    assert c.post(PREFIX + url, headers=h, json={'allocations': body(claim)['allocations']}).status_code == 422
    intent = body(claim)
    first = post(c, h, url, intent)
    intent['allocations'][0]['amount'] = '250.00'
    assert post(c, h, url, intent) == first
