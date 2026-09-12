from datetime import datetime
from decimal import Decimal

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Integer, Numeric, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class VitalSigns(Base):
    __tablename__ = "vital_signs"
    __table_args__ = (
        UniqueConstraint("clinical_history_id", name="uq_vital_signs_clinical_history_id"),
        CheckConstraint("systolic_pressure IS NULL OR systolic_pressure BETWEEN 40 AND 300", name="ck_vital_signs_systolic"),
        CheckConstraint("diastolic_pressure IS NULL OR diastolic_pressure BETWEEN 20 AND 200", name="ck_vital_signs_diastolic"),
        CheckConstraint("heart_rate IS NULL OR heart_rate BETWEEN 20 AND 300", name="ck_vital_signs_heart_rate"),
        CheckConstraint("respiratory_rate IS NULL OR respiratory_rate BETWEEN 5 AND 80", name="ck_vital_signs_respiratory_rate"),
        CheckConstraint("temperature_c IS NULL OR temperature_c BETWEEN 25 AND 45", name="ck_vital_signs_temperature"),
        CheckConstraint("oxygen_saturation IS NULL OR oxygen_saturation BETWEEN 0 AND 100", name="ck_vital_signs_oxygen_saturation"),
        CheckConstraint("weight_kg IS NULL OR weight_kg BETWEEN 1 AND 500", name="ck_vital_signs_weight"),
        CheckConstraint("height_cm IS NULL OR height_cm BETWEEN 20 AND 300", name="ck_vital_signs_height"),
        CheckConstraint(
            "systolic_pressure IS NULL OR diastolic_pressure IS NULL OR systolic_pressure > diastolic_pressure",
            name="ck_vital_signs_pressure_order",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    clinical_history_id: Mapped[int] = mapped_column(
        ForeignKey("clinical_histories.id", ondelete="CASCADE"), nullable=False, index=True
    )
    systolic_pressure: Mapped[int | None] = mapped_column(Integer, nullable=True)
    diastolic_pressure: Mapped[int | None] = mapped_column(Integer, nullable=True)
    heart_rate: Mapped[int | None] = mapped_column(Integer, nullable=True)
    respiratory_rate: Mapped[int | None] = mapped_column(Integer, nullable=True)
    temperature_c: Mapped[Decimal | None] = mapped_column(Numeric(4, 1), nullable=True)
    oxygen_saturation: Mapped[Decimal | None] = mapped_column(Numeric(5, 2), nullable=True)
    weight_kg: Mapped[Decimal | None] = mapped_column(Numeric(6, 2), nullable=True)
    height_cm: Mapped[Decimal | None] = mapped_column(Numeric(5, 2), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
