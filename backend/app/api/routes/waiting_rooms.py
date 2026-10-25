"""Waiting-room configuration and scoped operational context."""

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import inspect, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.deps import require_permission
from app.db import get_db
from app.models import CareCenter, QueueDisplay, QueueLine, SecretaryCenterScope, User, WaitingRoom, WaitingRoomSecretary
from app.models.administration import SecurityAudit
from app.schemas.waiting_room import WaitingRoomLineAssignment, WaitingRoomRead, WaitingRoomSecretaryAssignment, WaitingRoomWrite
from app.services.appointment_scope import is_role, secretary_can_manage


router = APIRouter(prefix="/waiting-rooms", tags=["Salas de espera"])
manage = require_permission("centers:manage")
read = require_permission("patients:access")


def _require_schema(db: Session) -> None:
    if not inspect(db.get_bind()).has_table("waiting_rooms"):
        raise HTTPException(503, "Salas de espera aún no disponibles en esta base")


def _admin(user: User, db: Session) -> None:
    if db.info.get("access_scope") == "platform" or not is_role(user, "admin"):
        raise HTTPException(403, "Solo administración puede configurar salas de espera")


def _room(db: Session, room_id: int, *, lock: bool = False) -> WaitingRoom:
    query = select(WaitingRoom).where(WaitingRoom.id == room_id)
    if lock:
        query = query.with_for_update().execution_options(populate_existing=True)
    room = db.scalar(query)
    if room is None:
        raise HTTPException(404, "Sala de espera no disponible")
    return room


def _visible(db: Session, room: WaitingRoom, user: User) -> bool:
    if is_role(user, "admin"):
        return True
    if not room.is_active:
        return False
    if is_role(user, "secretary"):
        if room.center_id not in {center.id for center in user.centers if center.is_active}:
            return False
        if db.scalar(select(SecretaryCenterScope.id).where(
            SecretaryCenterScope.secretary_id == user.id,
            SecretaryCenterScope.center_id == room.center_id,
        )) is None:
            return False
        return db.scalar(select(WaitingRoomSecretary.id).where(
            WaitingRoomSecretary.waiting_room_id == room.id,
            WaitingRoomSecretary.secretary_user_id == user.id,
        )) is not None
    if is_role(user, "doctor"):
        return db.scalar(select(QueueLine.id).where(
            QueueLine.waiting_room_id == room.id, QueueLine.doctor_id == user.id,
        )) is not None
    return False


def _read(db: Session, room: WaitingRoom, user: User) -> WaitingRoomRead:
    lines = list(db.scalars(select(QueueLine).where(QueueLine.waiting_room_id == room.id)
                            .order_by(QueueLine.name, QueueLine.id)).all())
    if is_role(user, "secretary"):
        lines = [line for line in lines if secretary_can_manage(user, line.center_id, line.doctor_id, db)]
    elif is_role(user, "doctor"):
        lines = [line for line in lines if line.doctor_id == user.id]
    secretaries = []
    displays = []
    if is_role(user, "admin"):
        assigned = list(db.scalars(select(WaitingRoomSecretary).where(
            WaitingRoomSecretary.waiting_room_id == room.id)).all())
        users = {person.id: person for person in db.scalars(select(User).where(
            User.id.in_([item.secretary_user_id for item in assigned]))).all()} if assigned else {}
        secretaries = [{"user_id": item.secretary_user_id, "full_name": users[item.secretary_user_id].full_name}
                       for item in assigned if item.secretary_user_id in users]
        displays = [{"id": display.id, "name": display.name, "is_active": display.is_active}
                    for display in db.scalars(select(QueueDisplay).where(
                        QueueDisplay.waiting_room_id == room.id).order_by(QueueDisplay.name)).all()]
    return WaitingRoomRead(
        id=room.id, center_id=room.center_id, name=room.name, code=room.code,
        description=room.description, is_active=room.is_active, sort_order=room.sort_order,
        created_at=room.created_at, updated_at=room.updated_at,
        queue_lines=[{"id": line.id, "name": line.name, "prefix": line.prefix,
                      "provider_name": line.doctor.full_name, "specialty_id": line.specialty_id}
                     for line in lines],
        secretaries=secretaries, displays=displays,
    )


@router.get("", response_model=list[WaitingRoomRead])
def list_rooms(center_id: int | None = None, user: User = Depends(read), db: Session = Depends(get_db)):
    _require_schema(db)
    if not any(is_role(user, role) for role in ("admin", "secretary", "doctor")):
        raise HTTPException(403, "No tiene acceso a salas de espera")
    query = select(WaitingRoom).order_by(WaitingRoom.center_id, WaitingRoom.sort_order, WaitingRoom.name)
    if center_id is not None:
        query = query.where(WaitingRoom.center_id == center_id)
    return [_read(db, room, user) for room in db.scalars(query).all() if _visible(db, room, user)]


@router.get("/{room_id}", response_model=WaitingRoomRead)
def get_room(room_id: int, user: User = Depends(read), db: Session = Depends(get_db)):
    _require_schema(db)
    room = _room(db, room_id)
    if not _visible(db, room, user):
        raise HTTPException(404, "Sala de espera no disponible")
    return _read(db, room, user)


@router.post("", response_model=WaitingRoomRead, status_code=status.HTTP_201_CREATED)
def create_room(payload: WaitingRoomWrite, user: User = Depends(manage), db: Session = Depends(get_db)):
    _admin(user, db)
    _require_schema(db)
    center = db.get(CareCenter, payload.center_id)
    if center is None or not center.is_active:
        raise HTTPException(404, "Centro no disponible")
    room = WaitingRoom(**payload.model_dump(), organization_id=center.organization_id)
    db.add(room)
    try:
        db.flush()
        db.add(SecurityAudit(actor_id=user.id, center_id=center.id, action=f"waiting_room.create:{room.id}"))
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, "Ya existe una sala con ese nombre en el centro") from None
    return _read(db, _room(db, room.id), user)


@router.put("/{room_id}", response_model=WaitingRoomRead)
def update_room(room_id: int, payload: WaitingRoomWrite, user: User = Depends(manage), db: Session = Depends(get_db)):
    _admin(user, db)
    _require_schema(db)
    room = _room(db, room_id, lock=True)
    if payload.center_id != room.center_id:
        raise HTTPException(409, "El centro de una sala no puede cambiarse")
    for key in ("name", "code", "description", "is_active", "sort_order"):
        setattr(room, key, getattr(payload, key))
    room.updated_at = datetime.utcnow()
    db.add(SecurityAudit(actor_id=user.id, center_id=room.center_id, action=f"waiting_room.update:{room.id}"))
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, "Ya existe una sala con ese nombre en el centro") from None
    return _read(db, _room(db, room_id), user)


@router.put("/{room_id}/queue-lines", response_model=WaitingRoomRead)
def assign_lines(room_id: int, payload: WaitingRoomLineAssignment,
                 user: User = Depends(manage), db: Session = Depends(get_db)):
    _admin(user, db)
    _require_schema(db)
    room = _room(db, room_id, lock=True)
    requested = payload.queue_line_ids
    if len(requested) != len(set(requested)):
        raise HTTPException(422, "No repita líneas")
    current = list(db.scalars(select(QueueLine).where(QueueLine.waiting_room_id == room.id)).all())
    ids = set(requested) | {line.id for line in current}
    lines = list(db.scalars(select(QueueLine).where(QueueLine.id.in_(ids))
                            .order_by(QueueLine.id).with_for_update()).all()) if ids else []
    by_id = {line.id: line for line in lines}
    if len(set(requested) - by_id.keys()):
        raise HTTPException(404, "Línea de turnos no disponible")
    if not room.is_active and any(by_id.get(line_id) is not None and by_id[line_id].waiting_room_id != room.id for line_id in requested):
        raise HTTPException(409, "No se puede asignar una sala inactiva")
    if any(by_id[line_id].center_id != room.center_id or by_id[line_id].organization_id != room.organization_id
           for line_id in requested):
        raise HTTPException(422, "Todas las líneas deben pertenecer al centro de la sala")
    for line in lines:
        if line.id in requested:
            line.waiting_room_id = room.id
        elif line.waiting_room_id == room.id:
            line.waiting_room_id = None
    db.add(SecurityAudit(actor_id=user.id, center_id=room.center_id, action=f"waiting_room.lines.update:{room.id}"))
    db.commit()
    return _read(db, _room(db, room.id), user)


@router.put("/{room_id}/secretaries", response_model=WaitingRoomRead)
def assign_secretaries(room_id: int, payload: WaitingRoomSecretaryAssignment,
                       user: User = Depends(manage), db: Session = Depends(get_db)):
    _admin(user, db)
    _require_schema(db)
    room = _room(db, room_id, lock=True)
    requested = payload.secretary_user_ids
    if len(requested) != len(set(requested)):
        raise HTTPException(422, "No repita secretarias")
    people = {person.id: person for person in db.scalars(select(User).where(User.id.in_(requested))).all()} if requested else {}
    if len(people) != len(requested):
        raise HTTPException(404, "Secretaria no disponible")
    for person in people.values():
        if not person.is_active or not is_role(person, "secretary") or room.center_id not in {center.id for center in person.centers}:
            raise HTTPException(422, "La secretaria debe estar activa y asignada al centro")
        if db.scalar(select(SecretaryCenterScope.id).where(
            SecretaryCenterScope.secretary_id == person.id,
            SecretaryCenterScope.center_id == room.center_id,
        )) is None:
            raise HTTPException(422, "La secretaria debe tener alcance vigente en el centro")
    existing = list(db.scalars(select(WaitingRoomSecretary).where(
        WaitingRoomSecretary.waiting_room_id == room.id).with_for_update()).all())
    assigned_ids = {item.secretary_user_id for item in existing}
    if not room.is_active and any(secretary_id not in assigned_ids for secretary_id in requested):
        raise HTTPException(409, "No se puede asignar una sala inactiva")
    for assignment in existing:
        if assignment.secretary_user_id not in people:
            db.delete(assignment)
    for secretary_id in requested:
        if secretary_id not in assigned_ids:
            db.add(WaitingRoomSecretary(organization_id=room.organization_id, waiting_room_id=room.id,
                                        secretary_user_id=secretary_id, created_by_user_id=user.id))
    db.add(SecurityAudit(actor_id=user.id, center_id=room.center_id, action=f"waiting_room.secretaries.update:{room.id}"))
    db.commit()
    return _read(db, _room(db, room.id), user)


@router.get("/{room_id}/displays", response_model=list[dict])
def room_displays(room_id: int, user: User = Depends(manage), db: Session = Depends(get_db)):
    _admin(user, db)
    _require_schema(db)
    room = _room(db, room_id)
    return _read(db, room, user).displays
