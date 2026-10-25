"""Synthetic card provider and register-scoped POS batch contracts."""
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Role, SecretaryCenterScope
from app.models.finance import CardBatchAudit, CashMovement, CashRegister
from test_finance_6c6 import PREFIX, bill, financial_api, open_cash, payment, post
from test_insurance_6c5 import insurance_api, shared_membership
from test_organization_isolation import tenant_api, sign_in


def test_provider_scope_and_card_batch_required(financial_api):
    client, headers, engine, data = financial_api
    center = data[1]['center']
    url = f'{PREFIX}/centers/{center}/card-providers'
    providers = client.get(url, headers=headers).json()
    assert [x['provider'] for x in providers] == ['CARDNET', 'AZUL', 'VISANET']
    assert [x['enabled'] for x in providers] == [True, False, False]
    assert client.get(f"{PREFIX}/centers/{data[2]['center']}/card-providers", headers=headers).status_code == 404
    with Session(engine) as db:
        member = shared_membership(db)
        hidden = CashRegister(organization_id=2, center_id=data[2]['center'], opened_by=member.user_id, opening_amount=0)
        db.add(hidden); db.commit(); hidden_id = hidden.id
    assert client.get(f'{PREFIX}/registers/{hidden_id}/card-batches', headers=headers).status_code == 404
    assert client.post(f'{PREFIX}/registers/{hidden_id}/card-batches', headers=headers,
        json={'provider': 'CARDNET', 'batch_number': 'OTHER', 'declared_count': 0, 'declared_amount': '0'}).status_code == 404
    register = open_cash(client, headers, data[1])
    disabled = payment(register, ('card', '100'))
    disabled['parts'][0]['provider'] = 'AZUL'
    post(client, headers, '/invoices', bill(data[1], payment=disabled), 409)
    changed = client.put(url + '/AZUL', headers=headers, json={'enabled': True})
    assert changed.status_code == 200 and changed.json()['enabled'] is True
    assert client.put(f"{PREFIX}/centers/{data[2]['center']}/card-providers/AZUL",
        headers=headers, json={'enabled': True}).status_code == 404
    assert client.get(url, headers=headers).json()[1]['enabled'] is True


def test_batch_close_before_register_and_pos_closed_reversal_blocked(financial_api):
    client, headers, engine, data = financial_api
    register = open_cash(client, headers, data[1])
    invoice = post(client, headers, '/invoices', bill(data[1], payment=payment(register, ('card', '100'))))
    movement = client.get(f"{PREFIX}/invoices/{invoice['id']}", headers=headers).json()['movements'][0]
    post(client, headers, f"/registers/{register['id']}/close", {'counted_cash': '100'}, 409)
    batches = client.get(f"{PREFIX}/registers/{register['id']}/card-batches", headers=headers).json()
    assert len(batches) == 1 and batches[0]['state'] == 'open' and batches[0]['atlas_amount'] == '100.00'
    close = {'provider': 'CARDNET', 'batch_number': 'QA-LOTE-001', 'declared_count': 1, 'declared_amount': '99'}
    post(client, headers, f"/registers/{register['id']}/card-batches", close, 422)
    close['notes'] = 'Diferencia sintética de POS'
    batch = post(client, headers, f"/registers/{register['id']}/card-batches", close)
    assert batch['amount_difference'] == '-1.00' and batch['count_difference'] == 0
    post(client, headers, f"/registers/{register['id']}/card-batches", close, 409)
    assert post(client, headers, f"/registers/{register['id']}/close", {'counted_cash': '100'}, 200)['state'] == 'closed'
    new_register = open_cash(client, headers, data[1])
    post(client, headers, f"/movements/{movement['id']}/reverse",
        {'register_id': new_register['id'], 'request_key': str(uuid4()), 'reason': 'Devolución'}, 409)
    with Session(engine) as db:
        assert len(db.scalars(select(CashMovement).where(CashMovement.kind == 'reversal')).all()) == 0
        assert any(e.action == 'close' for e in db.scalars(select(CardBatchAudit)))


def test_admin_reopen_and_correct_metadata_preserves_amount_and_audit(financial_api):
    client, headers, engine, data = financial_api
    register = open_cash(client, headers, data[1])
    invoice = post(client, headers, '/invoices', bill(data[1], payment=payment(register, ('card', '100'))))
    movement_id = client.get(f"{PREFIX}/invoices/{invoice['id']}", headers=headers).json()['movements'][0]['id']
    old = post(client, headers, f"/registers/{register['id']}/card-batches",
        {'provider': 'CARDNET', 'batch_number': 'QA-LOTE-001', 'declared_count': 1, 'declared_amount': '100'})
    assert client.put(f"{PREFIX}/centers/{data[1]['center']}/card-providers/AZUL", headers=headers,
        json={'enabled': True}).status_code == 200
    change = {'provider': 'AZUL', 'batch_number': 'QA-CORREGIDO', 'reason': 'Error de digitación sintético'}
    assert client.put(f'{PREFIX}/movements/{movement_id}/card-assignment', headers=headers, json=change).status_code == 409
    reopened = post(client, headers, f"/card-batches/{old['id']}/reopen", {'reason': 'Revisión administrativa'}, 200)
    assert reopened['state'] == 'open'
    post(client, headers, f"/movements/{movement_id}/reverse",
        {'register_id': register['id'], 'request_key': str(uuid4()), 'reason': 'No hay reverso POS'}, 409)
    corrected = client.put(f'{PREFIX}/movements/{movement_id}/card-assignment', headers=headers, json=change)
    assert corrected.status_code == 200 and corrected.json()['amount'] == '100.00'
    assert corrected.json()['parts'][0]['batch_number'] == 'QA-CORREGIDO'
    post(client, headers, f"/movements/{movement_id}/reverse",
        {'register_id': register['id'], 'request_key': str(uuid4()), 'reason': 'Tampoco tras corregir'}, 409)
    post(client, headers, f"/registers/{register['id']}/close", {'counted_cash': '100'}, 409)
    post(client, headers, f"/registers/{register['id']}/card-batches",
        {'provider': 'CARDNET', 'batch_number': 'QA-LOTE-001', 'declared_count': 0, 'declared_amount': '0'})
    post(client, headers, f"/registers/{register['id']}/card-batches",
        {'provider': 'AZUL', 'batch_number': 'QA-CORREGIDO', 'declared_count': 1, 'declared_amount': '100'})
    assert post(client, headers, f"/registers/{register['id']}/close", {'counted_cash': '100'}, 200)['state'] == 'closed'
    with Session(engine) as db:
        events = db.scalars(select(CardBatchAudit).order_by(CardBatchAudit.id)).all()
        correction = next(e for e in events if e.action == 'assignment_correction')
        assert correction.before == {'provider': 'CARDNET', 'batch_number': 'QA-LOTE-001'}
        assert correction.after == {'provider': 'AZUL', 'batch_number': 'QA-CORREGIDO'}
        assert correction.actor_id and correction.reason
    history = client.get(f"{PREFIX}/registers/{register['id']}/card-batch-history", headers=headers).json()
    assert any(e['action'] == 'reopen' for e in history)


def test_secretary_can_close_own_batch_but_cannot_configure_or_reopen(financial_api):
    client, headers, engine, data = financial_api
    register = open_cash(client, headers, data[1])
    post(client, headers, '/invoices', bill(data[1], payment=payment(register, ('card', '100'))))
    with Session(engine) as db:
        member = shared_membership(db)
        member.roles = [db.scalar(select(Role).where(Role.code == 'secretary'))]
        db.add(SecretaryCenterScope(organization_id=1, secretary_id=member.user_id,
            center_id=data[1]['center'], manage_all_doctors=True))
        db.commit()
    headers = sign_in(client)
    config = f"{PREFIX}/centers/{data[1]['center']}/card-providers/AZUL"
    assert client.put(config, headers=headers, json={'enabled': True}).status_code == 403
    batch = post(client, headers, f"/registers/{register['id']}/card-batches",
        {'provider': 'CARDNET', 'batch_number': 'QA-LOTE-001', 'declared_count': 1, 'declared_amount': '100'})
    assert batch['state'] == 'closed'
    assert client.post(f"{PREFIX}/card-batches/{batch['id']}/reopen", headers=headers,
        json={'reason': 'No autorizado'}).status_code == 403
    movement = client.get(f"{PREFIX}/registers/{register['id']}/card-batch-history", headers=headers).json()
    assert any(e['action'] == 'close' for e in movement)


def test_admin_recounts_lot_after_cash_register_closed(financial_api):
    client, headers, engine, data = financial_api
    register = open_cash(client, headers, data[1])
    post(client, headers, '/invoices', bill(data[1], payment=payment(register, ('card', '100'))))
    url = f"/registers/{register['id']}/card-batches"
    batch = post(client, headers, url,
        {'provider': 'CARDNET', 'batch_number': 'QA-LOTE-001', 'declared_count': 1, 'declared_amount': '100'})
    post(client, headers, f"/registers/{register['id']}/close", {'counted_cash': '100'}, 200)
    post(client, headers, f"/card-batches/{batch['id']}/reopen", {'reason': 'Revisar voucher'}, 200)
    revised = post(client, headers, url,
        {'provider': 'CARDNET', 'batch_number': 'QA-LOTE-001', 'declared_count': 1,
         'declared_amount': '99', 'notes': 'Diferencia del POS documentada'})
    assert revised['amount_difference'] == '-1.00'
    with Session(engine) as db:
        events = db.scalars(select(CardBatchAudit).where(CardBatchAudit.batch_id == batch['id']).order_by(CardBatchAudit.id)).all()
        assert [e.action for e in events] == ['close', 'reopen', 'close']
        assert events[-1].before['state'] == 'open' and events[-1].after['declared_amount'] == '99.00'
