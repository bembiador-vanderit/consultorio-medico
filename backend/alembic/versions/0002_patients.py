"""create patients"""
from alembic import op
import sqlalchemy as sa
revision = "0002_patients"
down_revision = "0001_identity"
branch_labels = None
depends_on = None
def upgrade():
    op.create_table("patients", sa.Column("id", sa.Integer(), primary_key=True), sa.Column("first_name", sa.String(100), nullable=False), sa.Column("last_name", sa.String(100), nullable=False), sa.Column("date_of_birth", sa.Date(), nullable=False), sa.Column("phone", sa.String(30)), sa.Column("email", sa.String(254)), sa.Column("created_at", sa.DateTime(), nullable=False))
    op.create_index("ix_patients_first_name", "patients", ["first_name"]); op.create_index("ix_patients_last_name", "patients", ["last_name"])
def downgrade():
    op.drop_index("ix_patients_last_name", table_name="patients"); op.drop_index("ix_patients_first_name", table_name="patients"); op.drop_table("patients")
