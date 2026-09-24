from datetime import datetime, timedelta
from secrets import token_urlsafe
from hashlib import sha256
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.api.deps import current_user, require_permission
from app.core.security import verify_password
from app.db import get_db
from app.models import Role, User
from app.models.administration import AdminTransfer, ReauthenticationGrant, SecurityAudit
from app.services.administration import audit, authorize_sensitive_write, lock_administration

router = APIRouter(prefix="/administration", tags=["Seguridad administrativa"])
manage = require_permission("users:manage")

class ReauthenticationRequest(BaseModel):
    password: str = Field(min_length=1, max_length=128)
    method: Literal["POST", "PUT", "PATCH", "DELETE"]
    path: str = Field(pattern=r"^/api/v1/[a-zA-Z0-9/_-]+$", max_length=180)

class TransferRequest(BaseModel):
    target_id: int = Field(gt=0)
    replace_initiator: bool = True


def transfer_response(db: Session, transfer: AdminTransfer) -> dict:
    return {
        "id": transfer.id, "initiator_id": transfer.initiator_id, "target_id": transfer.target_id,
        "initiator_name": db.get(User, transfer.initiator_id).full_name,
        "target_name": db.get(User, transfer.target_id).full_name,
        "replace_initiator": transfer.replace_initiator, "state": transfer.state,
        "expires_at": transfer.expires_at,
    }


def is_admin(user: User) -> bool:
    return user.is_active and any(role.code == "admin" for role in user.roles)


@router.post("/reauthenticate")
def reauthenticate(payload: ReauthenticationRequest, actor: User = Depends(current_user), db: Session = Depends(get_db)):
    version = actor.session_version
    lock_administration(db)
    db.refresh(actor)
    if not actor.is_active or version != actor.session_version:
        raise HTTPException(401, "Sesión inválida")
    now = datetime.utcnow()
    if actor.reauth_locked_until and actor.reauth_locked_until > now:
        raise HTTPException(429, "Demasiados intentos; espere 5 minutos")
    if not verify_password(payload.password, actor.password_hash):
        actor.reauth_failures += 1
        if actor.reauth_failures >= 5:
            actor.reauth_locked_until = now + timedelta(minutes=5)
            actor.reauth_failures = 0
        audit(db, actor, "reauthenticate", "denied")
        db.commit()
        raise HTTPException(403, "Contraseña incorrecta")
    actor.reauth_failures = 0
    actor.reauth_locked_until = None
    # Only store a hash of the proof; a database read cannot recover it.
    proof = token_urlsafe(32)
    db.execute(delete(ReauthenticationGrant).where(ReauthenticationGrant.user_id == actor.id))
    db.add(ReauthenticationGrant(id=sha256(proof.encode()).hexdigest(), user_id=actor.id,
        session_version=actor.session_version, action=f"{payload.method} {payload.path}",
        expires_at=now + timedelta(minutes=2)))
    audit(db, actor, "reauthenticate")
    db.commit()
    return {"proof": proof, "expires_in": 120}


@router.get("/transfers")
def list_transfers(actor: User = Depends(current_user), db: Session = Depends(get_db)):
    query = select(AdminTransfer).where(AdminTransfer.state == "pending", AdminTransfer.expires_at > datetime.utcnow())
    if not is_admin(actor):
        query = query.where(AdminTransfer.target_id == actor.id)
    return [transfer_response(db, item) for item in db.scalars(query.order_by(AdminTransfer.id.desc()).limit(100)).all()]


@router.post("/transfers", status_code=201)
def request_transfer(payload: TransferRequest, actor: User = Depends(manage), db: Session = Depends(get_db)):
    if not is_admin(actor):
        raise HTTPException(403, "Se requiere un administrador activo")
    target = db.get(User, payload.target_id)
    if not target or not target.is_active or target.id == actor.id or is_admin(target):
        raise HTTPException(422, "Seleccione otro usuario activo que no sea administrador")
    if db.scalar(select(AdminTransfer.id).where(AdminTransfer.target_id == target.id,
            AdminTransfer.state == "pending", AdminTransfer.expires_at > datetime.utcnow())):
        raise HTTPException(409, "El destinatario ya tiene una solicitud pendiente")
    transfer = AdminTransfer(initiator_id=actor.id, target_id=target.id,
        initiator_version=actor.session_version, target_version=target.session_version,
        replace_initiator=payload.replace_initiator, expires_at=datetime.utcnow() + timedelta(hours=24))
    db.add(transfer)
    db.flush()
    audit(db, actor, f"admin.request:{transfer.id}:target:{target.id}:replace:{payload.replace_initiator}")
    db.commit()
    db.refresh(transfer)
    return transfer_response(db, transfer)


def sensitive_actor(request: Request, actor: User = Depends(current_user), db: Session = Depends(get_db)):
    authorize_sensitive_write(db, actor, f"{request.method} {request.url.path}", request.headers.get("X-Reauthentication"))
    return actor


@router.post("/transfers/{transfer_id}/accept")
def accept_transfer(transfer_id: int, actor: User = Depends(sensitive_actor), db: Session = Depends(get_db)):
    transfer = db.get(AdminTransfer, transfer_id)
    if not transfer or transfer.target_id != actor.id:
        raise HTTPException(404, "Solicitud no encontrada")
    initiator = db.get(User, transfer.initiator_id)
    if (transfer.state != "pending" or transfer.expires_at <= datetime.utcnow()
            or not initiator or not is_admin(initiator) or is_admin(actor)
            or initiator.session_version != transfer.initiator_version
            or actor.session_version != transfer.target_version):
        raise HTTPException(409, "La solicitud ya no es válida; solicite una nueva")
    admin_role = db.scalar(select(Role).where(Role.code == "admin"))
    actor.roles.append(admin_role)
    if transfer.replace_initiator:
        initiator.roles = [role for role in initiator.roles if role.code != "admin"]
    transfer.state = "accepted"
    db.commit()
    return {"state": "accepted", "login_required": True}


@router.post("/transfers/{transfer_id}/cancel")
def cancel_transfer(transfer_id: int, actor: User = Depends(sensitive_actor), db: Session = Depends(get_db)):
    transfer = db.get(AdminTransfer, transfer_id)
    if not transfer or not (actor.id in {transfer.target_id, transfer.initiator_id} or is_admin(actor)):
        raise HTTPException(404, "Solicitud no encontrada")
    if transfer.state != "pending":
        raise HTTPException(409, "Solicitud ya resuelta")
    transfer.state = "cancelled"
    db.commit()
    return {"state": "cancelled"}


@router.get("/audit")
def list_audit(offset: int = Query(0, ge=0), limit: int = Query(50, ge=1, le=100),
               actor: User = Depends(manage), db: Session = Depends(get_db)):
    return list(db.scalars(select(SecurityAudit).order_by(SecurityAudit.id.desc()).offset(offset).limit(limit)).all())
