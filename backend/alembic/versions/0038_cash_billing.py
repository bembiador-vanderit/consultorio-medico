"""6C6 additive internal billing; no pilot transactions are seeded."""
from alembic import op
import sqlalchemy as sa
revision = "0038_cash_billing"
down_revision = "0037_insurance_coverage"
branch_labels = depends_on = None

def upgrade():
    op.create_table('cash_registers',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('center_id', sa.Integer(), nullable=False),
    sa.Column('opened_by', sa.Integer(), nullable=False),
    sa.Column('closed_by', sa.Integer(), nullable=True),
    sa.Column('state', sa.String(length=10), nullable=False),
    sa.Column('opening_amount', sa.Numeric(precision=12, scale=2), nullable=False),
    sa.Column('counted_cash', sa.Numeric(precision=12, scale=2), nullable=True),
    sa.Column('expected_cash', sa.Numeric(precision=14, scale=2), nullable=True),
    sa.Column('difference', sa.Numeric(precision=14, scale=2), nullable=True),
    sa.Column('opening_notes', sa.String(length=1000), nullable=True),
    sa.Column('closing_notes', sa.String(length=1000), nullable=True),
    sa.Column('opened_at', sa.DateTime(), nullable=False),
    sa.Column('closed_at', sa.DateTime(), nullable=True),
    sa.Column('organization_id', sa.Integer(), nullable=False),
    sa.CheckConstraint("state IN ('open', 'closed')", name='ck_register_state'),
    sa.CheckConstraint('opening_amount >= 0 AND (counted_cash IS NULL OR counted_cash >= 0)', name='ck_register_amounts'),
    sa.ForeignKeyConstraint(['center_id'], ['care_centers.id'], ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['closed_by'], ['users.id'], ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['opened_by'], ['users.id'], ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['organization_id'], ['organizations.id'], ondelete='RESTRICT'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_cash_registers_center_id'), 'cash_registers', ['center_id'], unique=False)
    op.create_index(op.f('ix_cash_registers_organization_id'), 'cash_registers', ['organization_id'], unique=False)
    op.create_index('uq_open_register', 'cash_registers', ['organization_id', 'center_id', 'opened_by'], unique=True, postgresql_where=sa.text("state = 'open'"), sqlite_where=sa.text("state = 'open'"))
    op.create_table('financial_invoices',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('center_id', sa.Integer(), nullable=False),
    sa.Column('patient_id', sa.Integer(), nullable=False),
    sa.Column('appointment_id', sa.Integer(), nullable=True),
    sa.Column('coverage_id', sa.Integer(), nullable=True),
    sa.Column('coverage_snapshot', sa.JSON(), nullable=False),
    sa.Column('patient_name', sa.String(length=201), nullable=False),
    sa.Column('concept', sa.String(length=200), nullable=False),
    sa.Column('base_amount', sa.Numeric(precision=12, scale=2), nullable=False),
    sa.Column('ars_amount', sa.Numeric(precision=12, scale=2), nullable=False),
    sa.Column('patient_amount', sa.Numeric(precision=12, scale=2), nullable=False),
    sa.Column('paid_amount', sa.Numeric(precision=12, scale=2), nullable=False),
    sa.Column('request_key', sa.String(length=36), nullable=False),
    sa.Column('request_hash', sa.String(length=64), nullable=False),
    sa.Column('created_by', sa.Integer(), nullable=False),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.Column('voided_at', sa.DateTime(), nullable=True),
    sa.Column('voided_by', sa.Integer(), nullable=True),
    sa.Column('void_reason', sa.String(length=1000), nullable=True),
    sa.Column('organization_id', sa.Integer(), nullable=False),
    sa.CheckConstraint('base_amount = ars_amount + patient_amount', name='ck_invoice_total'),
    sa.CheckConstraint('base_amount >= 0 AND ars_amount >= 0 AND patient_amount >= 0 AND paid_amount >= 0 AND paid_amount <= patient_amount', name='ck_invoice_amounts'),
    sa.ForeignKeyConstraint(['appointment_id'], ['appointments.id'], ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['center_id'], ['care_centers.id'], ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['coverage_id'], ['appointment_insurance_coverages.id'], ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['created_by'], ['users.id'], ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['organization_id'], ['organizations.id'], ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['patient_id'], ['patients.id'], ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['voided_by'], ['users.id'], ondelete='RESTRICT'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('organization_id', 'request_key', name='uq_invoice_request')
    )
    op.create_index(op.f('ix_financial_invoices_appointment_id'), 'financial_invoices', ['appointment_id'], unique=False)
    op.create_index(op.f('ix_financial_invoices_center_id'), 'financial_invoices', ['center_id'], unique=False)
    op.create_index(op.f('ix_financial_invoices_organization_id'), 'financial_invoices', ['organization_id'], unique=False)
    op.create_index(op.f('ix_financial_invoices_patient_id'), 'financial_invoices', ['patient_id'], unique=False)
    op.create_index('uq_active_appointment_invoice', 'financial_invoices', ['appointment_id'], unique=True, postgresql_where=sa.text('voided_at IS NULL'), sqlite_where=sa.text('voided_at IS NULL'))
    op.create_table('cash_movements',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('center_id', sa.Integer(), nullable=False),
    sa.Column('register_id', sa.Integer(), nullable=False),
    sa.Column('invoice_id', sa.Integer(), nullable=True),
    sa.Column('reverses_id', sa.Integer(), nullable=True),
    sa.Column('kind', sa.String(length=20), nullable=False),
    sa.Column('amount', sa.Numeric(precision=12, scale=2), nullable=False),
    sa.Column('parts', sa.JSON(), nullable=False),
    sa.Column('reason', sa.String(length=1000), nullable=True),
    sa.Column('request_key', sa.String(length=36), nullable=False),
    sa.Column('request_hash', sa.String(length=64), nullable=False),
    sa.Column('created_by', sa.Integer(), nullable=False),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.Column('organization_id', sa.Integer(), nullable=False),
    sa.CheckConstraint("kind IN ('payment','reversal','adjustment_in','adjustment_out')", name='ck_movement_kind'),
    sa.CheckConstraint('amount > 0', name='ck_movement_positive'),
    sa.ForeignKeyConstraint(['center_id'], ['care_centers.id'], ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['created_by'], ['users.id'], ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['invoice_id'], ['financial_invoices.id'], ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['organization_id'], ['organizations.id'], ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['register_id'], ['cash_registers.id'], ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['reverses_id'], ['cash_movements.id'], ondelete='RESTRICT'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('organization_id', 'request_key', name='uq_movement_request'),
    sa.UniqueConstraint('reverses_id')
    )
    op.create_index(op.f('ix_cash_movements_center_id'), 'cash_movements', ['center_id'], unique=False)
    op.create_index(op.f('ix_cash_movements_created_at'), 'cash_movements', ['created_at'], unique=False)
    op.create_index(op.f('ix_cash_movements_invoice_id'), 'cash_movements', ['invoice_id'], unique=False)
    op.create_index(op.f('ix_cash_movements_organization_id'), 'cash_movements', ['organization_id'], unique=False)
    op.create_index(op.f('ix_cash_movements_register_id'), 'cash_movements', ['register_id'], unique=False)

    for code in ('finance:read', 'finance:collect', 'finance:manage'):
        op.execute(sa.text("INSERT INTO permissions (code, description) VALUES (:code, :code) ON CONFLICT (code) DO NOTHING").bindparams(code=code))
    op.execute("INSERT INTO role_permissions (role_id, permission_id) SELECT r.id, p.id FROM roles r CROSS JOIN permissions p WHERE (r.code = 'admin' AND p.code IN ('finance:read','finance:collect','finance:manage')) OR (r.code = 'secretary' AND p.code IN ('finance:read','finance:collect')) ON CONFLICT DO NOTHING")

def downgrade():
    op.execute("DELETE FROM role_permissions WHERE permission_id IN (SELECT id FROM permissions WHERE code IN ('finance:read','finance:collect','finance:manage'))")
    op.execute("DELETE FROM permissions WHERE code IN ('finance:read','finance:collect','finance:manage')")
    op.drop_table('cash_movements')
    op.drop_table('financial_invoices')
    op.drop_table('cash_registers')
