"""Document presentation templates; no financial or clinical backfill."""
from alembic import op
import sqlalchemy as sa

revision = '0066_document_designer'
down_revision = '0065_ars_apply_idempotency'
branch_labels = depends_on = None


def upgrade():
    op.create_table('document_templates',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('organization_id', sa.Integer(), sa.ForeignKey('organizations.id', ondelete='RESTRICT'), nullable=False),
        sa.Column('code', sa.String(100), nullable=False),
        sa.Column('name', sa.String(180), nullable=False),
        sa.Column('document_type', sa.String(32), nullable=False),
        sa.Column('scope_key', sa.String(100), nullable=False),
        sa.Column('center_id', sa.Integer(), sa.ForeignKey('care_centers.id', ondelete='RESTRICT')),
        sa.Column('doctor_id', sa.Integer(), sa.ForeignKey('users.id', ondelete='RESTRICT')),
        sa.Column('created_by', sa.Integer(), sa.ForeignKey('users.id', ondelete='RESTRICT'), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.UniqueConstraint('organization_id', 'code', name='uq_document_template_code'),
        sa.UniqueConstraint('organization_id', 'document_type', 'scope_key', name='uq_document_template_scope'),
        sa.CheckConstraint("document_type IN ('invoice','receipt','cash_close')", name='ck_document_template_type'),
        sa.CheckConstraint('doctor_id IS NULL OR center_id IS NOT NULL', name='ck_document_template_doctor_center'))
    op.create_index('ix_document_templates_organization_id', 'document_templates', ['organization_id'])
    op.create_index('ix_document_templates_center_id', 'document_templates', ['center_id'])
    op.create_index('ix_document_templates_doctor_id', 'document_templates', ['doctor_id'])
    op.create_table('document_template_versions',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('organization_id', sa.Integer(), sa.ForeignKey('organizations.id', ondelete='RESTRICT'), nullable=False),
        sa.Column('template_id', sa.Integer(), sa.ForeignKey('document_templates.id', ondelete='RESTRICT'), nullable=False),
        sa.Column('version', sa.Integer(), nullable=False),
        sa.Column('status', sa.String(16), nullable=False),
        sa.Column('definition', sa.JSON(), nullable=False),
        sa.Column('created_by', sa.Integer(), sa.ForeignKey('users.id', ondelete='RESTRICT'), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('published_at', sa.DateTime()),
        sa.UniqueConstraint('template_id', 'version', name='uq_document_template_version'),
        sa.CheckConstraint('version > 0', name='ck_document_version_positive'),
        sa.CheckConstraint("status IN ('draft','published','archived')", name='ck_document_version_status'))
    op.create_index('ix_document_template_versions_organization_id', 'document_template_versions', ['organization_id'])
    op.create_index('ix_document_template_versions_template_id', 'document_template_versions', ['template_id'])
    op.create_index('uq_document_one_draft', 'document_template_versions', ['template_id'], unique=True,
                    postgresql_where=sa.text("status = 'draft'"))
    op.create_table('document_template_audits',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('organization_id', sa.Integer(), sa.ForeignKey('organizations.id', ondelete='RESTRICT'), nullable=False),
        sa.Column('template_id', sa.Integer(), sa.ForeignKey('document_templates.id', ondelete='RESTRICT')),
        sa.Column('version_id', sa.Integer(), sa.ForeignKey('document_template_versions.id', ondelete='RESTRICT')),
        sa.Column('center_id', sa.Integer(), sa.ForeignKey('care_centers.id', ondelete='RESTRICT')),
        sa.Column('actor_id', sa.Integer(), sa.ForeignKey('users.id', ondelete='RESTRICT'), nullable=False),
        sa.Column('action', sa.String(32), nullable=False),
        sa.Column('before', sa.JSON(), nullable=False),
        sa.Column('after', sa.JSON(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False))
    op.create_index('ix_document_template_audits_organization_id', 'document_template_audits', ['organization_id'])
    op.create_index('ix_document_template_audits_template_id', 'document_template_audits', ['template_id'])
    op.create_index('ix_document_template_audits_version_id', 'document_template_audits', ['version_id'])


def downgrade():
    op.drop_index('ix_document_template_audits_version_id', table_name='document_template_audits')
    op.drop_index('ix_document_template_audits_template_id', table_name='document_template_audits')
    op.drop_index('ix_document_template_audits_organization_id', table_name='document_template_audits')
    op.drop_table('document_template_audits')
    op.drop_index('uq_document_one_draft', table_name='document_template_versions')
    op.drop_index('ix_document_template_versions_template_id', table_name='document_template_versions')
    op.drop_index('ix_document_template_versions_organization_id', table_name='document_template_versions')
    op.drop_table('document_template_versions')
    op.drop_index('ix_document_templates_doctor_id', table_name='document_templates')
    op.drop_index('ix_document_templates_center_id', table_name='document_templates')
    op.drop_index('ix_document_templates_organization_id', table_name='document_templates')
    op.drop_table('document_templates')
