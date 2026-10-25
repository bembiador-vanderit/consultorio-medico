"""Device registry, outbound pairing only; no official activation or print routing."""
from alembic import op
import sqlalchemy as sa

revision = "0067_local_agent_registry"
down_revision = "0066_document_designer"
branch_labels = depends_on = None


def fk(name, target, nullable=False):
    return sa.Column(name, sa.Integer(), sa.ForeignKey(target, ondelete="RESTRICT"), nullable=nullable)


def org():
    return fk("organization_id", "organizations.id")


def stamp(name):
    return sa.Column(name, sa.DateTime(), nullable=False)


def upgrade():
    op.create_table("agent_workgroups", sa.Column("id", sa.Integer(), primary_key=True), org(),
        fk("center_id", "care_centers.id"), sa.Column("name", sa.String(100), nullable=False),
        fk("created_by", "users.id"), stamp("created_at"),
        sa.UniqueConstraint("organization_id", "center_id", "name", name="uq_agent_workgroup_name"))
    op.create_table("local_agents", sa.Column("id", sa.Integer(), primary_key=True), org(),
        sa.Column("agent_uuid", sa.String(36), nullable=False, unique=True),
        sa.Column("display_code", sa.String(32), nullable=False), sa.Column("station_name", sa.String(100), nullable=False),
        fk("center_id", "care_centers.id"), fk("workgroup_id", "agent_workgroups.id"),
        sa.Column("version", sa.String(40), nullable=False), sa.Column("protocol_version", sa.Integer(), nullable=False),
        sa.Column("fingerprint", sa.String(64), nullable=False),
        sa.Column("credential_hash", sa.String(64), nullable=False, unique=True),
        stamp("credential_expires_at"), sa.Column("credential_revision", sa.Integer(), nullable=False),
        sa.Column("health", sa.String(12), nullable=False), fk("paired_by", "users.id"),
        stamp("paired_at"), stamp("last_seen_at"), sa.Column("revoked_at", sa.DateTime()),
        stamp("created_at"), stamp("updated_at"),
        sa.CheckConstraint("health IN ('online','degraded')", name="ck_local_agent_health"))
    op.create_table("agent_pairing_codes", sa.Column("id", sa.Integer(), primary_key=True), org(),
        sa.Column("code_hash", sa.String(64), nullable=False, unique=True),
        fk("center_id", "care_centers.id"), fk("workgroup_id", "agent_workgroups.id"),
        fk("created_by", "users.id"), stamp("created_at"), stamp("expires_at"), sa.Column("consumed_at", sa.DateTime()))
    op.create_table("agent_printers", sa.Column("id", sa.Integer(), primary_key=True), org(),
        fk("agent_id", "local_agents.id"), sa.Column("local_id", sa.String(100), nullable=False),
        sa.Column("display_name", sa.String(200), nullable=False), sa.Column("driver", sa.String(200)),
        sa.Column("is_default", sa.Boolean(), nullable=False), sa.Column("connection", sa.String(12), nullable=False),
        sa.Column("is_virtual", sa.Boolean(), nullable=False), sa.Column("status", sa.String(80), nullable=False),
        sa.Column("papers", sa.JSON(), nullable=False), sa.Column("available", sa.Boolean(), nullable=False), stamp("last_seen_at"),
        sa.UniqueConstraint("agent_id", "local_id", name="uq_agent_printer_local"))
    op.create_table("authorized_station_scopes", sa.Column("id", sa.Integer(), primary_key=True), org(),
        fk("source_id", "local_agents.id"), fk("target_id", "local_agents.id"), fk("created_by", "users.id"), stamp("created_at"),
        sa.UniqueConstraint("source_id", "target_id", name="uq_station_scope"),
        sa.CheckConstraint("source_id <> target_id", name="ck_station_scope_not_self"))
    for table in ("agent_workgroups", "local_agents", "agent_pairing_codes", "agent_printers", "authorized_station_scopes"):
        op.create_index("ix_" + table + "_organization_id", table, ["organization_id"])
    op.create_index("ix_agent_printers_agent_id", "agent_printers", ["agent_id"])
    # First activation only. Bootstrap preserves later explicit revocations.
    bind = op.get_bind()
    for code in ("local_agents:view", "local_agents:manage"):
        bind.execute(sa.text("INSERT INTO permissions(code,description) VALUES (:code,:code) ON CONFLICT (code) DO NOTHING"), {"code": code})
        bind.execute(sa.text("INSERT INTO role_permissions(role_id,permission_id) SELECT r.id,p.id FROM roles r,permissions p WHERE r.code='admin' AND p.code=:code ON CONFLICT DO NOTHING"), {"code": code})


def downgrade():
    bind = op.get_bind()
    bind.execute(sa.text("DELETE FROM role_permissions WHERE permission_id IN (SELECT id FROM permissions WHERE code IN ('local_agents:view','local_agents:manage'))"))
    bind.execute(sa.text("DELETE FROM permissions WHERE code IN ('local_agents:view','local_agents:manage')"))
    for table in ("authorized_station_scopes", "agent_printers", "agent_pairing_codes", "local_agents", "agent_workgroups"):
        op.drop_table(table)
