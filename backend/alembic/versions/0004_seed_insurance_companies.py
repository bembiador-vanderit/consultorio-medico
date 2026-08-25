"""Seed the initial Dominican Republic ARS catalog.

The catalog is intended to provide the initial selectable ARS list for the
patient insurance workflow. The migration is idempotent and does not create
duplicates when a company already exists.
"""

from alembic import op
import sqlalchemy as sa

revision = "0004_seed_insurance_companies"
down_revision = "0003_insurance"
branch_labels = None
depends_on = None


ARS_COMPANIES = [
    ("Seguro Nacional de Salud (SeNaSa)", "SENASA"),
    ("ARS Humano", "HUMANO"),
    ("ARS Universal", "UNIVERSAL"),
    ("ARS Reservas", "RESERVAS"),
    ("ARS Futuro", "FUTURO"),
    ("ARS Primera", "PRIMERA"),
    ("MAPFRE Salud ARS", "MAPFRE"),
    ("ARS Renacer", "RENACER"),
    ("ARS APS", "APS"),
    ("ARS GMA", "GMA"),
    ("ARS SEMMA", "SEMMA"),
    ("ARS CMD", "CMD"),
    ("Grupo Yunen", "YUNEN"),
    ("ARS SIMAG", "SIMAG"),
    ("ARS Meta Salud", "META_SALUD"),
    ("ARS Monumental", "MONUMENTAL"),
    ("ARS Plan Salud Banco Central", "PLAN_SALUD_BCRD"),
]


def upgrade():
    bind = op.get_bind()
    table = sa.table(
        "insurance_companies",
        sa.column("name", sa.String(150)),
        sa.column("code", sa.String(50)),
        sa.column("is_active", sa.Boolean()),
        sa.column("created_at", sa.DateTime()),
    )

    for name, code in ARS_COMPANIES:
        exists = bind.execute(
            sa.text("SELECT 1 FROM insurance_companies WHERE name = :name LIMIT 1"),
            {"name": name},
        ).first()
        if exists:
            continue

        bind.execute(
            table.insert().values(
                name=name,
                code=code,
                is_active=True,
                created_at=sa.func.now(),
            )
        )


def downgrade():
    bind = op.get_bind()
    for name, _ in ARS_COMPANIES:
        bind.execute(
            sa.text("DELETE FROM insurance_companies WHERE name = :name"),
            {"name": name},
        )
