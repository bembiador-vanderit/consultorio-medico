"""Issue one immutable ticket per appointment using an atomic daily counter."""

from datetime import datetime

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.orm import Session

from app.models import Appointment, Patient, QueueLine, QueueSequence, QueueTicket, QueueTicketEvent, User
from app.models.administration import SecurityAudit
from app.services.agenda_schedule import organization_today
from app.services.appointment_scope import assigned_center_ids, ensure_appointment_access, is_role, secretary_can_manage


def _event(db: Session, ticket: QueueTicket, event_type: str, occurred_at: datetime, actor: User | None) -> None:
    db.add(QueueTicketEvent(
        organization_id=ticket.organization_id,
        queue_ticket_id=ticket.id,
        event_type=event_type,
        occurred_at=occurred_at,
        actor_user_id=actor.id if actor is not None else None,
        created_at=occurred_at,
    ))


def _line_for_ticket(db: Session, ticket: QueueTicket) -> QueueLine:
    line = db.get(QueueLine, ticket.queue_line_id)
    if line is None or line.organization_id != ticket.organization_id:
        raise HTTPException(404, "Línea de turnos no encontrada")
    return line


def ensure_line_operator(user: User, line: QueueLine, db: Session) -> None:
    if not user.is_active:
        raise HTTPException(403, "Usuario inactivo")
    if is_role(user, "admin"):
        return
    if is_role(user, "secretary") and secretary_can_manage(user, line.center_id, line.doctor_id, db):
        return
    if is_role(user, "doctor") and line.doctor_id == user.id and line.center_id in assigned_center_ids(user):
        return
    raise HTTPException(403, "No tiene autorización para operar esta línea")


def _ticket_for_update(db: Session, ticket_id: int, user: User) -> tuple[QueueTicket, QueueLine, Appointment]:
    ticket = db.scalar(select(QueueTicket).where(QueueTicket.id == ticket_id).with_for_update())
    if ticket is None:
        raise HTTPException(404, "Turno no encontrado")
    appointment = db.get(Appointment, ticket.appointment_id)
    if appointment is None:
        raise HTTPException(404, "Cita no encontrada")
    ensure_appointment_access(user, appointment, db)
    line = _line_for_ticket(db, ticket)
    ensure_line_operator(user, line, db)
    return ticket, line, appointment


def call_ticket(db: Session, ticket_id: int, user: User) -> QueueTicket:
    ticket, _, _ = _ticket_for_update(db, ticket_id, user)
    if ticket.status != "waiting":
        raise HTTPException(409, "El turno ya fue llamado o cambió de estado")
    now = datetime.utcnow()
    ticket.status = "called"
    ticket.first_called_at = now
    ticket.last_called_at = now
    ticket.called_by_user_id = user.id
    ticket.call_count = 1
    ticket.updated_at = now
    _event(db, ticket, "CALLED", now, user)
    db.commit()
    db.refresh(ticket)
    return ticket


def recall_ticket(db: Session, ticket_id: int, user: User) -> QueueTicket:
    ticket, _, _ = _ticket_for_update(db, ticket_id, user)
    if ticket.status != "called":
        raise HTTPException(409, "Solo un turno llamado puede volver a llamarse")
    now = datetime.utcnow()
    ticket.last_called_at = now
    ticket.called_by_user_id = user.id
    ticket.call_count += 1
    ticket.updated_at = now
    _event(db, ticket, "RECALLED", now, user)
    db.commit()
    db.refresh(ticket)
    return ticket


def call_next_ticket(db: Session, line_id: int, day, user: User) -> QueueTicket:
    line = db.get(QueueLine, line_id)
    if line is None:
        raise HTTPException(404, "Línea de turnos no encontrada")
    ensure_line_operator(user, line, db)
    if not line.is_active:
        raise HTTPException(409, "La línea de turnos está inactiva")
    # Do not use SKIP LOCKED: the earliest waiting ticket must not be bypassed.
    for _ in range(3):
        ticket = db.scalar(
            select(QueueTicket)
            .where(
                QueueTicket.queue_line_id == line.id,
                QueueTicket.organization_id == line.organization_id,
                QueueTicket.service_date == day,
                QueueTicket.status == "waiting",
            )
            .order_by(QueueTicket.sequence_number, QueueTicket.id)
            .with_for_update()
        )
        if ticket is None:
            raise HTTPException(409, "No hay turnos esperando en esta línea")
        if ticket.status != "waiting":
            continue
        now = datetime.utcnow()
        ticket.status = "called"
        ticket.first_called_at = ticket.first_called_at or now
        ticket.last_called_at = now
        ticket.called_by_user_id = user.id
        ticket.call_count += 1
        ticket.updated_at = now
        _event(db, ticket, "CALLED", now, user)
        db.commit()
        db.refresh(ticket)
        return ticket
    raise HTTPException(409, "El turno siguiente cambió durante la llamada; intente de nuevo")


def start_consultation(db: Session, ticket_id: int, user: User) -> QueueTicket:
    if not (is_role(user, "doctor") or is_role(user, "admin")):
        raise HTTPException(403, "Solo el médico autorizado puede iniciar la consulta")
    ticket, line, _ = _ticket_for_update(db, ticket_id, user)
    now = datetime.utcnow()
    if ticket.status == "waiting":
        if not line.call_on_consultation_start:
            raise HTTPException(409, "Primero debe llamar el turno")
        ticket.first_called_at = ticket.first_called_at or now
        ticket.last_called_at = now
        ticket.called_by_user_id = user.id
        ticket.call_count += 1
        _event(db, ticket, "CALLED", now, user)
    elif ticket.status != "called":
        raise HTTPException(409, "El turno no puede iniciar consulta en su estado actual")
    ticket.status = "in_service"
    ticket.consultation_started_at = now
    ticket.consultation_started_by_user_id = user.id
    ticket.updated_at = now
    _event(db, ticket, "SERVICE_STARTED", now, user)
    db.commit()
    db.refresh(ticket)
    return ticket


def complete_consultation(db: Session, ticket_id: int, user: User) -> QueueTicket:
    if not is_role(user, "doctor"):
        raise HTTPException(403, "Solo el médico asociado puede finalizar la atención")
    ticket, line, _ = _ticket_for_update(db, ticket_id, user)
    if ticket.doctor_id != user.id or line.doctor_id != user.id:
        raise HTTPException(403, "Solo el médico asociado puede finalizar la atención")
    if ticket.status != "in_service" or ticket.consultation_started_at is None:
        raise HTTPException(409, "Solo una atención en curso puede finalizarse")
    now = datetime.utcnow()
    if now < ticket.consultation_started_at:
        raise HTTPException(409, "El inicio de atención es posterior a la hora actual")
    ticket.status = "completed"
    ticket.consultation_finished_at = now
    ticket.consultation_finished_by_user_id = user.id
    ticket.updated_at = now
    _event(db, ticket, "SERVICE_COMPLETED", now, user)
    db.commit()
    db.refresh(ticket)
    return ticket


def mark_no_response(db: Session, ticket_id: int, user: User) -> QueueTicket:
    ticket, _, _ = _ticket_for_update(db, ticket_id, user)
    if ticket.status != "called":
        raise HTTPException(409, "Solo un turno llamado puede marcarse sin respuesta")
    now = datetime.utcnow()
    ticket.status = "no_response"
    ticket.updated_at = now
    _event(db, ticket, "NO_RESPONSE", now, user)
    db.commit()
    db.refresh(ticket)
    return ticket


def mark_left(db: Session, ticket_id: int, user: User) -> QueueTicket:
    ticket, _, _ = _ticket_for_update(db, ticket_id, user)
    if ticket.status not in {"waiting", "called"}:
        raise HTTPException(409, "El turno no puede marcarse como retirado en su estado actual")
    now = datetime.utcnow()
    ticket.status = "left"
    ticket.left_at = now
    ticket.left_by_user_id = user.id
    ticket.updated_at = now
    _event(db, ticket, "LEFT", now, user)
    db.commit()
    db.refresh(ticket)
    return ticket


def next_number(db: Session, line: QueueLine, day) -> int:
    """The UPSERT serializes contenders on the unique daily row in PostgreSQL."""
    dialect = db.bind.dialect.name
    if dialect == "postgresql":
        insert = pg_insert(QueueSequence)
    elif dialect == "sqlite":  # Isolated tests use SQLite; production is PostgreSQL.
        insert = sqlite_insert(QueueSequence)
    else:
        raise RuntimeError("Unsupported queue counter dialect")
    stmt = insert.values(
        organization_id=line.organization_id, center_id=line.center_id,
        queue_line_id=line.id, service_date=day, last_number=1,
    ).on_conflict_do_update(
        index_elements=["organization_id", "center_id", "queue_line_id", "service_date"],
        set_={"last_number": QueueSequence.last_number + 1},
    ).returning(QueueSequence.last_number)
    return db.execute(stmt).scalar_one()


def issue_arrival(db: Session, appointment_id: int, line_id: int, user: User) -> QueueTicket:
    if not (is_role(user, "secretary") or is_role(user, "admin")):
        raise HTTPException(403, "Solo secretaría o administración puede registrar llegadas")
    appointment = db.scalar(select(Appointment).where(Appointment.id == appointment_id).with_for_update())
    if appointment is None:
        raise HTTPException(404, "Cita no encontrada")
    ensure_appointment_access(user, appointment, db)
    patient = db.get(Patient, appointment.patient_id)
    if patient is None or patient.organization_id != appointment.organization_id:
        raise HTTPException(404, "Paciente no disponible en este contexto")
    line = db.get(QueueLine, line_id)
    if line is None or line.organization_id != appointment.organization_id:
        raise HTTPException(404, "Línea de turnos no encontrada")
    if (not line.is_active or not line.center.is_active or not line.doctor.is_active
            or line.center_id != appointment.center_id or line.doctor_id != appointment.doctor_id
            or (line.specialty_id is not None and line.specialty_id != appointment.specialty_id)):
        raise HTTPException(422, "La línea no corresponde a esta cita o está inactiva")
    if appointment.status not in {"scheduled", "confirmed"}:
        raise HTTPException(409, "La cita no está prevista para atención")
    if appointment.appointment_date != organization_today(db):
        raise HTTPException(409, "La llegada solo puede registrarse el día de atención")
    if appointment.schedule_mode != "queue":
        raise HTTPException(409, "La cita no está en modalidad por turnos")
    if db.scalar(select(QueueTicket.id).where(QueueTicket.appointment_id == appointment.id)) is not None:
        raise HTTPException(409, "Esta cita ya tiene un turno emitido")

    number = next_number(db, line, appointment.appointment_date)
    now = datetime.utcnow()  # Capture after counter serialization: order by issuance, not agenda/contact order.
    ticket = QueueTicket(
        organization_id=appointment.organization_id,
        center_id=appointment.center_id, queue_line_id=line.id,
        appointment_id=appointment.id, patient_id=appointment.patient_id,
        doctor_id=appointment.doctor_id, specialty_id=appointment.specialty_id,
        service_date=appointment.appointment_date, sequence_number=number,
        public_code=f"{line.prefix}-{number:03d}", source="arrival", status="waiting",
        arrived_at=now, ticket_issued_at=now,
        arrival_registered_by=user.id, ticket_issued_by=user.id,
        created_at=now, updated_at=now,
    )
    db.add(ticket)
    db.flush()
    _event(db, ticket, "ARRIVED", now, user)
    _event(db, ticket, "ISSUED", now, user)
    db.add(SecurityAudit(
        organization_id=appointment.organization_id, center_id=appointment.center_id,
        actor_id=user.id, action=f"queue.arrival:appointment:{appointment.id}:ticket:{ticket.id}",
    ))
    db.commit()
    db.refresh(ticket)
    return ticket
