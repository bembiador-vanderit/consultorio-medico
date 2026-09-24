from datetime import date, datetime
from sqlalchemy import CheckConstraint, Date, DateTime, ForeignKey, Index, String
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.db import Base
from app.models.organization import TenantOwned

class Patient(TenantOwned, Base):
    __tablename__ = "patients"
    __table_args__ = (
        Index("uq_patients_document", "organization_id", "document_type", "document_number", unique=True),
        CheckConstraint("(document_type IS NULL AND document_number IS NULL) OR (document_type IS NOT NULL AND document_number IS NOT NULL)", name="ck_patients_document_pair"),
        CheckConstraint("document_type IN ('cedula', 'passport', 'other')", name="ck_patients_document_type"),
        CheckConstraint("blood_type IN ('A+', 'A-', 'B+', 'B-', 'AB+', 'AB-', 'O+', 'O-')", name="ck_patients_blood_type"),
        CheckConstraint("registered_sex IN ('female', 'male', 'other', 'unknown')", name="ck_patients_registered_sex"),
    )
    id: Mapped[int] = mapped_column(primary_key=True)
    first_name: Mapped[str] = mapped_column(String(100), index=True)
    last_name: Mapped[str] = mapped_column(String(100), index=True)
    date_of_birth: Mapped[date] = mapped_column(Date)
    phone: Mapped[str | None] = mapped_column(String(30), nullable=True)
    email: Mapped[str | None] = mapped_column(String(254), nullable=True)
    document_type: Mapped[str | None] = mapped_column(String(20), nullable=True)
    document_number: Mapped[str | None] = mapped_column(String(100), nullable=True)
    home_phone: Mapped[str | None] = mapped_column(String(30), nullable=True)
    registered_sex: Mapped[str | None] = mapped_column(String(20), nullable=True)
    blood_type: Mapped[str | None] = mapped_column(String(10), nullable=True)
    address: Mapped[str | None] = mapped_column(String(500), nullable=True)
    country_code: Mapped[str | None] = mapped_column(ForeignKey("countries.code"), nullable=True, index=True)
    territorial_unit_id: Mapped[int | None] = mapped_column(ForeignKey("territorial_units.id"), nullable=True, index=True)
    sector_locality: Mapped[str | None] = mapped_column(String(150), nullable=True)
    province: Mapped[str | None] = mapped_column(String(100), nullable=True)
    nationality: Mapped[str | None] = mapped_column(String(100), nullable=True)
    occupation: Mapped[str | None] = mapped_column(String(150), nullable=True)
    emergency_contact_name: Mapped[str | None] = mapped_column(String(150), nullable=True)
    emergency_contact_relationship: Mapped[str | None] = mapped_column(String(100), nullable=True)
    emergency_contact_mobile: Mapped[str | None] = mapped_column(String(30), nullable=True)
    emergency_contact_home_phone: Mapped[str | None] = mapped_column(String(30), nullable=True)
    guardian_name: Mapped[str | None] = mapped_column(String(150), nullable=True)
    guardian_relationship: Mapped[str | None] = mapped_column(String(100), nullable=True)
    guardian_mobile: Mapped[str | None] = mapped_column(String(30), nullable=True)
    guardian_home_phone: Mapped[str | None] = mapped_column(String(30), nullable=True)
    locality_id: Mapped[int | None] = mapped_column(ForeignKey("localities.id"), nullable=True)
    locality: Mapped["Locality | None"] = relationship()
    country: Mapped["Country | None"] = relationship()
    territorial_unit: Mapped["TerritorialUnit | None"] = relationship()
    @property
    def locality_name(self) -> str | None:
        return self.locality.name if self.locality else None
    @property
    def country_name(self) -> str | None:
        return self.country.name if self.country else None
    @property
    def territorial_path(self) -> list[dict]:
        path = []
        unit = self.territorial_unit
        while unit is not None:
            path.append({"level": unit.level.position, "key": unit.level.key, "label": unit.level.display_label, "unit_id": unit.id, "name": unit.name})
            unit = unit.parent
        return list(reversed(path))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    insurances: Mapped[list["PatientInsurance"]] = relationship(
        back_populates="patient",
        cascade="all, delete-orphan",
    )
