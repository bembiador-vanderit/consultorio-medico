"""Tenant-owned, versioned clinical form definitions.

The page/section/field tree is a validated JSON document on a version. Keeping
it together makes publication atomic and prevents partially edited layouts.
"""
from datetime import datetime

from sqlalchemy import Boolean, CheckConstraint, DateTime, ForeignKey, Index, Integer, JSON, String, UniqueConstraint, text
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base
from app.models.organization import TenantOwned


class ClinicalFormTemplate(TenantOwned, Base):
    __tablename__ = "clinical_form_templates"
    __table_args__ = (
        UniqueConstraint("organization_id", "code", name="uq_clinical_form_template_code"),
        CheckConstraint("status IN ('draft', 'published', 'retired')", name="ck_clinical_form_template_status"),
        CheckConstraint("document_type IN ('preoperative', 'physical_exam')", name="ck_clinical_form_template_type"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(180), nullable=False)
    code: Mapped[str] = mapped_column(String(100), nullable=False)
    description: Mapped[str] = mapped_column(String(1000), default="")
    document_type: Mapped[str] = mapped_column(String(32), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="draft")
    current_version_id: Mapped[int | None] = mapped_column(ForeignKey("clinical_form_versions.id", ondelete="RESTRICT", use_alter=True), nullable=True)
    created_by_user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)


class ClinicalFormVersion(TenantOwned, Base):
    __tablename__ = "clinical_form_versions"
    __table_args__ = (
        UniqueConstraint("template_id", "version", name="uq_clinical_form_template_version"),
        CheckConstraint("status IN ('draft', 'published')", name="ck_clinical_form_version_status"),
        CheckConstraint("version > 0", name="ck_clinical_form_version_positive"),
        Index("uq_clinical_form_one_draft", "template_id", unique=True, postgresql_where=text("status = 'draft'"), sqlite_where=text("status = 'draft'")),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    template_id: Mapped[int] = mapped_column(ForeignKey("clinical_form_templates.id", ondelete="RESTRICT"), nullable=False, index=True)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="draft", nullable=False)
    definition: Mapped[dict] = mapped_column(JSON, nullable=False)
    created_by_user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow, nullable=False)
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class ClinicalFormAssignment(TenantOwned, Base):
    __tablename__ = "clinical_form_assignments"
    __table_args__ = (
        CheckConstraint("doctor_id IS NULL OR center_id IS NOT NULL", name="ck_clinical_form_doctor_center"),
        CheckConstraint("specialty_id IS NULL OR center_id IS NOT NULL", name="ck_clinical_form_specialty_center"),
        UniqueConstraint("organization_id", "document_type", "scope_key", name="uq_clinical_form_assignment_scope"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    template_id: Mapped[int] = mapped_column(ForeignKey("clinical_form_templates.id", ondelete="RESTRICT"), nullable=False, index=True)
    document_type: Mapped[str] = mapped_column(String(32), nullable=False)
    scope_key: Mapped[str] = mapped_column(String(120), nullable=False)
    center_id: Mapped[int | None] = mapped_column(ForeignKey("care_centers.id", ondelete="RESTRICT"), nullable=True, index=True)
    specialty_id: Mapped[int | None] = mapped_column(ForeignKey("specialties.id", ondelete="RESTRICT"), nullable=True, index=True)
    doctor_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"), nullable=True, index=True)
    created_by_user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow, nullable=False)


class SecretaryDocumentGrant(TenantOwned, Base):
    __tablename__ = "secretary_document_grants"
    __table_args__ = (UniqueConstraint("organization_id", "user_id", name="uq_secretary_document_grant_user"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"), nullable=False, index=True)
    start_preoperative: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    start_physical_exam: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    prepare_administrative: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    updated_by_user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
