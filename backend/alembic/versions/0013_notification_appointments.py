"""link notifications to appointments

Revision ID: 0013_notification_appointments
Revises: 0012_follow_ups
"""
from alembic import op
import sqlalchemy as sa

revision = "0013_notification_appointments"
down_revision = "0012_follow_ups"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("notifications", sa.Column("appointment_id", sa.Integer(), nullable=True))
    op.create_foreign_key(
        "fk_notifications_appointment_id",
        "notifications",
        "appointments",
        ["appointment_id"],
        ["id"],
        ondelete="CASCADE",
    )
    op.create_index("ix_notifications_appointment_id", "notifications", ["appointment_id"])


def downgrade():
    op.drop_index("ix_notifications_appointment_id", table_name="notifications")
    op.drop_constraint("fk_notifications_appointment_id", "notifications", type_="foreignkey")
    op.drop_column("notifications", "appointment_id")
