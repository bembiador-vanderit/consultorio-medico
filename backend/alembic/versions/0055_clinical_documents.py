"""Independent preoperative evaluations and physical examinations."""
from alembic import op
import sqlalchemy as sa


revision = "0055_clinical_documents"
down_revision = "0054_agenda_multimode"
branch_labels = depends_on = None

PERMISSIONS = (
    "clinical_documents:create", "clinical_documents:view", "clinical_documents:prepare",
    "clinical_documents:edit_clinical", "clinical_documents:sign",
)


def _create_document_table(table: str, prefix: str) -> None:
    op.create_table(
        table,
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("organization_id", sa.Integer(), sa.ForeignKey("organizations.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("patient_id", sa.Integer(), sa.ForeignKey("patients.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("doctor_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("center_id", sa.Integer(), sa.ForeignKey("care_centers.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("appointment_id", sa.Integer(), sa.ForeignKey("appointments.id", ondelete="SET NULL"), nullable=True),
        sa.Column("clinical_history_id", sa.Integer(), sa.ForeignKey("clinical_histories.id", ondelete="SET NULL"), nullable=True),
        sa.Column("document_date", sa.Date(), nullable=False),
        sa.Column("status", sa.String(24), nullable=False, server_default="draft"),
        sa.Column("content", sa.JSON(), nullable=False),
        sa.Column("identity_snapshot", sa.JSON(), nullable=True),
        sa.Column("revision", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_by_user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("last_updated_by_user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("signed_by_user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.current_timestamp()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.current_timestamp()),
        sa.Column("signed_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint("status IN ('draft', 'pending_evaluation', 'completed', 'signed')", name=f"ck_{prefix}_status"),
        sa.CheckConstraint("revision >= 0", name=f"ck_{prefix}_revision"),
    )
    for field in ("organization_id", "patient_id", "doctor_id", "center_id", "appointment_id", "clinical_history_id", "document_date"):
        op.create_index(f"ix_{table}_{field}", table, [field])
    op.create_index(f"uq_{prefix}_open_context", table,
                    ["organization_id", "patient_id", "doctor_id", "center_id", "document_date"], unique=True,
                    postgresql_where=sa.text("status IN ('draft', 'pending_evaluation')"),
                    sqlite_where=sa.text("status IN ('draft', 'pending_evaluation')"))


def upgrade() -> None:
    _create_document_table("preoperative_evaluations", "preoperative")
    _create_document_table("physical_examinations", "physical_exam")
    for code in PERMISSIONS:
        op.execute(sa.text("INSERT INTO permissions (code, description) VALUES (:code, :code) ON CONFLICT (code) DO NOTHING").bindparams(code=code))
    op.execute("""INSERT INTO role_permissions (role_id, permission_id)
        SELECT r.id, p.id FROM roles r CROSS JOIN permissions p
        WHERE (r.code IN ('admin', 'secretary', 'doctor') AND p.code IN
            ('clinical_documents:create', 'clinical_documents:view', 'clinical_documents:prepare'))
           OR (r.code = 'doctor' AND p.code IN
            ('clinical_documents:edit_clinical', 'clinical_documents:sign'))
        ON CONFLICT DO NOTHING""")


def downgrade() -> None:
    bind = op.get_bind()
    for table in ("preoperative_evaluations", "physical_examinations"):
        if bind.scalar(sa.text(f"SELECT count(*) FROM {table}")):
            raise RuntimeError("Clinical documents exist; downgrade would destroy them")
    op.execute(sa.text("DELETE FROM role_permissions WHERE permission_id IN (SELECT id FROM permissions WHERE code IN :codes)").bindparams(sa.bindparam("codes", expanding=True, value=PERMISSIONS)))
    op.execute(sa.text("DELETE FROM permissions WHERE code IN :codes").bindparams(sa.bindparam("codes", expanding=True, value=PERMISSIONS)))
    op.drop_table("physical_examinations")
    op.drop_table("preoperative_evaluations")
