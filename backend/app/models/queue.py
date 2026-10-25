"""Reception queue identity, daily counter, and immutable issued tickets."""

from datetime import date, datetime

from sqlalchemy import Boolean, CheckConstraint, Date, DateTime, ForeignKey, ForeignKeyConstraint, Index, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base
from app.models.organization import TenantOwned


class QueueLine(TenantOwned, Base):
    __tablename__ = "queue_lines"
    __table_args__ = (
        UniqueConstraint("organization_id", "center_id", "prefix", name="uq_queue_line_center_prefix"),
        CheckConstraint("length(prefix) BETWEEN 1 AND 4", name="ck_queue_line_prefix_length"),
        Index("ix_queue_line_assignment", "organization_id", "center_id", "doctor_id"),
        ForeignKeyConstraint(
            ["waiting_room_id", "organization_id", "center_id"],
            ["waiting_rooms.id", "waiting_rooms.organization_id", "waiting_rooms.center_id"],
            name="fk_queue_line_waiting_room_scope", ondelete="RESTRICT",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    center_id: Mapped[int] = mapped_column(ForeignKey("care_centers.id", ondelete="RESTRICT"), nullable=False)
    doctor_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)
    specialty_id: Mapped[int | None] = mapped_column(ForeignKey("specialties.id", ondelete="RESTRICT"), nullable=True)
    waiting_room_id: Mapped[int | None] = mapped_column(Integer, nullable=True, deferred=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    prefix: Mapped[str] = mapped_column(String(4), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    call_on_consultation_start: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="false")
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)
    doctor = relationship("User")
    center = relationship("CareCenter")


class QueueSequence(TenantOwned, Base):
    __tablename__ = "queue_sequences"
    __table_args__ = (
        UniqueConstraint("organization_id", "center_id", "queue_line_id", "service_date", name="uq_queue_sequence_day"),
        CheckConstraint("last_number > 0", name="ck_queue_sequence_positive"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    center_id: Mapped[int] = mapped_column(ForeignKey("care_centers.id", ondelete="RESTRICT"), nullable=False)
    queue_line_id: Mapped[int] = mapped_column(ForeignKey("queue_lines.id", ondelete="RESTRICT"), nullable=False)
    service_date: Mapped[date] = mapped_column(Date, nullable=False)
    last_number: Mapped[int] = mapped_column(nullable=False)


class QueueTicket(TenantOwned, Base):
    __tablename__ = "queue_tickets"
    __table_args__ = (
        UniqueConstraint("organization_id", "center_id", "queue_line_id", "service_date", "sequence_number", name="uq_queue_ticket_daily_number"),
        UniqueConstraint("organization_id", "appointment_id", name="uq_queue_ticket_appointment"),
        UniqueConstraint("organization_id", "center_id", "service_date", "public_code", name="uq_queue_ticket_public_code"),
        CheckConstraint("sequence_number > 0", name="ck_queue_ticket_positive_number"),
        CheckConstraint("source = 'arrival'", name="ck_queue_ticket_source"),
        CheckConstraint(
            "status IN ('waiting', 'called', 'in_service', 'completed', 'no_response', 'left')",
            name="ck_queue_ticket_status",
        ),
        CheckConstraint(
            "consultation_finished_at IS NULL OR (consultation_started_at IS NOT NULL AND consultation_finished_at >= consultation_started_at)",
            name="ck_queue_ticket_finish_after_start",
        ),
        Index("ix_queue_ticket_day", "organization_id", "service_date", "center_id"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    center_id: Mapped[int] = mapped_column(ForeignKey("care_centers.id", ondelete="RESTRICT"), nullable=False)
    queue_line_id: Mapped[int] = mapped_column(ForeignKey("queue_lines.id", ondelete="RESTRICT"), nullable=False)
    appointment_id: Mapped[int] = mapped_column(ForeignKey("appointments.id", ondelete="RESTRICT"), nullable=False)
    patient_id: Mapped[int] = mapped_column(ForeignKey("patients.id", ondelete="RESTRICT"), nullable=False)
    doctor_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)
    specialty_id: Mapped[int | None] = mapped_column(ForeignKey("specialties.id", ondelete="RESTRICT"), nullable=True)
    service_date: Mapped[date] = mapped_column(Date, nullable=False)
    sequence_number: Mapped[int] = mapped_column(nullable=False)
    public_code: Mapped[str] = mapped_column(String(20), nullable=False)
    source: Mapped[str] = mapped_column(String(20), nullable=False, default="arrival")
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="waiting")
    arrived_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    ticket_issued_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    arrival_registered_by: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)
    ticket_issued_by: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)
    first_called_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    last_called_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    called_by_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"), nullable=True)
    call_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    consultation_started_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    consultation_started_by_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"), nullable=True)
    consultation_finished_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    consultation_finished_by_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"), nullable=True)
    left_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    left_by_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)
    appointment = relationship("Appointment")
    queue_line = relationship("QueueLine")
    events = relationship("QueueTicketEvent", back_populates="ticket", order_by="QueueTicketEvent.occurred_at")


class QueueTicketEvent(TenantOwned, Base):
    __tablename__ = "queue_ticket_events"
    __table_args__ = (
        CheckConstraint(
            "event_type IN ('ARRIVED', 'ISSUED', 'CALLED', 'RECALLED', 'SERVICE_STARTED', 'SERVICE_COMPLETED', 'NO_RESPONSE', 'LEFT')",
            name="ck_queue_ticket_event_type",
        ),
        Index("ix_queue_ticket_event_ticket_time", "organization_id", "queue_ticket_id", "occurred_at", "id"),
        Index("ix_queue_ticket_event_day", "organization_id", "occurred_at"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    queue_ticket_id: Mapped[int] = mapped_column(ForeignKey("queue_tickets.id", ondelete="RESTRICT"), nullable=False)
    event_type: Mapped[str] = mapped_column(String(30), nullable=False)
    occurred_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    actor_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)
    ticket = relationship("QueueTicket", back_populates="events")

    @property
    def call_source(self) -> str | None:
        if self.event_type == "CALLED":
            return "automatic" if self.actor_user_id is None else "manual"
        return None
