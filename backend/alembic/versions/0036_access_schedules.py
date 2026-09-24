"""Opt-in membership access schedules; preserve pilot access."""
from alembic import op
import sqlalchemy as sa

revision = "0036_access_schedules"
down_revision = "0035_organizations"
branch_labels = depends_on = None


def upgrade():
    op.add_column("organizations", sa.Column("timezone", sa.String(64), nullable=False, server_default="UTC"))
    op.execute("UPDATE organizations SET timezone = 'America/Santo_Domingo' WHERE slug = 'pilot'")
    op.add_column("organization_memberships", sa.Column("restrict_outside_schedule", sa.Boolean(), nullable=False, server_default=sa.false()))
    op.add_column("organization_memberships", sa.Column("weekly_schedule", sa.JSON(), nullable=False, server_default="[]"))
    op.add_column("organization_memberships", sa.Column("schedule_version", sa.Integer(), nullable=False, server_default="0"))
    op.add_column("organization_memberships", sa.Column("schedule_denied_at", sa.DateTime(), nullable=True))
    for name, columns, constraints in (
        ("access_exceptions", [sa.Column("starts_at", sa.DateTime(), nullable=False), sa.Column("ends_at", sa.DateTime(), nullable=False)],
         [sa.CheckConstraint("ends_at > starts_at", name="ck_access_exception_period")]),
        ("access_blocked_dates", [sa.Column("day", sa.Date(), nullable=False)],
         [sa.UniqueConstraint("membership_id", "day", name="uq_access_blocked_day")]),
    ):
        op.create_table(name,
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("organization_id", sa.Integer(), sa.ForeignKey("organizations.id", ondelete="RESTRICT"), nullable=False),
            sa.Column("membership_id", sa.Integer(), sa.ForeignKey("organization_memberships.id"), nullable=False),
            *columns,
            sa.Column("reason", sa.String(300), nullable=False),
            sa.Column("authorized_by", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            *constraints)
        op.create_index(f"ix_{name}_organization_id", name, ["organization_id"])
        op.create_index(f"ix_{name}_membership_id", name, ["membership_id"])


def downgrade():
    op.drop_table("access_blocked_dates")
    op.drop_table("access_exceptions")
    for column in ("schedule_denied_at", "schedule_version", "weekly_schedule", "restrict_outside_schedule"):
        op.drop_column("organization_memberships", column)
    op.drop_column("organizations", "timezone")
