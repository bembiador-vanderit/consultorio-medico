"""add structured laboratory and study orders

Revision ID: 0026_clinical_orders
Revises: 0025_clinical_addenda
"""
from alembic import op
import sqlalchemy as sa


revision = "0026_clinical_orders"
down_revision = "0025_clinical_addenda"
branch_labels = None
depends_on = None


LABORATORY_TESTS = (
    ("Hematología", "Hemograma completo"),
    ("Hematología", "Hemoglobina"),
    ("Hematología", "Hematocrito"),
    ("Hematología", "Plaquetas"),
    ("Hematología", "VSG"),
    ("Coagulación", "TP"),
    ("Coagulación", "INR"),
    ("Coagulación", "TPT / aPTT"),
    ("Coagulación", "Dímero D"),
    ("Química sanguínea", "Glucosa"),
    ("Química sanguínea", "Urea"),
    ("Química sanguínea", "Creatinina"),
    ("Química sanguínea", "Ácido úrico"),
    ("Química sanguínea", "Sodio"),
    ("Química sanguínea", "Potasio"),
    ("Química sanguínea", "Cloro"),
    ("Química sanguínea", "Calcio"),
    ("Química sanguínea", "Magnesio"),
    ("Química sanguínea", "Fósforo"),
    ("Química sanguínea", "Proteínas totales"),
    ("Química sanguínea", "Albúmina"),
    ("Marcadores hepáticos", "Bilirrubina total"),
    ("Marcadores hepáticos", "Bilirrubina directa"),
    ("Marcadores hepáticos", "AST / TGO"),
    ("Marcadores hepáticos", "ALT / TGP"),
    ("Marcadores hepáticos", "Fosfatasa alcalina"),
    ("Marcadores hepáticos", "GGT"),
    ("Química sanguínea", "LDH"),
    ("Química sanguínea", "Colesterol total"),
    ("Química sanguínea", "HDL"),
    ("Química sanguínea", "LDL"),
    ("Química sanguínea", "VLDL"),
    ("Química sanguínea", "Triglicéridos"),
    ("Química sanguínea", "Hemoglobina glucosilada / HbA1c"),
    ("Hormonas", "TSH"),
    ("Hormonas", "T4 libre"),
    ("Hormonas", "T3"),
    ("Marcadores cardíacos", "Troponina"),
    ("Marcadores cardíacos", "CK total"),
    ("Marcadores cardíacos", "CK-MB"),
    ("Marcadores cardíacos", "BNP"),
    ("Marcadores cardíacos", "NT-proBNP"),
    ("Inmunología / Serología", "PCR"),
    ("Inmunología / Serología", "PCR ultrasensible"),
    ("Enfermedades infecciosas", "VIH 1/2"),
    ("Microbiología", "Urocultivo"),
    ("Biología molecular", "PCR molecular"),
    ("Química sanguínea", "Ferritina"),
    ("Química sanguínea", "Hierro sérico"),
    ("Química sanguínea", "Vitamina B12"),
    ("Química sanguínea", "Ácido fólico"),
    ("Química sanguínea", "Vitamina D"),
    ("Marcadores tumorales", "PSA"),
    ("Orina", "Examen general de orina"),
    ("Parasitología", "Coprológico"),
    ("Drogas terapéuticas / abuso", "Panel toxicológico"),
    ("Otros", "Prueba de embarazo"),
)

STUDY_TYPES = (
    ("radiography", "Radiografía"),
    ("ultrasound", "Ecografía"),
    ("echocardiography", "Ecocardiograma"),
    ("electrocardiography", "Electrocardiograma"),
    ("monitoring", "Holter 24 horas"),
    ("monitoring", "MAPA 24 horas"),
    ("tomography", "Tomografía"),
    ("magnetic_resonance", "Resonancia magnética"),
    ("doppler", "Doppler"),
    ("functional", "Prueba de esfuerzo"),
    ("other", "Otro estudio/procedimiento"),
)


def _context_columns() -> list[sa.Column]:
    return [
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("clinical_history_id", sa.Integer(), sa.ForeignKey("clinical_histories.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("appointment_id", sa.Integer(), sa.ForeignKey("appointments.id", ondelete="SET NULL"), nullable=True),
        sa.Column("patient_id", sa.Integer(), sa.ForeignKey("patients.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("doctor_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("center_id", sa.Integer(), sa.ForeignKey("care_centers.id", ondelete="SET NULL"), nullable=True),
        sa.Column("specialty_id", sa.Integer(), sa.ForeignKey("specialties.id", ondelete="RESTRICT"), nullable=True),
        sa.Column("patient_name", sa.String(length=250), nullable=False),
        sa.Column("doctor_name", sa.String(length=250), nullable=False),
        sa.Column("center_name", sa.String(length=250), nullable=True),
        sa.Column("specialty_name", sa.String(length=180), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="ordered"),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
    ]


def _create_context_indexes(table: str) -> None:
    for column in ("clinical_history_id", "appointment_id", "patient_id", "doctor_id", "center_id", "specialty_id", "created_at"):
        op.create_index(f"ix_{table}_{column}", table, [column])


def upgrade() -> None:
    op.add_column("medical_studies", sa.Column("seed_key", sa.String(length=100), nullable=True))
    op.create_index("ix_medical_studies_seed_key", "medical_studies", ["seed_key"])

    op.create_table(
        "laboratory_tests",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("code", sa.String(length=50), nullable=True, unique=True),
        sa.Column("name", sa.String(length=180), nullable=False, unique=True),
        sa.Column("category", sa.String(length=100), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
    )
    for column in ("code", "name", "category", "is_active"):
        op.create_index(f"ix_laboratory_tests_{column}", "laboratory_tests", [column])

    op.create_table("laboratory_orders", *_context_columns(), sa.CheckConstraint("status = 'ordered'", name="ck_laboratory_orders_status"))
    _create_context_indexes("laboratory_orders")
    op.create_table(
        "laboratory_order_items",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("laboratory_order_id", sa.Integer(), sa.ForeignKey("laboratory_orders.id", ondelete="CASCADE"), nullable=False),
        sa.Column("laboratory_test_id", sa.Integer(), sa.ForeignKey("laboratory_tests.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("test_code", sa.String(length=50), nullable=True),
        sa.Column("test_name", sa.String(length=180), nullable=False),
        sa.Column("test_category", sa.String(length=100), nullable=False),
        sa.Column("custom_note", sa.Text(), nullable=True),
        sa.UniqueConstraint("laboratory_order_id", "laboratory_test_id", name="uq_laboratory_order_test"),
    )
    op.create_index("ix_laboratory_order_items_laboratory_order_id", "laboratory_order_items", ["laboratory_order_id"])
    op.create_index("ix_laboratory_order_items_laboratory_test_id", "laboratory_order_items", ["laboratory_test_id"])

    op.create_table("study_orders", *_context_columns(), sa.CheckConstraint("status = 'ordered'", name="ck_study_orders_status"))
    _create_context_indexes("study_orders")
    op.create_table(
        "study_order_items",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("study_order_id", sa.Integer(), sa.ForeignKey("study_orders.id", ondelete="CASCADE"), nullable=False),
        sa.Column("medical_study_id", sa.Integer(), sa.ForeignKey("medical_studies.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("modality", sa.String(length=80), nullable=False),
        sa.Column("study_name", sa.String(length=180), nullable=False),
        sa.Column("region_description", sa.String(length=250), nullable=True),
        sa.Column("contrast", sa.String(length=20), nullable=False, server_default="not_applicable"),
        sa.Column("clinical_notes", sa.Text(), nullable=True),
        sa.CheckConstraint("contrast IN ('yes', 'no', 'not_applicable')", name="ck_study_order_items_contrast"),
    )
    op.create_index("ix_study_order_items_study_order_id", "study_order_items", ["study_order_id"])
    op.create_index("ix_study_order_items_medical_study_id", "study_order_items", ["medical_study_id"])

    laboratory_table = sa.table(
        "laboratory_tests",
        sa.column("name", sa.String), sa.column("category", sa.String), sa.column("sort_order", sa.Integer),
    )
    op.bulk_insert(laboratory_table, [
        {"name": name, "category": category, "sort_order": index}
        for index, (category, name) in enumerate(LABORATORY_TESTS, start=1)
    ])

    for index, (category, name) in enumerate(STUDY_TYPES, start=1):
        seed_key = f"0026:{index}"
        op.execute(sa.text(
            "INSERT INTO medical_studies (specialty_id, anatomical_region_id, name, category, is_active, seed_key) "
            "SELECT s.id, NULL, :name, :category, true, :seed_key FROM specialties s "
            "WHERE s.is_active = true AND s.name <> 'No especificada (registro histórico)' "
            "AND NOT EXISTS (SELECT 1 FROM medical_studies m WHERE m.specialty_id = s.id AND lower(m.name) = lower(:name))"
        ).bindparams(name=name, category=category, seed_key=seed_key))


def downgrade() -> None:
    op.drop_index("ix_study_order_items_medical_study_id", table_name="study_order_items")
    op.drop_index("ix_study_order_items_study_order_id", table_name="study_order_items")
    op.drop_table("study_order_items")
    for column in reversed(("clinical_history_id", "appointment_id", "patient_id", "doctor_id", "center_id", "specialty_id", "created_at")):
        op.drop_index(f"ix_study_orders_{column}", table_name="study_orders")
    op.drop_table("study_orders")
    op.drop_index("ix_laboratory_order_items_laboratory_test_id", table_name="laboratory_order_items")
    op.drop_index("ix_laboratory_order_items_laboratory_order_id", table_name="laboratory_order_items")
    op.drop_table("laboratory_order_items")
    for column in reversed(("clinical_history_id", "appointment_id", "patient_id", "doctor_id", "center_id", "specialty_id", "created_at")):
        op.drop_index(f"ix_laboratory_orders_{column}", table_name="laboratory_orders")
    op.drop_table("laboratory_orders")
    for column in reversed(("code", "name", "category", "is_active")):
        op.drop_index(f"ix_laboratory_tests_{column}", table_name="laboratory_tests")
    op.drop_table("laboratory_tests")
    op.execute(sa.text("DELETE FROM medical_studies WHERE seed_key LIKE '0026:%'"))
    op.drop_index("ix_medical_studies_seed_key", table_name="medical_studies")
    op.drop_column("medical_studies", "seed_key")
