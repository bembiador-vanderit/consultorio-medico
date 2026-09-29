"""enforce clinical history concurrency invariants

Revision ID: 0029_clinical_concurrency
Revises: 0028_canonical_study_catalog
"""

from alembic import op
import sqlalchemy as sa


revision = "0029_clinical_concurrency"
down_revision = "0028_canonical_study_catalog"
branch_labels = None
depends_on = None


def upgrade() -> None:
    connection = op.get_bind()
    duplicates = connection.execute(sa.text(
        "SELECT appointment_id, COUNT(*) AS history_count "
        "FROM clinical_histories "
        "WHERE appointment_id IS NOT NULL "
        "GROUP BY appointment_id "
        "HAVING COUNT(*) > 1 "
        "ORDER BY appointment_id "
        "LIMIT 20"
    )).all()
    if duplicates:
        summary = ", ".join(
            f"appointment_id={appointment_id} ({history_count} histories)"
            for appointment_id, history_count in duplicates
        )
        raise RuntimeError(
            "Cannot enforce one clinical history per appointment: duplicate linked histories "
            f"require manual reconciliation before retrying the migration. {summary}"
        )

    op.add_column(
        "clinical_histories",
        sa.Column("revision", sa.Integer(), nullable=False, server_default=sa.text("1")),
    )
    op.create_unique_constraint(
        "uq_clinical_histories_appointment_id",
        "clinical_histories",
        ["appointment_id"],
    )


def downgrade() -> None:
    op.drop_constraint(
        "uq_clinical_histories_appointment_id",
        "clinical_histories",
        type_="unique",
    )
    op.drop_column("clinical_histories", "revision")
