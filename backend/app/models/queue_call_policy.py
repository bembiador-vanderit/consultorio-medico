"""Per-line call timing; absence of a row means safe manual defaults."""

from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base
from app.models.organization import TenantOwned


class QueueCallPolicy(TenantOwned, Base):
    __tablename__ = "queue_call_policies"
    __table_args__ = (
        UniqueConstraint("organization_id", "queue_line_id", name="uq_queue_call_policy_line"),
        CheckConstraint("call_mode IN ('manual', 'assisted', 'automatic')", name="ck_queue_call_policy_mode"),
        CheckConstraint("preparation_seconds BETWEEN 0 AND 3600", name="ck_queue_call_policy_preparation"),
        Index("ix_queue_call_policy_auto", "organization_id", "call_mode"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    center_id: Mapped[int] = mapped_column(ForeignKey("care_centers.id", ondelete="RESTRICT"), nullable=False)
    queue_line_id: Mapped[int] = mapped_column(ForeignKey("queue_lines.id", ondelete="RESTRICT"), nullable=False)
    call_mode: Mapped[str] = mapped_column(String(16), nullable=False, default="manual")
    preparation_seconds: Mapped[int] = mapped_column(Integer, nullable=False, default=60)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)
