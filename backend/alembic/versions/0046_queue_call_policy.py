"""Per-line call mode and preparation without changing historical tickets."""

from alembic import op
import sqlalchemy as sa


revision = "0046_queue_call_policy"
down_revision = "0045_provider_operational_pauses"
branch_labels = depends_on = None


def upgrade():
    op.create_table(
        "queue_call_policies",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("organization_id", sa.Integer(), sa.ForeignKey("organizations.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("center_id", sa.Integer(), sa.ForeignKey("care_centers.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("queue_line_id", sa.Integer(), sa.ForeignKey("queue_lines.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("call_mode", sa.String(16), nullable=False),
        sa.Column("preparation_seconds", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint("organization_id", "queue_line_id", name="uq_queue_call_policy_line"),
        sa.CheckConstraint("call_mode IN ('manual', 'assisted', 'automatic')", name="ck_queue_call_policy_mode"),
        sa.CheckConstraint("preparation_seconds BETWEEN 0 AND 3600", name="ck_queue_call_policy_preparation"),
    )
    op.create_index("ix_queue_call_policies_organization_id", "queue_call_policies", ["organization_id"])
    op.create_index("ix_queue_call_policy_auto", "queue_call_policies", ["organization_id", "call_mode"])


def downgrade():
    if op.get_bind().scalar(sa.text("SELECT count(*) FROM queue_call_policies")):
        raise RuntimeError("Cannot discard configured queue call policies")
    op.drop_index("ix_queue_call_policy_auto", table_name="queue_call_policies")
    op.drop_index("ix_queue_call_policies_organization_id", table_name="queue_call_policies")
    op.drop_table("queue_call_policies")
