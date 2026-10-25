"""Allow both appointment modalities per doctor/center and date."""

from alembic import op
import sqlalchemy as sa


revision = "0054_agenda_multimode"
down_revision = "0053_queue_booking_order"
branch_labels = depends_on = None


def _upgrade_table(table: str, old_mode: str, prefix: str) -> None:
    op.add_column(table, sa.Column("allowed_timed", sa.Boolean(), nullable=True))
    op.add_column(table, sa.Column("allowed_queue", sa.Boolean(), nullable=True))
    op.add_column(table, sa.Column("default_mode", sa.String(10), nullable=True))
    op.execute(sa.text(f"UPDATE {table} SET allowed_timed = ({old_mode} = 'timed'), allowed_queue = ({old_mode} = 'queue'), default_mode = {old_mode}"))
    for column, kind in (("allowed_timed", sa.Boolean()), ("allowed_queue", sa.Boolean()), ("default_mode", sa.String(10))):
        op.alter_column(table, column, existing_type=kind, nullable=False)
    op.create_check_constraint(f"{prefix}_allowed", table, "allowed_timed OR allowed_queue")
    op.create_check_constraint(f"{prefix}_default_allowed", table,
        "(default_mode = 'timed' AND allowed_timed) OR (default_mode = 'queue' AND allowed_queue)")


def upgrade() -> None:
    _upgrade_table("doctor_agenda_settings", "base_mode", "ck_doctor_agenda")
    _upgrade_table("doctor_agenda_exceptions", "mode", "ck_doctor_agenda_exception")


def downgrade() -> None:
    bind = op.get_bind()
    for table in ("doctor_agenda_settings", "doctor_agenda_exceptions"):
        if bind.scalar(sa.text(f"SELECT count(*) FROM {table} WHERE allowed_timed AND allowed_queue")):
            raise RuntimeError("Cannot downgrade multimodal agenda configuration without losing allowed modalities")
    for table, prefix in (("doctor_agenda_exceptions", "ck_doctor_agenda_exception"),
                          ("doctor_agenda_settings", "ck_doctor_agenda")):
        op.drop_constraint(f"{prefix}_default_allowed", table, type_="check")
        op.drop_constraint(f"{prefix}_allowed", table, type_="check")
        op.drop_column(table, "default_mode")
        op.drop_column(table, "allowed_queue")
        op.drop_column(table, "allowed_timed")
