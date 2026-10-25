"""Minimal administration and reception endpoints for queue-mode appointments."""

from datetime import date, datetime

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import inspect, insert, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, joinedload
from sqlalchemy.orm import object_session

from app.api.deps import require_permission
from app.db import get_db
from app.models import Appointment, CareCenter, QueueLine, QueueTicket, QueueTicketEvent, User
from app.models.administration import SecurityAudit
from app.schemas.queue import ArrivalCreate, QueueLineCreate, QueueLineRead, QueueLineUpdate, QueueTicketEventRead, QueueTicketRead
from app.services.agenda_schedule import validate_pair
from app.services.appointment_scope import apply_appointment_scope, is_role, secretary_can_manage
from app.services.clinical_specialties import active_doctor_specialties
from app.services.queue import call_next_ticket, call_ticket, complete_consultation, issue_arrival, mark_left, mark_no_response, recall_ticket, start_consultation
from app.schemas.queue_call import NextCallState, QueueCallPolicyRead, QueueCallPolicyWrite
from app.services.queue_call import call_next as policy_call_next, line_for_access, next_call_state, policy_schema_ready, policy_values, require_policy_schema, save_policy, _lock_doctor_then_line


router = APIRouter(tags=["Turnos"])
read_access = require_permission("patients:access")
clinical_access = require_permission("clinical:access")
manage = require_permission("centers:manage")


def _admin(user: User, db: Session) -> None:
    if db.info.get("access_scope") == "platform" or not is_role(user, "admin"):
        raise HTTPException(403, "Solo administración puede configurar líneas de turnos")


def _line_response(line: QueueLine) -> QueueLineRead:
    db = object_session(line)
    room_ready = db is not None and inspect(db.get_bind()).has_table("waiting_rooms")
    return QueueLineRead(
        id=line.id, center_id=line.center_id, doctor_id=line.doctor_id,
        specialty_id=line.specialty_id, name=line.name, prefix=line.prefix,
        is_active=line.is_active, call_on_consultation_start=line.call_on_consultation_start,
        doctor_name=line.doctor.full_name, center_name=line.center.name,
        waiting_room_id=line.waiting_room_id if room_ready else None,
    )


@router.get("/queue-lines", response_model=list[QueueLineRead])
def list_lines(
    center_id: int | None = None, doctor_id: int | None = None, active_only: bool = False,
    user: User = Depends(read_access), db: Session = Depends(get_db),
):
    if not (is_role(user, "admin") or is_role(user, "secretary") or is_role(user, "doctor")):
        raise HTTPException(403, "No tiene acceso a líneas de turnos")
    if is_role(user, "doctor"):
        doctor_id = user.id
    query = select(QueueLine).options(joinedload(QueueLine.doctor), joinedload(QueueLine.center)).order_by(QueueLine.center_id, QueueLine.name, QueueLine.id)
    if center_id is not None:
        query = query.where(QueueLine.center_id == center_id)
    if doctor_id is not None:
        query = query.where(QueueLine.doctor_id == doctor_id)
    if active_only:
        query = query.where(QueueLine.is_active.is_(True))
    lines = db.scalars(query).all()
    if is_role(user, "secretary"):
        lines = [line for line in lines if secretary_can_manage(user, line.center_id, line.doctor_id, db)]
    return [_line_response(line) for line in lines]


@router.post("/queue-lines", response_model=QueueLineRead, status_code=status.HTTP_201_CREATED)
def create_line(payload: QueueLineCreate, user: User = Depends(manage), db: Session = Depends(get_db)):
    _admin(user, db)
    validate_pair(db, payload.doctor_id, payload.center_id)
    doctor = db.get(User, payload.doctor_id)
    if payload.specialty_id is not None and payload.specialty_id not in {item.id for item in active_doctor_specialties(doctor)}:
        raise HTTPException(422, "La especialidad no está activa para este médico")
    room_ready = inspect(db.get_bind()).has_table("waiting_rooms")
    line = QueueLine(**payload.model_dump(), is_active=True) if room_ready else None
    if line is not None:
        db.add(line)
    try:
        if line is None:
            line_id = db.execute(insert(QueueLine.__table__).values(
                organization_id=db.get(CareCenter, payload.center_id).organization_id,
                center_id=payload.center_id, doctor_id=payload.doctor_id,
                specialty_id=payload.specialty_id, name=payload.name, prefix=payload.prefix,
                is_active=True, call_on_consultation_start=payload.call_on_consultation_start,
                created_at=datetime.utcnow(), updated_at=datetime.utcnow(),
            ).returning(QueueLine.id)).scalar_one()
            line = db.get(QueueLine, line_id)
        else:
            db.flush()
        db.add(SecurityAudit(actor_id=user.id, center_id=line.center_id, action=f"queue.line.create:{line.id}"))
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, "El prefijo ya está en uso en este centro") from None
    db.refresh(line)
    return _line_response(line)


@router.put("/queue-lines/{line_id}", response_model=QueueLineRead)
def update_line(line_id: int, payload: QueueLineUpdate, user: User = Depends(manage), db: Session = Depends(get_db)):
    _admin(user, db)
    line = db.scalar(select(QueueLine).where(QueueLine.id == line_id).with_for_update())
    if line is None:
        raise HTTPException(404, "Línea de turnos no encontrada")
    if payload.prefix != line.prefix and db.scalar(select(QueueTicket.id).where(QueueTicket.queue_line_id == line.id)) is not None:
        raise HTTPException(409, "El prefijo de una línea con turnos emitidos no puede cambiarse")
    changed = [key for key in ("name", "prefix", "is_active") if getattr(line, key) != getattr(payload, key)]
    if payload.call_on_consultation_start is not None and line.call_on_consultation_start != payload.call_on_consultation_start:
        changed.append("call_on_consultation_start")
    for key in changed:
        setattr(line, key, getattr(payload, key))
    try:
        if changed:
            db.add(SecurityAudit(actor_id=user.id, center_id=line.center_id, action=f"queue.line.update:{line.id}:{','.join(changed)}"))
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, "El prefijo ya está en uso en este centro") from None
    db.refresh(line)
    return _line_response(line)


@router.get("/queue-tickets", response_model=list[QueueTicketRead])
def list_tickets(
    day: date, center_id: int | None = None, doctor_id: int | None = None,
    user: User = Depends(read_access), db: Session = Depends(get_db),
):
    query = select(QueueTicket).join(Appointment, QueueTicket.appointment_id == Appointment.id).where(
        QueueTicket.service_date == day
    ).order_by(QueueTicket.arrived_at, QueueTicket.id)
    if center_id is not None:
        query = query.where(QueueTicket.center_id == center_id)
    if doctor_id is not None:
        query = query.where(QueueTicket.doctor_id == doctor_id)
    return db.scalars(apply_appointment_scope(query, user, db)).all()


@router.post("/queue-tickets/arrivals/{appointment_id}", response_model=QueueTicketRead, status_code=status.HTTP_201_CREATED)
def register_arrival(
    appointment_id: int, payload: ArrivalCreate,
    user: User = Depends(read_access), db: Session = Depends(get_db),
):
    try:
        return issue_arrival(db, appointment_id, payload.queue_line_id, user)
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, "Esta cita ya tiene turno o el código ya está ocupado") from None


@router.post("/queue-lines/{line_id}/call-next", response_model=QueueTicketRead)
def call_next(line_id: int, day: date, user: User = Depends(read_access), db: Session = Depends(get_db)):
    if not policy_schema_ready(db):
        return call_next_ticket(db, line_id, day, user)
    return policy_call_next(db, line_id, day, user)


@router.get("/queue-lines/{line_id}/call-policy", response_model=QueueCallPolicyRead)
def get_call_policy(line_id: int, user: User = Depends(read_access), db: Session = Depends(get_db)):
    require_policy_schema(db)
    return policy_values(db, line_for_access(db, line_id, user))


@router.put("/queue-lines/{line_id}/call-policy", response_model=QueueCallPolicyRead)
def put_call_policy(line_id: int, payload: QueueCallPolicyWrite,
                    user: User = Depends(manage), db: Session = Depends(get_db)):
    _admin(user, db)
    require_policy_schema(db)
    line = line_for_access(db, line_id, user, lock=True)
    return save_policy(db, line, payload, user)


@router.get("/queue-lines/{line_id}/next-call-state", response_model=NextCallState)
def get_next_call_state(line_id: int, day: date, user: User = Depends(read_access), db: Session = Depends(get_db)):
    require_policy_schema(db)
    return next_call_state(db, line_for_access(db, line_id, user), day)


@router.post("/queue-tickets/{ticket_id}/call", response_model=QueueTicketRead)
def call(ticket_id: int, user: User = Depends(read_access), db: Session = Depends(get_db)):
    if policy_schema_ready(db):
        ticket = db.get(QueueTicket, ticket_id)
        if ticket is None:
            raise HTTPException(404, "Turno no encontrado")
        return policy_call_next(db, ticket.queue_line_id, ticket.service_date, user, expected_ticket_id=ticket_id)
    return call_ticket(db, ticket_id, user)


@router.post("/queue-tickets/{ticket_id}/recall", response_model=QueueTicketRead)
def recall(ticket_id: int, user: User = Depends(read_access), db: Session = Depends(get_db)):
    if policy_schema_ready(db):
        ticket = db.get(QueueTicket, ticket_id)
        if ticket is None:
            raise HTTPException(404, "Turno no encontrado")
        line = _lock_doctor_then_line(db, ticket.queue_line_id, user)
        state = next_call_state(db, line, ticket.service_date)
        if state.block_reason in {"provider_paused", "line_inactive", "provider_unavailable", "wrong_day", "in_service"}:
            raise HTTPException(409, state.block_reason)
    return recall_ticket(db, ticket_id, user)


@router.post("/queue-tickets/{ticket_id}/start", response_model=QueueTicketRead)
def start(ticket_id: int, user: User = Depends(read_access), db: Session = Depends(get_db)):
    if policy_schema_ready(db):
        ticket = db.get(QueueTicket, ticket_id)
        if ticket is None:
            raise HTTPException(404, "Turno no encontrado")
        if ticket.status == "waiting":
            line = _lock_doctor_then_line(db, ticket.queue_line_id, user)
            state = next_call_state(db, line, ticket.service_date)
            if not state.can_call or state.next_waiting_ticket_id != ticket.id:
                raise HTTPException(409, state.block_reason or "Debe iniciar el siguiente turno en espera")
    return start_consultation(db, ticket_id, user)


@router.post("/queue-tickets/{ticket_id}/complete", response_model=QueueTicketRead)
def complete(ticket_id: int, user: User = Depends(clinical_access), db: Session = Depends(get_db)):
    return complete_consultation(db, ticket_id, user)


@router.post("/queue-tickets/{ticket_id}/no-response", response_model=QueueTicketRead)
def no_response(ticket_id: int, user: User = Depends(read_access), db: Session = Depends(get_db)):
    return mark_no_response(db, ticket_id, user)


@router.post("/queue-tickets/{ticket_id}/left", response_model=QueueTicketRead)
def left(ticket_id: int, user: User = Depends(read_access), db: Session = Depends(get_db)):
    return mark_left(db, ticket_id, user)


@router.get("/queue-tickets/{ticket_id}/events", response_model=list[QueueTicketEventRead])
def events(ticket_id: int, user: User = Depends(read_access), db: Session = Depends(get_db)):
    ticket = db.get(QueueTicket, ticket_id)
    if ticket is None:
        raise HTTPException(404, "Turno no encontrado")
    appointment = db.get(Appointment, ticket.appointment_id)
    if appointment is None:
        raise HTTPException(404, "Turno no encontrado")
    ensure = apply_appointment_scope(select(Appointment.id).where(Appointment.id == appointment.id), user, db)
    if db.scalar(ensure) is None:
        raise HTTPException(404, "Turno no encontrado")
    return list(db.scalars(select(QueueTicketEvent).where(QueueTicketEvent.queue_ticket_id == ticket.id).order_by(QueueTicketEvent.occurred_at, QueueTicketEvent.id)).all())
