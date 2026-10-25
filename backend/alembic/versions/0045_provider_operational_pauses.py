"""Record operational pauses without changing queue or clinical state."""

from alembic import op
import sqlalchemy as sa


revision = "0045_provider_operational_pauses"
down_revision = "0044_queue_service_completion"
branch_labels = depends_on = None


def upgrade():
    op.create_table(
        "provider_operational_pauses",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("organization_id", sa.Integer(), sa.ForeignKey("organizations.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("center_id", sa.Integer(), sa.ForeignKey("care_centers.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("doctor_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("reason", sa.String(32), nullable=False),
        sa.Column("notes", sa.String(1000), nullable=True),
        sa.Column("planned_start_at", sa.DateTime(), nullable=True),
        sa.Column("actual_started_at", sa.DateTime(), nullable=False),
        sa.Column("actual_finished_at", sa.DateTime(), nullable=True),
        sa.Column("started_by_user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("finished_by_user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.CheckConstraint(
            "reason IN ('ward_rounds', 'procedure', 'emergency', 'meeting', 'lunch', 'temporary_absence', 'other')",
            name="ck_provider_pause_reason",
        ),
        sa.CheckConstraint(
            "actual_finished_at IS NULL OR actual_finished_at >= actual_started_at",
            name="ck_provider_pause_finish_after_start",
        ),
    )
    op.create_index("ix_provider_operational_pauses_organization_id", "provider_operational_pauses", ["organization_id"])
    op.create_index(
        "ix_provider_pause_history", "provider_operational_pauses",
        ["organization_id", "doctor_id", "center_id", "actual_started_at"],
    )
    op.create_index(
        "uq_provider_pause_open", "provider_operational_pauses",
        ["organization_id", "center_id", "doctor_id"], unique=True,
        postgresql_where=sa.text("actual_finished_at IS NULL"),
        sqlite_where=sa.text("actual_finished_at IS NULL"),
    )


def downgrade():
    if op.get_bind().scalar(sa.text("SELECT count(*) FROM provider_operational_pauses")):
        raise RuntimeError("Cannot discard operational pause history")
    op.drop_index("uq_provider_pause_open", table_name="provider_operational_pauses")
    op.drop_index("ix_provider_pause_history", table_name="provider_operational_pauses")
    op.drop_index("ix_provider_operational_pauses_organization_id", table_name="provider_operational_pauses")
    op.drop_table("provider_operational_pauses")
