"""Versioned clinical form designer; preserve 0055 documents as legacy."""
from alembic import op
import sqlalchemy as sa


revision = "0056_clinical_forms"
down_revision = "0055_clinical_documents"
branch_labels = depends_on = None

TEMPLATE_PERMISSIONS = (
    "clinical_forms:view", "clinical_forms:create", "clinical_forms:edit_draft",
    "clinical_forms:publish", "clinical_forms:retire", "clinical_forms:assign",
)


def upgrade() -> None:
    op.create_table(
        "clinical_form_templates",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("organization_id", sa.Integer(), sa.ForeignKey("organizations.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("name", sa.String(180), nullable=False),
        sa.Column("code", sa.String(100), nullable=False),
        sa.Column("description", sa.String(1000), nullable=False, server_default=""),
        sa.Column("document_type", sa.String(32), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="draft"),
        sa.Column("current_version_id", sa.Integer(), nullable=True),
        sa.Column("created_by_user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.current_timestamp()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.current_timestamp()),
        sa.UniqueConstraint("organization_id", "code", name="uq_clinical_form_template_code"),
        sa.CheckConstraint("status IN ('draft', 'published', 'retired')", name="ck_clinical_form_template_status"),
        sa.CheckConstraint("document_type IN ('preoperative', 'physical_exam')", name="ck_clinical_form_template_type"),
    )
    op.create_index("ix_clinical_form_templates_organization_id", "clinical_form_templates", ["organization_id"])
    op.create_table(
        "clinical_form_versions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("organization_id", sa.Integer(), sa.ForeignKey("organizations.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("template_id", sa.Integer(), sa.ForeignKey("clinical_form_templates.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="draft"),
        sa.Column("definition", sa.JSON(), nullable=False),
        sa.Column("created_by_user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.current_timestamp()),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("template_id", "version", name="uq_clinical_form_template_version"),
        sa.CheckConstraint("status IN ('draft', 'published')", name="ck_clinical_form_version_status"),
        sa.CheckConstraint("version > 0", name="ck_clinical_form_version_positive"),
    )
    op.create_index("ix_clinical_form_versions_organization_id", "clinical_form_versions", ["organization_id"])
    op.create_index("ix_clinical_form_versions_template_id", "clinical_form_versions", ["template_id"])
    op.create_index("uq_clinical_form_one_draft", "clinical_form_versions", ["template_id"], unique=True,
                    postgresql_where=sa.text("status = 'draft'"), sqlite_where=sa.text("status = 'draft'"))
    op.create_foreign_key("fk_clinical_form_current_version", "clinical_form_templates", "clinical_form_versions",
                          ["current_version_id"], ["id"], ondelete="RESTRICT")
    op.create_table(
        "clinical_form_assignments",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("organization_id", sa.Integer(), sa.ForeignKey("organizations.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("template_id", sa.Integer(), sa.ForeignKey("clinical_form_templates.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("document_type", sa.String(32), nullable=False),
        sa.Column("scope_key", sa.String(120), nullable=False),
        sa.Column("center_id", sa.Integer(), sa.ForeignKey("care_centers.id", ondelete="RESTRICT"), nullable=True),
        sa.Column("specialty_id", sa.Integer(), sa.ForeignKey("specialties.id", ondelete="RESTRICT"), nullable=True),
        sa.Column("doctor_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=True),
        sa.Column("created_by_user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.current_timestamp()),
        sa.UniqueConstraint("organization_id", "document_type", "scope_key", name="uq_clinical_form_assignment_scope"),
        sa.CheckConstraint("doctor_id IS NULL OR center_id IS NOT NULL", name="ck_clinical_form_doctor_center"),
        sa.CheckConstraint("specialty_id IS NULL OR center_id IS NOT NULL", name="ck_clinical_form_specialty_center"),
    )
    for col in ("organization_id", "template_id", "center_id", "specialty_id", "doctor_id"):
        op.create_index(f"ix_clinical_form_assignments_{col}", "clinical_form_assignments", [col])
    op.create_table(
        "secretary_document_grants",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("organization_id", sa.Integer(), sa.ForeignKey("organizations.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("start_preoperative", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("start_physical_exam", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("prepare_administrative", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("updated_by_user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.current_timestamp()),
        sa.UniqueConstraint("organization_id", "user_id", name="uq_secretary_document_grant_user"),
    )
    op.create_index("ix_secretary_document_grants_organization_id", "secretary_document_grants", ["organization_id"])
    op.create_index("ix_secretary_document_grants_user_id", "secretary_document_grants", ["user_id"])
    for table in ("preoperative_evaluations", "physical_examinations"):
        op.add_column(table, sa.Column("template_id", sa.Integer(), nullable=True))
        op.add_column(table, sa.Column("template_version_id", sa.Integer(), nullable=True))
        op.create_foreign_key(f"fk_{table}_template", table, "clinical_form_templates", ["template_id"], ["id"], ondelete="RESTRICT")
        op.create_foreign_key(f"fk_{table}_template_version", table, "clinical_form_versions", ["template_version_id"], ["id"], ondelete="RESTRICT")
        op.create_index(f"ix_{table}_template_id", table, ["template_id"])
        op.create_index(f"ix_{table}_template_version_id", table, ["template_version_id"])
        op.create_check_constraint(f"ck_{table}_template_pair", table,
                                   "(template_id IS NULL AND template_version_id IS NULL) OR (template_id IS NOT NULL AND template_version_id IS NOT NULL)")
    for code in TEMPLATE_PERMISSIONS:
        op.execute(sa.text("INSERT INTO permissions (code, description) VALUES (:code, :code) ON CONFLICT (code) DO NOTHING").bindparams(code=code))
    op.execute(sa.text("""INSERT INTO role_permissions (role_id, permission_id)
        SELECT r.id, p.id FROM roles r CROSS JOIN permissions p
        WHERE r.code = 'admin' AND p.code IN :codes ON CONFLICT DO NOTHING""").bindparams(sa.bindparam("codes", expanding=True, value=TEMPLATE_PERMISSIONS)))
    # 0055 granted preparation to every secretary. V1 makes it explicitly
    # configurable per secretary; all grants start disabled.
    op.execute(sa.text("""DELETE FROM role_permissions WHERE role_id IN
        (SELECT id FROM roles WHERE code = 'secretary') AND permission_id IN
        (SELECT id FROM permissions WHERE code IN ('clinical_documents:create', 'clinical_documents:prepare'))"""))


def downgrade() -> None:
    bind = op.get_bind()
    for table in ("clinical_form_templates", "clinical_form_versions", "clinical_form_assignments", "secretary_document_grants"):
        if bind.scalar(sa.text(f"SELECT count(*) FROM {table}")):
            raise RuntimeError("Clinical form data exists; downgrade would destroy it")
    for table in ("preoperative_evaluations", "physical_examinations"):
        if bind.scalar(sa.text(f"SELECT count(*) FROM {table} WHERE template_id IS NOT NULL OR template_version_id IS NOT NULL")):
            raise RuntimeError("Template-bound documents exist; downgrade would alter them")
        op.drop_constraint(f"ck_{table}_template_pair", table, type_="check")
        op.drop_index(f"ix_{table}_template_version_id", table_name=table)
        op.drop_index(f"ix_{table}_template_id", table_name=table)
        op.drop_constraint(f"fk_{table}_template_version", table, type_="foreignkey")
        op.drop_constraint(f"fk_{table}_template", table, type_="foreignkey")
        op.drop_column(table, "template_version_id")
        op.drop_column(table, "template_id")
    op.execute(sa.text("DELETE FROM role_permissions WHERE permission_id IN (SELECT id FROM permissions WHERE code IN :codes)").bindparams(sa.bindparam("codes", expanding=True, value=TEMPLATE_PERMISSIONS)))
    op.execute(sa.text("DELETE FROM permissions WHERE code IN :codes").bindparams(sa.bindparam("codes", expanding=True, value=TEMPLATE_PERMISSIONS)))
    op.execute(sa.text("""INSERT INTO role_permissions (role_id, permission_id)
        SELECT r.id, p.id FROM roles r CROSS JOIN permissions p
        WHERE r.code = 'secretary' AND p.code IN ('clinical_documents:create', 'clinical_documents:prepare')
        ON CONFLICT DO NOTHING"""))
    op.drop_table("secretary_document_grants")
    op.drop_table("clinical_form_assignments")
    op.drop_constraint("fk_clinical_form_current_version", "clinical_form_templates", type_="foreignkey")
    op.drop_table("clinical_form_versions")
    op.drop_table("clinical_form_templates")
