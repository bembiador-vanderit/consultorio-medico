"""6C7 ARS claims, remittances, applications and immutable history."""
from alembic import op
import sqlalchemy as sa

revision = '0039_ars_receivables'
down_revision = '0038_cash_billing'
branch_labels = depends_on = None


def base_columns(center=True):
    cols = [sa.Column('id', sa.Integer(), primary_key=True),
            sa.Column('organization_id', sa.Integer(), sa.ForeignKey('organizations.id', ondelete='RESTRICT'), nullable=False)]
    if center:
        cols.append(sa.Column('center_id', sa.Integer(), sa.ForeignKey('care_centers.id', ondelete='RESTRICT'), nullable=False))
    return cols


def upgrade():
    op.create_table('ars_claims', *base_columns(),
        sa.Column('patient_id', sa.Integer(), sa.ForeignKey('patients.id', ondelete='RESTRICT'), nullable=False),
        sa.Column('appointment_id', sa.Integer(), sa.ForeignKey('appointments.id', ondelete='RESTRICT'), nullable=False),
        sa.Column('coverage_id', sa.Integer(), sa.ForeignKey('appointment_insurance_coverages.id', ondelete='RESTRICT'), nullable=False),
        sa.Column('insurance_company_id', sa.Integer(), sa.ForeignKey('insurance_companies.id', ondelete='RESTRICT'), nullable=False),
        sa.Column('plan_id', sa.Integer(), sa.ForeignKey('insurance_plans.id', ondelete='RESTRICT')),
        sa.Column('snapshot', sa.JSON(), nullable=False),
        sa.Column('patient_name', sa.String(201), nullable=False),
        sa.Column('service_date', sa.Date(), nullable=False),
        sa.Column('state', sa.String(30), nullable=False),
        sa.Column('claimed_amount', sa.Numeric(12, 2), nullable=False),
        sa.Column('approved_amount', sa.Numeric(12, 2)),
        sa.Column('disputed_amount', sa.Numeric(12, 2), nullable=False),
        sa.Column('paid_amount', sa.Numeric(12, 2), nullable=False),
        sa.Column('created_by', sa.Integer(), sa.ForeignKey('users.id', ondelete='RESTRICT'), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('submitted_at', sa.DateTime()), sa.Column('received_at', sa.DateTime()), sa.Column('cancelled_at', sa.DateTime()),
        sa.UniqueConstraint('organization_id', 'appointment_id', name='uq_ars_claim_appointment'),
        sa.CheckConstraint('claimed_amount > 0 AND paid_amount >= 0 AND disputed_amount >= 0 AND disputed_amount <= claimed_amount AND (approved_amount IS NULL OR (approved_amount >= 0 AND approved_amount + disputed_amount = claimed_amount)) AND paid_amount <= COALESCE(approved_amount, claimed_amount - disputed_amount)', name='ck_ars_claim_amounts'))
    for col in ('organization_id', 'center_id', 'patient_id', 'insurance_company_id'):
        op.create_index(f'ix_ars_claims_{col}', 'ars_claims', [col])
    op.create_index('ix_ars_claim_aging', 'ars_claims', ['organization_id', 'insurance_company_id', 'service_date'])

    op.create_table('ars_claim_events', *base_columns(),
        sa.Column('claim_id', sa.Integer(), sa.ForeignKey('ars_claims.id', ondelete='RESTRICT'), nullable=False),
        sa.Column('kind', sa.String(30), nullable=False), sa.Column('from_state', sa.String(30)),
        sa.Column('to_state', sa.String(30), nullable=False), sa.Column('code', sa.String(50)),
        sa.Column('note', sa.String(1000)), sa.Column('amount', sa.Numeric(12, 2)),
        sa.Column('actor_id', sa.Integer(), sa.ForeignKey('users.id', ondelete='RESTRICT'), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False))
    for col in ('organization_id', 'claim_id'):
        op.create_index(f'ix_ars_claim_events_{col}', 'ars_claim_events', [col])

    op.create_table('ars_remittances',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('organization_id', sa.Integer(), sa.ForeignKey('organizations.id', ondelete='RESTRICT'), nullable=False),
        sa.Column('center_id', sa.Integer(), sa.ForeignKey('care_centers.id', ondelete='RESTRICT')),
        sa.Column('insurance_company_id', sa.Integer(), sa.ForeignKey('insurance_companies.id', ondelete='RESTRICT'), nullable=False),
        sa.Column('company_name', sa.String(150), nullable=False),
        sa.Column('received_on', sa.Date(), nullable=False), sa.Column('reference', sa.String(100), nullable=False),
        sa.Column('amount', sa.Numeric(12, 2), nullable=False), sa.Column('applied_amount', sa.Numeric(12, 2), nullable=False),
        sa.Column('created_by', sa.Integer(), sa.ForeignKey('users.id', ondelete='RESTRICT'), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.UniqueConstraint('organization_id', 'insurance_company_id', 'reference', name='uq_ars_remittance_reference'),
        sa.CheckConstraint('amount > 0 AND applied_amount >= 0 AND applied_amount <= amount', name='ck_ars_remittance_amounts'))
    for col in ('organization_id', 'center_id', 'insurance_company_id'):
        op.create_index(f'ix_ars_remittances_{col}', 'ars_remittances', [col])

    op.create_table('ars_applications', *base_columns(),
        sa.Column('remittance_id', sa.Integer(), sa.ForeignKey('ars_remittances.id', ondelete='RESTRICT'), nullable=False),
        sa.Column('claim_id', sa.Integer(), sa.ForeignKey('ars_claims.id', ondelete='RESTRICT'), nullable=False),
        sa.Column('amount', sa.Numeric(12, 2), nullable=False),
        sa.Column('created_by', sa.Integer(), sa.ForeignKey('users.id', ondelete='RESTRICT'), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('reversed_by', sa.Integer(), sa.ForeignKey('users.id', ondelete='RESTRICT')),
        sa.Column('reversed_at', sa.DateTime()), sa.Column('reversal_reason', sa.String(1000)),
        sa.CheckConstraint('amount > 0', name='ck_ars_application_amount'))
    for col in ('organization_id', 'remittance_id', 'claim_id'):
        op.create_index(f'ix_ars_applications_{col}', 'ars_applications', [col])

    codes = ('ars:read', 'ars:claim', 'ars:send', 'ars:glosa', 'ars:payment', 'ars:reconcile', 'ars:report')
    for code in codes:
        op.execute(sa.text('INSERT INTO permissions (code, description) VALUES (:code, :code) ON CONFLICT (code) DO NOTHING').bindparams(code=code))
    op.execute("INSERT INTO role_permissions (role_id, permission_id) SELECT r.id, p.id FROM roles r CROSS JOIN permissions p WHERE r.code = 'admin' AND p.code LIKE 'ars:%' ON CONFLICT DO NOTHING")


def downgrade():
    op.execute("DELETE FROM role_permissions WHERE permission_id IN (SELECT id FROM permissions WHERE code LIKE 'ars:%')")
    op.execute("DELETE FROM permissions WHERE code LIKE 'ars:%'")
    for table in ('ars_applications', 'ars_remittances', 'ars_claim_events', 'ars_claims'):
        op.drop_table(table)
