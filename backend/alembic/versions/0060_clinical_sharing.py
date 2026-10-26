"""Opt-in, resource-specific clinical sharing. No existing grants or backfill."""
from alembic import op
import sqlalchemy as sa

revision = "0060_clinical_sharing"
down_revision = "0059_patient_care"
branch_labels = depends_on = None


def upgrade():
    op.create_table("clinical_sharing_policies",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("organization_id", sa.Integer(), sa.ForeignKey("organizations.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("mode", sa.String(24), nullable=False, server_default="assigned"),
        sa.Column("limit_to_same_center", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("clinical_history", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("clinical_documents", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("patient_safety", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("revision", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("updated_by_user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("organization_id", name="uq_clinical_sharing_organization"),
        sa.CheckConstraint("mode IN ('assigned','active_relationship','same_center','organization')", name="ck_clinical_sharing_mode"),
        sa.CheckConstraint("revision >= 1", name="ck_clinical_sharing_revision"))
    op.create_index("ix_clinical_sharing_policies_organization_id", "clinical_sharing_policies", ["organization_id"])
    op.create_index("ix_clinical_shared_read_audit", "clinical_audit_logs", ["organization_id", "user_id", "resource_type", "resource_id", "created_at"])


def downgrade():
    if op.get_bind().scalar(sa.text("SELECT count(*) FROM clinical_sharing_policies")):
        raise RuntimeError("Preserve configured clinical policies before downgrade")
    op.drop_index("ix_clinical_shared_read_audit", table_name="clinical_audit_logs")
    op.drop_table("clinical_sharing_policies")
