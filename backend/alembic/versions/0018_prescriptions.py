"""add prescriptions

Revision ID: 0018_prescriptions
Revises: 0017_diagnoses
"""

from alembic import op
import sqlalchemy as sa

revision = "0018_prescriptions"
down_revision = "0017_diagnoses"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "prescriptions",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("clinical_history_id", sa.Integer(), nullable=False),
        sa.Column("medication", sa.String(length=255), nullable=False),
        sa.Column("presentation", sa.String(length=255), nullable=True),
        sa.Column("dose", sa.String(length=255), nullable=True),
        sa.Column("route", sa.String(length=100), nullable=True),
        sa.Column("frequency", sa.String(length=255), nullable=True),
        sa.Column("duration", sa.String(length=255), nullable=True),
        sa.Column("quantity", sa.Integer(), nullable=True),
        sa.Column("instructions", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["clinical_history_id"], ["clinical_histories.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_prescriptions_clinical_history_id", "prescriptions", ["clinical_history_id"])


def downgrade() -> None:
    op.drop_index("ix_prescriptions_clinical_history_id", table_name="prescriptions")
    op.drop_table("prescriptions")
