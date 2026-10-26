"""Versioned specialty workspace templates and historical snapshot."""

from datetime import datetime

from alembic import op
import sqlalchemy as sa


revision = "0032_specialty_templates"
down_revision = "0031_country_territory"
branch_labels = None
depends_on = None


DEFAULT_MODULE_KEYS = (
    "core.anamnesis",
    "core.vital-signs",
    "core.diagnoses",
    "core.prescriptions",
    "core.clinical-orders",
)


def upgrade():
    op.create_table(
        "specialty_templates",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("specialty_id", sa.Integer(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("published_at", sa.DateTime(), nullable=True),
        sa.CheckConstraint(
            "status IN ('draft', 'published', 'retired')",
            name="ck_specialty_templates_status",
        ),
        sa.ForeignKeyConstraint(["specialty_id"], ["specialties.id"], ondelete="RESTRICT"),
        sa.UniqueConstraint(
            "specialty_id", "version", name="uq_specialty_templates_specialty_version"
        ),
    )
    op.create_index(
        "ix_specialty_templates_specialty_id",
        "specialty_templates",
        ["specialty_id"],
    )
    op.create_index(
        "uq_specialty_templates_one_published",
        "specialty_templates",
        ["specialty_id"],
        unique=True,
        postgresql_where=sa.text("status = 'published'"),
        sqlite_where=sa.text("status = 'published'"),
    )
    op.create_table(
        "specialty_template_modules",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("template_id", sa.Integer(), nullable=False),
        sa.Column("module_key", sa.String(length=120), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.CheckConstraint(
            "position > 0", name="ck_specialty_template_modules_position_positive"
        ),
        sa.ForeignKeyConstraint(
            ["template_id"], ["specialty_templates.id"], ondelete="CASCADE"
        ),
        sa.UniqueConstraint(
            "template_id", "module_key", name="uq_specialty_template_modules_key"
        ),
        sa.UniqueConstraint(
            "template_id", "position", name="uq_specialty_template_modules_position"
        ),
    )
    op.create_index(
        "ix_specialty_template_modules_template_id",
        "specialty_template_modules",
        ["template_id"],
    )

    with op.batch_alter_table("clinical_histories") as batch_op:
        batch_op.add_column(sa.Column("specialty_template_id", sa.Integer(), nullable=True))
        batch_op.create_foreign_key(
            "fk_clinical_histories_specialty_template_id",
            "specialty_templates",
            ["specialty_template_id"],
            ["id"],
            ondelete="RESTRICT",
        )
        batch_op.create_index(
            "ix_clinical_histories_specialty_template_id", ["specialty_template_id"]
        )

    bind = op.get_bind()
    metadata = sa.MetaData()
    specialties = sa.Table("specialties", metadata, autoload_with=bind)
    templates = sa.Table("specialty_templates", metadata, autoload_with=bind)
    modules = sa.Table("specialty_template_modules", metadata, autoload_with=bind)
    histories = sa.Table("clinical_histories", metadata, autoload_with=bind)
    now = datetime.utcnow()

    for specialty_id in bind.execute(sa.select(specialties.c.id)).scalars():
        result = bind.execute(
            templates.insert().values(
                specialty_id=specialty_id,
                version=1,
                status="published",
                created_at=now,
                published_at=now,
            )
        )
        template_id = result.inserted_primary_key[0]
        bind.execute(
            modules.insert(),
            [
                {
                    "template_id": template_id,
                    "module_key": module_key,
                    "position": position,
                }
                for position, module_key in enumerate(DEFAULT_MODULE_KEYS, start=1)
            ],
        )
        bind.execute(
            histories.update()
            .where(histories.c.specialty_id == specialty_id)
            .values(specialty_template_id=template_id)
        )


def downgrade():
    with op.batch_alter_table("clinical_histories") as batch_op:
        batch_op.drop_index("ix_clinical_histories_specialty_template_id")
        batch_op.drop_constraint(
            "fk_clinical_histories_specialty_template_id", type_="foreignkey"
        )
        batch_op.drop_column("specialty_template_id")
    op.drop_index(
        "ix_specialty_template_modules_template_id",
        table_name="specialty_template_modules",
    )
    op.drop_table("specialty_template_modules")
    op.drop_index("uq_specialty_templates_one_published", table_name="specialty_templates")
    op.drop_index("ix_specialty_templates_specialty_id", table_name="specialty_templates")
    op.drop_table("specialty_templates")
