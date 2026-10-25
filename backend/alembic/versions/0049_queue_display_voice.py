"""Persist an optional local browser voice choice per public queue display."""

from alembic import op
import sqlalchemy as sa


revision = "0049_queue_display_voice"
down_revision = "0048_queue_display_audio"
branch_labels = depends_on = None


def upgrade():
    op.add_column("queue_displays", sa.Column("audio_voice_uri", sa.String(255), nullable=True))


def downgrade():
    if op.get_bind().scalar(sa.text("SELECT count(*) FROM queue_displays WHERE audio_voice_uri IS NOT NULL")):
        raise RuntimeError("Cannot discard configured display voices")
    op.drop_column("queue_displays", "audio_voice_uri")
