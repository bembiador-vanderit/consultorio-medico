from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, Integer, String, UniqueConstraint, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base


class SpecialtyTemplate(Base):
    __tablename__ = "specialty_templates"
    __table_args__ = (
        UniqueConstraint("specialty_id", "version", name="uq_specialty_templates_specialty_version"),
        CheckConstraint(
            "status IN ('draft', 'published', 'retired')",
            name="ck_specialty_templates_status",
        ),
        Index(
            "uq_specialty_templates_one_published",
            "specialty_id",
            unique=True,
            postgresql_where=text("status = 'published'"),
            sqlite_where=text("status = 'published'"),
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    specialty_id: Mapped[int] = mapped_column(
        ForeignKey("specialties.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="draft")
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)
    published_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    specialty = relationship("Specialty", back_populates="templates")
    modules: Mapped[list["SpecialtyTemplateModule"]] = relationship(
        back_populates="template",
        cascade="all, delete-orphan",
        order_by="SpecialtyTemplateModule.position",
    )


class SpecialtyTemplateModule(Base):
    __tablename__ = "specialty_template_modules"
    __table_args__ = (
        UniqueConstraint("template_id", "module_key", name="uq_specialty_template_modules_key"),
        UniqueConstraint("template_id", "position", name="uq_specialty_template_modules_position"),
        CheckConstraint("position > 0", name="ck_specialty_template_modules_position_positive"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    template_id: Mapped[int] = mapped_column(
        ForeignKey("specialty_templates.id", ondelete="CASCADE"), nullable=False, index=True
    )
    module_key: Mapped[str] = mapped_column(String(120), nullable=False)
    position: Mapped[int] = mapped_column(Integer, nullable=False)

    template: Mapped[SpecialtyTemplate] = relationship(back_populates="modules")
