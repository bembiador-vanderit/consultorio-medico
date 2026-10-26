"""Two independent longitudinal clinical records with a shared lifecycle."""
from datetime import date, datetime

from sqlalchemy import CheckConstraint, Date, DateTime, ForeignKey, Index, Integer, JSON, String, text
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base
from app.models.organization import TenantOwned


class DocumentColumns(TenantOwned):
    id: Mapped[int] = mapped_column(primary_key=True)
    patient_id: Mapped[int] = mapped_column(ForeignKey("patients.id", ondelete="RESTRICT"), nullable=False, index=True)
    doctor_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"), nullable=False, index=True)
    center_id: Mapped[int] = mapped_column(ForeignKey("care_centers.id", ondelete="RESTRICT"), nullable=False, index=True)
    appointment_id: Mapped[int | None] = mapped_column(ForeignKey("appointments.id", ondelete="SET NULL"), nullable=True, index=True)
    clinical_history_id: Mapped[int | None] = mapped_column(ForeignKey("clinical_histories.id", ondelete="SET NULL"), nullable=True, index=True)
    document_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(24), nullable=False, default="draft")
    content: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    identity_snapshot: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    revision: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_by_user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)
    last_updated_by_user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)
    signed_by_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)
    signed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class PreoperativeEvaluation(DocumentColumns, Base):
    __tablename__ = "preoperative_evaluations"
    __table_args__ = (
        CheckConstraint("status IN ('draft', 'pending_evaluation', 'completed', 'signed')", name="ck_preoperative_status"),
        CheckConstraint("revision >= 0", name="ck_preoperative_revision"),
        Index("uq_preoperative_open_appointment", "organization_id", "appointment_id", unique=True,
              postgresql_where=text("status IN ('draft', 'pending_evaluation') AND appointment_id IS NOT NULL"),
              sqlite_where=text("status IN ('draft', 'pending_evaluation') AND appointment_id IS NOT NULL")),
        Index("uq_preoperative_open_history", "organization_id", "clinical_history_id", unique=True,
              postgresql_where=text("status IN ('draft', 'pending_evaluation') AND appointment_id IS NULL AND clinical_history_id IS NOT NULL"),
              sqlite_where=text("status IN ('draft', 'pending_evaluation') AND appointment_id IS NULL AND clinical_history_id IS NOT NULL")),
        Index("uq_preoperative_open_standalone", "organization_id", "patient_id", "doctor_id", "center_id", "document_date",
              unique=True, postgresql_where=text("status IN ('draft', 'pending_evaluation') AND appointment_id IS NULL AND clinical_history_id IS NULL"),
              sqlite_where=text("status IN ('draft', 'pending_evaluation') AND appointment_id IS NULL AND clinical_history_id IS NULL")),
    )


class PhysicalExamination(DocumentColumns, Base):
    __tablename__ = "physical_examinations"
    __table_args__ = (
        CheckConstraint("status IN ('draft', 'pending_evaluation', 'completed', 'signed')", name="ck_physical_exam_status"),
        CheckConstraint("revision >= 0", name="ck_physical_exam_revision"),
        Index("uq_physical_exam_open_appointment", "organization_id", "appointment_id", unique=True,
              postgresql_where=text("status IN ('draft', 'pending_evaluation') AND appointment_id IS NOT NULL"),
              sqlite_where=text("status IN ('draft', 'pending_evaluation') AND appointment_id IS NOT NULL")),
        Index("uq_physical_exam_open_history", "organization_id", "clinical_history_id", unique=True,
              postgresql_where=text("status IN ('draft', 'pending_evaluation') AND appointment_id IS NULL AND clinical_history_id IS NOT NULL"),
              sqlite_where=text("status IN ('draft', 'pending_evaluation') AND appointment_id IS NULL AND clinical_history_id IS NOT NULL")),
        Index("uq_physical_exam_open_standalone", "organization_id", "patient_id", "doctor_id", "center_id", "document_date",
              unique=True, postgresql_where=text("status IN ('draft', 'pending_evaluation') AND appointment_id IS NULL AND clinical_history_id IS NULL"),
              sqlite_where=text("status IN ('draft', 'pending_evaluation') AND appointment_id IS NULL AND clinical_history_id IS NULL")),
    )
