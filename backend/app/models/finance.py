"""Internal DOP ledger. Corrections append movements; nothing is deleted."""
from datetime import datetime
from decimal import Decimal
from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, JSON, Numeric, String, UniqueConstraint, text
from sqlalchemy.orm import Mapped, mapped_column
from app.db import Base
from app.models.organization import TenantOwned


class CashRegister(TenantOwned, Base):
    __tablename__ = "cash_registers"
    __table_args__ = (
        CheckConstraint("opening_amount >= 0 AND (counted_cash IS NULL OR counted_cash >= 0)", name="ck_register_amounts"),
        CheckConstraint("state IN ('open', 'closed')", name="ck_register_state"),
        Index("uq_open_register", "organization_id", "center_id", "opened_by", unique=True,
              postgresql_where=text("state = 'open'"), sqlite_where=text("state = 'open'")),
    )
    id: Mapped[int] = mapped_column(primary_key=True)
    center_id: Mapped[int] = mapped_column(ForeignKey("care_centers.id", ondelete="RESTRICT"), index=True)
    opened_by: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"))
    closed_by: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"))
    state: Mapped[str] = mapped_column(String(10), default="open")
    opening_amount: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    counted_cash: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))
    expected_cash: Mapped[Decimal | None] = mapped_column(Numeric(14, 2))
    difference: Mapped[Decimal | None] = mapped_column(Numeric(14, 2))
    opening_notes: Mapped[str | None] = mapped_column(String(1000))
    closing_notes: Mapped[str | None] = mapped_column(String(1000))
    opened_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    closed_at: Mapped[datetime | None] = mapped_column(DateTime)


class Invoice(TenantOwned, Base):
    __tablename__ = "financial_invoices"
    __table_args__ = (
        UniqueConstraint("organization_id", "request_key", name="uq_invoice_request"),
        CheckConstraint("base_amount >= 0 AND ars_amount >= 0 AND patient_amount >= 0 AND paid_amount >= 0 AND paid_amount <= patient_amount", name="ck_invoice_amounts"),
        CheckConstraint("base_amount = ars_amount + patient_amount", name="ck_invoice_total"),
        Index("uq_active_appointment_invoice", "appointment_id", unique=True,
              postgresql_where=text("voided_at IS NULL"), sqlite_where=text("voided_at IS NULL")),
    )
    id: Mapped[int] = mapped_column(primary_key=True)
    center_id: Mapped[int] = mapped_column(ForeignKey("care_centers.id", ondelete="RESTRICT"), index=True)
    patient_id: Mapped[int] = mapped_column(ForeignKey("patients.id", ondelete="RESTRICT"), index=True)
    appointment_id: Mapped[int | None] = mapped_column(ForeignKey("appointments.id", ondelete="RESTRICT"), index=True)
    coverage_id: Mapped[int | None] = mapped_column(ForeignKey("appointment_insurance_coverages.id", ondelete="RESTRICT"))
    coverage_snapshot: Mapped[dict] = mapped_column(JSON, default=dict)
    patient_name: Mapped[str] = mapped_column(String(201))
    concept: Mapped[str] = mapped_column(String(200))
    base_amount: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    ars_amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=0)
    patient_amount: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    paid_amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=0)
    request_key: Mapped[str] = mapped_column(String(36))
    request_hash: Mapped[str] = mapped_column(String(64))
    created_by: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    voided_at: Mapped[datetime | None] = mapped_column(DateTime)
    voided_by: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"))
    void_reason: Mapped[str | None] = mapped_column(String(1000))

    @property
    def number(self):
        return f"INT-{self.organization_id}-{self.id:08d}"

    @property
    def balance(self):
        return self.patient_amount - self.paid_amount if not self.voided_at else Decimal("0.00")

    @property
    def state(self):
        return "void" if self.voided_at else "paid" if self.balance == 0 else "partial" if self.paid_amount else "pending"


class CashMovement(TenantOwned, Base):
    __tablename__ = "cash_movements"
    __table_args__ = (
        UniqueConstraint("organization_id", "request_key", name="uq_movement_request"),
        CheckConstraint("amount > 0", name="ck_movement_positive"),
        CheckConstraint("kind IN ('payment','reversal','adjustment_in','adjustment_out')", name="ck_movement_kind"),
    )
    id: Mapped[int] = mapped_column(primary_key=True)
    center_id: Mapped[int] = mapped_column(ForeignKey("care_centers.id", ondelete="RESTRICT"), index=True)
    register_id: Mapped[int] = mapped_column(ForeignKey("cash_registers.id", ondelete="RESTRICT"), index=True)
    invoice_id: Mapped[int | None] = mapped_column(ForeignKey("financial_invoices.id", ondelete="RESTRICT"), index=True)
    reverses_id: Mapped[int | None] = mapped_column(ForeignKey("cash_movements.id", ondelete="RESTRICT"), unique=True)
    kind: Mapped[str] = mapped_column(String(20))
    amount: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    # Exact decimal strings, one component per method; their sum is amount.
    parts: Mapped[list] = mapped_column(JSON)
    reason: Mapped[str | None] = mapped_column(String(1000))
    request_key: Mapped[str] = mapped_column(String(36))
    request_hash: Mapped[str] = mapped_column(String(64))
    created_by: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)
