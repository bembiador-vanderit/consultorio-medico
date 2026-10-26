from datetime import date

from sqlalchemy import Boolean, CheckConstraint, Date, ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base
from app.models.organization import TenantOwned


class DoctorAgendaSetting(TenantOwned, Base):
    __tablename__ = "doctor_agenda_settings"
    __table_args__ = (
        UniqueConstraint("organization_id", "doctor_id", "center_id", name="uq_doctor_agenda_setting"),
        CheckConstraint("base_mode IN ('timed', 'queue')", name="ck_doctor_agenda_base_mode"),
        CheckConstraint("allowed_timed OR allowed_queue", name="ck_doctor_agenda_allowed"),
        CheckConstraint("(default_mode = 'timed' AND allowed_timed) OR (default_mode = 'queue' AND allowed_queue)", name="ck_doctor_agenda_default_allowed"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    doctor_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"), index=True)
    center_id: Mapped[int] = mapped_column(ForeignKey("care_centers.id", ondelete="RESTRICT"), index=True)
    base_mode: Mapped[str] = mapped_column(String(10), default="timed", nullable=False)
    allowed_timed: Mapped[bool | None] = mapped_column(Boolean, nullable=True, deferred=True)
    allowed_queue: Mapped[bool | None] = mapped_column(Boolean, nullable=True, deferred=True)
    default_mode: Mapped[str | None] = mapped_column(String(10), nullable=True, deferred=True)


class DoctorAgendaException(TenantOwned, Base):
    __tablename__ = "doctor_agenda_exceptions"
    __table_args__ = (
        UniqueConstraint("organization_id", "doctor_id", "center_id", "agenda_date", name="uq_doctor_agenda_exception"),
        CheckConstraint("mode IN ('timed', 'queue')", name="ck_doctor_agenda_exception_mode"),
        CheckConstraint("allowed_timed OR allowed_queue", name="ck_doctor_agenda_exception_allowed"),
        CheckConstraint("(default_mode = 'timed' AND allowed_timed) OR (default_mode = 'queue' AND allowed_queue)", name="ck_doctor_agenda_exception_default_allowed"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    doctor_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"), index=True)
    center_id: Mapped[int] = mapped_column(ForeignKey("care_centers.id", ondelete="RESTRICT"), index=True)
    agenda_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    mode: Mapped[str] = mapped_column(String(10), nullable=False)
    allowed_timed: Mapped[bool | None] = mapped_column(Boolean, nullable=True, deferred=True)
    allowed_queue: Mapped[bool | None] = mapped_column(Boolean, nullable=True, deferred=True)
    default_mode: Mapped[str | None] = mapped_column(String(10), nullable=True, deferred=True)
