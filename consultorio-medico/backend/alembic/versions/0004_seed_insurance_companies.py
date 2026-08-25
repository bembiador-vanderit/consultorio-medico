"""Seed the initial Dominican Republic ARS catalog.

The catalog is based on ARS entities currently identified in SISALRIL's
supervised-entities information and recent SISALRIL publications.

This migration is intentionally idempotent so it can safely run on an
existing installation without duplicating companies.
"""

from alembic import op
import sqlalchemy as sa

revision = "0004_seed_insurance_companies"
down_revision = "0003_insurance"
branch_labels = None
depends_on = None


ARS_COMPANIES = [
    ("Seguro Nacional de Salud (SeNaSa)", "012-2005"),
    ("Administradora de Riesgos de Salud Universal S.A.", "001-2004"),
    ("ARS Renacer S.A.", "002-2004"),
    ("Administradora de Riesgos de Salud Primera", "005-2004"),
    ("MAPFRE Salud ARS, S.A.", "004-2004"),
    ("ARS Humano", None),
    ("ARS APS S.A.", "008-2005"),
    ("ARS Grupo Médico Asociado S.A. (GMA)", "007-2005"),
    ("ARS SEMMA", "014-2005"),
    ("ARS Colegio Médico Dominicano Inc. (CMD)", "013-2005"),
    ("Grupo Yunen S.R.L.", "016-2005"),
    ("ARS SIMAG S.A.", "015-2005"),
    ("ARS Futuro S.A.", "018-2005"),
    ("ARS Meta Salud S.A.", "028-2007"),
    ("ARS Monumental S.A.", "0025-2007"),
    ("Administradora de Riesgos de Salud Reservas", "031-2007"),
    ("ARS Plan Salud El Banco Central, Inc.", "026-2007"),
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
    names = [name for name, _ in ARS_COMPANIES]
    bind.execute(
        sa.text("DELETE FROM insurance_companies WHERE name = ANY(:names)"),
        {"names": names},
    )
