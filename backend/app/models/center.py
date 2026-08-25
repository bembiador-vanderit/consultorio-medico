from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, String, Table, Column
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base


user_centers = Table(
    "user_centers",
    Base.metadata,
    Column("user_id", ForeignKey("users.id", ondelete="CASCADE"), primary_key=True),
    Column("center_id", ForeignKey("care_centers.id", ondelete="CASCADE"), primary_key=True),
    Column("is_primary", Boolean, nullable=False, default=False),
)


class CareCenter(Base):
    """Lugar físico donde se presta atención médica."""

    __tablename__ = "care_centers"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(150), index=True)
    center_type: Mapped[str] = mapped_column(String(30), default="consultorio")
    city: Mapped[str] = mapped_column(String(100), index=True)
    address: Mapped[str | None] = mapped_column(String(250), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    users: Mapped[list["User"]] = relationship(
        secondary=user_centers,
        back_populates="centers",
    )
