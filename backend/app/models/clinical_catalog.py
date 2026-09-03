from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base


class Specialty(Base):
    __tablename__ = "specialties"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(120), unique=True, index=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    regions: Mapped[list["AnatomicalRegion"]] = relationship(back_populates="specialty", cascade="all, delete-orphan")
    studies: Mapped[list["MedicalStudy"]] = relationship(back_populates="specialty", cascade="all, delete-orphan")


class AnatomicalRegion(Base):
    __tablename__ = "anatomical_regions"

    id: Mapped[int] = mapped_column(primary_key=True)
    specialty_id: Mapped[int] = mapped_column(ForeignKey("specialties.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(120))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, index=True)

    specialty: Mapped[Specialty] = relationship(back_populates="regions")
    studies: Mapped[list["MedicalStudy"]] = relationship(back_populates="region")


class MedicalStudy(Base):
    __tablename__ = "medical_studies"

    id: Mapped[int] = mapped_column(primary_key=True)
    specialty_id: Mapped[int] = mapped_column(ForeignKey("specialties.id", ondelete="CASCADE"), index=True)
    anatomical_region_id: Mapped[int | None] = mapped_column(ForeignKey("anatomical_regions.id", ondelete="SET NULL"), nullable=True, index=True)
    name: Mapped[str] = mapped_column(String(180))
    category: Mapped[str] = mapped_column(String(50), default="study")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, index=True)

    specialty: Mapped[Specialty] = relationship(back_populates="studies")
    region: Mapped[AnatomicalRegion | None] = relationship(back_populates="studies")


class DoctorProfile(Base):
    __tablename__ = "doctor_profiles"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), unique=True, index=True)
    specialty_id: Mapped[int] = mapped_column(ForeignKey("specialties.id", ondelete="RESTRICT"), index=True)

    user = relationship("User")
    specialty: Mapped[Specialty] = relationship()
