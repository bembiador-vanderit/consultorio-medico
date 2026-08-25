from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base


class InsuranceCompany(Base):
    __tablename__ = "insurance_companies"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(150), unique=True, index=True)
    code: Mapped[str | None] = mapped_column(String(50), unique=True, nullable=True, index=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)

    patient_insurances: Mapped[list["PatientInsurance"]] = relationship(
        back_populates="insurance_company"
    )


class PatientInsurance(Base):
    __tablename__ = "patient_insurances"

    id: Mapped[int] = mapped_column(primary_key=True)
    patient_id: Mapped[int] = mapped_column(
        ForeignKey("patients.id", ondelete="CASCADE"), index=True
    )
    insurance_company_id: Mapped[int] = mapped_column(
        ForeignKey("insurance_companies.id", ondelete="RESTRICT"), index=True
    )
    member_number: Mapped[str] = mapped_column(String(100))
    plan_name: Mapped[str | None] = mapped_column(String(150), nullable=True)
    is_primary: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)

    patient: Mapped["Patient"] = relationship(back_populates="insurances")
    insurance_company: Mapped[InsuranceCompany] = relationship(
        back_populates="patient_insurances"
    )
