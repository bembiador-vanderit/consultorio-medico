"""Public queue screens, scoped to one tenant and care center."""

from datetime import datetime

from sqlalchemy import Boolean, CheckConstraint, DateTime, Float, ForeignKey, ForeignKeyConstraint, Index, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base
from app.models.organization import TenantOwned


class QueueDisplay(TenantOwned, Base):
    __tablename__ = "queue_displays"
    __table_args__ = (
        UniqueConstraint("token_hash", name="uq_queue_display_token_hash"),
        CheckConstraint("recent_call_limit BETWEEN 3 AND 10", name="ck_queue_display_recent_limit"),
        CheckConstraint("audio_volume BETWEEN 0 AND 1", name="ck_queue_display_audio_volume"),
        CheckConstraint("audio_rate BETWEEN 0.5 AND 2", name="ck_queue_display_audio_rate"),
        CheckConstraint("audio_pitch BETWEEN 0.5 AND 2", name="ck_queue_display_audio_pitch"),
        CheckConstraint("repeat_count BETWEEN 1 AND 10", name="ck_queue_display_repeat_count"),
        CheckConstraint("repeat_delay_ms BETWEEN 1000 AND 5000", name="ck_queue_display_repeat_delay"),
        CheckConstraint("audio_language IN ('es-DO', 'es')", name="ck_queue_display_audio_language"),
        Index("ix_queue_displays_center", "organization_id", "center_id"),
        ForeignKeyConstraint(
            ["waiting_room_id", "organization_id", "center_id"],
            ["waiting_rooms.id", "waiting_rooms.organization_id", "waiting_rooms.center_id"],
            name="fk_queue_display_waiting_room_scope", ondelete="RESTRICT",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    center_id: Mapped[int] = mapped_column(ForeignKey("care_centers.id", ondelete="RESTRICT"), nullable=False)
    waiting_room_id: Mapped[int | None] = mapped_column(Integer, nullable=True, deferred=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    token_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    show_service_name: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    show_provider_name: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    recent_call_limit: Mapped[int] = mapped_column(Integer, nullable=False, default=5)
    audio_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, deferred=True)
    audio_volume: Mapped[float] = mapped_column(Float, nullable=False, deferred=True)
    audio_language: Mapped[str] = mapped_column(String(5), nullable=False, deferred=True)
    audio_voice_uri: Mapped[str | None] = mapped_column(String(255), nullable=True, deferred=True)
    audio_rate: Mapped[float] = mapped_column(Float, nullable=False, deferred=True)
    audio_pitch: Mapped[float] = mapped_column(Float, nullable=False, deferred=True)
    repeat_count: Mapped[int] = mapped_column(Integer, nullable=False, deferred=True)
    repeat_delay_ms: Mapped[int] = mapped_column(Integer, nullable=False, deferred=True)
    announce_service_name: Mapped[bool] = mapped_column(Boolean, nullable=False, deferred=True)
    announce_provider_name: Mapped[bool] = mapped_column(Boolean, nullable=False, deferred=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)
    center = relationship("CareCenter")
    lines = relationship("QueueDisplayLine", back_populates="display", cascade="all, delete-orphan", order_by="QueueDisplayLine.sort_order")


class QueueDisplayLine(TenantOwned, Base):
    __tablename__ = "queue_display_lines"
    __table_args__ = (
        UniqueConstraint("organization_id", "queue_display_id", "queue_line_id", name="uq_queue_display_line"),
        UniqueConstraint("organization_id", "queue_display_id", "sort_order", name="uq_queue_display_sort"),
        CheckConstraint("sort_order >= 0", name="ck_queue_display_sort_nonnegative"),
        Index("ix_queue_display_lines_line", "organization_id", "queue_line_id"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    queue_display_id: Mapped[int] = mapped_column(ForeignKey("queue_displays.id", ondelete="CASCADE"), nullable=False)
    queue_line_id: Mapped[int] = mapped_column(ForeignKey("queue_lines.id", ondelete="RESTRICT"), nullable=False)
    destination: Mapped[str] = mapped_column(String(80), nullable=False)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    display = relationship("QueueDisplay", back_populates="lines")
    queue_line = relationship("QueueLine")
