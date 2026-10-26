"""Episode-specific findings; longitudinal identity/safety remain canonical elsewhere."""
from datetime import datetime
from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Integer, JSON, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column
from app.db import Base
from app.models.organization import TenantOwned


class CardiologyAssessment(TenantOwned, Base):
    __tablename__ = "cardiology_assessments"
    __table_args__ = (UniqueConstraint("clinical_history_id", name="uq_cardiology_history"),
                      CheckConstraint("revision >= 1", name="ck_cardiology_revision"))
    id: Mapped[int] = mapped_column(primary_key=True)
    clinical_history_id: Mapped[int] = mapped_column(ForeignKey("clinical_histories.id", ondelete="RESTRICT"), index=True)
    symptoms: Mapped[dict] = mapped_column(JSON, default=dict)
    cardiovascular_history: Mapped[dict] = mapped_column(JSON, default=dict)
    examination: Mapped[dict] = mapped_column(JSON, default=dict)
    impression: Mapped[str | None] = mapped_column(Text, nullable=True)
    plan: Mapped[str | None] = mapped_column(Text, nullable=True)
    studies: Mapped[list] = mapped_column(JSON, default=list)
    follow_up: Mapped[dict] = mapped_column(JSON, default=lambda: {"kind": "none"})
    revision: Mapped[int] = mapped_column(Integer, default=1)
    updated_by_user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class ClinicalFollowUpPlan(TenantOwned, Base):
    """Structured extension of the existing FollowUp, not a second task system."""
    __tablename__ = "clinical_follow_up_plans"
    __table_args__ = (UniqueConstraint("follow_up_id", name="uq_clinical_plan_task"),
        UniqueConstraint("clinical_history_id", name="uq_clinical_plan_history"),
        CheckConstraint("kind IN ('days','weeks','months','studies','date')", name="ck_clinical_plan_kind"),
        CheckConstraint("timeframe_value IS NULL OR timeframe_value BETWEEN 1 AND 365", name="ck_clinical_plan_timeframe"))
    id: Mapped[int] = mapped_column(primary_key=True)
    follow_up_id: Mapped[int] = mapped_column(ForeignKey("follow_ups.id", ondelete="RESTRICT"), index=True)
    clinical_history_id: Mapped[int] = mapped_column(ForeignKey("clinical_histories.id", ondelete="RESTRICT"), index=True)
    kind: Mapped[str] = mapped_column(String(12))
    timeframe_value: Mapped[int | None] = mapped_column(Integer, nullable=True)
    condition: Mapped[str | None] = mapped_column(Text, nullable=True)
    scheduled_appointment_id: Mapped[int | None] = mapped_column(ForeignKey("appointments.id", ondelete="RESTRICT"), nullable=True, index=True)
    created_by_user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"))
    revision: Mapped[int] = mapped_column(Integer, default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class FollowUpContactAttempt(TenantOwned, Base):
    __tablename__ = "follow_up_contact_attempts"
    __table_args__ = (CheckConstraint("result IN ('contacted','no_answer','retry','studies_ready','studies_pending','declined','scheduled')", name="ck_follow_up_contact_result"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    follow_up_id: Mapped[int] = mapped_column(ForeignKey("follow_ups.id", ondelete="RESTRICT"), index=True)
    recorded_by_user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"))
    result: Mapped[str] = mapped_column(String(24))
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
