"""Center-owned waiting rooms; assignments never grant clinical access."""

from datetime import datetime

from sqlalchemy import Boolean, CheckConstraint, DateTime, ForeignKey, Index, Integer, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base
from app.models.organization import TenantOwned


class WaitingRoom(TenantOwned, Base):
    __tablename__ = "waiting_rooms"
    __table_args__ = (
        UniqueConstraint("id", "organization_id", "center_id", name="uq_waiting_room_scope_reference"),
        CheckConstraint("length(trim(name)) > 0", name="ck_waiting_room_name_nonempty"),
        CheckConstraint("sort_order >= 0", name="ck_waiting_room_sort_order"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    center_id: Mapped[int] = mapped_column(ForeignKey("care_centers.id", ondelete="RESTRICT"), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    code: Mapped[str | None] = mapped_column(String(30), nullable=True)
    description: Mapped[str | None] = mapped_column(String(500), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)
    center = relationship("CareCenter")
    secretary_assignments = relationship("WaitingRoomSecretary", back_populates="room", cascade="all, delete-orphan")


Index("uq_waiting_room_center_name", WaitingRoom.__table__.c.organization_id,
      WaitingRoom.__table__.c.center_id, func.lower(func.trim(WaitingRoom.__table__.c.name)), unique=True)


class WaitingRoomSecretary(TenantOwned, Base):
    __tablename__ = "waiting_room_secretaries"
    __table_args__ = (
        UniqueConstraint("organization_id", "waiting_room_id", "secretary_user_id", name="uq_waiting_room_secretary"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    waiting_room_id: Mapped[int] = mapped_column(ForeignKey("waiting_rooms.id", ondelete="CASCADE"), nullable=False, index=True)
    secretary_user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"), nullable=False, index=True)
    created_by_user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)
    room = relationship("WaitingRoom", back_populates="secretary_assignments")
