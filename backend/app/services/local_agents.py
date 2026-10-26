"""Outbound registry only. SAME LAN/ORG/GROUP != AUTHORIZED. No clinical grants.

HTTP tenant context is resolved by Atlas host, never by a device-supplied org ID.
Bearer credentials authorize ONLY the /device registry endpoints, not user APIs.
"""
import base64
import hashlib
import secrets
from datetime import datetime, timedelta
from fastapi import HTTPException
from sqlalchemy import inspect, select
from sqlalchemy.exc import IntegrityError
from app.models import CareCenter, ClinicalAuditLog, Organization, User
from app.models.local_agent import AgentWorkgroup, LocalAgent, AgentPairingCode, AgentPrinter, AuthorizedStationScope
from app.services.administration import effective_permissions

PERMISSIONS = ("local_agents:view", "local_agents:manage")
PAIR_TTL = timedelta(minutes=5)
OFFLINE_AFTER = timedelta(seconds=120)  # Agent interval 30s: four missed intervals.
CREDENTIAL_TTL = timedelta(days=90)


def now():
    return datetime.utcnow()


def available(db):
    return inspect(db.connection()).has_table("local_agents")


def ensure_scope(db):
    if db.info.get("access_scope") != "tenant" or not db.info.get("organization_id"):
        raise HTTPException(403, "Se requiere organización activa")
    if not available(db):
        raise HTTPException(503, "Registro de estaciones pendiente de activación")
    return db.info["organization_id"]


def audit(db, action, row=None, actor=None, **context):
    if isinstance(row, LocalAgent):
        context = {"agent_uuid": row.agent_uuid, "credential_revision": row.credential_revision,
                   "actor_kind": "user" if actor else "station", **context}
    db.add(ClinicalAuditLog(organization_id=db.info["organization_id"],
        center_id=getattr(row, "center_id", None), user_id=actor,
        action="local_agent." + action, resource_type=getattr(row, "__tablename__", "local_agent"), resource_id=getattr(row, "id", None),
        outcome="denied" if action == "pairing_failed" else "success", context=context))


def get(db, model, identifier):
    row = db.scalar(select(model).where(model.id == identifier))
    if row is None:
        raise HTTPException(404, "Recurso de estación no disponible")
    return row


def lock_org(db):
    org = ensure_scope(db)
    db.scalar(select(Organization).where(Organization.id == org).with_for_update())
    return org


def group_create(db, user, payload):
    org = lock_org(db)
    center = get(db, CareCenter, payload.center_id)
    if not center.is_active:
        raise HTTPException(404, "Centro inactivo")
    row = db.scalar(select(AgentWorkgroup).where(AgentWorkgroup.center_id == center.id, AgentWorkgroup.name == payload.name))
    if row:
        return row
    row = AgentWorkgroup(organization_id=org, center_id=center.id, name=payload.name, created_by=user.id)
    db.add(row); db.flush()
    audit(db, "workgroup_created", row, user.id, name=row.name)
    db.commit()
    return row


def create_code(db, user, group_id):
    org = lock_org(db)
    group = get(db, AgentWorkgroup, group_id)
    raw = base64.b32encode(secrets.token_bytes(16)).decode().rstrip("=")
    code = "-".join(raw[i:i+4] for i in range(0, len(raw), 4))
    expires = now() + PAIR_TTL
    row = AgentPairingCode(organization_id=org, code_hash=digest(raw), center_id=group.center_id,
        workgroup_id=group.id, created_by=user.id, expires_at=expires)
    db.add(row); db.flush()
    audit(db, "pairing_code_created", row, user.id, workgroup_id=group.id, expires_at=expires.isoformat())
    db.commit()
    return {"code": code, "expires_at": expires.isoformat() + "Z"}  # Once only, never log/store plaintext.


def digest(value):
    return hashlib.sha256(value.encode()).hexdigest()


def issue_credential(row):
    token = "ala_" + secrets.token_urlsafe(32)
    row.credential_hash = digest(token)
    row.credential_expires_at = now() + CREDENTIAL_TTL
    return token


def credential_reply(row, token):
    return {"credential": token, "expires_at": row.credential_expires_at.isoformat() + "Z",
        "agent_uuid": row.agent_uuid, "organization_id": row.organization_id,
        "center_id": row.center_id, "workgroup_id": row.workgroup_id}


def pair(db, payload):
    org = lock_org(db)  # Serializes consume/duplicate checks within the tenant.
    code = db.scalar(select(AgentPairingCode).where(
        AgentPairingCode.code_hash == digest(payload.code.replace("-", ""))))
    issuer = db.get(User, code.created_by) if code else None
    if not code or code.consumed_at or code.expires_at <= now() or not issuer or not issuer.is_active or "local_agents:manage" not in effective_permissions(issuer):
        # Deliberately no raw code, agent-controlled names, tokens or identifying IP.
        # Bad random codes are unauthenticated noise, not one durable audit per guess.
        if code:
            audit(db, "pairing_failed", code, code.created_by, reason="invalid_or_expired_code")
            db.commit()
        raise HTTPException(403, "Código no disponible o vencido")
    group = get(db, AgentWorkgroup, code.workgroup_id)
    center = get(db, CareCenter, code.center_id)
    if not center.is_active or group.center_id != code.center_id:
        raise HTTPException(403, "Asociación no disponible")
    row = LocalAgent(organization_id=org, agent_uuid=str(payload.agent_uuid), display_code=payload.display_code,
        station_name=payload.station_name, center_id=code.center_id, workgroup_id=code.workgroup_id,
        version=payload.version, protocol_version=payload.protocol_version, fingerprint=payload.fingerprint,
        paired_by=code.created_by, credential_revision=1)
    token = issue_credential(row)
    db.add(row)
    try:
        db.flush()  # Global UUID uniqueness: cannot steal/reassign a station to another org.
    except IntegrityError:
        db.rollback()
        code = db.scalar(select(AgentPairingCode).where(AgentPairingCode.code_hash == digest(payload.code.replace("-", ""))))
        audit(db, "pairing_failed", code, code.created_by, reason="identity_conflict")
        db.commit()
        raise HTTPException(409, "Identidad ya registrada; no se reasigna automáticamente")
    code.consumed_at = now()
    audit(db, "paired", row, code.created_by, workgroup_id=row.workgroup_id, agent_uuid=row.agent_uuid)
    db.commit()
    return credential_reply(row, token)


def authenticate(db, token):
    ensure_scope(db)
    if len(token) > 128 or not token.startswith("ala_"):
        raise HTTPException(401, "Credencial de estación inválida")
    row = db.scalar(select(LocalAgent).where(LocalAgent.credential_hash == digest(token)).with_for_update())
    if not row or row.revoked_at or row.credential_expires_at <= now():
        raise HTTPException(401, "Credencial de estación inválida o revocada")
    center = get(db, CareCenter, row.center_id)
    if not center.is_active:
        raise HTTPException(403, "Centro no disponible")
    return row


def heartbeat(db, row, payload):
    if row.agent_uuid != str(payload.agent_uuid) or row.fingerprint != payload.fingerprint:
        raise HTTPException(409, "Identidad de estación incompatible")
    row.version = payload.version; row.protocol_version = payload.protocol_version
    # Name/association remain administrative; heartbeat cannot move tenant/center/group.
    row.health = payload.health; row.last_seen_at = row.updated_at = now()
    db.commit()
    return {"status": state(row), "last_seen_at": row.last_seen_at.isoformat() + "Z",
            "organization_id": row.organization_id, "center_id": row.center_id, "workgroup_id": row.workgroup_id}


def sync(db, row, payload):
    ids = [p.local_id for p in payload.printers]
    if len(set(ids)) != len(ids):
        raise HTTPException(422, "Identidad de impresora repetida")
    existing = {p.local_id: p for p in db.scalars(select(AgentPrinter).where(AgentPrinter.agent_id == row.id))}
    for item in payload.printers:
        printer = existing.get(item.local_id)
        created = printer is None
        if created:
            printer = AgentPrinter(organization_id=row.organization_id, agent_id=row.id, local_id=item.local_id)
            db.add(printer)
        for key, value in item.model_dump(exclude={"local_id"}).items():
            setattr(printer, key, value)
        restored = not created and not printer.available
        printer.available = True; printer.last_seen_at = now()
        if created or restored:
            audit(db, "printer_registered" if created else "printer_available", row,
                  local_id=item.local_id, credential_revision=row.credential_revision)
    for local_id, printer in existing.items():
        if local_id not in ids and printer.available:
            printer.available = False
            audit(db, "printer_unavailable", row, local_id=local_id, credential_revision=row.credential_revision)
    db.commit()
    return {"synchronized": len(ids)}


def state(row):
    if row.revoked_at:
        return "revoked"
    if row.last_seen_at < now() - OFFLINE_AFTER or row.credential_expires_at <= now():
        return "offline"
    return row.health


def revoke(db, user, identifier, reason):
    lock_org(db)
    row = get(db, LocalAgent, identifier)
    if not row.revoked_at:
        row.revoked_at = row.updated_at = now()
        audit(db, "revoked", row, user.id, before="paired", after="revoked", reason=reason)
    db.commit()
    return {"status": "revoked"}


def rotate(db, row):
    token = issue_credential(row); row.credential_revision += 1
    audit(db, "credential_rotated", row, credential_revision=row.credential_revision)
    db.commit()
    return credential_reply(row, token)


def configure(db, user, identifier, payload):
    lock_org(db)
    row = get(db, LocalAgent, identifier); group = get(db, AgentWorkgroup, payload.workgroup_id)
    before = {"station_name": row.station_name, "workgroup_id": row.workgroup_id, "center_id": row.center_id}
    row.station_name = payload.station_name; row.workgroup_id = group.id; row.center_id = group.center_id
    after = {"station_name": row.station_name, "workgroup_id": row.workgroup_id, "center_id": row.center_id}
    if before != after:
        row.updated_at = now()
        # Moving scope invalidates prior station discovery grants in both directions.
        if before["workgroup_id"] != row.workgroup_id:
            for grant in db.scalars(select(AuthorizedStationScope).where(
                (AuthorizedStationScope.source_id == row.id) | (AuthorizedStationScope.target_id == row.id))):
                db.delete(grant)
        audit(db, "configured", row, user.id, before=before, after=after, reason=payload.reason)
    db.commit()
    return {"updated": True}


def scope_change(db, user, identifier, payload):
    lock_org(db)
    source = get(db, LocalAgent, identifier); target = get(db, LocalAgent, payload.target_id)
    if source.id == target.id or source.revoked_at or target.revoked_at:
        raise HTTPException(422, "Relación de estación inválida")
    grant = db.scalar(select(AuthorizedStationScope).where(
        AuthorizedStationScope.source_id == source.id, AuthorizedStationScope.target_id == target.id))
    if bool(grant) != payload.allowed:
        if payload.allowed:
            db.add(AuthorizedStationScope(organization_id=source.organization_id, source_id=source.id,
                target_id=target.id, created_by=user.id))
        else:
            db.delete(grant)
        audit(db, "discovery_scope_changed", source, user.id, target_id=target.id,
              before=bool(grant), after=payload.allowed, reason=payload.reason)
    db.commit()
    return {"discovery_allowed": payload.allowed, "print_routing_allowed": False}


def visible_peers(db, row):
    # No LAN/group/organization shortcut. Directed grants only, plus own station.
    targets = select(AuthorizedStationScope.target_id).where(AuthorizedStationScope.source_id == row.id)
    return [{"agent_uuid": item.agent_uuid, "station_name": item.station_name,
             "status": state(item), "print_routing_allowed": False}
            for item in db.scalars(select(LocalAgent).where(
                (LocalAgent.id == row.id) | LocalAgent.id.in_(targets), LocalAgent.revoked_at.is_(None)))]


def registry(db):
    ensure_scope(db)
    org = get(db, Organization, db.info["organization_id"])
    groups = list(db.scalars(select(AgentWorkgroup).order_by(AgentWorkgroup.name)))
    centers = list(db.scalars(select(CareCenter).where(CareCenter.is_active.is_(True))))
    stations = []
    for row in db.scalars(select(LocalAgent).order_by(LocalAgent.station_name)):
        stations.append({"id": row.id, "agent_uuid": row.agent_uuid, "display_code": row.display_code,
            "station_name": row.station_name, "center_id": row.center_id, "workgroup_id": row.workgroup_id,
            "version": row.version, "protocol_version": row.protocol_version, "status": state(row),
            "paired_at": row.paired_at.isoformat() + "Z", "last_seen_at": row.last_seen_at.isoformat() + "Z",
            "printers": [{"id": p.id, "local_id": p.local_id, "display_name": p.display_name,
                "driver": p.driver, "is_default": p.is_default, "connection": p.connection,
                "is_virtual": p.is_virtual, "status": p.status, "available": p.available,
                "papers": p.papers, "last_seen_at": p.last_seen_at.isoformat() + "Z"}
                for p in db.scalars(select(AgentPrinter).where(AgentPrinter.agent_id == row.id))]})
    return {"organization": {"id": org.id, "name": org.name},
        "centers": [{"id": c.id, "name": c.name} for c in centers],
        "workgroups": [{"id": g.id, "name": g.name, "center_id": g.center_id} for g in groups], "agents": stations}
