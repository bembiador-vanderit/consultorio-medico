"""Per-center card providers and auditable POS batch closures."""

from alembic import op
import sqlalchemy as sa

revision = "0051_card_batch_controls"
down_revision = "0050_queue_display_repeat_limit"
branch_labels = depends_on = None


def upgrade():
    op.create_table(
        "card_provider_settings",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("organization_id", sa.Integer, sa.ForeignKey("organizations.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("center_id", sa.Integer, sa.ForeignKey("care_centers.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("provider", sa.String(10), nullable=False),
        sa.Column("enabled", sa.Boolean, nullable=False),
        sa.Column("updated_by", sa.Integer, sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("updated_at", sa.DateTime, nullable=False),
        sa.UniqueConstraint("organization_id", "center_id", "provider", name="uq_card_provider_center"),
        sa.CheckConstraint("provider IN ('CARDNET','AZUL','VISANET')", name="ck_card_provider_code"),
    )
    op.create_index("ix_card_provider_settings_organization_id", "card_provider_settings", ["organization_id"])
    op.create_index("ix_card_provider_settings_center_id", "card_provider_settings", ["center_id"])
    op.create_table(
        "card_batches",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("organization_id", sa.Integer, sa.ForeignKey("organizations.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("center_id", sa.Integer, sa.ForeignKey("care_centers.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("register_id", sa.Integer, sa.ForeignKey("cash_registers.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("provider", sa.String(10), nullable=False),
        sa.Column("batch_number", sa.String(40), nullable=False),
        sa.Column("state", sa.String(10), nullable=False),
        sa.Column("declared_count", sa.Integer, nullable=False),
        sa.Column("declared_amount", sa.Numeric(12, 2), nullable=False),
        sa.Column("atlas_count", sa.Integer, nullable=False),
        sa.Column("atlas_amount", sa.Numeric(12, 2), nullable=False),
        sa.Column("ever_closed_movement_ids", sa.JSON, nullable=False),
        sa.Column("closed_by", sa.Integer, sa.ForeignKey("users.id", ondelete="RESTRICT")),
        sa.Column("closed_at", sa.DateTime),
        sa.Column("reopened_by", sa.Integer, sa.ForeignKey("users.id", ondelete="RESTRICT")),
        sa.Column("reopened_at", sa.DateTime),
        sa.UniqueConstraint("organization_id", "register_id", "provider", "batch_number", name="uq_card_batch_register"),
        sa.CheckConstraint("provider IN ('CARDNET','AZUL','VISANET')", name="ck_card_batch_provider"),
        sa.CheckConstraint("state IN ('open','closed')", name="ck_card_batch_state"),
        sa.CheckConstraint("declared_count >= 0 AND declared_amount >= 0 AND atlas_count >= 0 AND atlas_amount >= 0", name="ck_card_batch_totals"),
    )
    for column in ("organization_id", "center_id", "register_id"):
        op.create_index(f"ix_card_batches_{column}", "card_batches", [column])
    op.create_table(
        "card_batch_audit",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("organization_id", sa.Integer, sa.ForeignKey("organizations.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("center_id", sa.Integer, sa.ForeignKey("care_centers.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("register_id", sa.Integer, sa.ForeignKey("cash_registers.id", ondelete="RESTRICT")),
        sa.Column("batch_id", sa.Integer, sa.ForeignKey("card_batches.id", ondelete="RESTRICT")),
        sa.Column("movement_id", sa.Integer, sa.ForeignKey("cash_movements.id", ondelete="RESTRICT")),
        sa.Column("action", sa.String(24), nullable=False),
        sa.Column("actor_id", sa.Integer, sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("before", sa.JSON, nullable=False),
        sa.Column("after", sa.JSON, nullable=False),
        sa.Column("reason", sa.String(1000)),
        sa.Column("created_at", sa.DateTime, nullable=False),
        sa.CheckConstraint("action IN ('provider_config','close','reopen','assignment_correction')", name="ck_card_batch_audit_action"),
    )
    for column in ("organization_id", "center_id", "register_id", "batch_id", "movement_id"):
        op.create_index(f"ix_card_batch_audit_{column}", "card_batch_audit", [column])


def downgrade():
    bind = op.get_bind()
    for table in ("card_batch_audit", "card_batches", "card_provider_settings"):
        if bind.execute(sa.text(f"SELECT 1 FROM {table} LIMIT 1")).first():
            raise RuntimeError("No se puede eliminar 0051 mientras existan configuraciones o cierres de tarjeta")
    op.drop_table("card_batch_audit")
    op.drop_table("card_batches")
    op.drop_table("card_provider_settings")
