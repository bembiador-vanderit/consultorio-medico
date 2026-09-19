"""add clinical lifecycle and audit log

Revision ID: 0021_clinical_lifecycle
Revises: 0020_secretary_doctor_scopes
"""

from alembic import op
import sqlalchemy as sa


revision = "0021_clinical_lifecycle"
down_revision = "0020_secretary_doctor_scopes"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "clinical_histories",
        sa.Column("status", sa.String(length=20), nullable=False, server_default="in_progress"),
    )
    op.add_column("clinical_histories", sa.Column("completed_at", sa.DateTime(), nullable=True))
    op.add_column("clinical_histories", sa.Column("completed_by_id", sa.Integer(), nullable=True))
    op.create_check_constraint(
        "ck_clinical_histories_status",
        "clinical_histories",
        "status IN ('in_progress', 'completed')",
    )
    op.create_foreign_key(
        "fk_clinical_histories_completed_by_id",
        "clinical_histories",
        "users",
        ["completed_by_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index("ix_clinical_histories_status", "clinical_histories", ["status"])
    op.create_index("ix_clinical_histories_completed_by_id", "clinical_histories", ["completed_by_id"])

    # Preserve the semantic state of consultations whose appointments were already
    # completed before lifecycle tracking existed. The responsible user is unknown,
    # so completed_by_id intentionally remains NULL for these legacy records.
    op.execute(
        """
        UPDATE clinical_histories
        SET status = 'completed', completed_at = updated_at
        WHERE appointment_id IN (
            SELECT id FROM appointments WHERE status = 'completed'
        )
        """
    )

    op.create_table(
        "clinical_audit_logs",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=True),
        sa.Column("action", sa.String(length=80), nullable=False),
        sa.Column("resource_type", sa.String(length=50), nullable=False),
        sa.Column("resource_id", sa.Integer(), nullable=True),
        sa.Column("clinical_history_id", sa.Integer(), nullable=True),
        sa.Column("outcome", sa.String(length=20), nullable=False),
        sa.Column("context", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["clinical_history_id"], ["clinical_histories.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_clinical_audit_logs_user_id", "clinical_audit_logs", ["user_id"])
    op.create_index("ix_clinical_audit_logs_action", "clinical_audit_logs", ["action"])
    op.create_index("ix_clinical_audit_logs_clinical_history_id", "clinical_audit_logs", ["clinical_history_id"])
    op.create_index("ix_clinical_audit_logs_outcome", "clinical_audit_logs", ["outcome"])
    op.create_index("ix_clinical_audit_logs_created_at", "clinical_audit_logs", ["created_at"])


def downgrade() -> None:
    op.drop_index("ix_clinical_audit_logs_created_at", table_name="clinical_audit_logs")
    op.drop_index("ix_clinical_audit_logs_outcome", table_name="clinical_audit_logs")
    op.drop_index("ix_clinical_audit_logs_clinical_history_id", table_name="clinical_audit_logs")
    op.drop_index("ix_clinical_audit_logs_action", table_name="clinical_audit_logs")
    op.drop_index("ix_clinical_audit_logs_user_id", table_name="clinical_audit_logs")
    op.drop_table("clinical_audit_logs")
    op.drop_index("ix_clinical_histories_completed_by_id", table_name="clinical_histories")
    op.drop_index("ix_clinical_histories_status", table_name="clinical_histories")
    op.drop_constraint("fk_clinical_histories_completed_by_id", "clinical_histories", type_="foreignkey")
    op.drop_constraint("ck_clinical_histories_status", "clinical_histories", type_="check")
    op.drop_column("clinical_histories", "completed_by_id")
    op.drop_column("clinical_histories", "completed_at")
    op.drop_column("clinical_histories", "status")
