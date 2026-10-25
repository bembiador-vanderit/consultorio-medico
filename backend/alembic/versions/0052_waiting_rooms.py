"""Add center-owned waiting rooms without assigning historic resources."""

from alembic import op
import sqlalchemy as sa


revision = "0052_waiting_rooms"
down_revision = "0051_card_batch_controls"
branch_labels = depends_on = None


def upgrade():
    op.create_table(
        "waiting_rooms",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("organization_id", sa.Integer, sa.ForeignKey("organizations.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("center_id", sa.Integer, sa.ForeignKey("care_centers.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("code", sa.String(30)),
        sa.Column("description", sa.String(500)),
        sa.Column("is_active", sa.Boolean, nullable=False),
        sa.Column("sort_order", sa.Integer, nullable=False),
        sa.Column("created_at", sa.DateTime, nullable=False),
        sa.Column("updated_at", sa.DateTime, nullable=False),
        sa.UniqueConstraint("id", "organization_id", "center_id", name="uq_waiting_room_scope_reference"),
        sa.CheckConstraint("length(trim(name)) > 0", name="ck_waiting_room_name_nonempty"),
        sa.CheckConstraint("sort_order >= 0", name="ck_waiting_room_sort_order"),
    )
    op.create_index("ix_waiting_rooms_organization_id", "waiting_rooms", ["organization_id"])
    op.create_index("ix_waiting_rooms_center_id", "waiting_rooms", ["center_id"])
    op.create_index("uq_waiting_room_center_name", "waiting_rooms", ["organization_id", "center_id", sa.text("lower(trim(name))")], unique=True)
    op.create_table(
        "waiting_room_secretaries",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("organization_id", sa.Integer, sa.ForeignKey("organizations.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("waiting_room_id", sa.Integer, sa.ForeignKey("waiting_rooms.id", ondelete="CASCADE"), nullable=False),
        sa.Column("secretary_user_id", sa.Integer, sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("created_by_user_id", sa.Integer, sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("created_at", sa.DateTime, nullable=False),
        sa.UniqueConstraint("organization_id", "waiting_room_id", "secretary_user_id", name="uq_waiting_room_secretary"),
    )
    for column in ("organization_id", "waiting_room_id", "secretary_user_id"):
        op.create_index(f"ix_waiting_room_secretaries_{column}", "waiting_room_secretaries", [column])
    for table, prefix in (("queue_lines", "queue_line"), ("queue_displays", "queue_display")):
        op.add_column(table, sa.Column("waiting_room_id", sa.Integer, nullable=True))
        op.create_foreign_key(f"fk_{prefix}_waiting_room_scope", table, "waiting_rooms",
                              ["waiting_room_id", "organization_id", "center_id"],
                              ["id", "organization_id", "center_id"], ondelete="RESTRICT")
        op.create_index(f"ix_{table}_waiting_room_id", table, ["waiting_room_id"])


def downgrade():
    bind = op.get_bind()
    if bind.execute(sa.text("SELECT 1 FROM waiting_rooms LIMIT 1")).first():
        raise RuntimeError("No se puede revertir 0052 con salas configuradas")
    for table, prefix in (("queue_displays", "queue_display"), ("queue_lines", "queue_line")):
        op.drop_index(f"ix_{table}_waiting_room_id", table_name=table)
        op.drop_constraint(f"fk_{prefix}_waiting_room_scope", table, type_="foreignkey")
        op.drop_column(table, "waiting_room_id")
    op.drop_table("waiting_room_secretaries")
    op.drop_table("waiting_rooms")
