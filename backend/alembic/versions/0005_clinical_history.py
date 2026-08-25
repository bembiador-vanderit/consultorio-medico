"""Create the patient clinical history table.

Revision ID: 0005_clinical_history
Revises: 0004_seed_insurance_companies
"""

from alembic import op
import sqlalchemy as sa

revision = "0005_clinical_history"
down_revision = "0004_seed_insurance_companies"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "clinical_histories",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("patient_id", sa.Integer(), nullable=False),
        sa.Column("reason_for_visit", sa.Text(), nullable=True),
        sa.Column("current_illness", sa.Text(), nullable=True),
        sa.Column("personal_history", sa.Text(), nullable=True),
        sa.Column("family_history", sa.Text(), nullable=True),
        sa.Column("allergies", sa.Text(), nullable=True),
        sa.Column("current_medications", sa.Text(), nullable=True),
        sa.Column("previous_surgeries", sa.Text(), nullable=True),
        sa.Column("chronic_conditions", sa.Text(), nullable=True),
        sa.Column("habits", sa.Text(), nullable=True),
        sa.Column("clinical_notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["patient_id"], ["patients.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("patient_id", name="uq_clinical_history_patient"),
    )
    op.create_index("ix_clinical_histories_patient_id", "clinical_histories", ["patient_id"], unique=False)


def downgrade():
    op.drop_index("ix_clinical_histories_patient_id", table_name="clinical_histories")
    op.drop_table("clinical_histories")
