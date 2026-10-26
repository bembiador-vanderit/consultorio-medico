from datetime import date, datetime
from decimal import Decimal
from sqlalchemy import Boolean, Date, DateTime, ForeignKey, String, Numeric, CheckConstraint, UniqueConstraint, JSON
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.db import Base
from app.models.organization import TenantOwned

class InsuranceCompany(TenantOwned, Base):
    __tablename__ = "insurance_companies"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(150), index=True)
    code: Mapped[str | None] = mapped_column(String(50), nullable=True, index=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    patient_insurances: Mapped[list["PatientInsurance"]] = relationship(
        back_populates="insurance_company"
    )

class PatientInsurance(TenantOwned, Base):
    __tablename__ = "patient_insurances"
    __table_args__ = (CheckConstraint("valid_until IS NULL OR valid_from IS NULL OR valid_until >= valid_from", name="ck_insurance_period"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    patient_id: Mapped[int] = mapped_column(
        ForeignKey("patients.id", ondelete="CASCADE"), index=True
    )
    insurance_company_id: Mapped[int] = mapped_column(
        ForeignKey("insurance_companies.id", ondelete="RESTRICT"), index=True
    )
    member_number: Mapped[str] = mapped_column(String(100))
    plan_name: Mapped[str | None] = mapped_column(String(150), nullable=True)
    plan_id: Mapped[int | None] = mapped_column(ForeignKey("insurance_plans.id", ondelete="RESTRICT"))
    policy_holder: Mapped[str | None] = mapped_column(String(150))
    relationship_to_holder: Mapped[str | None] = mapped_column(String(80))
    valid_from: Mapped[date | None] = mapped_column(Date)
    valid_until: Mapped[date | None] = mapped_column(Date)
    administrative_notes: Mapped[str | None] = mapped_column(String(1000))
    is_primary: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    patient: Mapped["Patient"] = relationship(back_populates="insurances")
    insurance_company: Mapped[InsuranceCompany] = relationship(
        back_populates="patient_insurances"
    )


class InsurancePlan(TenantOwned, Base):
    __tablename__ = "insurance_plans"
    __table_args__ = (UniqueConstraint("organization_id", "insurance_company_id", "name", name="uq_insurance_plan_name"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    insurance_company_id: Mapped[int] = mapped_column(ForeignKey("insurance_companies.id", ondelete="RESTRICT"), index=True)
    name: Mapped[str] = mapped_column(String(150))
    code: Mapped[str | None] = mapped_column(String(50))
    description: Mapped[str | None] = mapped_column(String(1000))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)


class AppointmentCoverage(TenantOwned, Base):
    """Financial snapshot; unrelated to clinical doctor coverage transfers."""
    __tablename__ = "appointment_insurance_coverages"
    __table_args__ = (
        CheckConstraint("base_amount >= 0 AND covered_amount >= 0 AND patient_copay >= 0", name="ck_coverage_nonnegative"),
        CheckConstraint("base_amount = covered_amount + patient_copay", name="ck_coverage_total"),
        CheckConstraint("authorized_amount IS NULL OR authorized_amount >= 0", name="ck_authorized_nonnegative"),
    )
    id: Mapped[int] = mapped_column(primary_key=True)
    appointment_id: Mapped[int] = mapped_column(ForeignKey("appointments.id", ondelete="RESTRICT"), unique=True)
    patient_insurance_id: Mapped[int | None] = mapped_column(ForeignKey("patient_insurances.id", ondelete="RESTRICT"))
    insurance_snapshot: Mapped[dict] = mapped_column(JSON)
    service: Mapped[str] = mapped_column(String(200))
    currency: Mapped[str] = mapped_column(String(3), default="DOP")
    base_amount: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    covered_amount: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    patient_copay: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    authorization_status: Mapped[str] = mapped_column(String(30), default="pending")
    authorization_number: Mapped[str | None] = mapped_column(String(100))
    authorized_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    authorized_amount: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))
    authorization_notes: Mapped[str | None] = mapped_column(String(1000))
    notes: Mapped[str | None] = mapped_column(String(1000))
    revision: Mapped[int] = mapped_column(default=1)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    @property
    def expected_insurer_balance(self) -> Decimal:
        return self.covered_amount
