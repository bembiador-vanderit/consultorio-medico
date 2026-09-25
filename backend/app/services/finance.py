"""Transactional operations. Lock order: register, appointment, invoice.

Every cash mutation locks its register, including closing. Every balance mutation
locks its invoice, including payments from another cashier. Client UUIDs make
retries safe; reusing a key with a different payload is a conflict.
"""
from datetime import datetime
from decimal import Decimal
import hashlib
from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from app.models import Appointment, CareCenter, Patient
from app.models.administration import SecurityAudit
from app.models.finance import CashRegister, CashMovement, Invoice
from app.models.insurance import AppointmentCoverage
from app.services.administration import effective_permissions
from app.services.appointment_scope import assigned_center_ids, is_role, ensure_appointment_access
from app.services.patient_scope import require_patient_identity_access

METHODS = {'cash': 'Efectivo', 'card': 'Tarjeta', 'transfer': 'Transferencia', 'check': 'Cheque', 'other': 'Otro'}


def center_access(db, user, center_id):
    center = db.get(CareCenter, center_id)
    if center is None or (not is_role(user, 'admin') and center_id not in assigned_center_ids(user)):
        raise HTTPException(404, 'Centro no disponible')
    return center


def center_query(query, model, user):
    return query if is_role(user, 'admin') else query.where(model.center_id.in_(assigned_center_ids(user)))


def audit(db, user, action, entity, center_id):
    db.add(SecurityAudit(actor_id=user.id, center_id=center_id, action=f'finance:{action}:{entity}'))


def commit(db):
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, 'La operación cambió o ya existe; recargue y reintente con la misma referencia')


def flush(db):
    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, 'Referencia ya utilizada o conflicto concurrente; recargue antes de reintentar')


def digest(payload, context=''):
    return hashlib.sha256((context + payload.model_dump_json()).encode()).hexdigest()


def replay(db, model, payload, fingerprint, user):
    row = db.scalar(select(model).where(model.request_key == str(payload.request_key)))
    if row:
        center_access(db, user, row.center_id)
        if row.request_hash != fingerprint or row.created_by != user.id:
            raise HTTPException(409, 'Referencia de operación ya utilizada')
    return row


def register_access(db, user, register_id, *, lock=False, write=False):
    query = select(CashRegister).where(CashRegister.id == register_id)
    if lock:
        query = query.with_for_update().execution_options(populate_existing=True)
    row = db.scalar(query)
    if row is None:
        raise HTTPException(404, 'Caja no encontrada')
    center_access(db, user, row.center_id)
    if write and row.opened_by != user.id and 'finance:manage' not in effective_permissions(user):
        raise HTTPException(403, 'Solo el responsable o un supervisor puede operar esta caja')
    return row


def require_open(row):
    if row.state != 'open':
        raise HTTPException(409, 'Se requiere una caja abierta')


def invoice_access(db, user, invoice_id, *, lock=False):
    query = select(Invoice).where(Invoice.id == invoice_id)
    if lock:
        query = query.with_for_update().execution_options(populate_existing=True)
    row = db.scalar(query)
    if row is None:
        raise HTTPException(404, 'Factura no encontrada')
    center_access(db, user, row.center_id)
    return row


def open_register(db, user, payload):
    center = center_access(db, user, payload.center_id)
    if not center.is_active:
        raise HTTPException(409, 'Centro inactivo')
    # Serialize openings even when no open register exists yet.
    db.scalar(select(CareCenter).where(CareCenter.id == center.id).with_for_update())
    if db.scalar(select(CashRegister.id).where(CashRegister.center_id == center.id,
            CashRegister.opened_by == user.id, CashRegister.state == 'open')):
        raise HTTPException(409, 'Ya tiene una caja abierta en este centro')
    row = CashRegister(center_id=center.id, opened_by=user.id, opening_amount=payload.opening_amount, opening_notes=payload.notes)
    db.add(row); flush(db)
    audit(db, user, 'open', row.id, row.center_id)
    commit(db)
    return row


def register_totals(db, row):
    collected = {key: Decimal('0.00') for key in METHODS}
    reversed_totals = dict(collected)
    adjustments_in = adjustments_out = Decimal('0.00')
    for item in db.scalars(select(CashMovement).where(CashMovement.register_id == row.id)):
        if item.kind in ('payment', 'reversal'):
            target = collected if item.kind == 'payment' else reversed_totals
            for part in item.parts:
                target[part['method']] += Decimal(part['amount'])
        elif item.kind == 'adjustment_in':
            adjustments_in += item.amount
        else:
            adjustments_out += item.amount
    return dict(collected=collected, reversed=reversed_totals, adjustments_in=adjustments_in,
                adjustments_out=adjustments_out, expected_cash=row.opening_amount + collected['cash'] - reversed_totals['cash'] + adjustments_in - adjustments_out)


def close_register(db, user, register_id, payload):
    row = register_access(db, user, register_id, lock=True, write=True)
    require_open(row)
    totals = register_totals(db, row)
    difference = payload.counted_cash - totals['expected_cash']
    if difference and not (payload.notes or '').strip():
        raise HTTPException(422, 'Debe explicar la diferencia de caja')
    row.state = 'closed'
    row.counted_cash = payload.counted_cash
    row.expected_cash = totals['expected_cash']
    row.difference = difference
    row.closing_notes = payload.notes
    row.closed_by = user.id
    row.closed_at = datetime.utcnow()
    audit(db, user, 'close', row.id, row.center_id)
    commit(db)
    return row


def billing_context(db, user, center_id, patient_id, appointment_id=None, *, lock=False):
    center = center_access(db, user, center_id)
    if not center.is_active:
        raise HTTPException(409, 'No se emiten documentos nuevos en un centro inactivo')
    patient = require_patient_identity_access(db, user, patient_id)
    coverage = None
    if appointment_id is not None:
        query = select(Appointment).where(Appointment.id == appointment_id)
        if lock:
            query = query.with_for_update().execution_options(populate_existing=True)
        appt = db.scalar(query)
        if not appt:
            raise HTTPException(404, 'Cita no encontrada')
        ensure_appointment_access(user, appt, db)
        if appt.patient_id != patient_id or appt.center_id != center_id:
            raise HTTPException(422, 'Paciente, cita y centro deben coincidir')
        if appt.status in ('cancelled', 'no_show'):
            raise HTTPException(409, 'No se factura una cita cancelada o ausente')
        coverage = db.scalar(select(AppointmentCoverage).where(AppointmentCoverage.appointment_id == appointment_id))
        if coverage and coverage.currency != 'DOP':
            raise HTTPException(422, 'Caja opera en DOP; revise la moneda de la cobertura')
    return patient, coverage


def apply_payment(db, user, invoice, register, payload):
    require_open(register)
    if invoice.voided_at or invoice.center_id != register.center_id:
        raise HTTPException(409, 'Factura anulada o caja de otro centro')
    amount = sum((part.amount for part in payload.parts), Decimal('0.00'))
    if amount > invoice.balance:
        raise HTTPException(422, 'El pago excede el saldo del paciente')
    row = CashMovement(center_id=invoice.center_id, register_id=register.id, invoice_id=invoice.id,
        kind='payment', amount=amount, parts=[{'method': p.method, 'amount': str(p.amount)} for p in payload.parts],
        request_key=str(payload.request_key), request_hash=digest(payload, f'pay:{invoice.id}:'), created_by=user.id)
    invoice.paid_amount += amount
    db.add(row); flush(db)
    audit(db, user, 'payment', row.id, row.center_id)
    return row


def create_invoice(db, user, payload):
    fingerprint = digest(payload)
    prior = replay(db, Invoice, payload, fingerprint, user)
    if prior:
        return prior
    register = register_access(db, user, payload.payment.register_id, lock=True, write=True) if payload.payment else None
    patient, coverage = billing_context(db, user, payload.center_id, payload.patient_id, payload.appointment_id, lock=True)
    prior = replay(db, Invoice, payload, fingerprint, user)
    if prior:
        return prior
    if payload.appointment_id and db.scalar(select(Invoice.id).where(Invoice.appointment_id == payload.appointment_id, Invoice.voided_at.is_(None))):
        raise HTTPException(409, 'La cita ya tiene factura; aplique el pago al saldo existente')
    if payload.coverage_revision != (coverage.revision if coverage else None):
        raise HTTPException(409, 'La cobertura cambió; revise los importes antes de confirmar')
    if coverage and (coverage.base_amount != payload.base_amount or coverage.service != payload.concept):
        raise HTTPException(409, 'Importes o concepto distintos de la cobertura; vuelva a consultarla')
    ars = coverage.covered_amount if coverage else Decimal('0.00')
    row = Invoice(center_id=payload.center_id, patient_id=patient.id, patient_name=f'{patient.first_name} {patient.last_name}',
        appointment_id=payload.appointment_id, coverage_id=coverage.id if coverage else None,
        coverage_snapshot=({'revision': coverage.revision, 'insurance': coverage.insurance_snapshot,
            'authorization_status': coverage.authorization_status, 'authorization_number': coverage.authorization_number,
            'authorized_amount': str(coverage.authorized_amount) if coverage.authorized_amount is not None else None} if coverage else {}),
        concept=payload.concept, base_amount=payload.base_amount, ars_amount=ars, patient_amount=payload.base_amount - ars,
        paid_amount=Decimal('0.00'), request_key=str(payload.request_key), request_hash=fingerprint, created_by=user.id)
    db.add(row)
    try:
        db.flush()
        audit(db, user, 'invoice_created', row.id, row.center_id)
        if payload.payment:
            apply_payment(db, user, row, register, payload.payment)
        commit(db)
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, 'Operación duplicada; recargue antes de reintentar')
    return row


def pay_invoice(db, user, invoice_id, payload):
    register = register_access(db, user, payload.register_id, lock=True, write=True)
    invoice = invoice_access(db, user, invoice_id, lock=True)
    prior = replay(db, CashMovement, payload, digest(payload, f'pay:{invoice.id}:'), user)
    if prior:
        return invoice
    apply_payment(db, user, invoice, register, payload)
    commit(db)
    return invoice


def reverse_payment(db, user, movement_id, payload):
    register = register_access(db, user, payload.register_id, lock=True, write=True)
    prior = replay(db, CashMovement, payload, digest(payload, f'reverse:{movement_id}:'), user)
    if prior:
        return prior
    require_open(register)
    original = db.get(CashMovement, movement_id)
    if original is None:
        raise HTTPException(404, 'Movimiento no encontrado')
    center_access(db, user, original.center_id)
    if original.kind != 'payment' or original.center_id != register.center_id:
        raise HTTPException(422, 'Solo puede revertir un cobro del mismo centro')
    invoice = invoice_access(db, user, original.invoice_id, lock=True)
    if db.scalar(select(CashMovement.id).where(CashMovement.reverses_id == original.id)):
        raise HTTPException(409, 'El cobro ya fue revertido')
    invoice.paid_amount -= original.amount
    row = CashMovement(center_id=register.center_id, register_id=register.id, invoice_id=invoice.id,
        reverses_id=original.id, kind='reversal', amount=original.amount, parts=original.parts,
        reason=payload.reason, request_key=str(payload.request_key), request_hash=digest(payload, f'reverse:{movement_id}:'), created_by=user.id)
    db.add(row); flush(db)
    audit(db, user, 'reversal', row.id, row.center_id)
    commit(db)
    return row


def adjust_register(db, user, register_id, payload):
    register = register_access(db, user, register_id, lock=True, write=True)
    fingerprint = digest(payload, f'adjust:{register.id}:')
    prior = replay(db, CashMovement, payload, fingerprint, user)
    if prior:
        return prior
    require_open(register)
    row = CashMovement(center_id=register.center_id, register_id=register.id, kind=payload.kind,
        amount=payload.amount, parts=[{'method': 'cash', 'amount': str(payload.amount)}], reason=payload.reason,
        request_key=str(payload.request_key), request_hash=fingerprint, created_by=user.id)
    db.add(row); flush(db)
    audit(db, user, payload.kind, row.id, row.center_id)
    commit(db)
    return row


def void_invoice(db, user, invoice_id, payload):
    row = invoice_access(db, user, invoice_id, lock=True)
    if row.voided_at or row.paid_amount:
        raise HTTPException(409, 'La factura está anulada o tiene pagos; revierta los cobros primero')
    row.voided_at, row.voided_by, row.void_reason = datetime.utcnow(), user.id, payload.reason
    audit(db, user, 'invoice_void', row.id, row.center_id)
    commit(db)
    return row


def serialize(row):
    result = {c.key: getattr(row, c.key) for c in row.__table__.columns if c.key not in {'request_hash', 'request_key'}}
    if isinstance(row, Invoice):
        result.update(number=row.number, balance=row.balance, state=row.state,
                      expected_ars=Decimal('0.00') if row.voided_at else row.ars_amount, currency='DOP')
    # Explicit decimal strings are the transport contract, never JSON floats.
    return {k: str(v) if isinstance(v, Decimal) else v for k, v in result.items()}


def register_view(db, row):
    totals = register_totals(db, row)
    return {**serialize(row), 'totals': {k: {m: str(n) for m, n in v.items()} if isinstance(v, dict) else str(v) for k, v in totals.items()}}
