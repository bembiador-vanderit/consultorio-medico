"""prevent duplicate logical notifications

Revision ID: 0023_notification_dedup
Revises: 0022_clinical_coverages
"""
from alembic import op


revision = "0023_notification_dedup"
down_revision = "0022_clinical_coverages"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        DELETE FROM notifications duplicate
        USING notifications original
        WHERE duplicate.id > original.id
          AND duplicate.user_id = original.user_id
          AND duplicate.notification_type = original.notification_type
          AND duplicate.appointment_id IS NOT NULL
          AND duplicate.appointment_id = original.appointment_id
    """)
    op.execute("""
        DELETE FROM notifications duplicate
        USING notifications original
        WHERE duplicate.id > original.id
          AND duplicate.user_id = original.user_id
          AND duplicate.notification_type = original.notification_type
          AND duplicate.follow_up_id IS NOT NULL
          AND duplicate.follow_up_id = original.follow_up_id
    """)
    op.create_unique_constraint(
        "uq_notifications_user_appointment_type",
        "notifications",
        ["user_id", "appointment_id", "notification_type"],
    )
    op.create_unique_constraint(
        "uq_notifications_user_follow_up_type",
        "notifications",
        ["user_id", "follow_up_id", "notification_type"],
    )


def downgrade() -> None:
    op.drop_constraint("uq_notifications_user_follow_up_type", "notifications", type_="unique")
    op.drop_constraint("uq_notifications_user_appointment_type", "notifications", type_="unique")
