"""Physical result semantics, not dispatch authority. State/result remain authoritative.

Audit contains actor/time/provenance, not queue state or a permission bypass.
Unknown is intentionally not manually promoted in V1.
"""
from fastapi import HTTPException
from sqlalchemy import select
from app.models import ClinicalAuditLog
from app.models.print_job import PrintResult
from app.services import print_jobs as jobs

HUMAN_PROBLEM='HUMAN_REPORTED_PROBLEM'

def confirmation(db,job):
    event=db.scalar(select(ClinicalAuditLog).where(
        ClinicalAuditLog.resource_type=='print_job',ClinicalAuditLog.organization_id==job.organization_id,
        ClinicalAuditLog.center_id==job.center_id,
        ClinicalAuditLog.action.in_(['print_job.human_confirmed_yes','print_job.human_confirmed_no']),
        ClinicalAuditLog.context['job_id'].as_string()==job.id,
        ClinicalAuditLog.context['intent_hash'].as_string()==job.intent_hash).order_by(ClinicalAuditLog.id.desc()).limit(1))
    if event is None:return None
    return {'confirmed':event.action=='print_job.human_confirmed_yes','actor_id':event.user_id,
            'at':event.created_at.isoformat()+'Z','reason':event.context.get('reason')}

def evidence(db,job):
    result=db.get(PrintResult,job.id)
    if job.document_type=='synthetic_test':
        return {'kind':'SIMULATED_PRINTED' if job.status=='printed' else 'SAFE_VALIDATION','confirmation':None}
    if job.document_type!='physical_routing_qa':return {'kind':'UNSUPPORTED','confirmation':None}
    human=confirmation(db,job)
    if human and human['confirmed'] and job.status=='printed':kind='HUMAN_CONFIRMED_PRINTED'
    elif job.status=='unknown':kind='UNKNOWN_AFTER_SPOOL'
    elif job.status=='submitted' and result and result.spool_id:kind='AWAITING_HUMAN_CONFIRMATION'
    elif job.status=='printed' and result and result.spool_id:kind='OS_REPORTED_PRINTED'
    else:kind='PHYSICAL_PENDING'
    return {'kind':kind,'confirmation':human}

def can_confirm(db,job):
    result=db.get(PrintResult,job.id)
    return bool(job.document_type=='physical_routing_qa' and job.artifact_ref=='physical-routing-qa'
        and job.contract_version==2 and job.status=='submitted' and result and result.outcome=='submitted'
        and result.spool_id and result.spool_id>0 and result.error_code is None)

def confirm(db,job,actor,confirmed,reason=None):
    # Caller has already resolved current user, tenant/center, target and row lock via user_job.
    result=db.get(PrintResult,job.id)
    if job.document_type!='physical_routing_qa' or job.artifact_ref!='physical-routing-qa':
        raise HTTPException(409,'Una validación simulada no admite confirmación física')
    old=confirmation(db,job)
    if old:
        consistent=(confirmed and job.status=='printed') or (not confirmed and job.status=='unknown' and result and result.error_code==HUMAN_PROBLEM)
        if old['confirmed']==confirmed and consistent:return job
        raise HTTPException(409,'El resultado físico ya tiene una confirmación incompatible')
    if not can_confirm(db,job):raise HTTPException(409,'El trabajo no tiene un recibo físico pendiente de confirmación')
    target='printed' if confirmed else 'unknown'
    jobs._change(db,job,target)
    result.outcome=target;result.error_code=None if confirmed else HUMAN_PROBLEM;result.recorded_at=jobs.utcnow()
    jobs._audit(db,job,'print_job.human_confirmed_yes' if confirmed else 'print_job.human_confirmed_no',
        actor_id=actor.id,extra={'confirmed':confirmed,'reason':reason,'spool_id':result.spool_id,'evidence_source':'human'})
    db.flush()
    return job
