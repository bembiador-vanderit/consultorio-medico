"""Allow a configurable finite number of repeats for each queue announcement."""

from alembic import op
import sqlalchemy as sa


revision = "0050_queue_display_repeat_limit"
down_revision = "0049_queue_display_voice"
branch_labels = depends_on = None


def upgrade():
    op.drop_constraint("ck_queue_display_repeat_count", "queue_displays", type_="check")
    op.create_check_constraint("ck_queue_display_repeat_count", "queue_displays", "repeat_count BETWEEN 1 AND 10")


def downgrade():
    bind = op.get_bind()
    if bind.execute(sa.text("SELECT 1 FROM queue_displays WHERE repeat_count > 3 LIMIT 1")).first():
        raise RuntimeError("No se puede volver a 0049 con pantallas configuradas para más de 3 repeticiones")
    op.drop_constraint("ck_queue_display_repeat_count", "queue_displays", type_="check")
    op.create_check_constraint("ck_queue_display_repeat_count", "queue_displays", "repeat_count BETWEEN 1 AND 3")
