from datetime import date, datetime, time
from sqlalchemy import CheckConstraint, Date, DateTime, ForeignKey, Index, Integer, String, Text, Time, UniqueConstraint, text
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.db import Base
from app.models.organization import TenantOwned

SLOT_OCCUPYING_STATUSES = ("scheduled", "confirmed")
TIMED_SLOT_INDEX = "uq_appointments_active_timed_slot"

class Appointment(TenantOwned, Base):
    __tablename__ = "appointments"
    __table_args__ = (
        CheckConstraint("schedule_mode IN ('timed', 'queue')", name="ck_appointments_schedule_mode"),
        CheckConstraint("appointment_time IS NOT NULL OR schedule_mode = 'queue'", name="ck_appointments_timed_time"),
        CheckConstraint("daily_booking_order IS NULL OR daily_booking_order > 0", name="ck_appointments_booking_order_positive"),
        Index(TIMED_SLOT_INDEX, "organization_id", "center_id", "doctor_id", "appointment_date", "appointment_time",
              unique=True, postgresql_nulls_not_distinct=True,
              postgresql_where=text("schedule_mode = 'timed' AND status IN ('scheduled', 'confirmed')"),
              sqlite_where=text("schedule_mode = 'timed' AND status IN ('scheduled', 'confirmed')")),
    )
    id: Mapped[int] = mapped_column(primary_key=True)
    patient_id: Mapped[int] = mapped_column(ForeignKey("patients.id", ondelete="CASCADE"), index=True)
    doctor_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"), index=True)
    center_id: Mapped[int | None] = mapped_column(ForeignKey("care_centers.id", ondelete="RESTRICT"), nullable=True, index=True)
    # Nullable in metadata so isolated legacy fixtures can still be loaded; migration 0024
    # enforces NOT NULL in PostgreSQL and all API writes resolve a valid specialty.
    specialty_id: Mapped[int | None] = mapped_column(ForeignKey("specialties.id", ondelete="RESTRICT"), nullable=True, index=True)
    appointment_date: Mapped[date] = mapped_column(Date, index=True)
    appointment_time: Mapped[time | None] = mapped_column(Time, nullable=True)
    # Deferred until 0053 is activated on the official database.
    daily_booking_order: Mapped[int | None] = mapped_column(Integer, nullable=True, deferred=True)
    schedule_mode: Mapped[str] = mapped_column(String(10), nullable=False, default="timed", server_default="timed")
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="scheduled", index=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    patient = relationship("Patient")
    doctor = relationship("User")
    center = relationship("CareCenter")
    specialty = relationship("Specialty")
    clinical_history = relationship("ClinicalHistory", uselist=False, foreign_keys="ClinicalHistory.appointment_id")
    coverage_transfer = relationship("AppointmentCoverageTransfer", back_populates="appointment", uselist=False)


class AppointmentBookingSequence(TenantOwned, Base):
    __tablename__ = "appointment_booking_sequences"
    __table_args__ = (
        UniqueConstraint("organization_id", "center_id", "doctor_id", "appointment_date", name="uq_appointment_booking_sequence_bucket"),
        CheckConstraint("last_number > 0", name="ck_appointment_booking_sequence_positive"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    center_id: Mapped[int] = mapped_column(ForeignKey("care_centers.id", ondelete="RESTRICT"), nullable=False)
    doctor_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)
    appointment_date: Mapped[date] = mapped_column(Date, nullable=False)
    last_number: Mapped[int] = mapped_column(Integer, nullable=False)
