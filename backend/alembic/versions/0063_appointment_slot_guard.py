"""Prevent concurrent active timed bookings without rewriting any appointment."""
from alembic import op
import sqlalchemy as sa

revision = "0063_appointment_slot_guard"
down_revision = "0062_feature_visibility"
branch_labels = depends_on = None

INDEX = "uq_appointments_active_timed_slot"
PREDICATE = "schedule_mode = 'timed' AND status IN ('scheduled', 'confirmed')"


def upgrade():
    # Fail closed on existing collisions. Never choose, cancel or merge records.
    if op.get_bind().execute(sa.text(f"""
        SELECT 1 FROM appointments WHERE {PREDICATE}
        GROUP BY organization_id, center_id, doctor_id, appointment_date, appointment_time
        HAVING count(*) > 1 LIMIT 1
    """)).first():
        raise RuntimeError("Existen citas activas por hora duplicadas; revise los datos antes de aplicar 0063")
    op.create_index(INDEX, "appointments",
        ["organization_id", "center_id", "doctor_id", "appointment_date", "appointment_time"],
        unique=True, postgresql_nulls_not_distinct=True,
        postgresql_where=sa.text(PREDICATE), sqlite_where=sa.text(PREDICATE))


def downgrade():
    op.drop_index(INDEX, table_name="appointments")
