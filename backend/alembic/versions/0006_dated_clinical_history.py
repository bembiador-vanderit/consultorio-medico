"""Allow multiple dated clinical history records per patient.

Revision ID: 0006_dated_clinical_history
Revises: 0005_clinical_history
"""

from alembic import op
import sqlalchemy as sa

revision = "0006_dated_clinical_history"
down_revision = "0005_clinical_history"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("clinical_histories", sa.Column("consultation_date", sa.Date(), nullable=True))
    op.execute(
        "UPDATE clinical_histories SET consultation_date = DATE(created_at) "
        "WHERE consultation_date IS NULL"
    )
    op.alter_column("clinical_histories", "consultation_date", nullable=False)
    op.drop_constraint("uq_clinical_history_patient", "clinical_histories", type_="unique")
    op.create_index(
        "ix_clinical_histories_consultation_date",
        "clinical_histories",
        ["consultation_date"],
        unique=False,
    )


def downgrade():
    op.drop_index("ix_clinical_histories_consultation_date", table_name="clinical_histories")
    op.create_unique_constraint(
        "uq_clinical_history_patient", "clinical_histories", ["patient_id"]
    )
    op.drop_column("clinical_histories", "consultation_date")
