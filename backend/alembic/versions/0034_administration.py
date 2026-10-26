"""Security administration; requires new login after upgrade."""
from alembic import op
import sqlalchemy as sa
revision = "0034_administration"
down_revision = "0033_specialty_codes"
branch_labels = None
depends_on = None

def upgrade():
    op.add_column("users", sa.Column("session_version", sa.Integer(), nullable=False, server_default="0"))
    op.add_column("users", sa.Column("denied_permissions", sa.JSON(), nullable=False, server_default="[]"))
    op.add_column("users", sa.Column("reauth_failures", sa.Integer(), nullable=False, server_default="0"))
    op.add_column("users", sa.Column("reauth_locked_until", sa.DateTime(), nullable=True))
    op.create_table("security_audits",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("actor_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("action", sa.String(200), nullable=False),
        sa.Column("outcome", sa.String(20), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False))
    op.create_index("ix_security_audits_actor_id", "security_audits", ["actor_id"])
    op.create_table("reauthentication_grants",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("session_version", sa.Integer(), nullable=False),
        sa.Column("action", sa.String(200), nullable=False),
        sa.Column("expires_at", sa.DateTime(), nullable=False),
        sa.Column("consumed", sa.Boolean(), nullable=False))
    op.create_index("ix_reauthentication_grants_user_id", "reauthentication_grants", ["user_id"])
    op.create_table("admin_transfers",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("initiator_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("target_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("initiator_version", sa.Integer(), nullable=False),
        sa.Column("target_version", sa.Integer(), nullable=False),
        sa.Column("replace_initiator", sa.Boolean(), nullable=False),
        sa.Column("state", sa.String(20), nullable=False),
        sa.Column("expires_at", sa.DateTime(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False))
    op.create_index("ix_admin_transfers_target_id", "admin_transfers", ["target_id"])
    op.execute("DELETE FROM role_permissions WHERE role_id IN (SELECT id FROM roles WHERE code='admin') AND permission_id IN (SELECT id FROM permissions WHERE code='clinical:access')")

def downgrade():
    op.drop_table("admin_transfers")
    op.drop_table("reauthentication_grants")
    op.drop_table("security_audits")
    for column in ("reauth_locked_until", "reauth_failures", "denied_permissions", "session_version"):
        op.drop_column("users", column)
