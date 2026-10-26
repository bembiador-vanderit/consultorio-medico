"""Device registry only: relationships never authorize clinical access or print routing."""
from datetime import datetime
from sqlalchemy import Boolean, CheckConstraint, DateTime, ForeignKey, JSON, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column
from app.db import Base
from app.models.organization import TenantOwned


class AgentWorkgroup(TenantOwned, Base):
    __tablename__ = "agent_workgroups"
    __table_args__ = (UniqueConstraint("organization_id", "center_id", "name", name="uq_agent_workgroup_name"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    center_id: Mapped[int] = mapped_column(ForeignKey("care_centers.id", ondelete="RESTRICT"))
    name: Mapped[str] = mapped_column(String(100))
    created_by: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class LocalAgent(TenantOwned, Base):
    __tablename__ = "local_agents"
    __table_args__ = (CheckConstraint("health IN ('online','degraded')", name="ck_local_agent_health"),
                      UniqueConstraint("id", "organization_id", name="uq_local_agent_identity_scope"),
                      UniqueConstraint("id", "organization_id", "center_id", name="uq_local_agent_print_scope"))
    id: Mapped[int] = mapped_column(primary_key=True)
    agent_uuid: Mapped[str] = mapped_column(String(36), unique=True)
    display_code: Mapped[str] = mapped_column(String(32))
    station_name: Mapped[str] = mapped_column(String(100))
    center_id: Mapped[int] = mapped_column(ForeignKey("care_centers.id", ondelete="RESTRICT"))
    workgroup_id: Mapped[int] = mapped_column(ForeignKey("agent_workgroups.id", ondelete="RESTRICT"))
    version: Mapped[str] = mapped_column(String(40))
    protocol_version: Mapped[int] = mapped_column()
    fingerprint: Mapped[str] = mapped_column(String(64))
    credential_hash: Mapped[str] = mapped_column(String(64), unique=True)
    credential_expires_at: Mapped[datetime] = mapped_column(DateTime)
    credential_revision: Mapped[int] = mapped_column(default=1)
    health: Mapped[str] = mapped_column(String(12), default="online")
    paired_by: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"))
    paired_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class AgentPairingCode(TenantOwned, Base):
    __tablename__ = "agent_pairing_codes"
    id: Mapped[int] = mapped_column(primary_key=True)
    code_hash: Mapped[str] = mapped_column(String(64), unique=True)
    center_id: Mapped[int] = mapped_column(ForeignKey("care_centers.id", ondelete="RESTRICT"))
    workgroup_id: Mapped[int] = mapped_column(ForeignKey("agent_workgroups.id", ondelete="RESTRICT"))
    created_by: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    expires_at: Mapped[datetime] = mapped_column(DateTime)
    consumed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class AgentPrinter(TenantOwned, Base):
    __tablename__ = "agent_printers"
    __table_args__ = (UniqueConstraint("agent_id", "local_id", name="uq_agent_printer_local"),
                      UniqueConstraint("id", "agent_id", "organization_id", name="uq_agent_printer_print_scope"))
    id: Mapped[int] = mapped_column(primary_key=True)
    agent_id: Mapped[int] = mapped_column(ForeignKey("local_agents.id", ondelete="RESTRICT"), index=True)
    local_id: Mapped[str] = mapped_column(String(100))
    display_name: Mapped[str] = mapped_column(String(200))
    driver: Mapped[str | None] = mapped_column(String(200), nullable=True)
    is_default: Mapped[bool] = mapped_column(Boolean)
    connection: Mapped[str] = mapped_column(String(12))
    is_virtual: Mapped[bool] = mapped_column(Boolean)
    status: Mapped[str] = mapped_column(String(80))
    papers: Mapped[list] = mapped_column(JSON, default=list)
    available: Mapped[bool] = mapped_column(Boolean, default=True)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class AuthorizedStationScope(TenantOwned, Base):
    __tablename__ = "authorized_station_scopes"
    __table_args__ = (UniqueConstraint("source_id", "target_id", name="uq_station_scope"),
                      CheckConstraint("source_id <> target_id", name="ck_station_scope_not_self"))
    id: Mapped[int] = mapped_column(primary_key=True)
    source_id: Mapped[int] = mapped_column(ForeignKey("local_agents.id", ondelete="RESTRICT"))
    target_id: Mapped[int] = mapped_column(ForeignKey("local_agents.id", ondelete="RESTRICT"))
    created_by: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
