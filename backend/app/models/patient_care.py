"""Longitudinal association, never an encounter assignment or an access grant."""
from datetime import datetime, timezone

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base
from app.models.organization import TenantOwned


class PatientCareRelationship(TenantOwned, Base):
    __tablename__ = "patient_care_relationships"
    __table_args__ = (
        UniqueConstraint("organization_id", "patient_id", "doctor_id", name="uq_patient_care_doctor"),
        CheckConstraint("relationship_type IN ('treating','consultant','specialist_followup','primary')", name="ck_patient_care_type"),
        CheckConstraint("origin IN ('consultation','administrative_assignment','referral','migration','emergency','inpatient','interconsultation')", name="ck_patient_care_origin"),
        CheckConstraint("status IN ('active','follow_up','historical','ended')", name="ck_patient_care_status"),
        CheckConstraint("(status = 'ended' AND ended_at IS NOT NULL AND ended_at >= started_at) OR (status != 'ended' AND ended_at IS NULL)", name="ck_patient_care_end"),
        CheckConstraint("(first_seen_at IS NULL AND last_seen_at IS NULL) OR (first_seen_at IS NOT NULL AND last_seen_at IS NOT NULL AND last_seen_at >= first_seen_at)", name="ck_patient_care_seen"),
        CheckConstraint("revision >= 1", name="ck_patient_care_revision"),
        Index("ix_patient_care_patient_status", "organization_id", "patient_id", "status"),
        Index("ix_patient_care_doctor_status", "organization_id", "doctor_id", "status", "last_seen_at"),
    )
    id: Mapped[int] = mapped_column(primary_key=True)
    patient_id: Mapped[int] = mapped_column(ForeignKey("patients.id", ondelete="RESTRICT"))
    doctor_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"))
    center_id: Mapped[int | None] = mapped_column(ForeignKey("care_centers.id", ondelete="RESTRICT"), nullable=True)
    specialty_id: Mapped[int | None] = mapped_column(ForeignKey("specialties.id", ondelete="RESTRICT"), nullable=True)
    relationship_type: Mapped[str] = mapped_column(String(32), default="treating", nullable=False)
    origin: Mapped[str] = mapped_column(String(32), nullable=False)
    status: Mapped[str] = mapped_column(String(16), default="active", nullable=False)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    first_seen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_seen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_from_clinical_history_id: Mapped[int | None] = mapped_column(ForeignKey("clinical_histories.id", ondelete="RESTRICT"), nullable=True)
    last_clinical_history_id: Mapped[int | None] = mapped_column(ForeignKey("clinical_histories.id", ondelete="RESTRICT"), nullable=True)
    created_by_user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"))
    updated_by_user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    revision: Mapped[int] = mapped_column(Integer, default=1, server_default="1")
    doctor = relationship("User", foreign_keys=[doctor_id])
    center = relationship("CareCenter")
    specialty = relationship("Specialty")
    organization = relationship("Organization")
    patient = relationship("Patient")

    @property
    def doctor_name(self):
        return self.doctor.full_name

    @property
    def center_name(self):
        return self.center.name if self.center else None

    @property
    def specialty_name(self):
        return self.specialty.name if self.specialty else None

    @property
    def organization_name(self):
        return self.organization.name
