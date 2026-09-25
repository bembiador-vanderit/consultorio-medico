from datetime import date, datetime, time, timedelta, timezone
from decimal import Decimal
from zoneinfo import ZoneInfo
from fastapi import APIRouter, Depends, Query
from sqlalchemy import select, func, or_
from sqlalchemy.orm import Session
from app.api.deps import require_permission
from app.db import get_db
from app.models import Appointment, CareCenter, Organization, Patient, User
from app.models.finance import CashRegister, CashMovement, Invoice
from app.schemas.finance import OpenRegister, CloseRegister, NewInvoice, Payment, Reversal, Adjustment, VoidInvoice
from app.services import finance as service
from app.services.appointment_scope import assigned_center_ids, is_role, apply_appointment_scope
from app.services.patient_scope import scope_patient_identities

router = APIRouter(prefix='/finance', tags=['Caja / Facturación'])
read = require_permission('finance:read')


def collect(user: User = Depends(require_permission('finance:collect')), _: User = Depends(read)):
    return user


def manage(user: User = Depends(require_permission('finance:manage')), _: User = Depends(read)):
    return user


@router.get('/centers')
def centers(user: User = Depends(read), db: Session = Depends(get_db)):
    q = select(CareCenter)
    if not is_role(user, 'admin'):
        q = q.where(CareCenter.id.in_(assigned_center_ids(user)))
    return [{'id': c.id, 'name': c.name, 'is_active': c.is_active} for c in db.scalars(q.order_by(CareCenter.name))]


@router.get('/patients')
def patients(center_id: int, q: str = Query(min_length=2, max_length=100), user: User = Depends(collect), db: Session = Depends(get_db)):
    service.center_access(db, user, center_id)
    query = scope_patient_identities(select(Patient), user, db).where(or_(Patient.first_name.ilike(f'%{q}%'), Patient.last_name.ilike(f'%{q}%')))
    return [{'id': p.id, 'name': f'{p.first_name} {p.last_name}'} for p in db.scalars(query.order_by(Patient.last_name, Patient.id).limit(20))]


@router.get('/appointments')
def appointments(center_id: int, patient_id: int, user: User = Depends(collect), db: Session = Depends(get_db)):
    service.billing_context(db, user, center_id, patient_id)
    q = apply_appointment_scope(select(Appointment), user, db).where(Appointment.center_id == center_id, Appointment.patient_id == patient_id)
    return [{'id': a.id, 'date': a.appointment_date, 'status': a.status} for a in db.scalars(q.order_by(Appointment.appointment_date.desc(), Appointment.id.desc()).limit(100))]


@router.get('/preview')
def preview(center_id: int, patient_id: int, appointment_id: int | None = None, user: User = Depends(collect), db: Session = Depends(get_db)):
    _, coverage = service.billing_context(db, user, center_id, patient_id, appointment_id)
    invoice = db.scalar(select(Invoice).where(Invoice.appointment_id == appointment_id, Invoice.voided_at.is_(None))) if appointment_id else None
    return {'coverage': ({'revision': coverage.revision, 'concept': coverage.service, 'base_amount': str(coverage.base_amount),
        'ars_amount': str(coverage.covered_amount), 'patient_amount': str(coverage.patient_copay),
        'insurance': coverage.insurance_snapshot, 'authorization_status': coverage.authorization_status} if coverage else None),
        'invoice': service.serialize(invoice) if invoice else None}


@router.get('/registers')
def registers(center_id: int, user: User = Depends(read), db: Session = Depends(get_db)):
    service.center_access(db, user, center_id)
    q = select(CashRegister).where(CashRegister.center_id == center_id)
    # Keep all open registers discoverable; history is paged separately by ID.
    rows = db.scalars(q.order_by(CashRegister.state.desc(), CashRegister.id.desc()).limit(100))
    return [service.register_view(db, r) for r in rows]


@router.get('/registers/{register_id}')
def register(register_id: int, user: User = Depends(read), db: Session = Depends(get_db)):
    return service.register_view(db, service.register_access(db, user, register_id))


@router.post('/registers', status_code=201)
def open_register(payload: OpenRegister, user: User = Depends(collect), db: Session = Depends(get_db)):
    return service.register_view(db, service.open_register(db, user, payload))


@router.post('/registers/{register_id}/close')
def close_register(register_id: int, payload: CloseRegister, user: User = Depends(collect), db: Session = Depends(get_db)):
    return service.register_view(db, service.close_register(db, user, register_id, payload))


@router.post('/registers/{register_id}/adjustments', status_code=201)
def adjust(register_id: int, payload: Adjustment, user: User = Depends(manage), db: Session = Depends(get_db)):
    return service.serialize(service.adjust_register(db, user, register_id, payload))


@router.get('/invoices')
def invoices(center_id: int, pending: bool = False, patient_id: int | None = None,
             offset: int = Query(0, ge=0), limit: int = Query(50, ge=1, le=100),
             user: User = Depends(read), db: Session = Depends(get_db)):
    service.center_access(db, user, center_id)
    q = select(Invoice).where(Invoice.center_id == center_id)
    if pending:
        q = q.where(Invoice.voided_at.is_(None), Invoice.patient_amount > Invoice.paid_amount)
    if patient_id is not None:
        q = q.where(Invoice.patient_id == patient_id)
    return [service.serialize(r) for r in db.scalars(q.order_by(Invoice.id.desc()).offset(offset).limit(limit))]


@router.post('/invoices', status_code=201)
def create_invoice(payload: NewInvoice, user: User = Depends(collect), db: Session = Depends(get_db)):
    return service.serialize(service.create_invoice(db, user, payload))


@router.get('/invoices/{invoice_id}')
def invoice(invoice_id: int, user: User = Depends(read), db: Session = Depends(get_db)):
    row = service.invoice_access(db, user, invoice_id)
    return {**service.serialize(row), 'movements': [service.serialize(m) for m in db.scalars(select(CashMovement).where(CashMovement.invoice_id == row.id).order_by(CashMovement.id))]}


@router.post('/invoices/{invoice_id}/payments')
def pay(invoice_id: int, payload: Payment, user: User = Depends(collect), db: Session = Depends(get_db)):
    return service.serialize(service.pay_invoice(db, user, invoice_id, payload))


@router.post('/invoices/{invoice_id}/void')
def void(invoice_id: int, payload: VoidInvoice, user: User = Depends(manage), db: Session = Depends(get_db)):
    return service.serialize(service.void_invoice(db, user, invoice_id, payload))


@router.post('/movements/{movement_id}/reverse', status_code=201)
def reverse(movement_id: int, payload: Reversal, user: User = Depends(manage), db: Session = Depends(get_db)):
    return service.serialize(service.reverse_payment(db, user, movement_id, payload))


def day_bounds(db, day):
    org = db.get(Organization, db.info.get('organization_id', 1))
    zone = ZoneInfo(org.timezone)
    start = datetime.combine(day, time.min, zone)
    return start.astimezone(timezone.utc).replace(tzinfo=None), (start + timedelta(days=1)).astimezone(timezone.utc).replace(tzinfo=None)


@router.get('/movements')
def movements(center_id: int, day: date, offset: int = Query(0, ge=0), limit: int = Query(50, ge=1, le=100),
              user: User = Depends(read), db: Session = Depends(get_db)):
    service.center_access(db, user, center_id)
    start, end = day_bounds(db, day)
    q = select(CashMovement).where(CashMovement.center_id == center_id, CashMovement.created_at >= start, CashMovement.created_at < end)
    return [service.serialize(m) for m in db.scalars(q.order_by(CashMovement.id.desc()).offset(offset).limit(limit))]


@router.get('/summary')
def summary(center_id: int, day: date, user: User = Depends(read), db: Session = Depends(get_db)):
    service.center_access(db, user, center_id)
    start, end = day_bounds(db, day)
    gross = {key: Decimal('0.00') for key in service.METHODS}
    returns = dict(gross)
    insured = private = adjustments = Decimal('0.00')
    q = select(CashMovement, Invoice).outerjoin(Invoice, Invoice.id == CashMovement.invoice_id).where(
        CashMovement.center_id == center_id, CashMovement.created_at >= start, CashMovement.created_at < end)
    for movement, bill in db.execute(q):
        if movement.kind in ('payment', 'reversal'):
            target = gross if movement.kind == 'payment' else returns
            for part in movement.parts:
                target[part['method']] += Decimal(part['amount'])
            signed = movement.amount * (1 if movement.kind == 'payment' else -1)
            if bill.coverage_snapshot.get('insurance'):
                insured += signed
            else:
                private += signed
        else:
            adjustments += movement.amount * (1 if movement.kind == 'adjustment_in' else -1)
    pending, ars = db.execute(select(func.coalesce(func.sum(Invoice.patient_amount - Invoice.paid_amount), 0),
        func.coalesce(func.sum(Invoice.ars_amount), 0)).where(Invoice.center_id == center_id, Invoice.voided_at.is_(None))).one()
    return {'day': day, 'collected': {k: str(v) for k, v in gross.items()}, 'reversed': {k: str(v) for k, v in returns.items()},
            'copays': str(insured), 'private': str(private), 'adjustments': str(adjustments), 'patient_pending': str(pending), 'ars_expected': str(ars)}
