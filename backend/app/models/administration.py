from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base
from app.models.organization import TenantOwned


class SecurityAudit(TenantOwned, Base):
    __tablename__ = "security_audits"
    id: Mapped[int] = mapped_column(primary_key=True)
    center_id: Mapped[int | None] = mapped_column(ForeignKey("care_centers.id"), nullable=True)
    actor_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    action: Mapped[str] = mapped_column(String(200))
    outcome: Mapped[str] = mapped_column(String(20), default="success")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class ReauthenticationGrant(TenantOwned, Base):
    __tablename__ = "reauthentication_grants"
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    session_version: Mapped[int]
    action: Mapped[str] = mapped_column(String(200))
    expires_at: Mapped[datetime] = mapped_column(DateTime)
    consumed: Mapped[bool] = mapped_column(default=False)


class AdminTransfer(TenantOwned, Base):
    __tablename__ = "admin_transfers"
    id: Mapped[int] = mapped_column(primary_key=True)
    initiator_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    target_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    initiator_version: Mapped[int]
    target_version: Mapped[int]
    replace_initiator: Mapped[bool] = mapped_column(default=True)
    state: Mapped[str] = mapped_column(String(20), default="pending")
    expires_at: Mapped[datetime] = mapped_column(DateTime)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
