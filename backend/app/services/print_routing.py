"""Validation routing policies. No real document resolver, bytes store or executor.

The disposable QA adapter and official authenticated validation API have distinct
policies. Registry credentials authenticate devices; user sessions never do.
"""
from dataclasses import dataclass
from datetime import timedelta
from hashlib import sha256
from fastapi import HTTPException
from sqlalchemy import select, or_, and_, exists
from app.models import User
from app.models.local_agent import LocalAgent, AgentPrinter
from app.models.print_job import PrintJob, PrintDelivery, PrintResult
from app.services import print_jobs as jobs, local_agents as registry
from app.services.administration import effective_permissions
from app.services.appointment_scope import assigned_center_ids, is_role


ARTIFACTS = {
    'qa-general': ('GENERAL', 'documents:print'),
    'qa-financial': ('FINANCIAL', 'finance:read'),
    'qa-clinical': ('CLINICAL', 'clinical_documents:view'),
}


@dataclass(frozen=True)
class SyntheticRoutingPolicy:
    """In-process QA dependency, never a client-supplied flag or permission."""
    synthetic_only: bool = True

    def prepare(self, db, actor, payload, agent, printer, existing):
        return (self.resolve(db,actor,payload.document_reference,'synthetic_test'),
                existing.expires_at if existing else jobs.utcnow()+timedelta(seconds=payload.ttl_seconds))

    def target(self, db, user, agent_uuid, printer_local_id=None):
        return target(db,user,agent_uuid,printer_local_id)

    def content(self, reference):
        if reference not in ARTIFACTS:
            raise HTTPException(404, 'Documento sintético no disponible')
        return b'ATLAS PERGAMO\nPRUEBA SINTETICA DE ROUTING\nSIN DATOS CLINICOS NI FINANCIEROS\n'

    def resolve(self, db, actor, reference, kind):
        content = self.content(reference)
        classification, permission = ARTIFACTS[reference]
        allowed = effective_permissions(actor)
        if not {'local_agents:view', 'documents:print', permission}.issubset(allowed) or kind != 'synthetic_test':
            raise HTTPException(403, 'Documento no autorizado')
        return jobs.ResolvedPrintDocument(db.info['organization_id'], reference, kind, classification, sha256(content).hexdigest())


def target(db, user, agent_uuid, printer_local_id=None, *, virtual_only=True):
    allowed = effective_permissions(user)
    if not {'local_agents:view','documents:print'}.issubset(allowed):
        raise HTTPException(403, 'Impresión sintética no autorizada')
    agent = db.scalar(select(LocalAgent).where(LocalAgent.agent_uuid == str(agent_uuid), LocalAgent.revoked_at.is_(None)))
    if agent is None or (not is_role(user,'admin') and agent.center_id not in assigned_center_ids(user)):
        raise HTTPException(404, 'Destino no disponible')
    # QA routes cannot target a physical printer, even with a privileged user.
    conditions=[AgentPrinter.agent_id==agent.id,AgentPrinter.local_id==printer_local_id]
    if virtual_only: conditions.append(AgentPrinter.is_virtual.is_(True))
    printer = db.scalar(select(AgentPrinter).where(*conditions)) if printer_local_id else None
    if printer_local_id and printer is None:
        raise HTTPException(404, 'Impresora fake no disponible')
    return agent, printer


def user_job(db, user, job_id):
    row = db.scalar(select(PrintJob).where(PrintJob.id == str(job_id)))
    if row is None:
        raise HTTPException(404, 'Trabajo no disponible')
    agent = db.scalar(select(LocalAgent).where(LocalAgent.id == row.agent_id))
    if agent is None:
        raise HTTPException(404, 'Trabajo no disponible')
    target(db,user,agent.agent_uuid)
    if row.requested_by != user.id and 'local_agents:manage' not in effective_permissions(user):
        raise HTTPException(403, 'Trabajo de otro solicitante')
    return jobs.get_job(db,jobs.PrintScope(row.organization_id,row.center_id,row.agent_id),row.id)


def status(db, row, user=None):
    from app.services import physical_print_evidence as physical
    result = db.get(PrintResult,row.id)
    agent=db.get(LocalAgent,row.agent_id);printer=db.get(AgentPrinter,row.printer_id)
    return {'job_id':row.id,'status':row.status,'requested_by':row.requested_by,
        'execution_mode':'safe_validation' if row.document_type=='synthetic_test' else 'physical_qa' if row.document_type=='physical_routing_qa' else 'unsupported',
        'physical_execution_authorized':physical_authorized(db,row),
        'physical_evidence':physical.evidence(db,row),
        'can_confirm_physical':bool(user is not None and physical.can_confirm(db,row)),
        'target_agent':agent.agent_uuid,'target_printer':printer.local_id,'printer_name':printer.display_name,
        'target_online':registry.state(db.get(LocalAgent,row.agent_id))=='online',
        'origin_type':row.origin_type,'security_class':row.document_security_class,
        'intent_hash':row.intent_hash,'copies':row.copies,
        'result':None if result is None else {'outcome':result.outcome,'synthetic_spooler_id':result.spool_id,'error_code':result.error_code}}


def delivery(db, agent, policy, job_id=None):
    scope=jobs.PrintScope(agent.organization_id,agent.center_id,agent.id)
    if registry.state(agent) != 'online':
        return None
    if job_id:
        row=jobs.get_job(db,scope,str(job_id))
    else:
        row=db.scalar(select(PrintJob).where(PrintJob.agent_id==agent.id,
            or_(PrintJob.status.in_(['queued','received','ready']),and_(PrintJob.status.in_(['printing','submitted']),
                ~exists(select(PrintResult.job_id).where(PrintResult.job_id==PrintJob.id))))).order_by(PrintJob.created_at).limit(1))
    if row is None:
        return None
    row=jobs.get_job(db,scope,row.id)
    receipt_only=row.status in {'printing','submitted','printed','unknown','failed','cancelled','expired'}
    if receipt_only:
        attempt=db.scalar(select(PrintDelivery).where(PrintDelivery.job_id==row.id).order_by(PrintDelivery.number.desc()).limit(1))
    else:
        attempt=jobs.deliver(db,scope,row.id)
    if attempt is None:
        return None
    printer=db.scalar(select(AgentPrinter).where(AgentPrinter.id==row.printer_id))
    from app.services import physical_print_evidence as physical
    result=db.get(PrintResult,row.id)
    evidence=physical.evidence(db,row)
    source=db.scalar(select(LocalAgent).where(LocalAgent.id==row.source_agent_id)) if row.source_agent_id else None
    return {'delivery_id':attempt.id,'job_id':row.id,'organization_id':row.organization_id,'center_id':row.center_id,
        'target_agent':agent.agent_uuid,'target_printer':printer.local_id,'requested_by':row.requested_by,
        'origin_type':row.origin_type,'source_agent':source.agent_uuid if source else None,
        'document_reference':row.artifact_ref,'document_type':row.document_type,'security_class':row.document_security_class,
        'format':row.format,'copies':row.copies,'expires_at':row.expires_at.isoformat(timespec='milliseconds')+'Z',
        'content_sha256':row.content_sha256,'intent_hash':row.intent_hash,'status':row.status,
        'printer_available':printer.available,'receipt_only':receipt_only,
        'physical_evidence':evidence['kind'],'result_spooler_id':result.spool_id if result else None,
        'human_confirmed':evidence['confirmation']['confirmed'] if evidence['confirmation'] else None}


class OfficialValidationPolicy(SyntheticRoutingPolicy):
    """Trusted official source, limited to fixed non-sensitive test artifacts.

    Physical destination availability is not authority to print physically. Runtime
    independently enforces SafeValidation. No real document resolver is enabled.
    """
    def target(self, db, user, agent_uuid, printer_local_id=None):
        return target(db,user,agent_uuid,printer_local_id,virtual_only=False)

    def content(self, reference):
        if reference=='physical-routing-qa':
            return b'ATLAS PERGAMO\nOFFICIAL PRINT ROUTING QA\nPHYSICAL_ROUTING_QA\nNO PHI\n'
        return super().content(reference)

    def resolve(self,db,actor,reference,kind):
        if reference!='physical-routing-qa':return super().resolve(db,actor,reference,kind)
        from app.services import physical_print_authorization as physical
        grant=physical.load()
        if (not grant or grant.get('Enabled') is not True or kind!='physical_routing_qa'
            or not {'documents:print','local_agents:view','local_agents:manage'}.issubset(effective_permissions(actor))):
            raise HTTPException(403,'Documento físico QA no autorizado')
        return jobs.ResolvedPrintDocument(db.info['organization_id'],reference,kind,'GENERAL',sha256(self.content(reference)).hexdigest())

    def prepare(self,db,actor,payload,agent,printer,existing):
        if payload.document_reference!='physical-routing-qa':return super().prepare(db,actor,payload,agent,printer,existing)
        from app.services import physical_print_authorization as physical
        grant=physical.load()
        physical.require(grant,job_id=payload.job_id,agent=agent,printer=printer,copies=payload.copies,origin=payload.origin_type)
        doc=self.resolve(db,actor,payload.document_reference,'physical_routing_qa')
        expiry=existing.expires_at if existing else physical.expires(grant)
        scope=jobs.PrintScope(agent.organization_id,agent.center_id,agent.id)
        intent=jobs.PrintIntent(str(payload.job_id),printer.id,doc.reference,doc.content_sha256,expiry,
            format='plain_text',copies=1,origin_type=payload.origin_type,document_type=doc.document_type,document_security_class='GENERAL')
        if (grant['ContentSha256']!=doc.content_sha256
            or grant['IntentHash']!=jobs.fingerprint(scope,intent,actor.id,agent.agent_uuid,printer.local_id)):
            raise HTTPException(403,'Huella física QA no autorizada')
        return doc,expiry


def physical_authorized(db,row):
    if row.document_type!='physical_routing_qa' or row.status not in {'queued','received','ready'}:return False
    from app.services import physical_print_authorization as physical
    return physical.matches(physical.load(),job_id=row.id,agent=db.get(LocalAgent,row.agent_id),
        printer=db.get(AgentPrinter,row.printer_id),copies=row.copies,origin=row.origin_type,intent_hash=row.intent_hash)
