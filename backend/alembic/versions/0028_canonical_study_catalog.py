"""separate canonical study catalog from specialty recommendations

Revision ID: 0028_canonical_study_catalog
Revises: 0027_expand_laboratory_catalog
"""

from alembic import op
import sqlalchemy as sa


revision = "0028_canonical_study_catalog"
down_revision = "0027_expand_laboratory_catalog"
branch_labels = None
depends_on = None


# These are the technical cross-specialty copies introduced by 0026. The
# migration matches their seed_key plus the known 0014 cardiology seed rows;
# it does not collapse arbitrary user rows merely because names coincide.
SEEDED_MASTER_STUDIES = (
    ("0026:1", "Radiografía"),
    ("0026:2", "Ecografía"),
    ("0026:3", "Ecocardiograma"),
    ("0026:4", "Electrocardiograma"),
    ("0026:5", "Holter 24 horas"),
    ("0026:6", "MAPA 24 horas"),
    ("0026:7", "Tomografía"),
    ("0026:8", "Resonancia magnética"),
    ("0026:9", "Doppler"),
    ("0026:10", "Prueba de esfuerzo"),
    ("0026:11", "Otro estudio/procedimiento"),
)


def upgrade() -> None:
    op.add_column(
        "medical_studies",
        sa.Column("canonical_key", sa.String(length=140), nullable=True),
    )
    op.add_column(
        "medical_studies",
        sa.Column("is_catalog_entry", sa.Boolean(), nullable=False, server_default=sa.true()),
    )
    op.create_index(
        "ix_medical_studies_canonical_key",
        "medical_studies",
        ["canonical_key"],
        unique=True,
    )
    op.create_index(
        "ix_medical_studies_is_catalog_entry",
        "medical_studies",
        ["is_catalog_entry"],
    )
    op.create_table(
        "medical_study_specialties",
        sa.Column(
            "medical_study_id",
            sa.Integer(),
            sa.ForeignKey("medical_studies.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column(
            "specialty_id",
            sa.Integer(),
            sa.ForeignKey("specialties.id", ondelete="RESTRICT"),
            primary_key=True,
        ),
    )
    op.create_index(
        "ix_medical_study_specialties_specialty_id",
        "medical_study_specialties",
        ["specialty_id"],
    )

    connection = op.get_bind()
    technical_identity = (
        "(seed_key = :seed_key OR ("
        "seed_key IS NULL AND anatomical_region_id IS NOT NULL "
        "AND specialty_id = (SELECT id FROM specialties WHERE name = 'Cardiología' LIMIT 1) "
        "AND lower(btrim(name)) = lower(btrim(:name))))"
    )
    for canonical_key, name in SEEDED_MASTER_STUDIES:
        row_ids = list(connection.scalars(sa.text(
            f"SELECT id FROM medical_studies WHERE {technical_identity} ORDER BY id"
        ).bindparams(seed_key=canonical_key, name=name)))
        if not row_ids:
            continue
        canonical_id = row_ids[0]
        connection.execute(sa.text(
            "INSERT INTO medical_study_specialties (medical_study_id, specialty_id) "
            "SELECT DISTINCT :canonical_id, specialty_id FROM medical_studies "
            f"WHERE {technical_identity} "
            "ON CONFLICT DO NOTHING"
        ).bindparams(canonical_id=canonical_id, seed_key=canonical_key, name=name))
        connection.execute(sa.text(
            "UPDATE medical_studies SET is_catalog_entry = false "
            f"WHERE {technical_identity}"
        ).bindparams(seed_key=canonical_key, name=name))
        connection.execute(sa.text(
            "UPDATE medical_studies SET is_catalog_entry = true, canonical_key = :canonical_key "
            "WHERE id = :canonical_id"
        ).bindparams(canonical_key=f"catalog:{canonical_key}", canonical_id=canonical_id))

    remaining = connection.execute(sa.text(
        "SELECT id, specialty_id FROM medical_studies "
        "WHERE is_catalog_entry = true AND canonical_key IS NULL ORDER BY id"
    )).all()
    for study_id, specialty_id in remaining:
        connection.execute(sa.text(
            "UPDATE medical_studies SET canonical_key = :canonical_key WHERE id = :study_id"
        ).bindparams(canonical_key=f"catalog:legacy:{study_id}", study_id=study_id))
        connection.execute(sa.text(
            "INSERT INTO medical_study_specialties (medical_study_id, specialty_id) "
            "VALUES (:study_id, :specialty_id) ON CONFLICT DO NOTHING"
        ).bindparams(study_id=study_id, specialty_id=specialty_id))


def downgrade() -> None:
    op.drop_index(
        "ix_medical_study_specialties_specialty_id",
        table_name="medical_study_specialties",
    )
    op.drop_table("medical_study_specialties")
    op.drop_index("ix_medical_studies_is_catalog_entry", table_name="medical_studies")
    op.drop_index("ix_medical_studies_canonical_key", table_name="medical_studies")
    op.drop_column("medical_studies", "is_catalog_entry")
    op.drop_column("medical_studies", "canonical_key")
