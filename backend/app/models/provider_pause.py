"""Operational doctor pauses, independent of appointments and queue tickets."""

from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, String, text
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base
from app.models.organization import TenantOwned


PAUSE_REASONS = (
    "ward_rounds", "procedure", "emergency", "meeting", "lunch",
    "temporary_absence", "other",
)


class ProviderOperationalPause(TenantOwned, Base):
    __tablename__ = "provider_operational_pauses"
    __table_args__ = (
        CheckConstraint(
            "reason IN ('ward_rounds', 'procedure', 'emergency', 'meeting', 'lunch', 'temporary_absence', 'other')",
            name="ck_provider_pause_reason",
        ),
        CheckConstraint(
            "actual_finished_at IS NULL OR actual_finished_at >= actual_started_at",
            name="ck_provider_pause_finish_after_start",
        ),
        Index(
            "uq_provider_pause_open", "organization_id", "center_id", "doctor_id",
            unique=True,
            postgresql_where=text("actual_finished_at IS NULL"),
            sqlite_where=text("actual_finished_at IS NULL"),
        ),
        Index("ix_provider_pause_history", "organization_id", "doctor_id", "center_id", "actual_started_at"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    center_id: Mapped[int] = mapped_column(ForeignKey("care_centers.id", ondelete="RESTRICT"), nullable=False)
    doctor_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)
    reason: Mapped[str] = mapped_column(String(32), nullable=False)
    notes: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    planned_start_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    actual_started_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    actual_finished_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    started_by_user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)
    finished_by_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)
