"""allow communication logs without patient

Revision ID: 0016_comm_logs_general
Revises: 0015_communication_logs
"""
from alembic import op

revision = "0016_comm_logs_general"
down_revision = "0015_communication_logs"
branch_labels = None
depends_on = None


def upgrade():
    op.alter_column("communication_logs", "patient_id", nullable=True)


def downgrade():
    op.alter_column("communication_logs", "patient_id", nullable=False)
