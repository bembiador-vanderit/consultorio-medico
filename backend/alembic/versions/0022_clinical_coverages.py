"""add explicit clinical coverage and appointment transfer trace

Revision ID: 0022_clinical_coverages
Revises: 0021_clinical_lifecycle
"""
from alembic import op
import sqlalchemy as sa

revision = "0022_clinical_coverages"
down_revision = "0021_clinical_lifecycle"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "clinical_coverages",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("principal_doctor_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("substitute_doctor_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("center_id", sa.Integer(), sa.ForeignKey("care_centers.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("starts_at", sa.DateTime(), nullable=False),
        sa.Column("ends_at", sa.DateTime(), nullable=False),
        sa.Column("revoked_at", sa.DateTime(), nullable=True),
        sa.Column("created_by_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.CheckConstraint("principal_doctor_id <> substitute_doctor_id", name="ck_clinical_coverage_distinct_doctors"),
        sa.CheckConstraint("ends_at > starts_at", name="ck_clinical_coverage_valid_period"),
    )
    for column in ("principal_doctor_id", "substitute_doctor_id", "center_id", "starts_at", "ends_at"):
        op.create_index(f"ix_clinical_coverages_{column}", "clinical_coverages", [column])

    op.create_table(
        "appointment_coverage_transfers",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("appointment_id", sa.Integer(), sa.ForeignKey("appointments.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("coverage_id", sa.Integer(), sa.ForeignKey("clinical_coverages.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("original_doctor_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("substitute_doctor_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("executed_by_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint("appointment_id", name="uq_appointment_coverage_transfer"),
    )
    for column in ("appointment_id", "coverage_id", "original_doctor_id", "substitute_doctor_id"):
        op.create_index(f"ix_appointment_coverage_transfers_{column}", "appointment_coverage_transfers", [column])


def downgrade() -> None:
    op.drop_table("appointment_coverage_transfers")
    op.drop_table("clinical_coverages")
