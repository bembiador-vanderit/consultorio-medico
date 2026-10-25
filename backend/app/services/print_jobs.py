"""Internal v2 persistence. Caller authenticates/authorizes actor and owns commit.

No HTTP API, routing or execution. Audit references the authoritative job, never
serves as a queue. Actor is a persistent User, not a field supplied by a client.
"""
import hashlib
import json
import re
from dataclasses import dataclass, replace
from datetime import datetime, timedelta, UTC
from uuid import UUID, uuid4
from fastapi import HTTPException
from sqlalchemy import select, inspect
from app.models import User, OrganizationMembership, ClinicalAuditLog
from app.models.center import CareCenter
from app.models.local_agent import AgentPrinter, LocalAgent
from app.models.print_job import PrintJob, PrintDelivery, PrintResult
from app.models.print_contract import may_transition


def utcnow():
    return datetime.now(UTC).replace(tzinfo=None)


@dataclass(frozen=True)
class PrintScope:
    organization_id: int
    center_id: int
    agent_id: int


@dataclass(frozen=True)
class PrintIntent:
    job_id: str
    printer_id: int
    artifact_ref: str
    content_sha256: str
    expires_at: datetime
    format: str = "pdf"
    copies: int = 1
    origin_type: str = "WEB_DESKTOP"
    document_type: str = "synthetic_test"
    document_security_class: str = "GENERAL"
    source_agent_id: int | None = None


@dataclass(frozen=True)
class ResolvedPrintDocument:
    """Metadata from a trusted server-side resolver, NOT a permission or auth token.

    Resolver applies existing document permissions. Never deserialize it from a
    client body. Artifact storage, HTTP download and routing are outside this phase.
    """
    organization_id: int
    reference: str
    document_type: str
    security_class: str
    content_sha256: str


def check_scope(db, scope):
    if (not all(type(value) is int and value > 0 for value in (scope.organization_id, scope.center_id, scope.agent_id))
        or db.info.get("access_scope") != "tenant" or db.info.get("organization_id") != scope.organization_id):
        raise HTTPException(403, "Contexto de impresión no autorizado")
    agent = db.scalar(select(LocalAgent).where(LocalAgent.id == scope.agent_id,
        LocalAgent.center_id == scope.center_id, LocalAgent.revoked_at.is_(None)))
    center = db.scalar(select(CareCenter).where(CareCenter.id == scope.center_id))
    if agent is None or center is None:
        raise HTTPException(404, "Destino no disponible")
    return agent


def get_job(db, scope, job_id):
    check_scope(db, scope)
    job = db.scalar(select(PrintJob).where(PrintJob.id == job_id, PrintJob.center_id == scope.center_id,
        PrintJob.agent_id == scope.agent_id).with_for_update().execution_options(populate_existing=True))
    if job is None:
        raise HTTPException(404, "Trabajo no disponible")
    return job


def fingerprint(scope, intent, actor_id, agent_uuid, printer_local_id, source_uuid=None):
    """Shared canonical JSON: sorted keys, opaque ASCII values, UTC milliseconds."""
    values = dict(version=2, job_id=intent.job_id, organization_id=scope.organization_id,
        center_id=scope.center_id, requested_by=actor_id, origin_type=intent.origin_type,
        source_agent=str(UUID(source_uuid)) if source_uuid else "", document_reference=intent.artifact_ref, document_type=intent.document_type,
        document_security_class=intent.document_security_class, target_agent=str(UUID(agent_uuid)),
        target_printer=printer_local_id, format=intent.format, copies=intent.copies,
        content_sha256=intent.content_sha256,
        expires_at=intent.expires_at.isoformat(timespec="milliseconds") + "Z")
    return hashlib.sha256(json.dumps(values, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()).hexdigest()


def _audit(db, job, action, previous=None, *, actor_id=None, extra=None):
    db.add(ClinicalAuditLog(organization_id=job.organization_id, center_id=job.center_id,
        user_id=job.requested_by if actor_id is None else actor_id, resource_type="print_job", resource_id=None, action=action,
        outcome="success", context={"job_id":job.id, "intent_hash":job.intent_hash, "from":previous, "to":job.status,
            "requested_by":job.requested_by,"origin_type":job.origin_type,"target_agent":job.agent_id,"target_printer":job.printer_id,
            "execution_mode":"safe_validation" if job.document_type=="synthetic_test" else "physical_qa" if job.document_type=="physical_routing_qa" else "unspecified",**(extra or {})}))


def _change(db, job, target):
    if not may_transition(job.status, target) or (job.contract_version == 2 and target in {"delivering","cancel_requested"}):
        raise HTTPException(409, "Transición de impresión no permitida")
    if job.status != target:
        previous = job.status
        job.status = target
        _audit(db, job, "print_job.transition", previous)


def register(db, scope, intent, *, actor=None, document_resolver=None, now=None):
    now = now or utcnow()
    agent = check_scope(db, scope)
    if not isinstance(actor, User) or inspect(actor).session is not db or not actor.identity_active:
        raise HTTPException(403, "Solicitante autenticado requerido")
    member = db.scalar(select(OrganizationMembership).where(OrganizationMembership.user_id == actor.id,
        OrganizationMembership.state == "active"))
    if member is None:
        raise HTTPException(403, "Solicitante fuera del tenant")
    try:
        valid = (str(UUID(intent.job_id)) == intent.job_id
            and re.fullmatch(r"[A-Za-z0-9_-]{1,128}", intent.artifact_ref)
            and re.fullmatch(r"[0-9a-f]{64}", intent.content_sha256)
            and re.fullmatch(r"[A-Za-z0-9_-]{1,64}", intent.document_type)
            and intent.format in {"pdf", "plain_text"} and type(intent.copies) is int and 1 <= intent.copies <= 999
            and type(intent.printer_id) is int and intent.printer_id > 0
            and intent.origin_type in {"WEB_DESKTOP","WEB_MOBILE","WEB_TABLET","LOCAL_AGENT","SYSTEM"}
            and intent.document_security_class in {"GENERAL","ADMINISTRATIVE","FINANCIAL","CLINICAL","SENSITIVE_CLINICAL"}
            and isinstance(intent.expires_at, datetime) and intent.expires_at.tzinfo is None)
    except (ValueError, TypeError, AttributeError):
        valid = False
    if not valid:
        raise HTTPException(422, "Metadatos de impresión inválidos")
    if not callable(document_resolver):
        raise HTTPException(403, "Documento resuelto por el servidor requerido")
    document = document_resolver(db, actor, intent.artifact_ref, intent.document_type)
    if not isinstance(document, ResolvedPrintDocument) or document.organization_id != scope.organization_id:
        raise HTTPException(404, "Documento fuera del tenant")
    if (document.reference, document.document_type, document.security_class, document.content_sha256) != (
        intent.artifact_ref, intent.document_type, intent.document_security_class, intent.content_sha256):
        raise HTTPException(403, "Metadatos distintos del documento autorizado")
    intent = replace(intent, expires_at=intent.expires_at.replace(microsecond=(intent.expires_at.microsecond//1000)*1000))
    source = None
    if intent.origin_type == "LOCAL_AGENT":
        source = db.scalar(select(LocalAgent).where(LocalAgent.id == intent.source_agent_id, LocalAgent.revoked_at.is_(None)))
        if source is None:
            raise HTTPException(404, "Estación de origen no disponible")
    elif intent.source_agent_id is not None:
        raise HTTPException(422, "Este origen no admite source_agent")
    printer = db.scalar(select(AgentPrinter).where(AgentPrinter.id == intent.printer_id, AgentPrinter.agent_id == scope.agent_id))
    if printer is None:
        raise HTTPException(404, "Impresora no disponible")
    digest = fingerprint(scope, intent, actor.id, agent.agent_uuid, printer.local_id, source.agent_uuid if source else None)
    if db.get(PrintJob, intent.job_id) is not None:
        existing = get_job(db, scope, intent.job_id)
        if existing.intent_hash != digest or existing.contract_version != 2:
            raise HTTPException(409, "PrintJobId ya tiene otra intención o es heredado")
        return existing
    if intent.expires_at <= now:
        raise HTTPException(410, "Trabajo expirado")
    if not printer.available:
        raise HTTPException(404, "Impresora no disponible")
    from sqlalchemy.dialects.postgresql import insert as pg_insert
    from sqlalchemy.dialects.sqlite import insert as sqlite_insert
    insert = pg_insert if db.bind.dialect.name == "postgresql" else sqlite_insert
    created = db.execute(insert(PrintJob.__table__).values(id=intent.job_id, organization_id=scope.organization_id,
        center_id=scope.center_id, agent_id=scope.agent_id, printer_id=intent.printer_id,
        artifact_ref=intent.artifact_ref, content_sha256=intent.content_sha256, format=intent.format,
        copies=intent.copies, intent_hash=digest, status="queued", created_at=now, expires_at=intent.expires_at,
        contract_version=2, requested_by=actor.id, origin_type=intent.origin_type, source_agent_id=intent.source_agent_id,
        document_type=intent.document_type, document_security_class=intent.document_security_class)
        .on_conflict_do_nothing(index_elements=["id"]).returning(PrintJob.id)).scalar_one_or_none()
    job = get_job(db, scope, intent.job_id)
    if job.intent_hash != digest:
        raise HTTPException(409, "PrintJobId ya tiene otra intención")
    if created:
        _audit(db, job, "print_job.created"); db.flush()
    return job


def deliver(db, scope, job_id, *, now=None):
    now = now or utcnow()
    job = get_job(db, scope, job_id)
    if job.contract_version != 2 or job.status not in {"queued","received","ready"}:
        return None
    if job.expires_at <= now:
        _change(db, job, "expired"); db.flush()
        return None
    previous = db.scalar(select(PrintDelivery).where(PrintDelivery.job_id == job_id).order_by(PrintDelivery.number.desc()).limit(1))
    if previous and previous.lease_until > now:
        return previous
    attempt = PrintDelivery(id=str(uuid4()), organization_id=scope.organization_id, job_id=job_id,
        agent_id=scope.agent_id, number=previous.number+1 if previous else 1,
        created_at=now, lease_until=min(now+timedelta(seconds=60), job.expires_at))
    db.add(attempt); _audit(db, job, "print_job.delivery"); db.flush()
    return attempt


def _attempt(db, job_id, delivery_id):
    attempt = db.scalar(select(PrintDelivery).where(PrintDelivery.id == delivery_id, PrintDelivery.job_id == job_id))
    if attempt is None:
        raise HTTPException(404, "Entrega no disponible")
    return attempt


def advance(db, scope, job_id, target, *, delivery_id, now=None):
    job = get_job(db, scope, job_id)
    _attempt(db, job_id, delivery_id)
    if job.contract_version != 2 or target not in {"received","ready","printing"}:
        raise HTTPException(409, "Progreso no permitido")
    if job.status in {"queued","received","ready"} and job.expires_at <= (now or utcnow()):
        _change(db, job, "expired")
    else:
        _change(db, job, target)
    db.flush()
    return job


def record_result(db, scope, job_id, delivery_id, outcome, *, spool_id=None, error_code=None):
    job = get_job(db, scope, job_id)
    if outcome not in {"submitted","printed","failed","unknown","cancelled","expired"}:
        raise HTTPException(422, "Resultado inválido")
    if (outcome in {"submitted","printed"} and (spool_id is None or error_code is not None)) or (
        spool_id is not None and (type(spool_id) is not int or spool_id <= 0)) or (
        error_code is not None and not re.fullmatch(r"[A-Z0-9_]{1,40}", error_code)):
        raise HTTPException(422, "Resultado no sanitizado")
    attempt = _attempt(db, job_id, delivery_id)
    existing = db.get(PrintResult, job_id)
    if existing:
        if existing.spool_id is not None and existing.spool_id == spool_id and existing.error_code is None and error_code is None:
            if existing.outcome == "submitted" and outcome == "printed":
                _change(db, job, "printed")
                existing.outcome = "printed"; existing.recorded_at = utcnow()
            elif not (existing.outcome == "printed" and outcome == "submitted") and existing.outcome != outcome:
                raise HTTPException(409, "Resultado final ya registrado")
        elif (existing.outcome, existing.spool_id, existing.error_code) != (outcome, spool_id, error_code):
            raise HTTPException(409, "Resultado final ya registrado")
        if attempt.acknowledged_at is None:
            attempt.acknowledged_at = utcnow()
        db.flush()
        return existing
    _change(db, job, outcome)
    result = PrintResult(job_id=job_id, organization_id=scope.organization_id, delivery_id=delivery_id,
        outcome=outcome, spool_id=spool_id, error_code=error_code, recorded_at=utcnow())
    db.add(result); attempt.acknowledged_at = result.recorded_at
    db.flush()
    return result


def cancel(db, scope, job_id):
    job = get_job(db, scope, job_id)
    if job.status in {"queued","received","ready"}:
        _change(db, job, "cancelled")
    db.flush()  # Printing/submitted: actual state unchanged; never promise physical cancellation.
    return job
