"""Explicit operational completion of queue consultations."""

from alembic import op
import sqlalchemy as sa


revision = "0044_queue_service_completion"
down_revision = "0043_queue_call_lifecycle"
branch_labels = depends_on = None


def upgrade():
    op.add_column("queue_tickets", sa.Column("consultation_finished_at", sa.DateTime(), nullable=True))
    op.add_column("queue_tickets", sa.Column("consultation_finished_by_user_id", sa.Integer(), nullable=True))
    op.create_foreign_key(
        "fk_queue_ticket_finished_by", "queue_tickets", "users",
        ["consultation_finished_by_user_id"], ["id"], ondelete="RESTRICT",
    )
    op.create_check_constraint(
        "ck_queue_ticket_finish_after_start", "queue_tickets",
        "consultation_finished_at IS NULL OR (consultation_started_at IS NOT NULL AND consultation_finished_at >= consultation_started_at)",
    )
    op.drop_constraint("ck_queue_ticket_event_type", "queue_ticket_events", type_="check")
    op.create_check_constraint(
        "ck_queue_ticket_event_type", "queue_ticket_events",
        "event_type IN ('ARRIVED', 'ISSUED', 'CALLED', 'RECALLED', 'SERVICE_STARTED', 'SERVICE_COMPLETED', 'NO_RESPONSE', 'LEFT')",
    )


def downgrade():
    connection = op.get_bind()
    if connection.scalar(sa.text(
        "SELECT count(*) FROM queue_tickets WHERE consultation_finished_at IS NOT NULL OR consultation_finished_by_user_id IS NOT NULL"
    )) or connection.scalar(sa.text(
        "SELECT count(*) FROM queue_ticket_events WHERE event_type = 'SERVICE_COMPLETED'"
    )):
        raise RuntimeError("Cannot discard queue service completion history")
    op.drop_constraint("ck_queue_ticket_event_type", "queue_ticket_events", type_="check")
    op.create_check_constraint(
        "ck_queue_ticket_event_type", "queue_ticket_events",
        "event_type IN ('ARRIVED', 'ISSUED', 'CALLED', 'RECALLED', 'SERVICE_STARTED', 'NO_RESPONSE', 'LEFT')",
    )
    op.drop_constraint("ck_queue_ticket_finish_after_start", "queue_tickets", type_="check")
    op.drop_constraint("fk_queue_ticket_finished_by", "queue_tickets", type_="foreignkey")
    op.drop_column("queue_tickets", "consultation_finished_by_user_id")
    op.drop_column("queue_tickets", "consultation_finished_at")
