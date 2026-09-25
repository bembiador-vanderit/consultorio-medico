"""6C5: additive insurance plans and independent appointment snapshots."""
from alembic import op
import sqlalchemy as sa
revision = "0037_insurance_coverage"
down_revision = "0036_access_schedules"
branch_labels = depends_on = None


def upgrade():
    op.create_table("insurance_plans",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("organization_id", sa.Integer(), sa.ForeignKey("organizations.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("insurance_company_id", sa.Integer(), sa.ForeignKey("insurance_companies.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("name", sa.String(150), nullable=False), sa.Column("code", sa.String(50)),
        sa.Column("description", sa.String(1000)), sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.UniqueConstraint("organization_id", "insurance_company_id", "name", name="uq_insurance_plan_name"))
    for name, typ in (("plan_id", sa.Integer()), ("policy_holder", sa.String(150)), ("relationship_to_holder", sa.String(80)),
                      ("valid_from", sa.Date()), ("valid_until", sa.Date()), ("administrative_notes", sa.String(1000))):
        op.add_column("patient_insurances", sa.Column(name, typ, nullable=True))
    op.create_foreign_key("fk_patient_insurance_plan", "patient_insurances", "insurance_plans", ["plan_id"], ["id"], ondelete="RESTRICT")
    op.create_check_constraint("ck_insurance_period", "patient_insurances", "valid_until IS NULL OR valid_from IS NULL OR valid_until >= valid_from")
    op.create_table("appointment_insurance_coverages",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("organization_id", sa.Integer(), sa.ForeignKey("organizations.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("appointment_id", sa.Integer(), sa.ForeignKey("appointments.id", ondelete="RESTRICT"), nullable=False, unique=True),
        sa.Column("patient_insurance_id", sa.Integer(), sa.ForeignKey("patient_insurances.id", ondelete="RESTRICT")),
        sa.Column("insurance_snapshot", sa.JSON(), nullable=False), sa.Column("service", sa.String(200), nullable=False),
        sa.Column("currency", sa.String(3), nullable=False),
        *[sa.Column(name, sa.Numeric(12, 2), nullable=False) for name in ("base_amount", "covered_amount", "patient_copay")],
        sa.Column("authorization_status", sa.String(30), nullable=False), sa.Column("authorization_number", sa.String(100)),
        sa.Column("authorized_at", sa.DateTime(timezone=True)), sa.Column("authorized_amount", sa.Numeric(12, 2)),
        sa.Column("authorization_notes", sa.String(1000)), sa.Column("notes", sa.String(1000)),
        sa.Column("revision", sa.Integer(), nullable=False), sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.CheckConstraint("base_amount >= 0 AND covered_amount >= 0 AND patient_copay >= 0", name="ck_coverage_nonnegative"),
        sa.CheckConstraint("base_amount = covered_amount + patient_copay", name="ck_coverage_total"),
        sa.CheckConstraint("authorized_amount IS NULL OR authorized_amount >= 0", name="ck_authorized_nonnegative"))
    for table in ("insurance_plans", "appointment_insurance_coverages"):
        op.create_index(f"ix_{table}_organization_id", table, ["organization_id"])
    op.create_index("ix_insurance_plans_insurance_company_id", "insurance_plans", ["insurance_company_id"])
    op.execute("INSERT INTO permissions (code, description) VALUES ('insurance:manage', 'Gestionar afiliaciones y coberturas de seguro') ON CONFLICT (code) DO NOTHING")
    op.execute("INSERT INTO role_permissions (role_id, permission_id) SELECT r.id, p.id FROM roles r CROSS JOIN permissions p WHERE r.code IN ('admin', 'secretary') AND p.code = 'insurance:manage' ON CONFLICT DO NOTHING")


def downgrade():
    op.execute("DELETE FROM role_permissions WHERE permission_id IN (SELECT id FROM permissions WHERE code = 'insurance:manage')")
    op.execute("DELETE FROM permissions WHERE code = 'insurance:manage'")
    op.drop_table("appointment_insurance_coverages")
    op.drop_constraint("ck_insurance_period", "patient_insurances", type_="check")
    op.drop_constraint("fk_patient_insurance_plan", "patient_insurances", type_="foreignkey")
    for name in ("plan_id", "policy_holder", "relationship_to_holder", "valid_from", "valid_until", "administrative_notes"):
        op.drop_column("patient_insurances", name)
    op.drop_table("insurance_plans")
