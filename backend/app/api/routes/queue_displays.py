"""Administrative display configuration and a strictly public, token-only state."""

from datetime import datetime
from hashlib import sha256
import secrets

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy import inspect, insert, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, joinedload, object_session, selectinload

from app.api.deps import require_permission
from app.db import get_db
from app.models import CareCenter, QueueDisplay, QueueDisplayLine, QueueLine, QueueTicket, User, WaitingRoom
from app.models.administration import SecurityAudit
from app.schemas.queue_display import QueueDisplayAudio, QueueDisplayRead, QueueDisplayToken, QueueDisplayVoiceWrite, QueueDisplayWrite, PublicCall, PublicQueueDisplayState
from app.services.agenda_schedule import organization_today
from app.services.appointment_scope import is_role


router = APIRouter(tags=["Pantallas de turnos"])
manage = require_permission("centers:manage")
_AUDIO_FIELDS = tuple(QueueDisplayAudio.model_fields)


def _require_schema(db: Session) -> None:
    if not inspect(db.get_bind()).has_table("queue_displays"):
        raise HTTPException(503, "Pantallas de turnos aún no disponibles")


def _audio_schema_ready(db: Session) -> bool:
    return "audio_enabled" in {column["name"] for column in inspect(db.get_bind()).get_columns("queue_displays")}


def _voice_schema_ready(db: Session) -> bool:
    return "audio_voice_uri" in {column["name"] for column in inspect(db.get_bind()).get_columns("queue_displays")}


def _room_schema_ready(db: Session) -> bool:
    return inspect(db.get_bind()).has_table("waiting_rooms")


def _validate_room(db: Session, center_id: int, room_id: int | None, *, existing_room_id: int | None = None) -> None:
    if room_id is None:
        return
    if not _room_schema_ready(db):
        raise HTTPException(503, "Salas de espera aún no disponibles")
    room = db.get(WaitingRoom, room_id)
    center = db.get(CareCenter, center_id)
    if room is None or center is None:
        raise HTTPException(404, "Sala de espera no disponible")
    if room.center_id != center_id or room.organization_id != center.organization_id:
        raise HTTPException(422, "La sala debe pertenecer al centro de la pantalla")
    if not room.is_active and room_id != existing_room_id:
        raise HTTPException(409, "No se puede asignar una sala inactiva")


def _require_audio_schema(db: Session) -> None:
    if not _audio_schema_ready(db):
        raise HTTPException(503, "Audio de pantallas aún no disponible")


def _require_voice_schema(db: Session) -> None:
    if not _voice_schema_ready(db):
        raise HTTPException(503, "Selección de voz aún no disponible")


def _audio_changes_requested(payload: QueueDisplayWrite) -> bool:
    defaults = QueueDisplayAudio()
    return any(getattr(payload, field) != getattr(defaults, field) for field in _AUDIO_FIELDS)


def _audio_settings(display: QueueDisplay, *, public: bool = False) -> QueueDisplayAudio:
    db = object_session(display)
    if db is None or not _audio_schema_ready(db):
        return QueueDisplayAudio()
    available = {column["name"] for column in inspect(db.get_bind()).get_columns("queue_displays")}
    values = {field: getattr(display, field) for field in _AUDIO_FIELDS if field in available}
    if public:
        values["announce_service_name"] = values["announce_service_name"] and display.show_service_name
        values["announce_provider_name"] = values["announce_provider_name"] and display.show_provider_name
    return QueueDisplayAudio(**values)


def _admin(user: User, db: Session) -> None:
    if db.info.get("access_scope") == "platform" or not is_role(user, "admin"):
        raise HTTPException(403, "Solo administración puede configurar pantallas de turnos")


def _display(db: Session, display_id: int, *, lock: bool = False) -> QueueDisplay:
    query = select(QueueDisplay).where(QueueDisplay.id == display_id).options(
        joinedload(QueueDisplay.center),
        selectinload(QueueDisplay.lines).joinedload(QueueDisplayLine.queue_line),
    )
    if lock:
        query = query.with_for_update(of=QueueDisplay)
    display = db.scalar(query)
    if display is None:
        raise HTTPException(404, "Pantalla no disponible")
    return display


def _read(display: QueueDisplay) -> QueueDisplayRead:
    db = object_session(display)
    room_ready = db is not None and _room_schema_ready(db)
    room = db.get(WaitingRoom, display.waiting_room_id) if room_ready and display.waiting_room_id is not None else None
    return QueueDisplayRead(
        id=display.id, center_id=display.center_id, center_name=display.center.name,
        waiting_room_id=display.waiting_room_id if room_ready else None,
        waiting_room_name=room.name if room else None,
        name=display.name, is_active=display.is_active,
        show_service_name=display.show_service_name, show_provider_name=display.show_provider_name,
        recent_call_limit=display.recent_call_limit,
        **_audio_settings(display).model_dump(),
        lines=[{"queue_line_id": item.queue_line_id, "sort_order": item.sort_order,
                "is_active": item.is_active, "line_name": item.queue_line.name,
                "destination": item.destination}
               for item in sorted(display.lines, key=lambda item: (item.sort_order, item.id))],
    )


def _new_token() -> tuple[str, str]:
    token = secrets.token_urlsafe(32)
    return token, sha256(token.encode("utf-8")).hexdigest()


def _validate_lines(db: Session, payload: QueueDisplayWrite) -> list[QueueLine]:
    center = db.get(CareCenter, payload.center_id)
    if center is None or not center.is_active:
        raise HTTPException(404, "Centro no disponible")
    ids = [item.queue_line_id for item in payload.lines]
    positions = [item.sort_order for item in payload.lines]
    if len(ids) != len(set(ids)) or len(positions) != len(set(positions)):
        raise HTTPException(422, "Líneas y posiciones deben ser únicas")
    lines = list(db.scalars(select(QueueLine).where(QueueLine.id.in_(ids))).all()) if ids else []
    if len(lines) != len(ids):
        raise HTTPException(404, "Línea no disponible")
    if any(line.center_id != center.id for line in lines):
        raise HTTPException(422, "Todas las líneas deben pertenecer al centro de la pantalla")
    return lines


def _replace_lines(db: Session, display: QueueDisplay, payload: QueueDisplayWrite) -> None:
    # Flush removals before insertion to avoid conflicting with existing sort positions.
    for item in list(display.lines):
        db.delete(item)
    db.flush()
    for item in payload.lines:
        db.add(QueueDisplayLine(organization_id=display.organization_id, queue_display_id=display.id,
                                queue_line_id=item.queue_line_id, sort_order=item.sort_order,
                                destination=item.destination.strip(), is_active=item.is_active))
    db.flush()
    db.expire(display, ["lines"])


@router.get("/queue-displays", response_model=list[QueueDisplayRead])
def list_displays(center_id: int | None = None, user: User = Depends(manage), db: Session = Depends(get_db)):
    _admin(user, db)
    _require_schema(db)
    query = select(QueueDisplay.id).order_by(QueueDisplay.center_id, QueueDisplay.name, QueueDisplay.id)
    if center_id is not None:
        query = query.where(QueueDisplay.center_id == center_id)
    return [_read(_display(db, display_id)) for display_id in db.scalars(query)]


@router.post("/queue-displays", response_model=QueueDisplayToken, status_code=status.HTTP_201_CREATED)
def create_display(payload: QueueDisplayWrite, user: User = Depends(manage), db: Session = Depends(get_db)):
    _admin(user, db)
    _require_schema(db)
    audio_ready = _audio_schema_ready(db)
    if not audio_ready and _audio_changes_requested(payload):
        _require_audio_schema(db)
    if payload.audio_voice_uri is not None:
        _require_voice_schema(db)
    _validate_lines(db, payload)
    _validate_room(db, payload.center_id, payload.waiting_room_id)
    token, token_hash = _new_token()
    try:
        if audio_ready and _room_schema_ready(db):
            display = QueueDisplay(center_id=payload.center_id, name=payload.name, token_hash=token_hash,
                                   is_active=payload.is_active, show_service_name=payload.show_service_name,
                                   show_provider_name=payload.show_provider_name, recent_call_limit=payload.recent_call_limit,
                                   **({"waiting_room_id": payload.waiting_room_id} if _room_schema_ready(db) else {}),
                                   **{field: getattr(payload, field) for field in _AUDIO_FIELDS
                                      if field != "audio_voice_uri" or _voice_schema_ready(db)})
            db.add(display)
            db.flush()
        elif audio_ready:
            center = db.get(CareCenter, payload.center_id)
            display_id = db.execute(insert(QueueDisplay.__table__).values(
                organization_id=center.organization_id, center_id=center.id, name=payload.name,
                token_hash=token_hash, is_active=payload.is_active,
                show_service_name=payload.show_service_name, show_provider_name=payload.show_provider_name,
                recent_call_limit=payload.recent_call_limit,
                **{field: getattr(payload, field) for field in _AUDIO_FIELDS if field != "audio_voice_uri" or _voice_schema_ready(db)},
                created_at=datetime.utcnow(), updated_at=datetime.utcnow(),
            ).returning(QueueDisplay.id)).scalar_one()
            display = _display(db, display_id)
        else:
            # The official pilot remains on 0047 until 0048 is activated.
            center = db.get(CareCenter, payload.center_id)
            display_id = db.execute(text("""
                INSERT INTO queue_displays
                    (organization_id, center_id, name, token_hash, is_active,
                     show_service_name, show_provider_name, recent_call_limit, created_at, updated_at)
                VALUES (:organization_id, :center_id, :name, :token_hash, :is_active,
                        :show_service_name, :show_provider_name, :recent_call_limit, :now, :now)
                RETURNING id
            """), {
                "organization_id": center.organization_id, "center_id": center.id,
                "name": payload.name, "token_hash": token_hash, "is_active": payload.is_active,
                "show_service_name": payload.show_service_name, "show_provider_name": payload.show_provider_name,
                "recent_call_limit": payload.recent_call_limit, "now": datetime.utcnow(),
            }).scalar_one()
            display = _display(db, display_id)
        _replace_lines(db, display, payload)
        db.add(SecurityAudit(actor_id=user.id, center_id=display.center_id, action=f"queue.display.create:{display.id}"))
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, "No se pudo guardar la pantalla") from None
    return QueueDisplayToken(**_read(_display(db, display.id)).model_dump(), access_token=token)


@router.put("/queue-displays/{display_id}", response_model=QueueDisplayRead)
def update_display(display_id: int, payload: QueueDisplayWrite, user: User = Depends(manage), db: Session = Depends(get_db)):
    _admin(user, db)
    _require_schema(db)
    audio_ready = _audio_schema_ready(db)
    if not audio_ready and _audio_changes_requested(payload):
        _require_audio_schema(db)
    if payload.audio_voice_uri is not None:
        _require_voice_schema(db)
    display = _display(db, display_id, lock=True)
    if payload.center_id != display.center_id:
        raise HTTPException(409, "El centro de una pantalla no puede cambiarse")
    _validate_lines(db, payload)
    _validate_room(db, payload.center_id, payload.waiting_room_id,
                   existing_room_id=display.waiting_room_id if _room_schema_ready(db) else None)
    fields = ("name", "is_active", "show_service_name", "show_provider_name", "recent_call_limit")
    if audio_ready:
        for field in (*fields, *(field for field in _AUDIO_FIELDS
                                if field != "audio_voice_uri" or _voice_schema_ready(db))):
            setattr(display, field, getattr(payload, field))
        display.updated_at = datetime.utcnow()
        if _room_schema_ready(db):
            display.waiting_room_id = payload.waiting_room_id
    else:
        db.execute(text("""
            UPDATE queue_displays
            SET name=:name, is_active=:is_active, show_service_name=:show_service_name,
                show_provider_name=:show_provider_name, recent_call_limit=:recent_call_limit,
                updated_at=:now
            WHERE id=:id AND organization_id=:organization_id
        """), {
            "id": display.id, "organization_id": display.organization_id, "name": payload.name,
            "is_active": payload.is_active, "show_service_name": payload.show_service_name,
            "show_provider_name": payload.show_provider_name, "recent_call_limit": payload.recent_call_limit,
            "now": datetime.utcnow(),
        })
    try:
        _replace_lines(db, display, payload)
        db.add(SecurityAudit(actor_id=user.id, center_id=display.center_id, action=f"queue.display.update:{display.id}"))
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, "No se pudo guardar la pantalla") from None
    db.expire_all()
    return _read(_display(db, display.id))


@router.put("/queue-displays/{display_id}/voice", response_model=QueueDisplayRead)
def update_display_voice(display_id: int, payload: QueueDisplayVoiceWrite,
                         user: User = Depends(manage), db: Session = Depends(get_db)):
    _admin(user, db)
    _require_voice_schema(db)
    display = _display(db, display_id, lock=True)
    display.audio_voice_uri = payload.audio_voice_uri
    display.updated_at = datetime.utcnow()
    db.add(SecurityAudit(actor_id=user.id, center_id=display.center_id,
                         action=f"queue.display.voice.update:{display.id}"))
    db.commit()
    db.expire_all()
    return _read(_display(db, display.id))


@router.post("/queue-displays/{display_id}/rotate-token", response_model=QueueDisplayToken)
def rotate_display_token(display_id: int, user: User = Depends(manage), db: Session = Depends(get_db)):
    _admin(user, db)
    _require_schema(db)
    display = _display(db, display_id, lock=True)
    token, token_hash = _new_token()
    if _audio_schema_ready(db):
        display.token_hash = token_hash
        display.updated_at = datetime.utcnow()
    else:
        db.execute(text("""
            UPDATE queue_displays SET token_hash=:token_hash, updated_at=:now
            WHERE id=:id AND organization_id=:organization_id
        """), {
            "id": display.id, "organization_id": display.organization_id,
            "token_hash": token_hash, "now": datetime.utcnow(),
        })
    db.add(SecurityAudit(actor_id=user.id, center_id=display.center_id, action=f"queue.display.rotate_token:{display.id}"))
    db.commit()
    db.expire_all()
    return QueueDisplayToken(**_read(_display(db, display.id)).model_dump(), access_token=token)


@router.get("/queue/displays/{display_token}/state", response_model=PublicQueueDisplayState, response_model_exclude_unset=True)
def public_display_state(display_token: str, response: Response, db: Session = Depends(get_db)):
    response.headers["Cache-Control"] = "no-store"
    response.headers["Referrer-Policy"] = "no-referrer"
    _require_schema(db)
    if not (32 <= len(display_token) <= 128):
        raise HTTPException(404, "Pantalla no disponible")
    token_hash = sha256(display_token.encode("utf-8")).hexdigest()
    display = db.scalar(select(QueueDisplay).where(
        QueueDisplay.token_hash == token_hash, QueueDisplay.is_active.is_(True)
    ).options(joinedload(QueueDisplay.center), selectinload(QueueDisplay.lines).joinedload(QueueDisplayLine.queue_line)))
    if display is None or not display.center.is_active:
        raise HTTPException(404, "Pantalla no disponible")
    room = db.get(WaitingRoom, display.waiting_room_id) if _room_schema_ready(db) and display.waiting_room_id is not None else None
    explicit = {item.queue_line_id: item for item in display.lines if item.queue_line.center_id == display.center_id}
    if room is not None:
        room_lines = list(db.scalars(select(QueueLine).where(
            QueueLine.waiting_room_id == room.id, QueueLine.center_id == display.center_id,
            QueueLine.is_active.is_(True),
        ).order_by(QueueLine.name, QueueLine.id)).all()) if room.is_active else []
        # An explicit association overrides destination/visibility only for a line in this room.
        subscriptions = {line.id: (line, explicit[line.id].destination if line.id in explicit else line.name)
                         for line in room_lines if line.id not in explicit or explicit[line.id].is_active}
    else:
        line_items = [item for item in display.lines if item.is_active and item.queue_line.is_active
                      and item.queue_line.center_id == display.center_id]
        subscriptions = {item.queue_line_id: (item.queue_line, item.destination) for item in line_items}
    audio = _audio_settings(display, public=True)
    room_header = ({"waiting_room_name": room.name,
                    "provider_names": sorted({line.doctor.full_name for line, _ in subscriptions.values()}) if display.show_provider_name else [],
                    "service_names": sorted({line.name for line, _ in subscriptions.values()}) if display.show_service_name else []}
                   if room is not None else {})
    if not subscriptions:
        return PublicQueueDisplayState(display_name=display.name, center_name=display.center.name,
                                       current_calls=[], recent_calls=[], updated_at=datetime.utcnow(), audio=audio,
                                       **room_header)
    base_query = select(QueueTicket).where(
        QueueTicket.center_id == display.center_id, QueueTicket.queue_line_id.in_(subscriptions),
        QueueTicket.service_date == organization_today(db), QueueTicket.last_called_at.is_not(None),
    )
    latest_first = (QueueTicket.last_called_at.desc(), QueueTicket.id.desc())
    active_tickets = list(db.scalars(base_query.where(QueueTicket.status == "called")
                                     .order_by(*latest_first)).all())
    recent_tickets = list(db.scalars(base_query.where(QueueTicket.status != "called")
                                     .order_by(*latest_first).limit(display.recent_call_limit)).all())

    def public_call(ticket: QueueTicket) -> PublicCall:
        line, destination = subscriptions[ticket.queue_line_id]
        return PublicCall(ticket_code=ticket.public_code,
                          destination=destination,
                          called_at=ticket.last_called_at,
                          call_revision=ticket.call_count,
                          queue_line_name=line.name if display.show_service_name else None,
                          provider_name=line.doctor.full_name if display.show_provider_name and line.doctor else None)

    current = [public_call(ticket) for ticket in active_tickets]
    recent = [public_call(ticket) for ticket in recent_tickets]
    return PublicQueueDisplayState(display_name=display.name, center_name=display.center.name,
                                   current_calls=current, recent_calls=recent, updated_at=datetime.utcnow(), audio=audio,
                                   **room_header)
