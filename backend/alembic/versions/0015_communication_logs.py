"""add communication delivery audit logs

Revision ID: 0015_communication_logs
Revises: 0014_clinical_catalog
"""
from alembic import op
import sqlalchemy as sa

revision = "0015_communication_logs"
down_revision = "0014_clinical_catalog"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "communication_logs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("patient_id", sa.Integer(), sa.ForeignKey("patients.id", ondelete="CASCADE"), nullable=False),
        sa.Column("appointment_id", sa.Integer(), sa.ForeignKey("appointments.id", ondelete="CASCADE"), nullable=True),
        sa.Column("channel", sa.String(length=20), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("recipient", sa.String(length=254), nullable=False),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("sent_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_communication_logs_patient_id", "communication_logs", ["patient_id"])
    op.create_index("ix_communication_logs_appointment_id", "communication_logs", ["appointment_id"])
    op.create_index("ix_communication_logs_channel", "communication_logs", ["channel"])
    op.create_index("ix_communication_logs_status", "communication_logs", ["status"])
    op.create_index("ix_communication_logs_created_at", "communication_logs", ["created_at"])


def downgrade():
    op.drop_index("ix_communication_logs_created_at", table_name="communication_logs")
    op.drop_index("ix_communication_logs_status", table_name="communication_logs")
    op.drop_index("ix_communication_logs_channel", table_name="communication_logs")
    op.drop_index("ix_communication_logs_appointment_id", table_name="communication_logs")
    op.drop_index("ix_communication_logs_patient_id", table_name="communication_logs")
    op.drop_table("communication_logs")
