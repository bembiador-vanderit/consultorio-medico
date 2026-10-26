"""Register appointment presence without issuing a queue number."""
from alembic import op
import sqlalchemy as sa

revision = "0064_appointment_arrivals"
down_revision = "0063_appointment_slot_guard"
branch_labels = depends_on = None


def upgrade():
    op.create_table("appointment_arrivals",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("organization_id", sa.Integer(), sa.ForeignKey("organizations.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("appointment_id", sa.Integer(), sa.ForeignKey("appointments.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("arrived_at", sa.DateTime(), nullable=False),
        sa.Column("registered_by_user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False),
        sa.UniqueConstraint("appointment_id", name="uq_appointment_arrival_appointment"))
    op.create_index("ix_appointment_arrivals_organization_id", "appointment_arrivals", ["organization_id"])


def downgrade():
    op.drop_index("ix_appointment_arrivals_organization_id", table_name="appointment_arrivals")
    op.drop_table("appointment_arrivals")
