from datetime import datetime
from sqlalchemy import Boolean, Column, DateTime, ForeignKey, String, Table, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.core.specialty_codes import MAX_SPECIALTY_CODE_LENGTH, specialty_code_default
from app.db import Base
from app.models.organization import TenantOwned

doctor_specialties = Table(
    "doctor_specialties",
    Base.metadata,
    Column("user_id", ForeignKey("users.id", ondelete="CASCADE"), primary_key=True),
    Column("specialty_id", ForeignKey("specialties.id", ondelete="RESTRICT"), primary_key=True),
)
medical_study_specialties = Table(
    "medical_study_specialties",
    Base.metadata,
    Column("medical_study_id", ForeignKey("medical_studies.id", ondelete="CASCADE"), primary_key=True),
    Column("specialty_id", ForeignKey("specialties.id", ondelete="RESTRICT"), primary_key=True),
)

class Specialty(TenantOwned, Base):
    __tablename__ = "specialties"
    __table_args__ = (UniqueConstraint("organization_id", "code", name="uq_specialties_code"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(120), index=True)
    code: Mapped[str] = mapped_column(
        String(MAX_SPECIALTY_CODE_LENGTH),
        nullable=False,
        index=True,
        default=specialty_code_default,
    )
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    regions: Mapped[list["AnatomicalRegion"]] = relationship(back_populates="specialty", cascade="all, delete-orphan")
    studies: Mapped[list["MedicalStudy"]] = relationship(back_populates="specialty", cascade="all, delete-orphan")
    templates: Mapped[list["SpecialtyTemplate"]] = relationship(back_populates="specialty")

class AnatomicalRegion(TenantOwned, Base):
    __tablename__ = "anatomical_regions"
    id: Mapped[int] = mapped_column(primary_key=True)
    specialty_id: Mapped[int] = mapped_column(ForeignKey("specialties.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(120))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    specialty: Mapped[Specialty] = relationship(back_populates="regions")
    studies: Mapped[list["MedicalStudy"]] = relationship(back_populates="region")

class MedicalStudy(TenantOwned, Base):
    __tablename__ = "medical_studies"
    id: Mapped[int] = mapped_column(primary_key=True)
    specialty_id: Mapped[int] = mapped_column(ForeignKey("specialties.id", ondelete="CASCADE"), index=True)
    anatomical_region_id: Mapped[int | None] = mapped_column(ForeignKey("anatomical_regions.id", ondelete="SET NULL"), nullable=True, index=True)
    name: Mapped[str] = mapped_column(String(180))
    category: Mapped[str] = mapped_column(String(50), default="study")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    seed_key: Mapped[str | None] = mapped_column(String(100), nullable=True, index=True)
    canonical_key: Mapped[str | None] = mapped_column(String(140), nullable=True, index=True)
    is_catalog_entry: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False, index=True)
    specialty: Mapped[Specialty] = relationship(back_populates="studies")
    region: Mapped[AnatomicalRegion | None] = relationship(back_populates="studies")
    recommended_specialties: Mapped[list[Specialty]] = relationship(secondary=medical_study_specialties)
    @property
    def recommended_specialty_ids(self) -> list[int]:
        return sorted(specialty.id for specialty in self.recommended_specialties)

class DoctorProfile(TenantOwned, Base):
    __tablename__ = "doctor_profiles"
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    specialty_id: Mapped[int] = mapped_column(ForeignKey("specialties.id", ondelete="RESTRICT"), index=True)
    user = relationship("User", back_populates="doctor_profile")
    specialty: Mapped[Specialty] = relationship()
