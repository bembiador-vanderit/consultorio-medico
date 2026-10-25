"""Registry endpoints do not accept print jobs or user/clinical credentials."""
import os
import ipaddress
from typing import Literal
from fastapi import APIRouter, Depends, Header, HTTPException, Request, Response, Query
from app.api.deps import require_permission
from app.db import get_db
from app.schemas.local_agent import (WorkgroupCreate, PairingCodeCreate, PairRequest, Heartbeat,
    PrinterSync, RegistryChange, Reason, ScopeChange)
from app.services import local_agents as service
from app.services import agent_destinations

router = APIRouter(prefix="/local-agents", tags=["Estaciones y dispositivos"])
view = require_permission("local_agents:view")
manage = require_permission("local_agents:manage")


def secure_transport(request: Request, response: Response):
    # Host/forwarding headers are not evidence of a local TCP connection.
    try:
        loopback_peer = bool(request.client and ipaddress.ip_address(request.client.host).is_loopback)
    except ValueError:
        loopback_peer = False
    local_dev = (os.getenv("ATLAS_AGENT_ENVIRONMENT", "Production") == "Development"
                 and os.getenv("LOCAL_AGENT_ALLOW_LOOPBACK_HTTP") == "true"
                 and loopback_peer
                 and request.url.hostname in {"localhost", "127.0.0.1", "::1"}
                 and not any(h in request.headers for h in ("forwarded", "x-forwarded-for", "x-forwarded-proto")))
    if request.url.scheme != "https" and not local_dev:
        raise HTTPException(400, "Registro de agentes requiere HTTPS")
    response.headers["Cache-Control"] = "no-store"


def device(request: Request, response: Response, authorization: str = Header(default=""), db=Depends(get_db)):
    secure_transport(request, response)
    prefix, _, token = authorization.partition(" ")
    if prefix != "Bearer":
        raise HTTPException(401, "Credencial de estación requerida")
    return service.authenticate(db, token)


@router.get("/registry")
def registry(response: Response, user=Depends(view), db=Depends(get_db)):
    response.headers["Cache-Control"] = "no-store"
    return service.registry(db)


@router.get("/destinations", dependencies=[Depends(secure_transport)])
def destinations(response: Response, user=Depends(view), db=Depends(get_db),
                 center_id: int | None = Query(default=None, gt=0),
                 workgroup_id: int | None = Query(default=None, gt=0),
                 paper_name: str | None = Query(default=None, min_length=1, max_length=100),
                 origin_type: Literal["WEB_DESKTOP", "WEB_MOBILE", "WEB_TABLET", "LOCAL_AGENT", "SYSTEM"] = "WEB_DESKTOP"):
    response.headers["Cache-Control"] = "no-store"
    return agent_destinations.destinations(db, user, center_id=center_id, workgroup_id=workgroup_id,
                                           paper_name=paper_name, origin_type=origin_type)


@router.post("/workgroups")
def group(payload: WorkgroupCreate, user=Depends(manage), db=Depends(get_db)):
    row = service.group_create(db, user, payload)
    return {"id": row.id, "name": row.name, "center_id": row.center_id}


@router.post("/pairing-codes", dependencies=[Depends(secure_transport)])
def code(payload: PairingCodeCreate, user=Depends(manage), db=Depends(get_db)):
    return service.create_code(db, user, payload.workgroup_id)


@router.post("/pair", dependencies=[Depends(secure_transport)])
def pair(payload: PairRequest, db=Depends(get_db)):
    return service.pair(db, payload)


@router.post("/device/heartbeat")
def heartbeat(payload: Heartbeat, row=Depends(device), db=Depends(get_db)):
    return service.heartbeat(db, row, payload)


@router.put("/device/printers")
def printers(payload: PrinterSync, row=Depends(device), db=Depends(get_db)):
    return service.sync(db, row, payload)


@router.post("/device/rotate")
def rotate(row=Depends(device), db=Depends(get_db)):
    return service.rotate(db, row)


@router.get("/device/peers")
def peers(row=Depends(device), db=Depends(get_db)):
    return service.visible_peers(db, row)


@router.post("/{identifier}/revoke")
def revoke(identifier: int, payload: Reason, user=Depends(manage), db=Depends(get_db)):
    return service.revoke(db, user, identifier, payload.reason)


@router.put("/{identifier}")
def configure(identifier: int, payload: RegistryChange, user=Depends(manage), db=Depends(get_db)):
    return service.configure(db, user, identifier, payload)


@router.put("/{identifier}/discovery-scope")
def scope(identifier: int, payload: ScopeChange, user=Depends(manage), db=Depends(get_db)):
    return service.scope_change(db, user, identifier, payload)
