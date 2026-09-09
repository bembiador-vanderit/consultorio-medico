from datetime import datetime

from sqlalchemy import Boolean, CheckConstraint, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base


class LaboratoryTest(Base):
    __tablename__ = "laboratory_tests"

    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str | None] = mapped_column(String(50), nullable=True, unique=True, index=True)
    name: Mapped[str] = mapped_column(String(180), nullable=False, unique=True, index=True)
    category: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False, index=True)
    sort_order: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    seed_key: Mapped[str | None] = mapped_column(String(120), nullable=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)


class LaboratoryOrder(Base):
    __tablename__ = "laboratory_orders"
    __table_args__ = (CheckConstraint("status = 'ordered'", name="ck_laboratory_orders_status"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    clinical_history_id: Mapped[int] = mapped_column(ForeignKey("clinical_histories.id", ondelete="RESTRICT"), nullable=False, index=True)
    appointment_id: Mapped[int | None] = mapped_column(ForeignKey("appointments.id", ondelete="SET NULL"), nullable=True, index=True)
    patient_id: Mapped[int] = mapped_column(ForeignKey("patients.id", ondelete="RESTRICT"), nullable=False, index=True)
    doctor_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    center_id: Mapped[int | None] = mapped_column(ForeignKey("care_centers.id", ondelete="SET NULL"), nullable=True, index=True)
    specialty_id: Mapped[int | None] = mapped_column(ForeignKey("specialties.id", ondelete="RESTRICT"), nullable=True, index=True)
    patient_name: Mapped[str] = mapped_column(String(250), nullable=False)
    doctor_name: Mapped[str] = mapped_column(String(250), nullable=False)
    center_name: Mapped[str | None] = mapped_column(String(250), nullable=True)
    specialty_name: Mapped[str] = mapped_column(String(180), nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="ordered", nullable=False)
    is_additional: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False, index=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False, index=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    items: Mapped[list["LaboratoryOrderItem"]] = relationship(
        back_populates="order", cascade="all, delete-orphan", order_by="LaboratoryOrderItem.id"
    )


class LaboratoryOrderItem(Base):
    __tablename__ = "laboratory_order_items"
    __table_args__ = (UniqueConstraint("laboratory_order_id", "laboratory_test_id", name="uq_laboratory_order_test"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    laboratory_order_id: Mapped[int] = mapped_column(ForeignKey("laboratory_orders.id", ondelete="CASCADE"), nullable=False, index=True)
    laboratory_test_id: Mapped[int] = mapped_column(ForeignKey("laboratory_tests.id", ondelete="RESTRICT"), nullable=False, index=True)
    test_code: Mapped[str | None] = mapped_column(String(50), nullable=True)
    test_name: Mapped[str] = mapped_column(String(180), nullable=False)
    test_category: Mapped[str] = mapped_column(String(100), nullable=False)
    custom_note: Mapped[str | None] = mapped_column(Text, nullable=True)

    order: Mapped[LaboratoryOrder] = relationship(back_populates="items")
    laboratory_test: Mapped[LaboratoryTest] = relationship()


class StudyOrder(Base):
    __tablename__ = "study_orders"
    __table_args__ = (CheckConstraint("status = 'ordered'", name="ck_study_orders_status"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    clinical_history_id: Mapped[int] = mapped_column(ForeignKey("clinical_histories.id", ondelete="RESTRICT"), nullable=False, index=True)
    appointment_id: Mapped[int | None] = mapped_column(ForeignKey("appointments.id", ondelete="SET NULL"), nullable=True, index=True)
    patient_id: Mapped[int] = mapped_column(ForeignKey("patients.id", ondelete="RESTRICT"), nullable=False, index=True)
    doctor_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    center_id: Mapped[int | None] = mapped_column(ForeignKey("care_centers.id", ondelete="SET NULL"), nullable=True, index=True)
    specialty_id: Mapped[int | None] = mapped_column(ForeignKey("specialties.id", ondelete="RESTRICT"), nullable=True, index=True)
    patient_name: Mapped[str] = mapped_column(String(250), nullable=False)
    doctor_name: Mapped[str] = mapped_column(String(250), nullable=False)
    center_name: Mapped[str | None] = mapped_column(String(250), nullable=True)
    specialty_name: Mapped[str] = mapped_column(String(180), nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="ordered", nullable=False)
    is_additional: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False, index=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False, index=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    items: Mapped[list["StudyOrderItem"]] = relationship(
        back_populates="order", cascade="all, delete-orphan", order_by="StudyOrderItem.id"
    )


class StudyOrderItem(Base):
    __tablename__ = "study_order_items"
    __table_args__ = (
        CheckConstraint("contrast IN ('yes', 'no', 'not_applicable')", name="ck_study_order_items_contrast"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    study_order_id: Mapped[int] = mapped_column(ForeignKey("study_orders.id", ondelete="CASCADE"), nullable=False, index=True)
    medical_study_id: Mapped[int] = mapped_column(ForeignKey("medical_studies.id", ondelete="RESTRICT"), nullable=False, index=True)
    modality: Mapped[str] = mapped_column(String(80), nullable=False)
    study_name: Mapped[str] = mapped_column(String(180), nullable=False)
    region_description: Mapped[str | None] = mapped_column(String(250), nullable=True)
    contrast: Mapped[str] = mapped_column(String(20), default="not_applicable", nullable=False)
    clinical_notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    order: Mapped[StudyOrder] = relationship(back_populates="items")
    medical_study = relationship("MedicalStudy")
