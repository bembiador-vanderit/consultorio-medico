"""Center-scoped public queue displays and line subscriptions."""

from alembic import op
import sqlalchemy as sa


revision = "0047_queue_displays"
down_revision = "0046_queue_call_policy"
branch_labels = depends_on = None


def upgrade():
    op.create_table(
        "queue_displays",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("organization_id", sa.Integer(), sa.ForeignKey("organizations.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("center_id", sa.Integer(), sa.ForeignKey("care_centers.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("token_hash", sa.String(64), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("show_service_name", sa.Boolean(), nullable=False),
        sa.Column("show_provider_name", sa.Boolean(), nullable=False),
        sa.Column("recent_call_limit", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint("token_hash", name="uq_queue_display_token_hash"),
        sa.CheckConstraint("recent_call_limit BETWEEN 3 AND 10", name="ck_queue_display_recent_limit"),
    )
    op.create_index("ix_queue_displays_organization_id", "queue_displays", ["organization_id"])
    op.create_index("ix_queue_displays_center", "queue_displays", ["organization_id", "center_id"])
    op.create_table(
        "queue_display_lines",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("organization_id", sa.Integer(), sa.ForeignKey("organizations.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("queue_display_id", sa.Integer(), sa.ForeignKey("queue_displays.id", ondelete="CASCADE"), nullable=False),
        sa.Column("queue_line_id", sa.Integer(), sa.ForeignKey("queue_lines.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("destination", sa.String(80), nullable=False),
        sa.Column("sort_order", sa.Integer(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.UniqueConstraint("organization_id", "queue_display_id", "queue_line_id", name="uq_queue_display_line"),
        sa.UniqueConstraint("organization_id", "queue_display_id", "sort_order", name="uq_queue_display_sort"),
        sa.CheckConstraint("sort_order >= 0", name="ck_queue_display_sort_nonnegative"),
    )
    op.create_index("ix_queue_display_lines_organization_id", "queue_display_lines", ["organization_id"])
    op.create_index("ix_queue_display_lines_line", "queue_display_lines", ["organization_id", "queue_line_id"])


def downgrade():
    if op.get_bind().scalar(sa.text("SELECT count(*) FROM queue_displays")):
        raise RuntimeError("Cannot discard configured queue displays")
    op.drop_index("ix_queue_display_lines_line", table_name="queue_display_lines")
    op.drop_index("ix_queue_display_lines_organization_id", table_name="queue_display_lines")
    op.drop_table("queue_display_lines")
    op.drop_index("ix_queue_displays_center", table_name="queue_displays")
    op.drop_index("ix_queue_displays_organization_id", table_name="queue_displays")
    op.drop_table("queue_displays")
