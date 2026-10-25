"""Durable metadata only. No document bytes, tokens, clinical data or financial queue."""
from datetime import datetime
from sqlalchemy import CheckConstraint, DateTime, ForeignKey, ForeignKeyConstraint, String, UniqueConstraint, event, inspect
from sqlalchemy.orm import Mapped, mapped_column, Session
from app.db import Base
from app.models.organization import TenantOwned
from app.models.print_contract import IMMUTABLE, may_transition


class PrintJob(TenantOwned, Base):
    __tablename__ = "print_jobs"
    __table_args__ = (
        UniqueConstraint("id", "organization_id", "agent_id", name="uq_print_job_scope"),
        ForeignKeyConstraint(["agent_id", "organization_id", "center_id"],
                             ["local_agents.id", "local_agents.organization_id", "local_agents.center_id"], ondelete="RESTRICT"),
        ForeignKeyConstraint(["printer_id", "agent_id", "organization_id"],
                             ["agent_printers.id", "agent_printers.agent_id", "agent_printers.organization_id"], ondelete="RESTRICT"),
        ForeignKeyConstraint(["requested_by", "organization_id"],
                             ["organization_memberships.user_id", "organization_memberships.organization_id"], name="fk_print_requester_tenant", ondelete="RESTRICT"),
        ForeignKeyConstraint(["source_agent_id", "organization_id"],
                             ["local_agents.id", "local_agents.organization_id"], name="fk_print_source_tenant", ondelete="RESTRICT"),
        CheckConstraint("copies BETWEEN 1 AND 999", name="ck_print_job_copies"),
        CheckConstraint("format IN ('pdf','plain_text')", name="ck_print_job_format"),
        CheckConstraint("status IN ('queued','delivering','received','ready','printing','cancel_requested','cancelled','expired','submitted','printed','failed','unknown')", name="ck_print_job_status"),
        CheckConstraint("expires_at > created_at", name="ck_print_job_expiry"),
        CheckConstraint("(contract_version=1 AND requested_by IS NULL AND origin_type IS NULL AND document_type IS NULL AND document_security_class IS NULL AND source_agent_id IS NULL) OR (contract_version=2 AND requested_by IS NOT NULL AND origin_type IS NOT NULL AND document_type IS NOT NULL AND document_security_class IS NOT NULL)", name="ck_print_contract_metadata"),
        CheckConstraint("origin_type IS NULL OR origin_type IN ('WEB_DESKTOP','WEB_MOBILE','WEB_TABLET','LOCAL_AGENT','SYSTEM')", name="ck_print_origin"),
        CheckConstraint("document_security_class IS NULL OR document_security_class IN ('GENERAL','ADMINISTRATIVE','FINANCIAL','CLINICAL','SENSITIVE_CLINICAL')", name="ck_print_security_class"),
        CheckConstraint("(origin_type='LOCAL_AGENT' AND source_agent_id IS NOT NULL) OR (source_agent_id IS NULL AND (origin_type IS NULL OR origin_type<>'LOCAL_AGENT'))", name="ck_print_source_origin"),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    center_id: Mapped[int] = mapped_column()
    agent_id: Mapped[int] = mapped_column(index=True)
    printer_id: Mapped[int] = mapped_column()
    artifact_ref: Mapped[str] = mapped_column(String(128))
    content_sha256: Mapped[str] = mapped_column(String(64))
    format: Mapped[str] = mapped_column(String(12))
    copies: Mapped[int] = mapped_column()
    intent_hash: Mapped[str] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(String(24), default="queued", index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime)
    expires_at: Mapped[datetime] = mapped_column(DateTime)
    contract_version: Mapped[int] = mapped_column(default=2, server_default="2")
    requested_by: Mapped[int | None] = mapped_column(ForeignKey("users.id", name="fk_print_requester", ondelete="RESTRICT"), nullable=True)
    origin_type: Mapped[str | None] = mapped_column(String(16), nullable=True)
    source_agent_id: Mapped[int | None] = mapped_column(nullable=True)
    document_type: Mapped[str | None] = mapped_column(String(64), nullable=True)
    document_security_class: Mapped[str | None] = mapped_column(String(24), nullable=True)


@event.listens_for(Session, "before_flush")
def protect_print_intent(db, _context, _instances):
    # Portable ORM defense; PostgreSQL additionally protects direct SQL with a trigger.
    for job in db.dirty:
        if not isinstance(job, PrintJob):
            continue
        state = inspect(job)
        if job.contract_version == 2 and job.status in {'delivering','cancel_requested'}:
            raise ValueError("Estado heredado no permitido para contrato v2")
        if any(state.attrs[name].history.has_changes() for name in IMMUTABLE):
            raise ValueError("La intención PrintJob es inmutable")
        history = state.attrs.status.history
        if history.has_changes() and history.deleted and not may_transition(history.deleted[0], job.status):
            raise ValueError("Transición PrintJob no permitida")


class PrintDelivery(TenantOwned, Base):
    __tablename__ = "print_deliveries"
    __table_args__ = (
        UniqueConstraint("job_id", "number", name="uq_print_delivery_number"),
        UniqueConstraint("id", "job_id", "organization_id", name="uq_print_delivery_result_scope"),
        ForeignKeyConstraint(["job_id", "organization_id", "agent_id"],
                             ["print_jobs.id", "print_jobs.organization_id", "print_jobs.agent_id"], ondelete="RESTRICT"),
        CheckConstraint("number > 0", name="ck_print_delivery_number"),
        CheckConstraint("lease_until > created_at", name="ck_print_delivery_lease"),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    job_id: Mapped[str] = mapped_column(String(36), index=True)
    agent_id: Mapped[int] = mapped_column()
    number: Mapped[int] = mapped_column()
    created_at: Mapped[datetime] = mapped_column(DateTime)
    lease_until: Mapped[datetime] = mapped_column(DateTime)
    acknowledged_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class PrintResult(TenantOwned, Base):
    __tablename__ = "print_results"
    __table_args__ = (
        ForeignKeyConstraint(["delivery_id", "job_id", "organization_id"],
                             ["print_deliveries.id", "print_deliveries.job_id", "print_deliveries.organization_id"], ondelete="RESTRICT"),
        CheckConstraint("outcome IN ('submitted','printed','failed','unknown','cancelled','expired')", name="ck_print_result_outcome"),
    )
    job_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    delivery_id: Mapped[str] = mapped_column(String(36))
    outcome: Mapped[str] = mapped_column(String(16))
    spool_id: Mapped[int | None] = mapped_column(nullable=True)
    error_code: Mapped[str | None] = mapped_column(String(40), nullable=True)
    recorded_at: Mapped[datetime] = mapped_column(DateTime)
