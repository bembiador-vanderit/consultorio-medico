from datetime import datetime, timezone

from sqlalchemy import Boolean, CheckConstraint, DateTime, ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base
from app.models.organization import TenantOwned


class ClinicalSharingPolicy(TenantOwned, Base):
    __tablename__ = "clinical_sharing_policies"
    __table_args__ = (
        UniqueConstraint("organization_id", name="uq_clinical_sharing_organization"),
        CheckConstraint("mode IN ('assigned','active_relationship','same_center','organization')", name="ck_clinical_sharing_mode"),
        CheckConstraint("revision >= 1", name="ck_clinical_sharing_revision"),
    )
    id: Mapped[int] = mapped_column(primary_key=True)
    mode: Mapped[str] = mapped_column(String(24), default="assigned", server_default="assigned")
    limit_to_same_center: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true")
    clinical_history: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    clinical_documents: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    patient_safety: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    revision: Mapped[int] = mapped_column(default=1, server_default="1")
    updated_by_user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
