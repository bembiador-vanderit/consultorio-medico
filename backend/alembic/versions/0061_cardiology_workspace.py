"""Cardiology episode findings and structured extensions of existing FollowUp."""
from alembic import op
import sqlalchemy as sa

revision = "0061_cardiology_workspace"
down_revision = "0060_clinical_sharing"
branch_labels = depends_on = None

def org():
    return sa.Column("organization_id",sa.Integer(),sa.ForeignKey("organizations.id",ondelete="RESTRICT"),nullable=False)

def upgrade():
    op.create_table("cardiology_assessments",sa.Column("id",sa.Integer(),primary_key=True),org(),
        sa.Column("clinical_history_id",sa.Integer(),sa.ForeignKey("clinical_histories.id",ondelete="RESTRICT"),nullable=False),
        *[sa.Column(k,sa.JSON(),nullable=False) for k in ("symptoms","cardiovascular_history","examination","studies","follow_up")],
        sa.Column("impression",sa.Text()),sa.Column("plan",sa.Text()),sa.Column("revision",sa.Integer(),nullable=False),
        sa.Column("updated_by_user_id",sa.Integer(),sa.ForeignKey("users.id",ondelete="RESTRICT"),nullable=False),
        sa.Column("created_at",sa.DateTime(),nullable=False),sa.Column("updated_at",sa.DateTime(),nullable=False),
        sa.UniqueConstraint("clinical_history_id",name="uq_cardiology_history"),sa.CheckConstraint("revision >= 1",name="ck_cardiology_revision"))
    op.alter_column("follow_ups","due_at",existing_type=sa.DateTime(),nullable=True)
    op.create_table("clinical_follow_up_plans",sa.Column("id",sa.Integer(),primary_key=True),org(),
        sa.Column("follow_up_id",sa.Integer(),sa.ForeignKey("follow_ups.id",ondelete="RESTRICT"),nullable=False),
        sa.Column("clinical_history_id",sa.Integer(),sa.ForeignKey("clinical_histories.id",ondelete="RESTRICT"),nullable=False),
        sa.Column("kind",sa.String(12),nullable=False),sa.Column("timeframe_value",sa.Integer()),sa.Column("condition",sa.Text()),
        sa.Column("scheduled_appointment_id",sa.Integer(),sa.ForeignKey("appointments.id",ondelete="RESTRICT")),
        sa.Column("created_by_user_id",sa.Integer(),sa.ForeignKey("users.id",ondelete="RESTRICT"),nullable=False),
        sa.Column("revision",sa.Integer(),nullable=False),sa.Column("created_at",sa.DateTime(),nullable=False),
        sa.UniqueConstraint("follow_up_id",name="uq_clinical_plan_task"),sa.UniqueConstraint("clinical_history_id",name="uq_clinical_plan_history"),
        sa.CheckConstraint("kind IN ('days','weeks','months','studies','date')",name="ck_clinical_plan_kind"),
        sa.CheckConstraint("timeframe_value IS NULL OR timeframe_value BETWEEN 1 AND 365",name="ck_clinical_plan_timeframe"))
    op.create_table("follow_up_contact_attempts",sa.Column("id",sa.Integer(),primary_key=True),org(),
        sa.Column("follow_up_id",sa.Integer(),sa.ForeignKey("follow_ups.id",ondelete="RESTRICT"),nullable=False),
        sa.Column("recorded_by_user_id",sa.Integer(),sa.ForeignKey("users.id",ondelete="RESTRICT"),nullable=False),
        sa.Column("result",sa.String(24),nullable=False),sa.Column("note",sa.Text()),sa.Column("created_at",sa.DateTime(),nullable=False),
        sa.CheckConstraint("result IN ('contacted','no_answer','retry','studies_ready','studies_pending','declined','scheduled')",name="ck_follow_up_contact_result"))
    for table,keys in (("cardiology_assessments",["organization_id","clinical_history_id"]),
        ("clinical_follow_up_plans",["organization_id","follow_up_id","clinical_history_id","scheduled_appointment_id"]),
        ("follow_up_contact_attempts",["organization_id","follow_up_id"])):
        for key in keys: op.create_index(f"ix_{table}_{key}",table,[key])

def downgrade():
    for table in ("follow_up_contact_attempts","clinical_follow_up_plans","cardiology_assessments"):
        if op.get_bind().scalar(sa.text(f"SELECT count(*) FROM {table}")):
            raise RuntimeError("Preserve clinical workspace records before downgrade")
    if op.get_bind().scalar(sa.text("SELECT count(*) FROM follow_ups WHERE due_at IS NULL")):
        raise RuntimeError("Undated follow-ups cannot be downgraded without explicit reconciliation")
    for table in ("follow_up_contact_attempts","clinical_follow_up_plans","cardiology_assessments"): op.drop_table(table)
    op.alter_column("follow_ups","due_at",existing_type=sa.DateTime(),nullable=False)
