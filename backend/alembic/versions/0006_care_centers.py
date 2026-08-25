"""Add care centers and user-center assignments.

Revision ID: 0006_care_centers
Revises: 0005_clinical_history
"""

from alembic import op
import sqlalchemy as sa

revision = "0006_care_centers"
down_revision = "0005_clinical_history"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "care_centers",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=150), nullable=False),
        sa.Column("center_type", sa.String(length=30), nullable=False, server_default="consultorio"),
        sa.Column("city", sa.String(length=100), nullable=False),
        sa.Column("address", sa.String(length=250), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_care_centers_name", "care_centers", ["name"], unique=False)
    op.create_index("ix_care_centers_city", "care_centers", ["city"], unique=False)
    op.create_index("ix_care_centers_is_active", "care_centers", ["is_active"], unique=False)

    op.create_table(
        "user_centers",
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("center_id", sa.Integer(), nullable=False),
        sa.Column("is_primary", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.ForeignKeyConstraint(["center_id"], ["care_centers.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("user_id", "center_id"),
    )
    op.create_index("ix_user_centers_center_id", "user_centers", ["center_id"], unique=False)


def downgrade():
    op.drop_index("ix_user_centers_center_id", table_name="user_centers")
    op.drop_table("user_centers")
    op.drop_index("ix_care_centers_is_active", table_name="care_centers")
    op.drop_index("ix_care_centers_city", table_name="care_centers")
    op.drop_index("ix_care_centers_name", table_name="care_centers")
    op.drop_table("care_centers")
