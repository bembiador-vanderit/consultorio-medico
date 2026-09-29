"""add secretary appointment scopes

Revision ID: 0020_secretary_doctor_scopes
Revises: 0019_vital_signs
"""

from alembic import op
import sqlalchemy as sa


revision = "0020_secretary_doctor_scopes"
down_revision = "0019_vital_signs"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "secretary_center_scopes",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("secretary_id", sa.Integer(), nullable=False),
        sa.Column("center_id", sa.Integer(), nullable=False),
        sa.Column("manage_all_doctors", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.ForeignKeyConstraint(["secretary_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["center_id"], ["care_centers.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("secretary_id", "center_id", name="uq_secretary_center_scope"),
    )
    op.create_index("ix_secretary_center_scopes_secretary_id", "secretary_center_scopes", ["secretary_id"])
    op.create_index("ix_secretary_center_scopes_center_id", "secretary_center_scopes", ["center_id"])
    op.create_table(
        "secretary_scope_doctors",
        sa.Column("scope_id", sa.Integer(), nullable=False),
        sa.Column("doctor_id", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(["scope_id"], ["secretary_center_scopes.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["doctor_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("scope_id", "doctor_id"),
    )

    # Preserve the previous behavior: every existing secretary assignment starts
    # with access to all doctors in that already assigned center.
    op.execute(
        sa.text(
            """
            INSERT INTO secretary_center_scopes (secretary_id, center_id, manage_all_doctors)
            SELECT DISTINCT uc.user_id, uc.center_id, true
            FROM user_centers AS uc
            JOIN user_roles AS ur ON ur.user_id = uc.user_id
            JOIN roles AS r ON r.id = ur.role_id
            WHERE r.code = 'secretary'
            """
        )
    )


def downgrade() -> None:
    op.drop_table("secretary_scope_doctors")
    op.drop_index("ix_secretary_center_scopes_center_id", table_name="secretary_center_scopes")
    op.drop_index("ix_secretary_center_scopes_secretary_id", table_name="secretary_center_scopes")
    op.drop_table("secretary_center_scopes")
