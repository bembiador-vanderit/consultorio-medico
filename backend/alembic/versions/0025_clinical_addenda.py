"""add immutable clinical addenda

Revision ID: 0025_clinical_addenda
Revises: 0024_clinical_specialties
"""
from alembic import op
import sqlalchemy as sa


revision = "0025_clinical_addenda"
down_revision = "0024_clinical_specialties"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "clinical_addenda",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "clinical_history_id", sa.Integer(),
            sa.ForeignKey("clinical_histories.id", ondelete="RESTRICT"), nullable=False,
        ),
        sa.Column(
            "author_user_id", sa.Integer(),
            sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True,
        ),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("note", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_clinical_addenda_clinical_history_id", "clinical_addenda", ["clinical_history_id"])
    op.create_index("ix_clinical_addenda_author_user_id", "clinical_addenda", ["author_user_id"])
    op.create_index("ix_clinical_addenda_created_at", "clinical_addenda", ["created_at"])


def downgrade() -> None:
    op.drop_index("ix_clinical_addenda_created_at", table_name="clinical_addenda")
    op.drop_index("ix_clinical_addenda_author_user_id", table_name="clinical_addenda")
    op.drop_index("ix_clinical_addenda_clinical_history_id", table_name="clinical_addenda")
    op.drop_table("clinical_addenda")
