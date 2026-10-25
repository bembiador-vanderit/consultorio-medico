"""Human pre-appointment contact attempts; append-only audit trail."""

from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base
from app.models.organization import TenantOwned


class AppointmentContactAttempt(TenantOwned, Base):
    __tablename__ = "appointment_contact_attempts"
    __table_args__ = (
        CheckConstraint("channel = 'phone'", name="ck_appointment_contact_channel"),
        CheckConstraint(
            "result IN ('will_attend', 'will_not_attend', 'no_answer', 'retry')",
            name="ck_appointment_contact_result",
        ),
        Index("ix_appointment_contact_latest", "organization_id", "appointment_id", "contacted_at", "id"),
        Index("ix_appointment_contact_actor", "contacted_by_user_id"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    appointment_id: Mapped[int] = mapped_column(ForeignKey("appointments.id", ondelete="RESTRICT"), nullable=False)
    contacted_by_user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)
    contacted_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)
    channel: Mapped[str] = mapped_column(String(20), nullable=False, default="phone")
    contact_value: Mapped[str | None] = mapped_column(String(30), nullable=True)
    result: Mapped[str] = mapped_column(String(20), nullable=False)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)

    appointment = relationship("Appointment")
    contacted_by = relationship("User")
