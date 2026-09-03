"""add follow-ups and notifications

Revision ID: 0012_follow_ups
Revises: 0011_requested_tests
"""
from alembic import op
import sqlalchemy as sa

revision = "0012_follow_ups"
down_revision = "0011_requested_tests"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "follow_ups",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("patient_id", sa.Integer(), sa.ForeignKey("patients.id", ondelete="CASCADE"), nullable=False),
        sa.Column("doctor_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("clinical_history_id", sa.Integer(), sa.ForeignKey("clinical_histories.id", ondelete="SET NULL"), nullable=True),
        sa.Column("center_id", sa.Integer(), sa.ForeignKey("care_centers.id", ondelete="SET NULL"), nullable=True),
        sa.Column("due_at", sa.DateTime(), nullable=False),
        sa.Column("reason", sa.String(length=255), nullable=False),
        sa.Column("priority", sa.String(length=20), nullable=False, server_default="normal"),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="pending"),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("completed_at", sa.DateTime(), nullable=True),
    )
    op.create_index("ix_follow_ups_patient_id", "follow_ups", ["patient_id"])
    op.create_index("ix_follow_ups_doctor_id", "follow_ups", ["doctor_id"])
    op.create_index("ix_follow_ups_clinical_history_id", "follow_ups", ["clinical_history_id"])
    op.create_index("ix_follow_ups_center_id", "follow_ups", ["center_id"])
    op.create_index("ix_follow_ups_due_at", "follow_ups", ["due_at"])
    op.create_index("ix_follow_ups_status", "follow_ups", ["status"])

    op.create_table(
        "notifications",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("follow_up_id", sa.Integer(), sa.ForeignKey("follow_ups.id", ondelete="CASCADE"), nullable=True),
        sa.Column("title", sa.String(length=160), nullable=False),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column("notification_type", sa.String(length=30), nullable=False, server_default="follow_up"),
        sa.Column("is_read", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("read_at", sa.DateTime(), nullable=True),
    )
    op.create_index("ix_notifications_user_id", "notifications", ["user_id"])
    op.create_index("ix_notifications_follow_up_id", "notifications", ["follow_up_id"])
    op.create_index("ix_notifications_is_read", "notifications", ["is_read"])
    op.create_index("ix_notifications_created_at", "notifications", ["created_at"])


def downgrade():
    op.drop_index("ix_notifications_created_at", table_name="notifications")
    op.drop_index("ix_notifications_is_read", table_name="notifications")
    op.drop_index("ix_notifications_follow_up_id", table_name="notifications")
    op.drop_index("ix_notifications_user_id", table_name="notifications")
    op.drop_table("notifications")
    op.drop_index("ix_follow_ups_status", table_name="follow_ups")
    op.drop_index("ix_follow_ups_due_at", table_name="follow_ups")
    op.drop_index("ix_follow_ups_center_id", table_name="follow_ups")
    op.drop_index("ix_follow_ups_clinical_history_id", table_name="follow_ups")
    op.drop_index("ix_follow_ups_doctor_id", table_name="follow_ups")
    op.drop_index("ix_follow_ups_patient_id", table_name="follow_ups")
    op.drop_table("follow_ups")
