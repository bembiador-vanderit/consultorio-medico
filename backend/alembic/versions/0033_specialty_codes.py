"""Add stable technical codes to specialties.

Revision ID: 0033_specialty_codes
Revises: 0032_specialty_templates
"""

import re
import unicodedata

from alembic import op
import sqlalchemy as sa


revision = "0033_specialty_codes"
down_revision = "0032_specialty_templates"
branch_labels = None
depends_on = None

MAX_CODE_LENGTH = 80
KNOWN_CODES = {
    "cardiologia": "cardiology",
    "pediatria": "pediatrics",
    "cardiologia pediatrica": "pediatric-cardiology",
    "medicina interna": "internal-medicine",
    "medicina general": "general-medicine",
    "no especificada registro historico": "historical-unspecified",
}


def _ascii_words(value: str) -> str:
    ascii_value = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode("ascii")
    return " ".join(re.findall(r"[a-z0-9]+", ascii_value.casefold()))


def _base_code(name: str) -> str:
    normalized_name = _ascii_words(name)
    known_code = KNOWN_CODES.get(normalized_name)
    if known_code is not None:
        return known_code
    generated = normalized_name.replace(" ", "-") or "specialty"
    return generated[:MAX_CODE_LENGTH].rstrip("-") or "specialty"


def _unique_code(name: str, used: set[str]) -> str:
    base = _base_code(name)
    if base.casefold() not in used:
        return base
    suffix_number = 2
    while True:
        suffix = f"-{suffix_number}"
        prefix = base[: MAX_CODE_LENGTH - len(suffix)].rstrip("-") or "specialty"
        candidate = f"{prefix}{suffix}"
        if candidate.casefold() not in used:
            return candidate
        suffix_number += 1


def upgrade() -> None:
    op.add_column("specialties", sa.Column("code", sa.String(length=MAX_CODE_LENGTH), nullable=True))

    bind = op.get_bind()
    metadata = sa.MetaData()
    specialties = sa.Table("specialties", metadata, autoload_with=bind)
    used: set[str] = set()
    rows = bind.execute(
        sa.select(specialties.c.id, specialties.c.name).order_by(specialties.c.id)
    ).all()
    for specialty_id, name in rows:
        code = _unique_code(name, used)
        bind.execute(
            specialties.update().where(specialties.c.id == specialty_id).values(code=code)
        )
        used.add(code.casefold())

    remaining = bind.scalar(
        sa.select(sa.func.count()).select_from(specialties).where(specialties.c.code.is_(None))
    )
    if remaining:
        raise RuntimeError("No fue posible asignar código a todas las especialidades")

    with op.batch_alter_table("specialties") as batch_op:
        batch_op.alter_column(
            "code",
            existing_type=sa.String(length=MAX_CODE_LENGTH),
            nullable=False,
        )
        batch_op.create_unique_constraint("uq_specialties_code", ["code"])
        batch_op.create_index("ix_specialties_code", ["code"], unique=False)


def downgrade() -> None:
    with op.batch_alter_table("specialties") as batch_op:
        batch_op.drop_index("ix_specialties_code")
        batch_op.drop_constraint("uq_specialties_code", type_="unique")
        batch_op.drop_column("code")
