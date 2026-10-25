"""Presentation policy only. Never referenced by authorization services."""
from datetime import datetime, timezone

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, String, Text, text
from sqlalchemy.orm import Mapped, mapped_column
from app.db import Base
from app.models.organization import TenantOwned


class FeatureVisibilitySetting(TenantOwned, Base):
    __tablename__ = "feature_visibility_settings"
    __table_args__ = (
        CheckConstraint("visibility_mode IN ('hidden','visible')", name="ck_feature_visibility_mode"),
        CheckConstraint("revision >= 1", name="ck_feature_visibility_revision"),
        Index("uq_feature_visibility_org", "organization_id", "feature_code", "context_code", "audience", unique=True,
              postgresql_where=text("center_id IS NULL"), sqlite_where=text("center_id IS NULL")),
        Index("uq_feature_visibility_center", "organization_id", "center_id", "feature_code", "context_code", "audience", unique=True,
              postgresql_where=text("center_id IS NOT NULL"), sqlite_where=text("center_id IS NOT NULL")),
    )
    id: Mapped[int] = mapped_column(primary_key=True)
    center_id: Mapped[int | None] = mapped_column(ForeignKey("care_centers.id", ondelete="RESTRICT"), nullable=True)
    feature_code: Mapped[str] = mapped_column(String(80))
    context_code: Mapped[str] = mapped_column(String(40))
    audience: Mapped[str] = mapped_column(String(40))
    visibility_mode: Mapped[str] = mapped_column(String(10))
    revision: Mapped[int] = mapped_column(default=1)
    updated_by_user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"))
    reason: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
