"""Patient-owned longitudinal safety entries; no historical data conversion."""
from alembic import op
import sqlalchemy as sa

revision = "0058_patient_safety"
down_revision = "0057_clinical_draft_identity"
branch_labels = depends_on = None


def upgrade():
    op.create_table("patient_safety_entries",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("organization_id", sa.Integer(), sa.ForeignKey("organizations.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("patient_id", sa.Integer(), sa.ForeignKey("patients.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("clinical_history_id", sa.Integer(), sa.ForeignKey("clinical_histories.id", ondelete="RESTRICT")),
        sa.Column("entry_type", sa.String(24), nullable=False),
        sa.Column("substance_or_agent", sa.String(200), nullable=False),
        sa.Column("reaction_description", sa.Text(), nullable=False),
        sa.Column("severity", sa.String(16), nullable=False, server_default="unknown"),
        sa.Column("status", sa.String(24), nullable=False, server_default="active"),
        sa.Column("onset_date", sa.Date()), sa.Column("notes", sa.Text()),
        sa.Column("source_type", sa.String(32), nullable=False),
        sa.Column("source_description", sa.String(1000)),
        sa.Column("recorded_by_user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("updated_by_user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("recorded_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False, server_default="1"),
        sa.CheckConstraint("entry_type IN ('allergy','adverse_reaction','contraindication','intolerance_avoid')", name="ck_safety_type"),
        sa.CheckConstraint("severity IN ('unknown','mild','moderate','severe','critical')", name="ck_safety_severity"),
        sa.CheckConstraint("status IN ('active','inactive','entered_in_error')", name="ck_safety_status"),
        sa.CheckConstraint("source_type IN ('patient_reported','family_reported','prior_documentation','observed_during_care','physician_confirmed')", name="ck_safety_source"),
        sa.CheckConstraint("length(trim(substance_or_agent)) > 0 AND length(trim(reaction_description)) > 0", name="ck_safety_content"),
        sa.CheckConstraint("revision >= 1", name="ck_safety_revision"))
    op.create_index("ix_patient_safety_entries_organization_id", "patient_safety_entries", ["organization_id"])
    op.create_index("ix_safety_patient_status", "patient_safety_entries", ["organization_id", "patient_id", "status"])


def downgrade():
    # Never discard safety data, even on an explicitly requested dev downgrade.
    if op.get_bind().scalar(sa.text("SELECT count(*) FROM patient_safety_entries")):
        raise RuntimeError("Downgrade blocked: preserve/export patient safety records before removing this schema")
    op.drop_table("patient_safety_entries")
