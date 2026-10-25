"""Optional browser speech settings for public queue displays."""

from alembic import op
import sqlalchemy as sa


revision = "0048_queue_display_audio"
down_revision = "0047_queue_displays"
branch_labels = depends_on = None


def upgrade():
    op.add_column("queue_displays", sa.Column("audio_enabled", sa.Boolean(), nullable=False, server_default=sa.false()))
    op.add_column("queue_displays", sa.Column("audio_volume", sa.Float(), nullable=False, server_default="1"))
    op.add_column("queue_displays", sa.Column("audio_language", sa.String(5), nullable=False, server_default="es-DO"))
    op.add_column("queue_displays", sa.Column("audio_rate", sa.Float(), nullable=False, server_default="1"))
    op.add_column("queue_displays", sa.Column("audio_pitch", sa.Float(), nullable=False, server_default="1"))
    op.add_column("queue_displays", sa.Column("repeat_count", sa.Integer(), nullable=False, server_default="1"))
    op.add_column("queue_displays", sa.Column("repeat_delay_ms", sa.Integer(), nullable=False, server_default="1000"))
    op.add_column("queue_displays", sa.Column("announce_service_name", sa.Boolean(), nullable=False, server_default=sa.false()))
    op.add_column("queue_displays", sa.Column("announce_provider_name", sa.Boolean(), nullable=False, server_default=sa.false()))
    for name, expression in (
        ("ck_queue_display_audio_volume", "audio_volume BETWEEN 0 AND 1"),
        ("ck_queue_display_audio_rate", "audio_rate BETWEEN 0.5 AND 2"),
        ("ck_queue_display_audio_pitch", "audio_pitch BETWEEN 0.5 AND 2"),
        ("ck_queue_display_repeat_count", "repeat_count BETWEEN 1 AND 3"),
        ("ck_queue_display_repeat_delay", "repeat_delay_ms BETWEEN 1000 AND 5000"),
        ("ck_queue_display_audio_language", "audio_language IN ('es-DO', 'es')"),
    ):
        op.create_check_constraint(name, "queue_displays", expression)


def downgrade():
    for name in (
        "ck_queue_display_audio_language", "ck_queue_display_repeat_delay",
        "ck_queue_display_repeat_count", "ck_queue_display_audio_pitch",
        "ck_queue_display_audio_rate", "ck_queue_display_audio_volume",
    ):
        op.drop_constraint(name, "queue_displays", type_="check")
    for name in (
        "announce_provider_name", "announce_service_name", "repeat_delay_ms",
        "repeat_count", "audio_pitch", "audio_rate", "audio_language",
        "audio_volume", "audio_enabled",
    ):
        op.drop_column("queue_displays", name)
