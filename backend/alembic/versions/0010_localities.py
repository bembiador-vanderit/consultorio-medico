"""Add first-class localities and link care centers to them.

Revision ID: 0010_localities
Revises: 0009_appt_centers_availability
"""
from alembic import op
import sqlalchemy as sa

revision = "0010_localities"
down_revision = "0009_appt_centers_availability"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "localities",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("name", name="uq_localities_name"),
    )
    op.create_index("ix_localities_name", "localities", ["name"], unique=False)
    op.create_index("ix_localities_is_active", "localities", ["is_active"], unique=False)

    op.add_column("care_centers", sa.Column("locality_id", sa.Integer(), nullable=True))

    op.execute(sa.text(
        "INSERT INTO localities (name, is_active, created_at) "
        "SELECT DISTINCT city, TRUE, NOW() FROM care_centers "
        "WHERE city IS NOT NULL AND TRIM(city) <> ''"
    ))
    op.execute(sa.text(
        "UPDATE care_centers c SET locality_id = l.id "
        "FROM localities l WHERE l.name = c.city"
    ))

    op.create_index("ix_care_centers_locality_id", "care_centers", ["locality_id"], unique=False)
    op.create_foreign_key(
        "fk_care_centers_locality_id",
        "care_centers",
        "localities",
        ["locality_id"],
        ["id"],
        ondelete="RESTRICT",
    )


def downgrade():
    op.drop_constraint("fk_care_centers_locality_id", "care_centers", type_="foreignkey")
    op.drop_index("ix_care_centers_locality_id", table_name="care_centers")
    op.drop_column("care_centers", "locality_id")
    op.drop_index("ix_localities_is_active", table_name="localities")
    op.drop_index("ix_localities_name", table_name="localities")
    op.drop_table("localities")
