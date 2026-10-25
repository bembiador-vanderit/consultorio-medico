"""Agenda mode by doctor/center/date and immutable appointment snapshot."""

from alembic import op
import sqlalchemy as sa

revision = "0040_agenda_schedule_mode"
down_revision = "0039_ars_receivables"
branch_labels = depends_on = None


def upgrade():
    op.create_table(
        "doctor_agenda_settings",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("organization_id", sa.Integer(), sa.ForeignKey("organizations.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("doctor_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("center_id", sa.Integer(), sa.ForeignKey("care_centers.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("base_mode", sa.String(10), nullable=False),
        sa.UniqueConstraint("organization_id", "doctor_id", "center_id", name="uq_doctor_agenda_setting"),
        sa.CheckConstraint("base_mode IN ('timed', 'queue')", name="ck_doctor_agenda_base_mode"),
    )
    op.create_table(
        "doctor_agenda_exceptions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("organization_id", sa.Integer(), sa.ForeignKey("organizations.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("doctor_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("center_id", sa.Integer(), sa.ForeignKey("care_centers.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("agenda_date", sa.Date(), nullable=False),
        sa.Column("mode", sa.String(10), nullable=False),
        sa.UniqueConstraint("organization_id", "doctor_id", "center_id", "agenda_date", name="uq_doctor_agenda_exception"),
        sa.CheckConstraint("mode IN ('timed', 'queue')", name="ck_doctor_agenda_exception_mode"),
    )
    for table in ("doctor_agenda_settings", "doctor_agenda_exceptions"):
        for column in ("organization_id", "doctor_id", "center_id"):
            op.create_index(f"ix_{table}_{column}", table, [column])
    op.create_index("ix_doctor_agenda_exceptions_agenda_date", "doctor_agenda_exceptions", ["agenda_date"])
    op.add_column("appointments", sa.Column("schedule_mode", sa.String(10), nullable=False, server_default="timed"))
    op.create_check_constraint("ck_appointments_schedule_mode", "appointments", "schedule_mode IN ('timed', 'queue')")


def downgrade():
    # Refuse to discard either snapshots or administrator choices.
    connection = op.get_bind()
    if connection.scalar(sa.text("SELECT count(*) FROM appointments WHERE schedule_mode <> 'timed'")):
        raise RuntimeError("Cannot drop agenda mode while queue-mode appointments exist")
    if connection.scalar(sa.text("SELECT count(*) FROM doctor_agenda_settings")) or connection.scalar(sa.text("SELECT count(*) FROM doctor_agenda_exceptions")):
        raise RuntimeError("Cannot drop non-empty agenda configuration")
    op.drop_constraint("ck_appointments_schedule_mode", "appointments", type_="check")
    op.drop_column("appointments", "schedule_mode")
    op.drop_table("doctor_agenda_exceptions")
    op.drop_table("doctor_agenda_settings")
