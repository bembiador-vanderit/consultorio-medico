"""formalize clinical specialties context

Revision ID: 0024_clinical_specialties
Revises: 0023_notification_dedup
"""
from alembic import op
import sqlalchemy as sa


revision = "0024_clinical_specialties"
down_revision = "0023_notification_dedup"
branch_labels = None
depends_on = None

HISTORICAL_SPECIALTY = "No especificada (registro histórico)"
INITIAL_SPECIALTIES = (
    "Cardiología",
    "Pediatría",
    "Cardiología pediátrica",
    "Medicina interna",
    "Medicina general",
)


def upgrade() -> None:
    for name in INITIAL_SPECIALTIES:
        op.execute(sa.text(
            "INSERT INTO specialties (name, is_active, created_at) "
            "SELECT :name, true, CURRENT_TIMESTAMP "
            "WHERE NOT EXISTS (SELECT 1 FROM specialties WHERE name = :name)"
        ).bindparams(name=name))
    op.execute(sa.text(
        "INSERT INTO specialties (name, is_active, created_at) "
        "SELECT :name, false, CURRENT_TIMESTAMP "
        "WHERE NOT EXISTS (SELECT 1 FROM specialties WHERE name = :name)"
    ).bindparams(name=HISTORICAL_SPECIALTY))

    op.create_table(
        "doctor_specialties",
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("specialty_id", sa.Integer(), sa.ForeignKey("specialties.id", ondelete="RESTRICT"), primary_key=True),
    )
    op.create_index("ix_doctor_specialties_specialty_id", "doctor_specialties", ["specialty_id"])
    op.execute("""
        INSERT INTO doctor_specialties (user_id, specialty_id)
        SELECT user_id, specialty_id FROM doctor_profiles
    """)

    op.add_column("appointments", sa.Column("specialty_id", sa.Integer(), nullable=True))
    op.create_foreign_key("fk_appointments_specialty_id", "appointments", "specialties", ["specialty_id"], ["id"], ondelete="RESTRICT")
    op.create_index("ix_appointments_specialty_id", "appointments", ["specialty_id"])
    op.execute("""
        UPDATE appointments
        SET specialty_id = doctor_profiles.specialty_id
        FROM doctor_profiles
        WHERE appointments.doctor_id = doctor_profiles.user_id
    """)
    op.execute(sa.text("""
        UPDATE appointments
        SET specialty_id = (SELECT id FROM specialties WHERE name = :name)
        WHERE specialty_id IS NULL
    """).bindparams(name=HISTORICAL_SPECIALTY))
    op.alter_column("appointments", "specialty_id", nullable=False)

    op.add_column("clinical_histories", sa.Column("specialty_id", sa.Integer(), nullable=True))
    op.create_foreign_key("fk_clinical_histories_specialty_id", "clinical_histories", "specialties", ["specialty_id"], ["id"], ondelete="RESTRICT")
    op.create_index("ix_clinical_histories_specialty_id", "clinical_histories", ["specialty_id"])
    op.execute("""
        UPDATE clinical_histories
        SET specialty_id = appointments.specialty_id
        FROM appointments
        WHERE clinical_histories.appointment_id = appointments.id
    """)
    op.execute("""
        UPDATE clinical_histories
        SET specialty_id = doctor_profiles.specialty_id
        FROM doctor_profiles
        WHERE clinical_histories.specialty_id IS NULL
          AND clinical_histories.doctor_id = doctor_profiles.user_id
    """)
    op.execute(sa.text("""
        UPDATE clinical_histories
        SET specialty_id = (SELECT id FROM specialties WHERE name = :name)
        WHERE specialty_id IS NULL
    """).bindparams(name=HISTORICAL_SPECIALTY))
    op.alter_column("clinical_histories", "specialty_id", nullable=False)


def downgrade() -> None:
    op.drop_index("ix_clinical_histories_specialty_id", table_name="clinical_histories")
    op.drop_constraint("fk_clinical_histories_specialty_id", "clinical_histories", type_="foreignkey")
    op.drop_column("clinical_histories", "specialty_id")
    op.drop_index("ix_appointments_specialty_id", table_name="appointments")
    op.drop_constraint("fk_appointments_specialty_id", "appointments", type_="foreignkey")
    op.drop_column("appointments", "specialty_id")
    op.drop_index("ix_doctor_specialties_specialty_id", table_name="doctor_specialties")
    op.drop_table("doctor_specialties")
    op.execute(sa.text("""
        DELETE FROM specialties
        WHERE name IN (:pediatrics, :pediatric_cardiology, :internal_medicine, :general_medicine, :historical)
          AND id NOT IN (SELECT specialty_id FROM doctor_profiles)
          AND id NOT IN (SELECT specialty_id FROM anatomical_regions)
          AND id NOT IN (SELECT specialty_id FROM medical_studies)
    """).bindparams(
        pediatrics="Pediatría",
        pediatric_cardiology="Cardiología pediátrica",
        internal_medicine="Medicina interna",
        general_medicine="Medicina general",
        historical=HISTORICAL_SPECIALTY,
    ))
