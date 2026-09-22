from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base


class Country(Base):
    __tablename__ = "countries"

    code: Mapped[str] = mapped_column(String(2), primary_key=True)
    name: Mapped[str] = mapped_column(String(100), unique=True, index=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class TerritorialLevel(Base):
    __tablename__ = "territorial_levels"
    __table_args__ = (UniqueConstraint("country_code", "position", name="uq_territorial_levels_country_position"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    country_code: Mapped[str] = mapped_column(ForeignKey("countries.code", ondelete="RESTRICT"), index=True)
    position: Mapped[int] = mapped_column(Integer)
    key: Mapped[str] = mapped_column(String(50))
    display_label: Mapped[str] = mapped_column(String(100))
    is_required: Mapped[bool] = mapped_column(Boolean, default=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, index=True)


class TerritorialUnit(Base):
    __tablename__ = "territorial_units"
    __table_args__ = (UniqueConstraint("country_code", "territorial_level_id", "parent_id", "name", name="uq_territorial_units_path_name"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    country_code: Mapped[str] = mapped_column(ForeignKey("countries.code", ondelete="RESTRICT"), index=True)
    territorial_level_id: Mapped[int] = mapped_column(ForeignKey("territorial_levels.id", ondelete="RESTRICT"), index=True)
    parent_id: Mapped[int | None] = mapped_column(ForeignKey("territorial_units.id", ondelete="RESTRICT"), nullable=True, index=True)
    code: Mapped[str | None] = mapped_column(String(30), nullable=True)
    name: Mapped[str] = mapped_column(String(150), index=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, index=True)

    level: Mapped["TerritorialLevel"] = relationship()
    parent: Mapped["TerritorialUnit | None"] = relationship(remote_side="TerritorialUnit.id")


class RegionalSettings(Base):
    __tablename__ = "regional_settings"

    id: Mapped[int] = mapped_column(primary_key=True, default=1)
    default_country_code: Mapped[str] = mapped_column(ForeignKey("countries.code", ondelete="RESTRICT"))
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    default_country: Mapped["Country"] = relationship()