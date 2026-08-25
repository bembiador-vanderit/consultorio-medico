"""Link appointments to care centers and add doctor availability.

Revision ID: 0007_appointments_centers_availability
Revises: 0006_care_centers
"""

from alembic import op
import sqlalchemy as sa

revision = "0007_appointments_centers_availability"
down_revision = "0006_care_centers"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("appointments", sa.Column("center_id", sa.Integer(), nullable=True))
    op.create_index("ix_appointments_center_id", "appointments", ["center_id"], unique=False)
    op.create_foreign_key(
        "fk_appointments_center_id",
        "appointments",
        "care_centers",
        ["center_id"],
        ["id"],
        ondelete="RESTRICT",
    )

    op.create_table(
        "doctor_availability",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("doctor_id", sa.Integer(), nullable=False),
        sa.Column("center_id", sa.Integer(), nullable=True),
        sa.Column("availability_date", sa.Date(), nullable=False),
        sa.Column("is_available", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["center_id"], ["care_centers.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["doctor_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("doctor_id", "center_id", "availability_date", name="uq_doctor_availability_date"),
    )
    op.create_index("ix_doctor_availability_doctor_id", "doctor_availability", ["doctor_id"], unique=False)
    op.create_index("ix_doctor_availability_center_id", "doctor_availability", ["center_id"], unique=False)
    op.create_index("ix_doctor_availability_date", "doctor_availability", ["availability_date"], unique=False)


def downgrade():
    op.drop_index("ix_doctor_availability_date", table_name="doctor_availability")
    op.drop_index("ix_doctor_availability_center_id", table_name="doctor_availability")
    op.drop_index("ix_doctor_availability_doctor_id", table_name="doctor_availability")
    op.drop_table("doctor_availability")
    op.drop_constraint("fk_appointments_center_id", "appointments", type_="foreignkey")
    op.drop_index("ix_appointments_center_id", table_name="appointments")
    op.drop_column("appointments", "center_id")
