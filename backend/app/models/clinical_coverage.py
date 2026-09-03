from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base


class ClinicalCoverage(Base):
    __tablename__ = "clinical_coverages"
    __table_args__ = (
        CheckConstraint("principal_doctor_id <> substitute_doctor_id", name="ck_clinical_coverage_distinct_doctors"),
        CheckConstraint("ends_at > starts_at", name="ck_clinical_coverage_valid_period"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    principal_doctor_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"), index=True)
    substitute_doctor_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"), index=True)
    center_id: Mapped[int] = mapped_column(ForeignKey("care_centers.id", ondelete="RESTRICT"), index=True)
    starts_at: Mapped[datetime] = mapped_column(DateTime, index=True)
    ends_at: Mapped[datetime] = mapped_column(DateTime, index=True)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_by_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)

    principal = relationship("User", foreign_keys=[principal_doctor_id])
    substitute = relationship("User", foreign_keys=[substitute_doctor_id])
    center = relationship("CareCenter")


class AppointmentCoverageTransfer(Base):
    __tablename__ = "appointment_coverage_transfers"
    __table_args__ = (UniqueConstraint("appointment_id", name="uq_appointment_coverage_transfer"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    appointment_id: Mapped[int] = mapped_column(ForeignKey("appointments.id", ondelete="RESTRICT"), index=True)
    coverage_id: Mapped[int] = mapped_column(ForeignKey("clinical_coverages.id", ondelete="RESTRICT"), index=True)
    original_doctor_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"), index=True)
    substitute_doctor_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"), index=True)
    executed_by_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)

    appointment = relationship("Appointment", back_populates="coverage_transfer")
    coverage = relationship("ClinicalCoverage")
