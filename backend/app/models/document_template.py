"""Versioned presentation settings; never the source of financial values."""
from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, Integer, JSON, String, UniqueConstraint, text
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base
from app.models.organization import TenantOwned


class DocumentTemplate(TenantOwned, Base):
    __tablename__ = "document_templates"
    __table_args__ = (
        UniqueConstraint("organization_id", "code", name="uq_document_template_code"),
        UniqueConstraint("organization_id", "document_type", "scope_key", name="uq_document_template_scope"),
        CheckConstraint("document_type IN ('invoice','receipt','cash_close')", name="ck_document_template_type"),
        CheckConstraint("doctor_id IS NULL OR center_id IS NOT NULL", name="ck_document_template_doctor_center"),
    )
    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(100), nullable=False)
    name: Mapped[str] = mapped_column(String(180), nullable=False)
    document_type: Mapped[str] = mapped_column(String(32), nullable=False)
    scope_key: Mapped[str] = mapped_column(String(100), nullable=False)
    center_id: Mapped[int | None] = mapped_column(ForeignKey("care_centers.id", ondelete="RESTRICT"), index=True)
    doctor_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"), index=True)
    created_by: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class DocumentTemplateVersion(TenantOwned, Base):
    __tablename__ = "document_template_versions"
    __table_args__ = (
        UniqueConstraint("template_id", "version", name="uq_document_template_version"),
        CheckConstraint("version > 0", name="ck_document_version_positive"),
        CheckConstraint("status IN ('draft','published','archived')", name="ck_document_version_status"),
        Index("uq_document_one_draft", "template_id", unique=True,
              postgresql_where=text("status = 'draft'"), sqlite_where=text("status = 'draft'")),
    )
    id: Mapped[int] = mapped_column(primary_key=True)
    template_id: Mapped[int] = mapped_column(ForeignKey("document_templates.id", ondelete="RESTRICT"), index=True)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="draft")
    definition: Mapped[dict] = mapped_column(JSON, nullable=False)
    created_by: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    published_at: Mapped[datetime | None] = mapped_column(DateTime)


class DocumentTemplateAudit(TenantOwned, Base):
    __tablename__ = "document_template_audits"
    id: Mapped[int] = mapped_column(primary_key=True)
    template_id: Mapped[int | None] = mapped_column(ForeignKey("document_templates.id", ondelete="RESTRICT"), index=True)
    version_id: Mapped[int | None] = mapped_column(ForeignKey("document_template_versions.id", ondelete="RESTRICT"), index=True)
    center_id: Mapped[int | None] = mapped_column(ForeignKey("care_centers.id", ondelete="RESTRICT"))
    actor_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"))
    action: Mapped[str] = mapped_column(String(32), nullable=False)
    before: Mapped[dict] = mapped_column(JSON, default=dict)
    after: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
