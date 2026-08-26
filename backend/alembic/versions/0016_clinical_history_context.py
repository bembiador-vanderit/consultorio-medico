"""link clinical history entries to appointment context

Revision ID: 0016_clinical_history_context
Revises: 0015_communication_logs
"""
from alembic import op
import sqlalchemy as sa

revision = "0016_clinical_history_context"
down_revision = "0015_communication_logs"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "clinical_histories",
        sa.Column("appointment_id", sa.Integer(), nullable=True),
    )
    op.add_column(
        "clinical_histories",
        sa.Column("doctor_id", sa.Integer(), nullable=True),
    )
    op.add_column(
        "clinical_histories",
        sa.Column("center_id", sa.Integer(), nullable=True),
    )
    op.create_foreign_key(
        "fk_clinical_histories_appointment_id",
        "clinical_histories",
        "appointments",
        ["appointment_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_foreign_key(
        "fk_clinical_histories_doctor_id",
        "clinical_histories",
        "users",
        ["doctor_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_foreign_key(
        "fk_clinical_histories_center_id",
        "clinical_histories",
        "care_centers",
        ["center_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index("ix_clinical_histories_appointment_id", "clinical_histories", ["appointment_id"])
    op.create_index("ix_clinical_histories_doctor_id", "clinical_histories", ["doctor_id"])
    op.create_index("ix_clinical_histories_center_id", "clinical_histories", ["center_id"])


def downgrade():
    op.drop_index("ix_clinical_histories_center_id", table_name="clinical_histories")
    op.drop_index("ix_clinical_histories_doctor_id", table_name="clinical_histories")
    op.drop_index("ix_clinical_histories_appointment_id", table_name="clinical_histories")
    op.drop_constraint("fk_clinical_histories_center_id", "clinical_histories", type_="foreignkey")
    op.drop_constraint("fk_clinical_histories_doctor_id", "clinical_histories", type_="foreignkey")
    op.drop_constraint("fk_clinical_histories_appointment_id", "clinical_histories", type_="foreignkey")
    op.drop_column("clinical_histories", "center_id")
    op.drop_column("clinical_histories", "doctor_id")
    op.drop_column("clinical_histories", "appointment_id")
