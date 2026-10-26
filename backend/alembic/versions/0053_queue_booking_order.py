"""Allow queue appointments without a time and preserve booking order."""

from alembic import op
import sqlalchemy as sa


revision = "0053_queue_booking_order"
down_revision = "0052_waiting_rooms"
branch_labels = depends_on = None


def upgrade():
    op.add_column("appointments", sa.Column("daily_booking_order", sa.Integer(), nullable=True))
    op.alter_column("appointments", "appointment_time", existing_type=sa.Time(), nullable=True)
    op.create_check_constraint("ck_appointments_timed_time", "appointments", "appointment_time IS NOT NULL OR schedule_mode = 'queue'")
    op.create_check_constraint("ck_appointments_booking_order_positive", "appointments", "daily_booking_order IS NULL OR daily_booking_order > 0")
    op.execute("""
        UPDATE appointments AS appointment SET daily_booking_order = ranked.booking_order
        FROM (
            SELECT id, row_number() OVER (
                PARTITION BY organization_id, center_id, doctor_id, appointment_date
                ORDER BY created_at, id
            ) AS booking_order
            FROM appointments WHERE schedule_mode = 'queue'
        ) AS ranked
        WHERE appointment.id = ranked.id
    """)
    op.create_index(
        "uq_appointments_queue_booking_order", "appointments",
        ["organization_id", "center_id", "doctor_id", "appointment_date", "daily_booking_order"],
        unique=True, postgresql_where=sa.text("schedule_mode = 'queue' AND daily_booking_order IS NOT NULL"),
    )
    op.create_table(
        "appointment_booking_sequences",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("organization_id", sa.Integer(), sa.ForeignKey("organizations.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("center_id", sa.Integer(), sa.ForeignKey("care_centers.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("doctor_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("appointment_date", sa.Date(), nullable=False),
        sa.Column("last_number", sa.Integer(), nullable=False),
        sa.UniqueConstraint("organization_id", "center_id", "doctor_id", "appointment_date", name="uq_appointment_booking_sequence_bucket"),
        sa.CheckConstraint("last_number > 0", name="ck_appointment_booking_sequence_positive"),
    )
    op.create_index("ix_appointment_booking_sequences_organization_id", "appointment_booking_sequences", ["organization_id"])
    op.execute("""
        INSERT INTO appointment_booking_sequences
            (organization_id, center_id, doctor_id, appointment_date, last_number)
        SELECT organization_id, center_id, doctor_id, appointment_date, max(daily_booking_order)
        FROM appointments WHERE schedule_mode = 'queue'
        GROUP BY organization_id, center_id, doctor_id, appointment_date
    """)


def downgrade():
    bind = op.get_bind()
    if bind.execute(sa.text("SELECT 1 FROM appointments WHERE appointment_time IS NULL LIMIT 1")).first():
        raise RuntimeError("No se puede revertir 0053 con citas sin hora")
    op.drop_table("appointment_booking_sequences")
    op.drop_index("uq_appointments_queue_booking_order", table_name="appointments")
    op.drop_constraint("ck_appointments_booking_order_positive", "appointments", type_="check")
    op.drop_constraint("ck_appointments_timed_time", "appointments", type_="check")
    op.alter_column("appointments", "appointment_time", existing_type=sa.Time(), nullable=False)
    op.drop_column("appointments", "daily_booking_order")
