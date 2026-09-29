"""Add requested tests linked to clinical history.

Revision ID: 0011_requested_tests
Revises: 0010_localities
"""
from alembic import op
import sqlalchemy as sa

revision = "0011_requested_tests"
down_revision = "0010_localities"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "requested_tests",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("clinical_history_id", sa.Integer(), nullable=False),
        sa.Column("test_name", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["clinical_history_id"], ["clinical_histories.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_requested_tests_clinical_history_id", "requested_tests", ["clinical_history_id"], unique=False)


def downgrade():
    op.drop_index("ix_requested_tests_clinical_history_id", table_name="requested_tests")
    op.drop_table("requested_tests")
