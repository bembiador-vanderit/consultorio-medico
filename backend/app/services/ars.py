"""ARS claim workflow and remittance ledger; no Caja movements are created."""
from datetime import datetime
from decimal import Decimal
from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from app.models import Appointment, Patient
from app.models.administration import SecurityAudit
from app.models.ars import ArsClaim, ArsClaimEvent, ArsRemittance, ArsApplication
from app.models.finance import Invoice
from app.models.insurance import AppointmentCoverage, InsuranceCompany
from app.services.finance import center_access
from app.services.appointment_scope import is_role

TRANSITIONS = {
    'draft': {'pending', 'cancelled'},
    'pending': {'sent', 'cancelled'},
    'sent': {'received', 'glosed', 'rejected', 'cancelled'},
    'received': {'glosed', 'rejected', 'cancelled'},
    'glosed': {'corrected', 'cancelled'},
    'rejected': {'corrected', 'cancelled'},
    'corrected': {'resent', 'cancelled'},
    'resent': {'received', 'glosed', 'rejected', 'cancelled'},
    'cancelled': set(),
}


def save(db):
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, 'Referencia duplicada o cambio concurrente; actualice la vista')


def flush(db):
    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, 'Referencia duplicada o cambio concurrente; actualice la vista')


def audit(db, user, action, entity, center_id):
    db.add(SecurityAudit(actor_id=user.id, center_id=center_id, action=f'ars:{action}:{entity}'))


def event(db, user, claim, kind, before=None, code=None, note=None, amount=None):
    db.add(ArsClaimEvent(center_id=claim.center_id, claim_id=claim.id, kind=kind,
                         from_state=before, to_state=claim.state, code=code, note=note,
                         amount=amount, actor_id=user.id))
    audit(db, user, kind, claim.id, claim.center_id)


def claim_access(db, user, claim_id, lock=False):
    q = select(ArsClaim).where(ArsClaim.id == claim_id)
    if lock:
        q = q.with_for_update().execution_options(populate_existing=True)
    row = db.scalar(q)
    if not row:
        raise HTTPException(404, 'Reclamación no encontrada')
    center_access(db, user, row.center_id)
    return row


def remittance_access(db, user, remittance_id, lock=False):
    q = select(ArsRemittance).where(ArsRemittance.id == remittance_id)
    if lock:
        q = q.with_for_update().execution_options(populate_existing=True)
    row = db.scalar(q)
    if not row:
        raise HTTPException(404, 'Remesa no encontrada')
    if row.center_id is not None:
        center_access(db, user, row.center_id)
    elif not is_role(user, 'admin'):
        raise HTTPException(404, 'Remesa no encontrada')
    return row


def create_claim(db, user, payload):
    appt = db.scalar(select(Appointment).where(Appointment.id == payload.appointment_id).with_for_update())
    if not appt:
        raise HTTPException(404, 'Cita no encontrada')
    center_access(db, user, appt.center_id)
    if appt.status in ('cancelled', 'no_show'):
        raise HTTPException(409, 'La cita no es reclamable')
    if db.scalar(select(ArsClaim.id).where(ArsClaim.appointment_id == appt.id)):
        raise HTTPException(409, 'La cita ya tiene reclamación; use su historial')
    cov = db.scalar(select(AppointmentCoverage).where(AppointmentCoverage.appointment_id == appt.id))
    invoice = db.scalar(select(Invoice).where(Invoice.appointment_id == appt.id, Invoice.voided_at.is_(None)))
    if not cov or (invoice and (invoice.coverage_id != cov.id or invoice.coverage_snapshot.get('revision') != payload.coverage_revision)) or (not invoice and (cov.revision != payload.coverage_revision or cov.currency != 'DOP')):
        raise HTTPException(409, 'La cobertura o factura histórica cambió; actualice la vista')
    if invoice:
        insured = invoice.coverage_snapshot.get('insurance') or {}
        amount = invoice.ars_amount
        snapshot = {**invoice.coverage_snapshot, 'service': invoice.concept,
                    'base_amount': str(invoice.base_amount), 'patient_amount': str(invoice.patient_amount),
                    'ars_amount': str(invoice.ars_amount), 'invoice_id': invoice.id,
                    'appointment_date': str(appt.appointment_date)}
    else:
        insured = cov.insurance_snapshot or {}
        amount = cov.covered_amount
        snapshot = {'revision': cov.revision, 'insurance': insured, 'service': cov.service,
                    'base_amount': str(cov.base_amount), 'patient_amount': str(cov.patient_copay),
                    'ars_amount': str(cov.covered_amount), 'authorization_status': cov.authorization_status,
                    'authorization_number': cov.authorization_number,
                    'authorized_amount': str(cov.authorized_amount) if cov.authorized_amount is not None else None,
                    'appointment_date': str(appt.appointment_date)}
    company_id = insured.get('company_id')
    if not company_id or amount <= 0 or cov.appointment_id != appt.id:
        raise HTTPException(422, 'Se requiere cobertura ARS válida con saldo esperado')
    company = db.get(InsuranceCompany, company_id)
    if not company:
        raise HTTPException(404, 'Aseguradora no disponible')
    patient = db.get(Patient, appt.patient_id)
    row = ArsClaim(center_id=appt.center_id, patient_id=appt.patient_id, appointment_id=appt.id,
                   coverage_id=cov.id, insurance_company_id=company_id, plan_id=insured.get('plan_id'),
                   snapshot=snapshot, patient_name=f'{patient.first_name} {patient.last_name}',
                   service_date=appt.appointment_date, state='draft', claimed_amount=amount,
                   disputed_amount=Decimal('0.00'), paid_amount=Decimal('0.00'), created_by=user.id)
    db.add(row)
    flush(db)
    event(db, user, row, 'created', amount=amount)
    save(db)
    return row


def transition(db, user, claim_id, payload):
    row = claim_access(db, user, claim_id, lock=True)
    before = row.state
    if payload.state not in TRANSITIONS[before]:
        raise HTTPException(409, 'Transición no permitida')
    if row.paid_amount and payload.state == 'cancelled':
        raise HTTPException(409, 'Revierta las aplicaciones antes de cancelar')
    if payload.state == 'cancelled' and not payload.note:
        raise HTTPException(422, 'Indique el motivo de cancelación')
    row.state = payload.state
    now = datetime.utcnow()
    if payload.state in ('sent', 'resent'):
        row.submitted_at = now
    if payload.state == 'received':
        row.received_at = now
    if payload.state == 'cancelled':
        row.cancelled_at = now
    event(db, user, row, payload.state, before, note=payload.note)
    save(db)
    return row


def glosa(db, user, claim_id, payload):
    row = claim_access(db, user, claim_id, lock=True)
    if payload.kind not in TRANSITIONS[row.state]:
        raise HTTPException(409, 'La reclamación no admite glosa en este estado')
    if payload.amount > row.claimed_amount:
        raise HTTPException(422, 'Glosa superior al monto reclamado')
    approved = payload.approved_amount if payload.approved_amount is not None else row.claimed_amount - payload.amount
    if approved != row.claimed_amount - payload.amount or approved < row.paid_amount:
        raise HTTPException(422, 'Reclamado debe ser igual a aprobado más glosado; aprobado no puede ser inferior a lo pagado')
    before = row.state
    row.state, row.disputed_amount, row.approved_amount = payload.kind, payload.amount, approved
    event(db, user, row, payload.kind, before, code=payload.code, note=payload.note, amount=payload.amount)
    save(db)
    return row


def correct(db, user, claim_id, payload):
    row = claim_access(db, user, claim_id, lock=True)
    if row.state not in ('glosed', 'rejected'):
        raise HTTPException(409, 'Solo una glosa o rechazo admite corrección')
    if payload.approved_amount > row.claimed_amount or payload.approved_amount < row.paid_amount:
        raise HTTPException(422, 'Aprobado fuera de los importes permitidos')
    before = row.state
    previous = row.approved_amount
    row.approved_amount = payload.approved_amount
    row.disputed_amount = row.claimed_amount - payload.approved_amount
    row.state = 'corrected'
    event(db, user, row, 'corrected', before, note=f'{payload.note[:930]} · aprobado anterior {previous}', amount=payload.approved_amount)
    save(db)
    return row


def create_remittance(db, user, payload):
    if payload.center_id is not None:
        center_access(db, user, payload.center_id)
    elif not is_role(user, 'admin'):
        raise HTTPException(403, 'Indique un centro autorizado')
    company = db.get(InsuranceCompany, payload.insurance_company_id)
    if not company:
        raise HTTPException(404, 'Aseguradora no disponible')
    row = ArsRemittance(center_id=payload.center_id, insurance_company_id=company.id,
                        company_name=company.name, received_on=payload.received_on,
                        reference=payload.reference.strip(), amount=payload.amount,
                        applied_amount=Decimal('0.00'), created_by=user.id)
    db.add(row)
    flush(db)
    audit(db, user, 'remittance_created', row.id, row.center_id)
    save(db)
    return row


def apply(db, user, remittance_id, payload):
    rem = remittance_access(db, user, remittance_id, lock=True)
    if len({x.claim_id for x in payload.allocations}) != len(payload.allocations):
        raise HTTPException(422, 'Consolide cada reclamación en una línea')
    total = sum((x.amount for x in payload.allocations), Decimal('0.00'))
    if total > rem.unapplied:
        raise HTTPException(422, 'Aplicación superior al saldo de la remesa')
    entries = {x.claim_id: x for x in payload.allocations}
    for claim_id in sorted(entries):
        item = entries[claim_id]
        claim = claim_access(db, user, claim_id, lock=True)
        if claim.insurance_company_id != rem.insurance_company_id or (rem.center_id is not None and claim.center_id != rem.center_id):
            raise HTTPException(422, 'La aseguradora y el centro deben coincidir')
        if claim.state not in ('sent', 'received', 'resent', 'glosed', 'rejected') or claim.balance <= 0:
            raise HTTPException(409, 'La reclamación no está lista para recibir pagos')
        if item.amount > claim.balance:
            raise HTTPException(422, 'Aplicación superior al saldo de la reclamación')
        row = ArsApplication(center_id=claim.center_id, remittance_id=rem.id, claim_id=claim.id,
                             amount=item.amount, created_by=user.id)
        db.add(row)
        claim.paid_amount += item.amount
        rem.applied_amount += item.amount
        flush(db)
        event(db, user, claim, 'applied', claim.state, amount=item.amount)
        audit(db, user, 'application_created', row.id, claim.center_id)
    save(db)
    return rem


def reverse(db, user, application_id, payload):
    original = db.get(ArsApplication, application_id)
    if not original:
        raise HTTPException(404, 'Aplicación no encontrada')
    center_access(db, user, original.center_id)
    rem = remittance_access(db, user, original.remittance_id, lock=True)
    claim = claim_access(db, user, original.claim_id, lock=True)
    row = db.scalar(select(ArsApplication).where(ArsApplication.id == application_id).with_for_update().execution_options(populate_existing=True))
    if row.reversed_at:
        raise HTTPException(409, 'Aplicación ya revertida')
    row.reversed_at, row.reversed_by, row.reversal_reason = datetime.utcnow(), user.id, payload.reason
    rem.applied_amount -= row.amount
    claim.paid_amount -= row.amount
    event(db, user, claim, 'application_reversed', claim.state, note=payload.reason, amount=row.amount)
    audit(db, user, 'application_reversed', row.id, row.center_id)
    save(db)
    return row


def serialize(row):
    result = {c.key: getattr(row, c.key) for c in row.__table__.columns}
    if isinstance(row, ArsClaim):
        result.update(balance=row.balance, collectible=row.collectible, display_state=row.display_state)
    if isinstance(row, ArsRemittance):
        result['unapplied'] = row.unapplied
    return {key: str(value) if isinstance(value, Decimal) else value for key, value in result.items()}
