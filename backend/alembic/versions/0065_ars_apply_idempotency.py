"""Persist tenant-scoped remittance application intents; no historical backfill."""
from alembic import op
import sqlalchemy as sa

revision = '0065_ars_apply_idempotency'
down_revision = '0064_appointment_arrivals'
branch_labels = depends_on = None


def upgrade():
    op.create_table('ars_apply_operations',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('organization_id', sa.Integer(), sa.ForeignKey('organizations.id', ondelete='RESTRICT'), nullable=False),
        sa.Column('request_key', sa.String(36), nullable=False),
        sa.Column('fingerprint', sa.String(64), nullable=False),
        sa.Column('remittance_id', sa.Integer(), sa.ForeignKey('ars_remittances.id', ondelete='RESTRICT'), nullable=False),
        sa.Column('created_by', sa.Integer(), sa.ForeignKey('users.id', ondelete='RESTRICT'), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('response', sa.JSON(), nullable=False),
        sa.UniqueConstraint('organization_id', 'request_key', name='uq_ars_apply_operation_key'))
    op.create_index('ix_ars_apply_operations_organization_id', 'ars_apply_operations', ['organization_id'])
    op.add_column('ars_applications', sa.Column('operation_id', sa.Integer(), nullable=True))
    op.create_foreign_key('fk_ars_application_operation', 'ars_applications', 'ars_apply_operations', ['operation_id'], ['id'], ondelete='RESTRICT')
    op.create_index('ix_ars_applications_operation_id', 'ars_applications', ['operation_id'])


def downgrade():
    op.drop_index('ix_ars_applications_operation_id', table_name='ars_applications')
    op.drop_constraint('fk_ars_application_operation', 'ars_applications', type_='foreignkey')
    op.drop_column('ars_applications', 'operation_id')
    op.drop_index('ix_ars_apply_operations_organization_id', table_name='ars_apply_operations')
    op.drop_table('ars_apply_operations')
