"""Backfill the single-installation pilot into an explicit tenant.

Run with application writers stopped. No production records are deleted.
"""
from alembic import op
import sqlalchemy as sa

revision = "0035_organizations"
down_revision = "0034_administration"
branch_labels = depends_on = None

TABLES = (
    "appointments", "care_centers", "specialties", "anatomical_regions", "medical_studies",
    "doctor_profiles", "clinical_audit_logs", "clinical_addenda", "laboratory_tests",
    "laboratory_orders", "laboratory_order_items", "study_orders", "study_order_items",
    "clinical_coverages", "appointment_coverage_transfers", "clinical_histories", "diagnoses",
    "doctor_availability", "follow_ups", "notifications", "communication_logs", "insurance_companies",
    "patient_insurances", "localities", "regional_settings", "patients", "prescriptions",
    "secretary_center_scopes", "specialty_templates", "specialty_template_modules", "vital_signs",
    "security_audits", "reauthentication_grants", "admin_transfers", "requested_tests",
)
SCOPED_UNIQUES = {
    "localities": [("name",)], "insurance_companies": [("name",), ("code",)],
    "specialties": [("name",), ("code",)], "medical_studies": [("canonical_key",)],
    "laboratory_tests": [("code",), ("name",)], "doctor_profiles": [("user_id",)],
    "patients": [("document_type", "document_number")],
}


def _scope_uniques(upgrade):
    inspector = sa.inspect(op.get_bind())
    for table, keys in SCOPED_UNIQUES.items():
        for constraint in inspector.get_unique_constraints(table):
            columns = constraint["column_names"]
            plain = tuple(c for c in columns if c != "organization_id")
            if plain in keys:
                op.drop_constraint(constraint["name"], table, type_="unique")
                op.create_unique_constraint(constraint["name"], table,
                    (["organization_id"] if upgrade else []) + list(plain))
        for index in inspector.get_indexes(table):
            if not index["unique"] or index.get("duplicates_constraint"):
                continue
            plain = tuple(c for c in index["column_names"] if c != "organization_id")
            if plain in keys:
                op.drop_index(index["name"], table_name=table)
                op.create_index(index["name"], table, (["organization_id"] if upgrade else []) + list(plain), unique=True)


def upgrade():
    op.create_table("organizations",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("slug", sa.String(63), nullable=False, unique=True),
        sa.Column("name", sa.String(150), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False))
    op.execute("INSERT INTO organizations (id, slug, name, is_active, created_at) VALUES (1, 'pilot', 'Organización inicial', true, CURRENT_TIMESTAMP)")
    op.execute("SELECT setval(pg_get_serial_sequence('organizations','id'), 1)")
    op.add_column("users", sa.Column("is_platform_admin", sa.Boolean(), nullable=False, server_default=sa.false()))
    op.create_table("organization_memberships",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("organization_id", sa.Integer(), sa.ForeignKey("organizations.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("state", sa.String(20), nullable=False),
        sa.Column("denied_permissions", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint("user_id", "organization_id", name="uq_membership_user_organization"),
        sa.CheckConstraint("state IN ('active', 'suspended', 'invited')", name="ck_membership_state"))
    for column in ("user_id", "organization_id"):
        op.create_index(f"ix_organization_memberships_{column}", "organization_memberships", [column])
    op.create_table("membership_roles",
        sa.Column("membership_id", sa.Integer(), sa.ForeignKey("organization_memberships.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("role_id", sa.Integer(), sa.ForeignKey("roles.id", ondelete="RESTRICT"), primary_key=True))
    op.execute("INSERT INTO organization_memberships (user_id, organization_id, state, denied_permissions, created_at) SELECT id, 1, CASE WHEN is_active THEN 'active' ELSE 'suspended' END, denied_permissions, CURRENT_TIMESTAMP FROM users")
    op.execute("INSERT INTO membership_roles SELECT m.id, r.role_id FROM organization_memberships m JOIN user_roles r ON r.user_id = m.user_id")
    for table in TABLES:
        op.add_column(table, sa.Column("organization_id", sa.Integer(), nullable=True))
        op.execute(sa.text(f'UPDATE "{table}" SET organization_id = 1'))
        op.alter_column(table, "organization_id", nullable=False)
        op.create_foreign_key(f"fk_{table}_organization", table, "organizations", ["organization_id"], ["id"], ondelete="RESTRICT")
        op.create_index(f"ix_{table}_organization_id", table, ["organization_id"])
    _scope_uniques(True)
    op.create_index("uq_tenant_regional_settings_singleton", "regional_settings", ["organization_id"], unique=True)
    op.execute("SELECT setval(pg_get_serial_sequence('regional_settings','id'), GREATEST(COALESCE((SELECT max(id) FROM regional_settings), 1), 1))")
    for table in ("security_audits", "clinical_audit_logs"):
        op.add_column(table, sa.Column("center_id", sa.Integer(), nullable=True))
        op.create_foreign_key(f"fk_{table}_center", table, "care_centers", ["center_id"], ["id"])
    op.execute("UPDATE clinical_audit_logs a SET center_id = h.center_id FROM clinical_histories h WHERE h.id = a.clinical_history_id")
    op.execute("UPDATE security_audits a SET center_id = c.id FROM care_centers c WHERE substring(a.action from '/centers/([0-9]+)') = c.id::text")
    # All former access/refresh tokens need a fresh, host-bound login.
    op.execute("UPDATE users SET session_version = session_version + 1")


def downgrade():
    if op.get_bind().scalar(sa.text("SELECT count(*) FROM organizations WHERE id <> 1")):
        raise RuntimeError("Refusing to collapse multiple tenants. Restore a coordinated backup instead.")
    # Preserve the current pilot authority when rolling back a disposable database.
    op.execute("DELETE FROM user_roles")
    op.execute("INSERT INTO user_roles SELECT m.user_id, r.role_id FROM membership_roles r JOIN organization_memberships m ON m.id = r.membership_id")
    op.execute("UPDATE users u SET denied_permissions = m.denied_permissions, is_active = u.is_active AND m.state = 'active', session_version = u.session_version + 1 FROM organization_memberships m WHERE m.user_id = u.id")
    for table in ("security_audits", "clinical_audit_logs"):
        op.drop_column(table, "center_id")
    _scope_uniques(False)
    op.drop_index("uq_tenant_regional_settings_singleton", table_name="regional_settings")
    for table in reversed(TABLES):
        op.drop_column(table, "organization_id")
    op.drop_table("membership_roles")
    op.drop_table("organization_memberships")
    op.drop_column("users", "is_platform_admin")
    op.drop_table("organizations")
