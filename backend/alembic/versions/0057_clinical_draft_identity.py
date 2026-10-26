"""Separate open clinical drafts by consultation or standalone daily context."""

from alembic import op
import sqlalchemy as sa


revision = "0057_clinical_draft_identity"
down_revision = "0056_clinical_forms"
branch_labels = depends_on = None

OPEN = "status IN ('draft', 'pending_evaluation')"
DOCUMENTS = (("preoperative_evaluations", "preoperative"),
             ("physical_examinations", "physical_exam"))


def _collisions(table: str, columns: str, condition: str) -> int:
    return op.get_bind().scalar(sa.text(
        f"SELECT count(*) FROM (SELECT {columns}, count(*) FROM {table} "
        f"WHERE {condition} GROUP BY {columns} HAVING count(*) > 1) collisions"
    )) or 0


def _index(name: str, table: str, columns: list[str], predicate: str) -> None:
    op.create_index(name, table, columns, unique=True,
                    postgresql_where=sa.text(predicate), sqlite_where=sa.text(predicate))


def upgrade() -> None:
    # Do not merge, reassign, or delete an existing clinical document.
    for table, _ in DOCUMENTS:
        if (_collisions(table, "organization_id, appointment_id", f"{OPEN} AND appointment_id IS NOT NULL")
                or _collisions(table, "organization_id, clinical_history_id",
                               f"{OPEN} AND appointment_id IS NULL AND clinical_history_id IS NOT NULL")
                or _collisions(table, "organization_id, patient_id, doctor_id, center_id, document_date",
                               f"{OPEN} AND appointment_id IS NULL AND clinical_history_id IS NULL")):
            raise RuntimeError(f"Open clinical-document identity collision in {table}; inspect before migrating")
    for table, prefix in DOCUMENTS:
        op.drop_index(f"uq_{prefix}_open_context", table_name=table)
        _index(f"uq_{prefix}_open_appointment", table, ["organization_id", "appointment_id"],
               f"{OPEN} AND appointment_id IS NOT NULL")
        _index(f"uq_{prefix}_open_history", table, ["organization_id", "clinical_history_id"],
               f"{OPEN} AND appointment_id IS NULL AND clinical_history_id IS NOT NULL")
        _index(f"uq_{prefix}_open_standalone", table,
               ["organization_id", "patient_id", "doctor_id", "center_id", "document_date"],
               f"{OPEN} AND appointment_id IS NULL AND clinical_history_id IS NULL")


def downgrade() -> None:
    for table, _ in DOCUMENTS:
        if _collisions(table, "organization_id, patient_id, doctor_id, center_id, document_date", OPEN):
            raise RuntimeError(f"Distinct consultation drafts exist in {table}; downgrade would conflate them")
    for table, prefix in DOCUMENTS:
        for suffix in ("appointment", "history", "standalone"):
            op.drop_index(f"uq_{prefix}_open_{suffix}", table_name=table)
        _index(f"uq_{prefix}_open_context", table,
               ["organization_id", "patient_id", "doctor_id", "center_id", "document_date"], OPEN)
