"""add diagnoses to clinical history

Revision ID: 0017_diagnoses
Revises: 0016_clinical_history_context
"""
from alembic import op
import sqlalchemy as sa

revision = "0017_diagnoses"
down_revision = "0016_clinical_history_context"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "diagnoses",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("clinical_history_id", sa.Integer(), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("icd10_code", sa.String(length=20), nullable=True),
        sa.Column("is_primary", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["clinical_history_id"], ["clinical_histories.id"], ondelete="CASCADE"),
    )
    op.create_index("ix_diagnoses_clinical_history_id", "diagnoses", ["clinical_history_id"])
    op.create_index("ix_diagnoses_icd10_code", "diagnoses", ["icd10_code"])


def downgrade():
    op.drop_index("ix_diagnoses_icd10_code", table_name="diagnoses")
    op.drop_index("ix_diagnoses_clinical_history_id", table_name="diagnoses")
    op.drop_table("diagnoses")
