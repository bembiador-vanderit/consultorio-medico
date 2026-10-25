"""Presence registration, independent of booking mode and queue numbering."""
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base
from app.models.organization import TenantOwned


class AppointmentArrival(TenantOwned, Base):
    __tablename__ = "appointment_arrivals"
    __table_args__ = (UniqueConstraint("appointment_id", name="uq_appointment_arrival_appointment"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    appointment_id: Mapped[int] = mapped_column(ForeignKey("appointments.id", ondelete="RESTRICT"), nullable=False)
    arrived_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    registered_by_user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)
