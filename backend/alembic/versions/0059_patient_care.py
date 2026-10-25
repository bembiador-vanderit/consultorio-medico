"""Longitudinal patient/doctor associations, without legacy inference or grants."""
from alembic import op
import sqlalchemy as sa

revision = "0059_patient_care"
down_revision = "0058_patient_safety"
branch_labels = depends_on = None


def upgrade():
    op.create_table("patient_care_relationships",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("organization_id", sa.Integer(), sa.ForeignKey("organizations.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("patient_id", sa.Integer(), sa.ForeignKey("patients.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("doctor_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("center_id", sa.Integer(), sa.ForeignKey("care_centers.id", ondelete="RESTRICT")),
        sa.Column("specialty_id", sa.Integer(), sa.ForeignKey("specialties.id", ondelete="RESTRICT")),
        sa.Column("relationship_type", sa.String(32), nullable=False),
        sa.Column("origin", sa.String(32), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("first_seen_at", sa.DateTime(timezone=True)),
        sa.Column("last_seen_at", sa.DateTime(timezone=True)),
        sa.Column("ended_at", sa.DateTime(timezone=True)),
        sa.Column("created_from_clinical_history_id", sa.Integer(), sa.ForeignKey("clinical_histories.id", ondelete="RESTRICT")),
        sa.Column("last_clinical_history_id", sa.Integer(), sa.ForeignKey("clinical_histories.id", ondelete="RESTRICT")),
        sa.Column("created_by_user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("updated_by_user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False, server_default="1"),
        sa.UniqueConstraint("organization_id", "patient_id", "doctor_id", name="uq_patient_care_doctor"),
        sa.CheckConstraint("relationship_type IN ('treating','consultant','specialist_followup','primary')", name="ck_patient_care_type"),
        sa.CheckConstraint("origin IN ('consultation','administrative_assignment','referral','migration','emergency','inpatient','interconsultation')", name="ck_patient_care_origin"),
        sa.CheckConstraint("status IN ('active','follow_up','historical','ended')", name="ck_patient_care_status"),
        sa.CheckConstraint("(status = 'ended' AND ended_at IS NOT NULL AND ended_at >= started_at) OR (status != 'ended' AND ended_at IS NULL)", name="ck_patient_care_end"),
        sa.CheckConstraint("(first_seen_at IS NULL AND last_seen_at IS NULL) OR (first_seen_at IS NOT NULL AND last_seen_at IS NOT NULL AND last_seen_at >= first_seen_at)", name="ck_patient_care_seen"),
        sa.CheckConstraint("revision >= 1", name="ck_patient_care_revision"))
    op.create_index("ix_patient_care_relationships_organization_id", "patient_care_relationships", ["organization_id"])
    op.create_index("ix_patient_care_patient_status", "patient_care_relationships", ["organization_id", "patient_id", "status"])
    op.create_index("ix_patient_care_doctor_status", "patient_care_relationships", ["organization_id", "doctor_id", "status", "last_seen_at"])


def downgrade():
    if op.get_bind().scalar(sa.text("SELECT count(*) FROM patient_care_relationships")):
        raise RuntimeError("Downgrade blocked: preserve patient care relationships and audit before removing the schema")
    op.drop_table("patient_care_relationships")
