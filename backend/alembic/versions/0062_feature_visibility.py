"""Contextual visibility only; no data/permission/entitlement backfill."""
from alembic import op
import sqlalchemy as sa

revision = "0062_feature_visibility"
down_revision = "0061_cardiology_workspace"
branch_labels = depends_on = None


def upgrade():
    op.create_table("feature_visibility_settings",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("organization_id", sa.Integer(), sa.ForeignKey("organizations.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("center_id", sa.Integer(), sa.ForeignKey("care_centers.id", ondelete="RESTRICT")),
        sa.Column("feature_code", sa.String(80), nullable=False),
        sa.Column("context_code", sa.String(40), nullable=False),
        sa.Column("audience", sa.String(40), nullable=False),
        sa.Column("visibility_mode", sa.String(10), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("updated_by_user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("visibility_mode IN ('hidden','visible')", name="ck_feature_visibility_mode"),
        sa.CheckConstraint("revision >= 1", name="ck_feature_visibility_revision"))
    op.create_index("ix_feature_visibility_settings_organization_id", "feature_visibility_settings", ["organization_id"])
    for name, columns, condition in (
        ("org", ["organization_id", "feature_code", "context_code", "audience"], "center_id IS NULL"),
        ("center", ["organization_id", "center_id", "feature_code", "context_code", "audience"], "center_id IS NOT NULL")):
        op.create_index("uq_feature_visibility_" + name, "feature_visibility_settings", columns, unique=True,
            postgresql_where=sa.text(condition), sqlite_where=sa.text(condition))


def downgrade():
    if op.get_bind().scalar(sa.text("SELECT count(*) FROM feature_visibility_settings")):
        raise RuntimeError("Preserve visibility configuration before downgrade")
    op.drop_table("feature_visibility_settings")
