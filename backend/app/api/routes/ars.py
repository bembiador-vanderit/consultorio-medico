from datetime import date
from decimal import Decimal
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select, case, or_, exists
from sqlalchemy.orm import Session
from app.api.deps import require_permission
from app.db import get_db
from app.models import User, CareCenter, Appointment, Patient
from app.models.ars import ArsClaim, ArsClaimEvent, ArsRemittance, ArsApplication
from app.models.finance import Invoice
from app.models.insurance import InsuranceCompany, AppointmentCoverage
from app.schemas.ars import NewClaim, Transition, Glosa, Correction, RemittanceInput, ApplyInput, ReverseInput
from app.services import ars as service
from app.services.appointment_scope import assigned_center_ids, is_role
from app.services.finance import center_access

router = APIRouter(prefix='/ars', tags=['Reclamaciones y cuentas por cobrar ARS'])
read = require_permission('ars:read')


@router.get('/centers')
def centers(user: User = Depends(read), db: Session = Depends(get_db)):
    q = select(CareCenter)
    if not is_role(user, 'admin'):
        q = q.where(CareCenter.id.in_(assigned_center_ids(user)))
    return [{'id': c.id, 'name': c.name} for c in db.scalars(q.order_by(CareCenter.name))]


def scoped(q, model, user, center_id=None):
    if center_id is not None:
        return q.where(model.center_id == center_id)
    return q if is_role(user, 'admin') else q.where(model.center_id.in_(assigned_center_ids(user)))


def state_filter(q, state):
    if not state:
        return q
    collectible = case((ArsClaim.approved_amount.is_not(None), ArsClaim.approved_amount), else_=ArsClaim.claimed_amount - ArsClaim.disputed_amount)
    if state == 'paid':
        return q.where(ArsClaim.state != 'cancelled', ArsClaim.paid_amount > 0, ArsClaim.paid_amount == collectible)
    if state == 'partial':
        return q.where(ArsClaim.state != 'cancelled', ArsClaim.paid_amount > 0, ArsClaim.paid_amount < collectible)
    return q.where(ArsClaim.state == state)


@router.get('/companies')
def companies(user: User = Depends(read), db: Session = Depends(get_db)):
    return [{'id': c.id, 'name': c.name} for c in db.scalars(select(InsuranceCompany).order_by(InsuranceCompany.name))]


@router.get('/eligible-appointments')
def eligible_appointments(center_id: int, q: str = Query(min_length=2, max_length=100),
                          user: User = Depends(require_permission('ars:claim')), db: Session = Depends(get_db)):
    center_access(db, user, center_id)
    query = (select(Appointment, Patient, AppointmentCoverage)
             .join(Patient, Patient.id == Appointment.patient_id)
             .join(AppointmentCoverage, AppointmentCoverage.appointment_id == Appointment.id)
             .outerjoin(Invoice, (Invoice.appointment_id == Appointment.id) & Invoice.voided_at.is_(None))
             .where(Appointment.center_id == center_id, Appointment.status.not_in(('cancelled', 'no_show')),
                    or_((AppointmentCoverage.covered_amount > 0) & (AppointmentCoverage.currency == 'DOP'), Invoice.ars_amount > 0),
                    or_(Patient.first_name.ilike(f'%{q}%'), Patient.last_name.ilike(f'%{q}%')),
                    ~exists(select(ArsClaim.id).where(ArsClaim.appointment_id == Appointment.id))))
    rows = []
    for a, p, cov in db.execute(query.order_by(Appointment.appointment_date.desc(), Appointment.id.desc()).limit(20)):
        invoice = db.scalar(select(Invoice).where(Invoice.appointment_id == a.id, Invoice.voided_at.is_(None)))
        rows.append({'id': a.id, 'date': a.appointment_date, 'patient_name': f'{p.first_name} {p.last_name}',
                     'coverage_revision': invoice.coverage_snapshot.get('revision') if invoice else cov.revision,
                     'ars_amount': str(invoice.ars_amount if invoice else cov.covered_amount)})
    return rows


@router.post('/claims', status_code=201)
def create_claim(payload: NewClaim, user: User = Depends(require_permission('ars:claim')), db: Session = Depends(get_db)):
    return service.serialize(service.create_claim(db, user, payload))


@router.get('/claims')
def claims(center_id: int | None = None, insurance_company_id: int | None = None, state: str | None = None,
           patient_id: int | None = None, patient_name: str | None = Query(default=None, max_length=100),
           from_date: date | None = None, to_date: date | None = None,
           offset: int = Query(0, ge=0), limit: int = Query(50, ge=1, le=100),
           user: User = Depends(read), db: Session = Depends(get_db)):
    if center_id is not None:
        center_access(db, user, center_id)
    q = scoped(select(ArsClaim), ArsClaim, user, center_id)
    if insurance_company_id is not None:
        q = q.where(ArsClaim.insurance_company_id == insurance_company_id)
    q = state_filter(q, state)
    if patient_id is not None:
        q = q.where(ArsClaim.patient_id == patient_id)
    if patient_name:
        q = q.where(ArsClaim.patient_name.ilike(f'%{patient_name}%'))
    if from_date:
        q = q.where(ArsClaim.service_date >= from_date)
    if to_date:
        q = q.where(ArsClaim.service_date <= to_date)
    return [service.serialize(r) for r in db.scalars(q.order_by(ArsClaim.id.desc()).offset(offset).limit(limit))]


@router.get('/claims/{claim_id}')
def claim(claim_id: int, user: User = Depends(read), db: Session = Depends(get_db)):
    row = service.claim_access(db, user, claim_id)
    return {**service.serialize(row),
            'events': [service.serialize(e) for e in db.scalars(select(ArsClaimEvent).where(ArsClaimEvent.claim_id == row.id).order_by(ArsClaimEvent.id))],
            'applications': [service.serialize(a) for a in db.scalars(select(ArsApplication).where(ArsApplication.claim_id == row.id).order_by(ArsApplication.id))]}


@router.post('/claims/{claim_id}/transition')
def transition(claim_id: int, payload: Transition, user: User = Depends(require_permission('ars:send')), db: Session = Depends(get_db)):
    return service.serialize(service.transition(db, user, claim_id, payload))


@router.post('/claims/{claim_id}/glosa')
def glosa(claim_id: int, payload: Glosa, user: User = Depends(require_permission('ars:glosa')), db: Session = Depends(get_db)):
    return service.serialize(service.glosa(db, user, claim_id, payload))


@router.post('/claims/{claim_id}/correction')
def correction(claim_id: int, payload: Correction, user: User = Depends(require_permission('ars:claim')), db: Session = Depends(get_db)):
    return service.serialize(service.correct(db, user, claim_id, payload))


@router.post('/remittances', status_code=201)
def create_remittance(payload: RemittanceInput, user: User = Depends(require_permission('ars:payment')), db: Session = Depends(get_db)):
    return service.serialize(service.create_remittance(db, user, payload))


@router.get('/remittances')
def remittances(center_id: int | None = None, insurance_company_id: int | None = None,
                offset: int = Query(0, ge=0), limit: int = Query(50, ge=1, le=100),
                user: User = Depends(read), db: Session = Depends(get_db)):
    if center_id is not None:
        center_access(db, user, center_id)
    q = scoped(select(ArsRemittance), ArsRemittance, user, center_id)
    if insurance_company_id is not None:
        q = q.where(ArsRemittance.insurance_company_id == insurance_company_id)
    return [service.serialize(r) for r in db.scalars(q.order_by(ArsRemittance.id.desc()).offset(offset).limit(limit))]


@router.get('/remittances/{remittance_id}')
def remittance(remittance_id: int, user: User = Depends(read), db: Session = Depends(get_db)):
    row = service.remittance_access(db, user, remittance_id)
    return {**service.serialize(row), 'applications': [service.serialize(a) for a in db.scalars(select(ArsApplication).where(ArsApplication.remittance_id == row.id).order_by(ArsApplication.id))]}


@router.post('/remittances/{remittance_id}/apply')
def apply(remittance_id: int, payload: ApplyInput, user: User = Depends(require_permission('ars:payment')), db: Session = Depends(get_db)):
    return service.serialize(service.apply(db, user, remittance_id, payload))


@router.post('/applications/{application_id}/reverse')
def reverse(application_id: int, payload: ReverseInput, user: User = Depends(require_permission('ars:payment')), db: Session = Depends(get_db)):
    return service.serialize(service.reverse(db, user, application_id, payload))


@router.get('/receivables')
def receivables(center_id: int | None = None, insurance_company_id: int | None = None,
                patient_id: int | None = None, patient_name: str | None = Query(default=None, max_length=100),
                state: str | None = None, as_of: date | None = None,
                offset: int = Query(0, ge=0), limit: int = Query(50, ge=1, le=100),
                user: User = Depends(require_permission('ars:report')), db: Session = Depends(get_db)):
    if center_id is not None:
        center_access(db, user, center_id)
    collectible = case((ArsClaim.approved_amount.is_not(None), ArsClaim.approved_amount), else_=ArsClaim.claimed_amount - ArsClaim.disputed_amount)
    q = scoped(select(ArsClaim).where(ArsClaim.state != 'cancelled', collectible > ArsClaim.paid_amount), ArsClaim, user, center_id)
    if insurance_company_id is not None:
        q = q.where(ArsClaim.insurance_company_id == insurance_company_id)
    if patient_id is not None:
        q = q.where(ArsClaim.patient_id == patient_id)
    if patient_name:
        q = q.where(ArsClaim.patient_name.ilike(f'%{patient_name}%'))
    q = state_filter(q, state)
    today = as_of or date.today()
    rows = []
    for row in db.scalars(q.order_by(ArsClaim.service_date, ArsClaim.id).offset(offset).limit(limit)):
        days = max(0, (today - row.service_date).days)
        bucket = '0-30' if days <= 30 else '31-60' if days <= 60 else '61-90' if days <= 90 else '90+'
        rows.append({**service.serialize(row), 'days_open': days, 'aging_bucket': bucket})
    return rows


@router.get('/reconciliation')
def reconciliation(from_date: date, to_date: date, center_id: int | None = None,
                   user: User = Depends(require_permission('ars:reconcile')), db: Session = Depends(get_db)):
    if center_id is not None:
        center_access(db, user, center_id)
    if to_date < from_date:
        raise HTTPException(422, 'Período inválido')
    q = scoped(select(ArsClaim).where(ArsClaim.service_date >= from_date, ArsClaim.service_date <= to_date), ArsClaim, user, center_id)
    groups = {}
    for row in db.scalars(q):
        key = row.insurance_company_id
        if key not in groups:
            groups[key] = {'insurance_company_id': key, 'company_name': row.snapshot['insurance']['company_name'],
                           'claims': 0, 'claimed': Decimal('0'), 'approved': Decimal('0'), 'collectible': Decimal('0'), 'paid': Decimal('0'),
                           'disputed': Decimal('0'), 'pending': Decimal('0'), 'aging': {x: Decimal('0') for x in ('0-30','31-60','61-90','90+')}}
        item = groups[key]
        item['claims'] += 1
        item['claimed'] += row.claimed_amount
        item['approved'] += row.approved_amount or Decimal('0')
        item['collectible'] += row.collectible if row.state != 'cancelled' else Decimal('0')
        item['paid'] += row.paid_amount
        item['disputed'] += row.disputed_amount
        item['pending'] += row.balance
        if row.balance > 0:
            days = max(0, (date.today() - row.service_date).days)
            bucket = '0-30' if days <= 30 else '31-60' if days <= 60 else '61-90' if days <= 90 else '90+'
            item['aging'][bucket] += row.balance
    return [{**item, **{k: str(item[k]) for k in ('claimed','approved','collectible','paid','disputed','pending')},
             'aging': {k: str(v) for k, v in item['aging'].items()}} for item in groups.values()]
