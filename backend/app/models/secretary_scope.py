from sqlalchemy import Boolean, Column, ForeignKey, Table, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base


secretary_scope_doctors = Table(
    "secretary_scope_doctors",
    Base.metadata,
    Column("scope_id", ForeignKey("secretary_center_scopes.id", ondelete="CASCADE"), primary_key=True),
    Column("doctor_id", ForeignKey("users.id", ondelete="CASCADE"), primary_key=True),
)


class SecretaryCenterScope(Base):
    __tablename__ = "secretary_center_scopes"
    __table_args__ = (UniqueConstraint("secretary_id", "center_id", name="uq_secretary_center_scope"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    secretary_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    center_id: Mapped[int] = mapped_column(ForeignKey("care_centers.id", ondelete="CASCADE"), index=True)
    manage_all_doctors: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    secretary: Mapped["User"] = relationship(foreign_keys=[secretary_id])
    center: Mapped["CareCenter"] = relationship()
    doctors: Mapped[list["User"]] = relationship(secondary=secretary_scope_doctors)
