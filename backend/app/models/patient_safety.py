"""Longitudinal patient safety; a consultation is optional provenance only."""
from datetime import date, datetime, timezone

from sqlalchemy import CheckConstraint, Date, DateTime, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base
from app.models.organization import TenantOwned


class PatientSafetyEntry(TenantOwned, Base):
    __tablename__ = "patient_safety_entries"
    __table_args__ = (
        CheckConstraint("entry_type IN ('allergy','adverse_reaction','contraindication','intolerance_avoid')", name="ck_safety_type"),
        CheckConstraint("severity IN ('unknown','mild','moderate','severe','critical')", name="ck_safety_severity"),
        CheckConstraint("status IN ('active','inactive','entered_in_error')", name="ck_safety_status"),
        CheckConstraint("source_type IN ('patient_reported','family_reported','prior_documentation','observed_during_care','physician_confirmed')", name="ck_safety_source"),
        CheckConstraint("length(trim(substance_or_agent)) > 0 AND length(trim(reaction_description)) > 0", name="ck_safety_content"),
        CheckConstraint("revision >= 1", name="ck_safety_revision"),
        Index("ix_safety_patient_status", "organization_id", "patient_id", "status"),
    )
    id: Mapped[int] = mapped_column(primary_key=True)
    patient_id: Mapped[int] = mapped_column(ForeignKey("patients.id", ondelete="RESTRICT"), nullable=False)
    clinical_history_id: Mapped[int | None] = mapped_column(ForeignKey("clinical_histories.id", ondelete="RESTRICT"), nullable=True)
    entry_type: Mapped[str] = mapped_column(String(24), nullable=False)
    substance_or_agent: Mapped[str] = mapped_column(String(200), nullable=False)
    reaction_description: Mapped[str] = mapped_column(Text, nullable=False)
    severity: Mapped[str] = mapped_column(String(16), nullable=False, default="unknown", server_default="unknown")
    status: Mapped[str] = mapped_column(String(24), nullable=False, default="active", server_default="active")
    onset_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    source_type: Mapped[str] = mapped_column(String(32), nullable=False)
    source_description: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    recorded_by_user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)
    updated_by_user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)
    recorded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))
    revision: Mapped[int] = mapped_column(Integer, nullable=False, default=1, server_default="1")
    recorded_by = relationship("User", foreign_keys=[recorded_by_user_id])
    updated_by = relationship("User", foreign_keys=[updated_by_user_id])

    @property
    def recorded_by_name(self):
        return self.recorded_by.full_name

    @property
    def updated_by_name(self):
        return self.updated_by.full_name
