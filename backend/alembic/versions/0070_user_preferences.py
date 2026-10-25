"""Per-user presentation preferences; no historical backfill."""
from alembic import op
import sqlalchemy as sa

revision = "0070_user_preferences"
down_revision = "0069_print_job_contract"
branch_labels = depends_on = None


def upgrade():
    op.create_table(
        "user_preferences",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("gestion_menu_order", sa.JSON(), nullable=False),
        sa.Column("dashboard_widget_order", sa.JSON(), nullable=False),
        sa.Column("accent_theme", sa.String(32), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("user_id", name="uq_user_preferences_user_id"),
        sa.CheckConstraint(
            "accent_theme IN ('classic','blue','turquoise','clinical-green','indigo','violet')",
            name="ck_user_preferences_accent_theme",
        ),
    )
    op.create_index("ix_user_preferences_user_id", "user_preferences", ["user_id"])


def downgrade():
    op.drop_index("ix_user_preferences_user_id", table_name="user_preferences")
    op.drop_table("user_preferences")
