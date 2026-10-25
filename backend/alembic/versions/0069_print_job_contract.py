"""Extend the existing print intent. Historical jobs remain explicitly un-attributed."""
from alembic import op
import sqlalchemy as sa

revision = "0069_print_job_contract"  # <=32 characters: existing alembic_version is VARCHAR(32).
down_revision = "0068_print_job_persistence"
branch_labels = depends_on = None
OLD_STATES = "status IN ('queued','delivering','cancel_requested','cancelled','expired','submitted','printed','failed','unknown')"
NEW_STATES = "status IN ('queued','delivering','received','ready','printing','cancel_requested','cancelled','expired','submitted','printed','failed','unknown')"


def upgrade():
    op.add_column('print_jobs', sa.Column('contract_version', sa.Integer(), nullable=False, server_default='1'))
    for name, kind in (('requested_by', sa.Integer()), ('origin_type', sa.String(16)), ('source_agent_id', sa.Integer()),
                       ('document_type', sa.String(64)), ('document_security_class', sa.String(24))):
        op.add_column('print_jobs', sa.Column(name, kind, nullable=True))
    # No fabricated actor/origin, no recalculation of historical intent hashes.
    op.alter_column('print_jobs', 'contract_version', server_default='2')
    op.drop_constraint('ck_print_job_status', 'print_jobs', type_='check')
    op.create_check_constraint('ck_print_job_status', 'print_jobs', NEW_STATES)
    op.create_check_constraint('ck_print_contract_metadata', 'print_jobs',
        "(contract_version=1 AND requested_by IS NULL AND origin_type IS NULL AND document_type IS NULL AND document_security_class IS NULL AND source_agent_id IS NULL) OR (contract_version=2 AND requested_by IS NOT NULL AND origin_type IS NOT NULL AND document_type IS NOT NULL AND document_security_class IS NOT NULL)")
    op.create_check_constraint('ck_print_origin', 'print_jobs', "origin_type IS NULL OR origin_type IN ('WEB_DESKTOP','WEB_MOBILE','WEB_TABLET','LOCAL_AGENT','SYSTEM')")
    op.create_check_constraint('ck_print_security_class', 'print_jobs', "document_security_class IS NULL OR document_security_class IN ('GENERAL','ADMINISTRATIVE','FINANCIAL','CLINICAL','SENSITIVE_CLINICAL')")
    op.create_check_constraint('ck_print_source_origin', 'print_jobs', "(origin_type='LOCAL_AGENT' AND source_agent_id IS NOT NULL) OR (source_agent_id IS NULL AND (origin_type IS NULL OR origin_type<>'LOCAL_AGENT'))")
    op.create_unique_constraint('uq_local_agent_identity_scope', 'local_agents', ['id','organization_id'])
    op.create_foreign_key('fk_print_requester', 'print_jobs', 'users', ['requested_by'], ['id'], ondelete='RESTRICT')
    op.create_foreign_key('fk_print_requester_tenant', 'print_jobs', 'organization_memberships', ['requested_by','organization_id'], ['user_id','organization_id'], ondelete='RESTRICT')
    op.create_foreign_key('fk_print_source_tenant', 'print_jobs', 'local_agents', ['source_agent_id','organization_id'], ['id','organization_id'], ondelete='RESTRICT')
    op.execute("""
    CREATE FUNCTION protect_print_job_contract() RETURNS trigger LANGUAGE plpgsql AS $$
    BEGIN
      IF TG_OP='INSERT' THEN
        IF NEW.contract_version<>2 OR NEW.status<>'queued' THEN RAISE EXCEPTION 'new jobs require queued contract v2' USING ERRCODE='23514'; END IF;
        RETURN NEW;
      END IF;
      IF ROW(OLD.id,OLD.organization_id,OLD.center_id,OLD.agent_id,OLD.printer_id,OLD.artifact_ref,
        OLD.content_sha256,OLD.format,OLD.copies,OLD.intent_hash,OLD.created_at,OLD.expires_at,
        OLD.contract_version,OLD.requested_by,OLD.origin_type,OLD.source_agent_id,OLD.document_type,OLD.document_security_class)
        IS DISTINCT FROM ROW(NEW.id,NEW.organization_id,NEW.center_id,NEW.agent_id,NEW.printer_id,NEW.artifact_ref,
        NEW.content_sha256,NEW.format,NEW.copies,NEW.intent_hash,NEW.created_at,NEW.expires_at,
        NEW.contract_version,NEW.requested_by,NEW.origin_type,NEW.source_agent_id,NEW.document_type,NEW.document_security_class)
      THEN RAISE EXCEPTION 'immutable print intent' USING ERRCODE='23514'; END IF;
      IF OLD.status<>NEW.status AND NOT (
        (OLD.status='queued' AND NEW.status IN ('received','delivering','cancelled','expired','failed','unknown')) OR
        (OLD.status='delivering' AND NEW.status IN ('received','cancel_requested','expired','failed','unknown','submitted','printed')) OR
        (OLD.status='received' AND NEW.status IN ('ready','cancelled','expired','failed','unknown')) OR
        (OLD.status='ready' AND NEW.status IN ('printing','cancelled','expired','failed','unknown')) OR
        (OLD.status='printing' AND NEW.status IN ('submitted','printed','unknown')) OR
        (OLD.status='submitted' AND NEW.status IN ('printed','unknown')) OR
        (OLD.status='cancel_requested' AND NEW.status IN ('cancelled','expired','failed','unknown','submitted','printed')))
      THEN RAISE EXCEPTION 'invalid print transition' USING ERRCODE='23514'; END IF;
      IF NEW.contract_version=2 AND NEW.status IN ('delivering','cancel_requested') THEN
        RAISE EXCEPTION 'legacy state is not valid for contract v2' USING ERRCODE='23514';
      END IF;
      RETURN NEW;
    END $$;
    CREATE TRIGGER print_job_contract_guard BEFORE INSERT OR UPDATE ON print_jobs
      FOR EACH ROW EXECUTE FUNCTION protect_print_job_contract();
    """)


def downgrade():
    # Refuse data loss rather than invent a lossy backfill or downgrade Printed to pending.
    if op.get_bind().scalar(sa.text("SELECT count(*) FROM print_jobs WHERE contract_version<>1 OR status IN ('received','ready','printing')")):
        raise RuntimeError('Downgrade blocked: v2 contracts/progress cannot be represented in 0068')
    op.execute('DROP TRIGGER print_job_contract_guard ON print_jobs; DROP FUNCTION protect_print_job_contract()')
    for name in ('fk_print_source_tenant','fk_print_requester_tenant','fk_print_requester'):
        op.drop_constraint(name, 'print_jobs', type_='foreignkey')
    op.drop_constraint('uq_local_agent_identity_scope', 'local_agents', type_='unique')
    for name in ('ck_print_source_origin','ck_print_security_class','ck_print_origin','ck_print_contract_metadata','ck_print_job_status'):
        op.drop_constraint(name, 'print_jobs', type_='check')
    op.create_check_constraint('ck_print_job_status', 'print_jobs', OLD_STATES)
    for name in ('document_security_class','document_type','source_agent_id','origin_type','requested_by','contract_version'):
        op.drop_column('print_jobs', name)
