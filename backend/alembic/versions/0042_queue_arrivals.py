"""Independent queue lines and atomic daily ticket numbering."""

from alembic import op
import sqlalchemy as sa


revision = "0042_queue_arrivals"
down_revision = "0041_appt_contact_attempts"
branch_labels = depends_on = None


def upgrade():
    op.create_table(
        "queue_lines",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("organization_id", sa.Integer(), sa.ForeignKey("organizations.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("center_id", sa.Integer(), sa.ForeignKey("care_centers.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("doctor_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("specialty_id", sa.Integer(), sa.ForeignKey("specialties.id", ondelete="RESTRICT"), nullable=True),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("prefix", sa.String(4), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint("organization_id", "center_id", "prefix", name="uq_queue_line_center_prefix"),
        sa.CheckConstraint("length(prefix) BETWEEN 1 AND 4", name="ck_queue_line_prefix_length"),
    )
    op.create_index("ix_queue_lines_organization_id", "queue_lines", ["organization_id"])
    op.create_index("ix_queue_line_assignment", "queue_lines", ["organization_id", "center_id", "doctor_id"])
    op.create_table(
        "queue_sequences",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("organization_id", sa.Integer(), sa.ForeignKey("organizations.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("center_id", sa.Integer(), sa.ForeignKey("care_centers.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("queue_line_id", sa.Integer(), sa.ForeignKey("queue_lines.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("service_date", sa.Date(), nullable=False),
        sa.Column("last_number", sa.Integer(), nullable=False),
        sa.UniqueConstraint("organization_id", "center_id", "queue_line_id", "service_date", name="uq_queue_sequence_day"),
        sa.CheckConstraint("last_number > 0", name="ck_queue_sequence_positive"),
    )
    op.create_index("ix_queue_sequences_organization_id", "queue_sequences", ["organization_id"])
    op.create_table(
        "queue_tickets",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("organization_id", sa.Integer(), sa.ForeignKey("organizations.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("center_id", sa.Integer(), sa.ForeignKey("care_centers.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("queue_line_id", sa.Integer(), sa.ForeignKey("queue_lines.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("appointment_id", sa.Integer(), sa.ForeignKey("appointments.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("patient_id", sa.Integer(), sa.ForeignKey("patients.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("doctor_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("specialty_id", sa.Integer(), sa.ForeignKey("specialties.id", ondelete="RESTRICT"), nullable=True),
        sa.Column("service_date", sa.Date(), nullable=False),
        sa.Column("sequence_number", sa.Integer(), nullable=False),
        sa.Column("public_code", sa.String(20), nullable=False),
        sa.Column("source", sa.String(20), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("arrived_at", sa.DateTime(), nullable=False),
        sa.Column("ticket_issued_at", sa.DateTime(), nullable=False),
        sa.Column("arrival_registered_by", sa.Integer(), sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("ticket_issued_by", sa.Integer(), sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint("organization_id", "center_id", "queue_line_id", "service_date", "sequence_number", name="uq_queue_ticket_daily_number"),
        sa.UniqueConstraint("organization_id", "appointment_id", name="uq_queue_ticket_appointment"),
        sa.UniqueConstraint("organization_id", "center_id", "service_date", "public_code", name="uq_queue_ticket_public_code"),
        sa.CheckConstraint("sequence_number > 0", name="ck_queue_ticket_positive_number"),
        sa.CheckConstraint("source = 'arrival'", name="ck_queue_ticket_source"),
        sa.CheckConstraint("status = 'waiting'", name="ck_queue_ticket_status"),
    )
    op.create_index("ix_queue_tickets_organization_id", "queue_tickets", ["organization_id"])
    op.create_index("ix_queue_ticket_day", "queue_tickets", ["organization_id", "service_date", "center_id"])


def downgrade():
    connection = op.get_bind()
    for table in ("queue_tickets", "queue_sequences", "queue_lines"):
        if connection.scalar(sa.text(f"SELECT count(*) FROM {table}")):
            raise RuntimeError("Cannot discard queue history or configured lines")
    op.drop_table("queue_tickets")
    op.drop_table("queue_sequences")
    op.drop_table("queue_lines")
