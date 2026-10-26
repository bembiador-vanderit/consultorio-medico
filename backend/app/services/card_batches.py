"""Card POS batches belong to one register; money movements remain the ledger."""
from datetime import datetime
from decimal import Decimal

from fastapi import HTTPException
from sqlalchemy import select

from app.models import CareCenter
from app.models.finance import CardBatch, CardBatchAudit, CardProviderSetting, CashMovement
from app.services.administration import effective_permissions
from app.services import finance

PROVIDERS = ('CARDNET', 'AZUL', 'VISANET')


def audit(db, user, center_id, action, before, after, *, register_id=None, batch_id=None, movement_id=None, reason=None):
    db.add(CardBatchAudit(center_id=center_id, register_id=register_id, batch_id=batch_id,
        movement_id=movement_id, action=action, actor_id=user.id, before=before, after=after, reason=reason))
    finance.audit(db, user, f'card_batch_{action}', batch_id or movement_id or center_id, center_id)


def settings(db, user, center_id):
    finance.center_access(db, user, center_id)
    rows = {r.provider: r for r in db.scalars(select(CardProviderSetting).where(CardProviderSetting.center_id == center_id))}
    return [{'provider': code, 'enabled': bool(rows.get(code) and rows[code].enabled)} for code in PROVIDERS]


def set_provider(db, user, center_id, provider, enabled):
    finance.center_access(db, user, center_id)
    # Serialize concurrent settings for this center, including the first insert.
    db.scalar(select(CareCenter).where(CareCenter.id == center_id).with_for_update())
    row = db.scalar(select(CardProviderSetting).where(CardProviderSetting.center_id == center_id,
        CardProviderSetting.provider == provider))
    before = bool(row and row.enabled)
    if row is None:
        row = CardProviderSetting(center_id=center_id, provider=provider, enabled=enabled,
            updated_by=user.id, updated_at=datetime.utcnow())
        db.add(row)
    else:
        row.enabled, row.updated_by, row.updated_at = enabled, user.id, datetime.utcnow()
    audit(db, user, center_id, 'provider_config', {'provider': provider, 'enabled': before},
        {'provider': provider, 'enabled': enabled})
    finance.commit(db)
    return {'provider': provider, 'enabled': enabled}


def require_enabled(db, center_id, provider):
    row = db.scalar(select(CardProviderSetting).where(CardProviderSetting.center_id == center_id,
        CardProviderSetting.provider == provider, CardProviderSetting.enabled.is_(True)))
    if row is None:
        raise HTTPException(409, 'La prestadora de tarjeta no está habilitada para este centro')


def batch(db, register_id, provider, batch_number):
    return db.scalar(select(CardBatch).where(CardBatch.register_id == register_id,
        CardBatch.provider == provider, CardBatch.batch_number == batch_number))


def require_new_payment_batch(db, register_id, provider, batch_number):
    row = batch(db, register_id, provider, batch_number)
    if row is not None:
        # Reopening an Atlas record does not reopen the POS/bank settlement.
        raise HTTPException(409, 'Este lote ya fue cerrado en el POS; use un lote nuevo')


def groups(db, register_id):
    result = {}
    for movement in db.scalars(select(CashMovement).where(CashMovement.register_id == register_id)
                               .order_by(CashMovement.id)):
        if movement.kind not in ('payment', 'reversal'):
            continue
        for part in movement.parts:
            if part['method'] != 'card':
                continue
            key = (part.get('provider'), part.get('batch_number'))
            item = result.setdefault(key, {'count': 0, 'amount': Decimal('0.00'), 'movement_ids': []})
            sign = 1 if movement.kind == 'payment' else -1
            item['count'] += sign
            item['amount'] += sign * Decimal(part['amount'])
            item['movement_ids'].append(movement.id)
    return result


def batch_view(row, figures):
    count = figures['count'] if figures else 0
    amount = figures['amount'] if figures else Decimal('0.00')
    money = lambda value: f'{value:.2f}'
    return {'id': row.id if row else None, 'provider': row.provider if row else None,
        'batch_number': row.batch_number if row else None,
        'state': row.state if row else 'open', 'atlas_count': count, 'atlas_amount': money(amount),
        'declared_count': row.declared_count if row and row.state == 'closed' else None,
        'declared_amount': money(row.declared_amount) if row and row.state == 'closed' else None,
        'count_difference': row.declared_count - count if row and row.state == 'closed' else None,
        'amount_difference': money(row.declared_amount - amount) if row and row.state == 'closed' else None,
        'closed_by': row.closed_by if row else None, 'closed_at': row.closed_at.isoformat() if row and row.closed_at else None,
        'ever_closed': row is not None}


def list_batches(db, user, register_id):
    register = finance.register_access(db, user, register_id)
    figures = groups(db, register.id)
    rows = {(r.provider, r.batch_number): r for r in db.scalars(
        select(CardBatch).where(CardBatch.register_id == register.id))}
    return [{**batch_view(rows.get(key), figures.get(key)), 'provider': key[0], 'batch_number': key[1]}
            for key in sorted(set(figures) | set(rows), key=lambda k: (str(k[0]), str(k[1])))]


def ensure_register_batches_closed(db, register):
    for (provider, number), figures in groups(db, register.id).items():
        if not provider or not number:
            raise HTTPException(409, 'Hay cobros antiguos con tarjeta sin prestadora o lote; solicite corrección administrativa')
        row = batch(db, register.id, provider, number)
        if row is None or row.state != 'closed':
            raise HTTPException(409, f'Cierre primero el lote {provider} {number}')
        if row.atlas_count != figures['count'] or row.atlas_amount != figures['amount']:
            raise HTTPException(409, 'El lote cambió desde su cierre; revise y vuelva a cerrarlo')
    for row in db.scalars(select(CardBatch).where(CardBatch.register_id == register.id, CardBatch.state != 'closed')):
        raise HTTPException(409, f'Cierre primero el lote {row.provider} {row.batch_number}')


def close_batch(db, user, register_id, payload):
    register = finance.register_access(db, user, register_id, lock=True, write=True)
    if register.state == 'closed' and 'finance:manage' not in effective_permissions(user):
        raise HTTPException(403, 'Solo un administrador puede corregir un lote de una caja cerrada')
    key = (payload.provider, payload.batch_number)
    figures = groups(db, register.id).get(key)
    row = batch(db, register.id, *key)
    if figures is None and row is None:
        raise HTTPException(404, 'No hay transacciones de este lote en la caja')
    if row and row.state == 'closed':
        raise HTTPException(409, 'Este lote ya está cerrado')
    figures = figures or {'count': 0, 'amount': Decimal('0.00'), 'movement_ids': []}
    if figures['count'] < 0 or figures['amount'] < 0:
        raise HTTPException(409, 'El lote contiene más devoluciones que cobros; revise los movimientos')
    difference = payload.declared_count != figures['count'] or payload.declared_amount != figures['amount']
    if difference and not (payload.notes or '').strip():
        raise HTTPException(422, 'Explique la diferencia entre el voucher y Atlas')
    before = batch_view(row, figures)
    if row is None:
        row = CardBatch(center_id=register.center_id, register_id=register.id,
            provider=payload.provider, batch_number=payload.batch_number)
        db.add(row)
        finance.flush(db)
    row.state = 'closed'
    row.declared_count, row.declared_amount = payload.declared_count, payload.declared_amount
    row.atlas_count, row.atlas_amount = figures['count'], figures['amount']
    row.ever_closed_movement_ids = sorted(set(row.ever_closed_movement_ids or []) | set(figures['movement_ids']))
    row.closed_by, row.closed_at = user.id, datetime.utcnow()
    after = batch_view(row, figures)
    audit(db, user, register.center_id, 'close', before, after, register_id=register.id,
          batch_id=row.id, reason=payload.notes)
    finance.commit(db)
    return after


def reopen_batch(db, user, batch_id, reason):
    row = db.get(CardBatch, batch_id)
    if row is None:
        raise HTTPException(404, 'Lote no encontrado')
    register = finance.register_access(db, user, row.register_id, lock=True)
    row = db.scalar(select(CardBatch).where(CardBatch.id == batch_id).execution_options(populate_existing=True))
    if row.state != 'closed':
        raise HTTPException(409, 'El lote ya está abierto para corrección')
    before = batch_view(row, groups(db, register.id).get((row.provider, row.batch_number)))
    row.state, row.reopened_by, row.reopened_at = 'open', user.id, datetime.utcnow()
    after = batch_view(row, groups(db, register.id).get((row.provider, row.batch_number)))
    audit(db, user, register.center_id, 'reopen', before, after, register_id=register.id,
          batch_id=row.id, reason=reason)
    finance.commit(db)
    return after


def correct_assignment(db, user, movement_id, payload):
    movement = db.get(CashMovement, movement_id)
    if movement is None:
        raise HTTPException(404, 'Movimiento no encontrado')
    register = finance.register_access(db, user, movement.register_id, lock=True)
    movement = db.scalar(select(CashMovement).where(CashMovement.id == movement_id).execution_options(populate_existing=True))
    if movement.kind != 'payment':
        raise HTTPException(422, 'Solo se corrige la prestadora y el lote de un cobro')
    part = next((p for p in movement.parts if p['method'] == 'card'), None)
    if part is None:
        raise HTTPException(422, 'El movimiento no tiene tarjeta')
    old = {'provider': part.get('provider'), 'batch_number': part.get('batch_number')}
    new = {'provider': payload.provider, 'batch_number': payload.batch_number}
    if old == new:
        raise HTTPException(409, 'No hay cambios que registrar')
    old_batch = batch(db, register.id, old['provider'], old['batch_number']) if all(old.values()) else None
    if old_batch and old_batch.state == 'closed':
        raise HTTPException(409, 'Reabra primero el lote de origen con motivo administrativo')
    require_enabled(db, register.center_id, payload.provider)
    require_new_payment_batch(db, register.id, payload.provider, payload.batch_number)
    movement.parts = [{**p, **new} if p['method'] == 'card' else p for p in movement.parts]
    audit(db, user, register.center_id, 'assignment_correction', old, new,
          register_id=register.id, movement_id=movement.id, reason=payload.reason)
    finance.commit(db)
    return finance.serialize(movement)


def ensure_pos_not_closed(db, original):
    if not any(p['method'] == 'card' for p in original.parts):
        return
    rows = db.scalars(select(CardBatch).where(CardBatch.register_id == original.register_id))
    if any(original.id in (row.ever_closed_movement_ids or []) for row in rows):
        raise HTTPException(409, 'El lote del POS ya fue cerrado; la devolución requiere trámite administrativo externo')


def history(db, user, register_id):
    finance.register_access(db, user, register_id)
    return [dict(id=e.id, action=e.action, actor_id=e.actor_id, created_at=e.created_at,
        batch_id=e.batch_id, movement_id=e.movement_id, before=e.before, after=e.after, reason=e.reason)
        for e in db.scalars(select(CardBatchAudit).where(CardBatchAudit.register_id == register_id)
                            .order_by(CardBatchAudit.id.desc()).limit(200))]
