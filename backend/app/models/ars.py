"""ARS receivables are independent of patient cash movements."""
from datetime import date, datetime
from decimal import Decimal
from sqlalchemy import CheckConstraint, Date, DateTime, ForeignKey, JSON, Numeric, String, UniqueConstraint, Index
from sqlalchemy.orm import Mapped, mapped_column
from app.db import Base
from app.models.organization import TenantOwned


class ArsClaim(TenantOwned, Base):
    __tablename__ = 'ars_claims'
    __table_args__ = (
        UniqueConstraint('organization_id', 'appointment_id', name='uq_ars_claim_appointment'),
        CheckConstraint('claimed_amount > 0 AND paid_amount >= 0 AND disputed_amount >= 0 AND disputed_amount <= claimed_amount AND (approved_amount IS NULL OR (approved_amount >= 0 AND approved_amount + disputed_amount = claimed_amount)) AND paid_amount <= COALESCE(approved_amount, claimed_amount - disputed_amount)', name='ck_ars_claim_amounts'),
        Index('ix_ars_claim_aging', 'organization_id', 'insurance_company_id', 'service_date'),
    )
    id: Mapped[int] = mapped_column(primary_key=True)
    center_id: Mapped[int] = mapped_column(ForeignKey('care_centers.id', ondelete='RESTRICT'), index=True)
    patient_id: Mapped[int] = mapped_column(ForeignKey('patients.id', ondelete='RESTRICT'), index=True)
    appointment_id: Mapped[int] = mapped_column(ForeignKey('appointments.id', ondelete='RESTRICT'))
    coverage_id: Mapped[int] = mapped_column(ForeignKey('appointment_insurance_coverages.id', ondelete='RESTRICT'))
    insurance_company_id: Mapped[int] = mapped_column(ForeignKey('insurance_companies.id', ondelete='RESTRICT'), index=True)
    plan_id: Mapped[int | None] = mapped_column(ForeignKey('insurance_plans.id', ondelete='RESTRICT'))
    snapshot: Mapped[dict] = mapped_column(JSON)
    patient_name: Mapped[str] = mapped_column(String(201))
    service_date: Mapped[date] = mapped_column(Date)
    state: Mapped[str] = mapped_column(String(30), default='draft')
    claimed_amount: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    approved_amount: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))
    disputed_amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=0)
    paid_amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=0)
    created_by: Mapped[int] = mapped_column(ForeignKey('users.id', ondelete='RESTRICT'))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime)
    received_at: Mapped[datetime | None] = mapped_column(DateTime)
    cancelled_at: Mapped[datetime | None] = mapped_column(DateTime)

    @property
    def collectible(self):
        return max(Decimal('0.00'), (self.approved_amount if self.approved_amount is not None else self.claimed_amount - self.disputed_amount))

    @property
    def balance(self):
        return self.collectible - self.paid_amount if self.state != 'cancelled' else Decimal('0.00')

    @property
    def display_state(self):
        if self.state == 'cancelled':
            return 'cancelled'
        if self.paid_amount and self.balance == 0:
            return 'paid'
        if self.paid_amount:
            return 'partial'
        return self.state


class ArsClaimEvent(TenantOwned, Base):
    __tablename__ = 'ars_claim_events'
    id: Mapped[int] = mapped_column(primary_key=True)
    center_id: Mapped[int] = mapped_column(ForeignKey('care_centers.id', ondelete='RESTRICT'))
    claim_id: Mapped[int] = mapped_column(ForeignKey('ars_claims.id', ondelete='RESTRICT'), index=True)
    kind: Mapped[str] = mapped_column(String(30))
    from_state: Mapped[str | None] = mapped_column(String(30))
    to_state: Mapped[str] = mapped_column(String(30))
    code: Mapped[str | None] = mapped_column(String(50))
    note: Mapped[str | None] = mapped_column(String(1000))
    amount: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))
    actor_id: Mapped[int] = mapped_column(ForeignKey('users.id', ondelete='RESTRICT'))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class ArsRemittance(TenantOwned, Base):
    __tablename__ = 'ars_remittances'
    __table_args__ = (
        UniqueConstraint('organization_id', 'insurance_company_id', 'reference', name='uq_ars_remittance_reference'),
        CheckConstraint('amount > 0 AND applied_amount >= 0 AND applied_amount <= amount', name='ck_ars_remittance_amounts'),
    )
    id: Mapped[int] = mapped_column(primary_key=True)
    center_id: Mapped[int | None] = mapped_column(ForeignKey('care_centers.id', ondelete='RESTRICT'), index=True)
    insurance_company_id: Mapped[int] = mapped_column(ForeignKey('insurance_companies.id', ondelete='RESTRICT'), index=True)
    company_name: Mapped[str] = mapped_column(String(150))
    received_on: Mapped[date] = mapped_column(Date)
    reference: Mapped[str] = mapped_column(String(100))
    amount: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    applied_amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=0)
    created_by: Mapped[int] = mapped_column(ForeignKey('users.id', ondelete='RESTRICT'))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    @property
    def unapplied(self):
        return self.amount - self.applied_amount


class ArsApplication(TenantOwned, Base):
    __tablename__ = 'ars_applications'
    __table_args__ = (CheckConstraint('amount > 0', name='ck_ars_application_amount'),)
    id: Mapped[int] = mapped_column(primary_key=True)
    center_id: Mapped[int] = mapped_column(ForeignKey('care_centers.id', ondelete='RESTRICT'))
    remittance_id: Mapped[int] = mapped_column(ForeignKey('ars_remittances.id', ondelete='RESTRICT'), index=True)
    claim_id: Mapped[int] = mapped_column(ForeignKey('ars_claims.id', ondelete='RESTRICT'), index=True)
    amount: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    created_by: Mapped[int] = mapped_column(ForeignKey('users.id', ondelete='RESTRICT'))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    reversed_by: Mapped[int | None] = mapped_column(ForeignKey('users.id', ondelete='RESTRICT'))
    reversed_at: Mapped[datetime | None] = mapped_column(DateTime)
    reversal_reason: Mapped[str | None] = mapped_column(String(1000))
