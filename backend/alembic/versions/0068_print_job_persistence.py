"""Durable logical print jobs, deliveries and results. No dispatch or data backfill."""
from alembic import op
import sqlalchemy as sa

revision = "0068_print_job_persistence"
down_revision = "0067_local_agent_registry"
branch_labels = depends_on = None


def org():
    return sa.Column("organization_id", sa.Integer(), sa.ForeignKey("organizations.id", ondelete="RESTRICT"), nullable=False)


def column(name, kind):
    return sa.Column(name, kind, nullable=False)


def upgrade():
    op.create_unique_constraint("uq_local_agent_print_scope", "local_agents", ["id", "organization_id", "center_id"])
    op.create_unique_constraint("uq_agent_printer_print_scope", "agent_printers", ["id", "agent_id", "organization_id"])
    op.create_table("print_jobs", column("id", sa.String(36)), org(), column("center_id", sa.Integer()),
        column("agent_id", sa.Integer()), column("printer_id", sa.Integer()), column("artifact_ref", sa.String(128)),
        column("content_sha256", sa.String(64)), column("format", sa.String(12)), column("copies", sa.Integer()),
        column("intent_hash", sa.String(64)), column("status", sa.String(24)),
        column("created_at", sa.DateTime()), column("expires_at", sa.DateTime()), sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("id", "organization_id", "agent_id", name="uq_print_job_scope"),
        sa.ForeignKeyConstraint(["agent_id", "organization_id", "center_id"], ["local_agents.id", "local_agents.organization_id", "local_agents.center_id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["printer_id", "agent_id", "organization_id"], ["agent_printers.id", "agent_printers.agent_id", "agent_printers.organization_id"], ondelete="RESTRICT"),
        sa.CheckConstraint("copies BETWEEN 1 AND 999", name="ck_print_job_copies"),
        sa.CheckConstraint("format IN ('pdf','plain_text')", name="ck_print_job_format"),
        sa.CheckConstraint("status IN ('queued','delivering','cancel_requested','cancelled','expired','submitted','printed','failed','unknown')", name="ck_print_job_status"),
        sa.CheckConstraint("expires_at > created_at", name="ck_print_job_expiry"))
    op.create_table("print_deliveries", column("id", sa.String(36)), org(), column("job_id", sa.String(36)),
        column("agent_id", sa.Integer()), column("number", sa.Integer()), column("created_at", sa.DateTime()),
        column("lease_until", sa.DateTime()), sa.Column("acknowledged_at", sa.DateTime()), sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("job_id", "number", name="uq_print_delivery_number"),
        sa.UniqueConstraint("id", "job_id", "organization_id", name="uq_print_delivery_result_scope"),
        sa.ForeignKeyConstraint(["job_id", "organization_id", "agent_id"], ["print_jobs.id", "print_jobs.organization_id", "print_jobs.agent_id"], ondelete="RESTRICT"),
        sa.CheckConstraint("number > 0", name="ck_print_delivery_number"),
        sa.CheckConstraint("lease_until > created_at", name="ck_print_delivery_lease"))
    op.create_table("print_results", column("job_id", sa.String(36)), org(), column("delivery_id", sa.String(36)),
        column("outcome", sa.String(16)), sa.Column("spool_id", sa.Integer()), sa.Column("error_code", sa.String(40)),
        column("recorded_at", sa.DateTime()), sa.PrimaryKeyConstraint("job_id"),
        sa.ForeignKeyConstraint(["delivery_id", "job_id", "organization_id"], ["print_deliveries.id", "print_deliveries.job_id", "print_deliveries.organization_id"], ondelete="RESTRICT"),
        sa.CheckConstraint("outcome IN ('submitted','printed','failed','unknown','cancelled','expired')", name="ck_print_result_outcome"))
    for table in ("print_jobs", "print_deliveries", "print_results"):
        op.create_index("ix_" + table + "_organization_id", table, ["organization_id"])
    op.create_index("ix_print_jobs_agent_id", "print_jobs", ["agent_id"])
    op.create_index("ix_print_jobs_status", "print_jobs", ["status"])
    op.create_index("ix_print_deliveries_job_id", "print_deliveries", ["job_id"])


def downgrade():
    for table in ("print_results", "print_deliveries", "print_jobs"):
        op.drop_table(table)
    op.drop_constraint("uq_agent_printer_print_scope", "agent_printers", type_="unique")
    op.drop_constraint("uq_local_agent_print_scope", "local_agents", type_="unique")
