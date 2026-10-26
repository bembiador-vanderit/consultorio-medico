"""add configurable clinical catalog

Revision ID: 0014_clinical_catalog
Revises: 0013_notification_appointments
"""
from alembic import op
import sqlalchemy as sa

revision = "0014_clinical_catalog"
down_revision = "0013_notification_appointments"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "specialties",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(length=120), nullable=False, unique=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_specialties_name", "specialties", ["name"])
    op.create_index("ix_specialties_is_active", "specialties", ["is_active"])

    op.create_table(
        "anatomical_regions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("specialty_id", sa.Integer(), sa.ForeignKey("specialties.id", ondelete="CASCADE"), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
    )
    op.create_index("ix_anatomical_regions_specialty_id", "anatomical_regions", ["specialty_id"])
    op.create_index("ix_anatomical_regions_is_active", "anatomical_regions", ["is_active"])

    op.create_table(
        "medical_studies",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("specialty_id", sa.Integer(), sa.ForeignKey("specialties.id", ondelete="CASCADE"), nullable=False),
        sa.Column("anatomical_region_id", sa.Integer(), sa.ForeignKey("anatomical_regions.id", ondelete="SET NULL"), nullable=True),
        sa.Column("name", sa.String(length=180), nullable=False),
        sa.Column("category", sa.String(length=50), nullable=False, server_default="study"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
    )
    op.create_index("ix_medical_studies_specialty_id", "medical_studies", ["specialty_id"])
    op.create_index("ix_medical_studies_anatomical_region_id", "medical_studies", ["anatomical_region_id"])
    op.create_index("ix_medical_studies_is_active", "medical_studies", ["is_active"])

    op.create_table(
        "doctor_profiles",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, unique=True),
        sa.Column("specialty_id", sa.Integer(), sa.ForeignKey("specialties.id", ondelete="RESTRICT"), nullable=False),
    )
    op.create_index("ix_doctor_profiles_user_id", "doctor_profiles", ["user_id"])
    op.create_index("ix_doctor_profiles_specialty_id", "doctor_profiles", ["specialty_id"])

    op.execute(sa.text("INSERT INTO specialties (name, is_active, created_at) VALUES ('Cardiología', true, CURRENT_TIMESTAMP)"))
    op.execute(sa.text("INSERT INTO anatomical_regions (specialty_id, name, is_active) SELECT id, 'Corazón', true FROM specialties WHERE name = 'Cardiología'"))
    op.execute(sa.text("INSERT INTO medical_studies (specialty_id, anatomical_region_id, name, category, is_active) SELECT s.id, r.id, v.name, v.category, true FROM specialties s JOIN anatomical_regions r ON r.specialty_id = s.id CROSS JOIN (VALUES ('Electrocardiograma','test'), ('Ecocardiograma','imaging'), ('Holter 24 horas','monitoring'), ('Prueba de esfuerzo','functional'), ('Resonancia cardíaca','imaging')) AS v(name, category) WHERE s.name = 'Cardiología' AND r.name = 'Corazón'"))


def downgrade():
    op.drop_index("ix_doctor_profiles_specialty_id", table_name="doctor_profiles")
    op.drop_index("ix_doctor_profiles_user_id", table_name="doctor_profiles")
    op.drop_table("doctor_profiles")
    op.drop_index("ix_medical_studies_is_active", table_name="medical_studies")
    op.drop_index("ix_medical_studies_anatomical_region_id", table_name="medical_studies")
    op.drop_index("ix_medical_studies_specialty_id", table_name="medical_studies")
    op.drop_table("medical_studies")
    op.drop_index("ix_anatomical_regions_is_active", table_name="anatomical_regions")
    op.drop_index("ix_anatomical_regions_specialty_id", table_name="anatomical_regions")
    op.drop_table("anatomical_regions")
    op.drop_index("ix_specialties_is_active", table_name="specialties")
    op.drop_index("ix_specialties_name", table_name="specialties")
    op.drop_table("specialties")
