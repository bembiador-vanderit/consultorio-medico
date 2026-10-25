"""Append-only human contact attempts before appointments."""

from alembic import op
import sqlalchemy as sa


revision = "0041_appt_contact_attempts"
down_revision = "0040_agenda_schedule_mode"
branch_labels = depends_on = None


def upgrade():
    op.create_table(
        "appointment_contact_attempts",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("organization_id", sa.Integer(), sa.ForeignKey("organizations.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("appointment_id", sa.Integer(), sa.ForeignKey("appointments.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("contacted_by_user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("contacted_at", sa.DateTime(), nullable=False),
        sa.Column("channel", sa.String(20), nullable=False),
        sa.Column("contact_value", sa.String(30), nullable=True),
        sa.Column("result", sa.String(20), nullable=False),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.CheckConstraint("channel = 'phone'", name="ck_appointment_contact_channel"),
        sa.CheckConstraint("result IN ('will_attend', 'will_not_attend', 'no_answer', 'retry')", name="ck_appointment_contact_result"),
    )
    op.create_index("ix_appointment_contact_attempts_organization_id", "appointment_contact_attempts", ["organization_id"])
    op.create_index("ix_appointment_contact_latest", "appointment_contact_attempts", ["organization_id", "appointment_id", "contacted_at", "id"])
    op.create_index("ix_appointment_contact_actor", "appointment_contact_attempts", ["contacted_by_user_id"])


def downgrade():
    connection = op.get_bind()
    if connection.scalar(sa.text("SELECT count(*) FROM appointment_contact_attempts")):
        raise RuntimeError("Cannot discard recorded appointment contact history")
    op.drop_table("appointment_contact_attempts")
