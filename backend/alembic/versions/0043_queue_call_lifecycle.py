"""Queue V2 call lifecycle, consultation start, and append-only events."""

from alembic import op
import sqlalchemy as sa


revision = "0043_queue_call_lifecycle"
down_revision = "0042_queue_arrivals"
branch_labels = depends_on = None


def upgrade():
    op.add_column(
        "queue_lines",
        sa.Column("call_on_consultation_start", sa.Boolean(), nullable=False, server_default=sa.text("false")),
    )
    op.add_column("queue_tickets", sa.Column("first_called_at", sa.DateTime(), nullable=True))
    op.add_column("queue_tickets", sa.Column("last_called_at", sa.DateTime(), nullable=True))
    op.add_column("queue_tickets", sa.Column("called_by_user_id", sa.Integer(), nullable=True))
    op.add_column("queue_tickets", sa.Column("call_count", sa.Integer(), nullable=False, server_default="0"))
    op.add_column("queue_tickets", sa.Column("consultation_started_at", sa.DateTime(), nullable=True))
    op.add_column("queue_tickets", sa.Column("consultation_started_by_user_id", sa.Integer(), nullable=True))
    op.add_column("queue_tickets", sa.Column("left_at", sa.DateTime(), nullable=True))
    op.add_column("queue_tickets", sa.Column("left_by_user_id", sa.Integer(), nullable=True))
    op.create_foreign_key("fk_queue_ticket_called_by", "queue_tickets", "users", ["called_by_user_id"], ["id"], ondelete="RESTRICT")
    op.create_foreign_key("fk_queue_ticket_started_by", "queue_tickets", "users", ["consultation_started_by_user_id"], ["id"], ondelete="RESTRICT")
    op.create_foreign_key("fk_queue_ticket_left_by", "queue_tickets", "users", ["left_by_user_id"], ["id"], ondelete="RESTRICT")
    op.create_check_constraint("ck_queue_ticket_call_count_nonnegative", "queue_tickets", "call_count >= 0")
    op.drop_constraint("ck_queue_ticket_status", "queue_tickets", type_="check")
    op.create_check_constraint(
        "ck_queue_ticket_status", "queue_tickets",
        "status IN ('waiting', 'called', 'in_service', 'completed', 'no_response', 'left')",
    )
    op.create_table(
        "queue_ticket_events",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("organization_id", sa.Integer(), sa.ForeignKey("organizations.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("queue_ticket_id", sa.Integer(), sa.ForeignKey("queue_tickets.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("event_type", sa.String(30), nullable=False),
        sa.Column("occurred_at", sa.DateTime(), nullable=False),
        sa.Column("actor_user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.CheckConstraint(
            "event_type IN ('ARRIVED', 'ISSUED', 'CALLED', 'RECALLED', 'SERVICE_STARTED', 'NO_RESPONSE', 'LEFT')",
            name="ck_queue_ticket_event_type",
        ),
    )
    op.create_index("ix_queue_ticket_events_organization_id", "queue_ticket_events", ["organization_id"])
    op.create_index("ix_queue_ticket_event_ticket_time", "queue_ticket_events", ["organization_id", "queue_ticket_id", "occurred_at", "id"])
    op.create_index("ix_queue_ticket_event_day", "queue_ticket_events", ["organization_id", "occurred_at"])


def downgrade():
    connection = op.get_bind()
    if connection.scalar(sa.text("SELECT count(*) FROM queue_ticket_events")):
        raise RuntimeError("Cannot discard queue event history")
    op.drop_index("ix_queue_ticket_event_day", table_name="queue_ticket_events")
    op.drop_index("ix_queue_ticket_event_ticket_time", table_name="queue_ticket_events")
    op.drop_index("ix_queue_ticket_events_organization_id", table_name="queue_ticket_events")
    op.drop_table("queue_ticket_events")
    op.drop_constraint("ck_queue_ticket_status", "queue_tickets", type_="check")
    op.create_check_constraint("ck_queue_ticket_status", "queue_tickets", "status = 'waiting'")
    op.drop_constraint("ck_queue_ticket_call_count_nonnegative", "queue_tickets", type_="check")
    op.drop_constraint("fk_queue_ticket_left_by", "queue_tickets", type_="foreignkey")
    op.drop_constraint("fk_queue_ticket_started_by", "queue_tickets", type_="foreignkey")
    op.drop_constraint("fk_queue_ticket_called_by", "queue_tickets", type_="foreignkey")
    for name in ("left_by_user_id", "left_at", "consultation_started_by_user_id", "consultation_started_at", "call_count", "called_by_user_id", "last_called_at", "first_called_at"):
        op.drop_column("queue_tickets", name)
    op.drop_column("queue_lines", "call_on_consultation_start")
