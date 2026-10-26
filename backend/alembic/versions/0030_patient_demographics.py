"""Patient Identity & Clinical Demographics (additive, nullable)."""
from alembic import op
import sqlalchemy as sa

revision = "0030_patient_demographics"
down_revision = "0029_clinical_concurrency"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("patients") as batch:
        batch.add_column(sa.Column("document_type", sa.String(20), nullable=True))
        batch.add_column(sa.Column("document_number", sa.String(100), nullable=True))
        batch.add_column(sa.Column("home_phone", sa.String(30), nullable=True))
        batch.add_column(sa.Column("registered_sex", sa.String(20), nullable=True))
        batch.add_column(sa.Column("blood_type", sa.String(10), nullable=True))
        batch.add_column(sa.Column("address", sa.String(500), nullable=True))
        batch.add_column(sa.Column("province", sa.String(100), nullable=True))
        batch.add_column(sa.Column("nationality", sa.String(100), nullable=True))
        batch.add_column(sa.Column("occupation", sa.String(150), nullable=True))
        batch.add_column(sa.Column("emergency_contact_name", sa.String(150), nullable=True))
        batch.add_column(sa.Column("emergency_contact_relationship", sa.String(100), nullable=True))
        batch.add_column(sa.Column("emergency_contact_mobile", sa.String(30), nullable=True))
        batch.add_column(sa.Column("emergency_contact_home_phone", sa.String(30), nullable=True))
        batch.add_column(sa.Column("guardian_name", sa.String(150), nullable=True))
        batch.add_column(sa.Column("guardian_relationship", sa.String(100), nullable=True))
        batch.add_column(sa.Column("guardian_mobile", sa.String(30), nullable=True))
        batch.add_column(sa.Column("guardian_home_phone", sa.String(30), nullable=True))
        batch.add_column(sa.Column("locality_id", sa.Integer(), nullable=True))
        batch.create_foreign_key("fk_patients_locality_id", "localities", ["locality_id"], ["id"])
        batch.create_check_constraint("ck_patients_document_pair", "(document_type IS NULL AND document_number IS NULL) OR (document_type IS NOT NULL AND document_number IS NOT NULL)")
        batch.create_check_constraint("ck_patients_document_type", "document_type IN ('cedula', 'passport', 'other')")
        batch.create_check_constraint("ck_patients_blood_type", "blood_type IN ('A+', 'A-', 'B+', 'B-', 'AB+', 'AB-', 'O+', 'O-')")
        batch.create_check_constraint("ck_patients_registered_sex", "registered_sex IN ('female', 'male', 'other', 'unknown')")
        batch.create_index("uq_patients_document", ["document_type", "document_number"], unique=True)


def downgrade():
    with op.batch_alter_table("patients") as batch:
        batch.drop_index("uq_patients_document")
        batch.drop_constraint("fk_patients_locality_id", type_="foreignkey")
        for name in ("document_pair", "document_type", "blood_type", "registered_sex"):
            batch.drop_constraint(f"ck_patients_{name}", type_="check")
        batch.drop_column("document_type")
        batch.drop_column("document_number")
        batch.drop_column("home_phone")
        batch.drop_column("registered_sex")
        batch.drop_column("blood_type")
        batch.drop_column("address")
        batch.drop_column("province")
        batch.drop_column("nationality")
        batch.drop_column("occupation")
        batch.drop_column("emergency_contact_name")
        batch.drop_column("emergency_contact_relationship")
        batch.drop_column("emergency_contact_mobile")
        batch.drop_column("emergency_contact_home_phone")
        batch.drop_column("guardian_name")
        batch.drop_column("guardian_relationship")
        batch.drop_column("guardian_mobile")
        batch.drop_column("guardian_home_phone")
        batch.drop_column("locality_id")
