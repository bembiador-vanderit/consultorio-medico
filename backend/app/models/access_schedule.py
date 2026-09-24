from datetime import date, datetime

from sqlalchemy import CheckConstraint, Date, DateTime, ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base
from app.models.organization import TenantOwned


class AccessException(TenantOwned, Base):
    __tablename__ = "access_exceptions"
    __table_args__ = (CheckConstraint("ends_at > starts_at", name="ck_access_exception_period"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    membership_id: Mapped[int] = mapped_column(ForeignKey("organization_memberships.id"), index=True)
    starts_at: Mapped[datetime] = mapped_column(DateTime)  # UTC
    ends_at: Mapped[datetime] = mapped_column(DateTime)
    reason: Mapped[str] = mapped_column(String(300))
    authorized_by: Mapped[int] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class AccessBlockedDate(TenantOwned, Base):
    __tablename__ = "access_blocked_dates"
    __table_args__ = (UniqueConstraint("membership_id", "day", name="uq_access_blocked_day"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    membership_id: Mapped[int] = mapped_column(ForeignKey("organization_memberships.id"), index=True)
    day: Mapped[date] = mapped_column(Date)
    reason: Mapped[str] = mapped_column(String(300))
    authorized_by: Mapped[int] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
