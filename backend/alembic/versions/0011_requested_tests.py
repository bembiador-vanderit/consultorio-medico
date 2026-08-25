"""Add requested tests to clinical history.

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
    op.add_column(
        "clinical_histories",
        sa.Column("requested_tests", sa.Text(), nullable=True),
    )


def downgrade():
    op.drop_column("clinical_histories", "requested_tests")
