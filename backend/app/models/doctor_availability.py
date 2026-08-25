from datetime import date, datetime

from sqlalchemy import Boolean, Date, DateTime, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base


class DoctorAvailability(Base):
    __tablename__ = "doctor_availability"

    id: Mapped[int] = mapped_column(primary_key=True)
    doctor_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    center_id: Mapped[int | None] = mapped_column(ForeignKey("care_centers.id", ondelete="CASCADE"), nullable=True, index=True)
    availability_date: Mapped[date] = mapped_column(Date, index=True)
    is_available: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    doctor = relationship("User")
    center = relationship("CareCenter")
