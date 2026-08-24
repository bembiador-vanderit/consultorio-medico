"""add insurance companies and patient insurance records"""

from alembic import op
import sqlalchemy as sa

revision = "0003_insurance"
down_revision = "0002_patients"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "insurance_companies",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(150), nullable=False),
        sa.Column("code", sa.String(50), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )
    op.create_index(
        "ix_insurance_companies_name",
        "insurance_companies",
        ["name"],
        unique=True,
    )
    op.create_index(
        "ix_insurance_companies_code",
        "insurance_companies",
        ["code"],
        unique=True,
    )

    op.create_table(
        "patient_insurances",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("patient_id", sa.Integer(), nullable=False),
        sa.Column("insurance_company_id", sa.Integer(), nullable=False),
        sa.Column("member_number", sa.String(100), nullable=False),
        sa.Column("plan_name", sa.String(150), nullable=True),
        sa.Column("is_primary", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["patient_id"], ["patients.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["insurance_company_id"],
            ["insurance_companies.id"],
            ondelete="RESTRICT",
        ),
    )
    op.create_index("ix_patient_insurances_patient_id", "patient_insurances", ["patient_id"])
    op.create_index(
        "ix_patient_insurances_insurance_company_id",
        "patient_insurances",
        ["insurance_company_id"],
    )


def downgrade():
    op.drop_index(
        "ix_patient_insurances_insurance_company_id",
        table_name="patient_insurances",
    )
    op.drop_index("ix_patient_insurances_patient_id", table_name="patient_insurances")
    op.drop_table("patient_insurances")
    op.drop_index("ix_insurance_companies_code", table_name="insurance_companies")
    op.drop_index("ix_insurance_companies_name", table_name="insurance_companies")
    op.drop_table("insurance_companies")
