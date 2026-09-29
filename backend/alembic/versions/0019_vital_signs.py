"""add vital signs

Revision ID: 0019_vital_signs
Revises: 0018_prescriptions
"""

from alembic import op
import sqlalchemy as sa

revision = "0019_vital_signs"
down_revision = "0018_prescriptions"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "vital_signs",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("clinical_history_id", sa.Integer(), nullable=False),
        sa.Column("systolic_pressure", sa.Integer(), nullable=True),
        sa.Column("diastolic_pressure", sa.Integer(), nullable=True),
        sa.Column("heart_rate", sa.Integer(), nullable=True),
        sa.Column("respiratory_rate", sa.Integer(), nullable=True),
        sa.Column("temperature_c", sa.Numeric(precision=4, scale=1), nullable=True),
        sa.Column("oxygen_saturation", sa.Numeric(precision=5, scale=2), nullable=True),
        sa.Column("weight_kg", sa.Numeric(precision=6, scale=2), nullable=True),
        sa.Column("height_cm", sa.Numeric(precision=5, scale=2), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
        sa.CheckConstraint("systolic_pressure IS NULL OR systolic_pressure BETWEEN 40 AND 300", name="ck_vital_signs_systolic"),
        sa.CheckConstraint("diastolic_pressure IS NULL OR diastolic_pressure BETWEEN 20 AND 200", name="ck_vital_signs_diastolic"),
        sa.CheckConstraint("heart_rate IS NULL OR heart_rate BETWEEN 20 AND 300", name="ck_vital_signs_heart_rate"),
        sa.CheckConstraint("respiratory_rate IS NULL OR respiratory_rate BETWEEN 5 AND 80", name="ck_vital_signs_respiratory_rate"),
        sa.CheckConstraint("temperature_c IS NULL OR temperature_c BETWEEN 25 AND 45", name="ck_vital_signs_temperature"),
        sa.CheckConstraint("oxygen_saturation IS NULL OR oxygen_saturation BETWEEN 0 AND 100", name="ck_vital_signs_oxygen_saturation"),
        sa.CheckConstraint("weight_kg IS NULL OR weight_kg BETWEEN 1 AND 500", name="ck_vital_signs_weight"),
        sa.CheckConstraint("height_cm IS NULL OR height_cm BETWEEN 20 AND 300", name="ck_vital_signs_height"),
        sa.CheckConstraint(
            "systolic_pressure IS NULL OR diastolic_pressure IS NULL OR systolic_pressure > diastolic_pressure",
            name="ck_vital_signs_pressure_order",
        ),
        sa.ForeignKeyConstraint(["clinical_history_id"], ["clinical_histories.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("clinical_history_id", name="uq_vital_signs_clinical_history_id"),
    )
    op.create_index("ix_vital_signs_clinical_history_id", "vital_signs", ["clinical_history_id"])


def downgrade() -> None:
    op.drop_index("ix_vital_signs_clinical_history_id", table_name="vital_signs")
    op.drop_table("vital_signs")
