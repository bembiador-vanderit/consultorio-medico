"""PostgreSQL-backed readiness and serialized line calls.

The line row is the serialization point for human and automatic callers.
No process-local timer or browser clock is authoritative.
"""

from datetime import date, datetime, timedelta

from fastapi import HTTPException
from sqlalchemy import inspect, select
from sqlalchemy.orm import Session

from app.models import ProviderOperationalPause, QueueCallPolicy, QueueLine, QueueTicket, User
from app.schemas.queue_call import NextCallState, QueueCallPolicyWrite
from app.services import queue as queue_service
from app.services.queue import _event, ensure_line_operator


def policy_schema_ready(db: Session) -> bool:
    return inspect(db.bind).has_table("queue_call_policies")


def require_policy_schema(db: Session) -> None:
    if not policy_schema_ready(db):
        raise HTTPException(409, "La configuración 0046 aún no está habilitada en esta base")


def line_for_access(db: Session, line_id: int, user: User | None, *, lock: bool = False) -> QueueLine:
    query = select(QueueLine).where(QueueLine.id == line_id)
    if lock:
        query = query.with_for_update().execution_options(populate_existing=True)
    line = db.scalar(query)
    if line is None or (db.info.get("access_scope") == "tenant" and line.organization_id != db.info["organization_id"]):
        raise HTTPException(404, "Línea de turnos no encontrada")
    if user is not None:
        ensure_line_operator(user, line, db)
    return line


def _policy(db: Session, line: QueueLine) -> QueueCallPolicy | None:
    return db.scalar(select(QueueCallPolicy).where(
        QueueCallPolicy.organization_id == line.organization_id,
        QueueCallPolicy.center_id == line.center_id,
        QueueCallPolicy.queue_line_id == line.id,
    ))


def policy_values(db: Session, line: QueueLine) -> dict:
    policy = _policy(db, line)
    return {
        "queue_line_id": line.id,
        "center_id": line.center_id,
        "call_mode": policy.call_mode if policy else "manual",
        "preparation_seconds": policy.preparation_seconds if policy else 60,
        "start_consultation_can_call": line.call_on_consultation_start,
    }


def save_policy(db: Session, line: QueueLine, payload: QueueCallPolicyWrite, user: User) -> dict:
    policy = _policy(db, line)
    now = datetime.utcnow()
    if policy is None:
        policy = QueueCallPolicy(
            organization_id=line.organization_id, center_id=line.center_id, queue_line_id=line.id,
            call_mode=payload.call_mode, preparation_seconds=payload.preparation_seconds,
            created_at=now, updated_at=now,
        )
        db.add(policy)
    else:
        policy.call_mode = payload.call_mode
        policy.preparation_seconds = payload.preparation_seconds
        policy.updated_at = now
    line.call_on_consultation_start = payload.start_consultation_can_call
    line.updated_at = now
    from app.models.administration import SecurityAudit
    db.add(SecurityAudit(organization_id=line.organization_id, center_id=line.center_id,
                         actor_id=user.id, action=f"queue.call_policy.update:{line.id}"))
    db.commit()
    return policy_values(db, line)


def get_next_waiting_ticket(db: Session, line: QueueLine, day: date) -> QueueTicket | None:
    return db.scalar(select(QueueTicket).where(
        QueueTicket.organization_id == line.organization_id,
        QueueTicket.center_id == line.center_id,
        QueueTicket.queue_line_id == line.id,
        QueueTicket.service_date == day,
        QueueTicket.status == "waiting",
    ).order_by(QueueTicket.sequence_number, QueueTicket.id).limit(1))


def next_call_state(db: Session, line: QueueLine, day: date, *, now: datetime | None = None) -> NextCallState:
    now = now or datetime.utcnow()
    values = policy_values(db, line)
    in_service = db.scalar(select(QueueTicket.id).where(
        QueueTicket.organization_id == line.organization_id,
        QueueTicket.center_id == line.center_id, QueueTicket.doctor_id == line.doctor_id,
        QueueTicket.service_date == day,
        QueueTicket.status == "in_service",
    ).limit(1))
    called = db.scalar(select(QueueTicket.id).where(
        QueueTicket.organization_id == line.organization_id,
        QueueTicket.center_id == line.center_id, QueueTicket.doctor_id == line.doctor_id,
        QueueTicket.service_date == day,
        QueueTicket.status == "called",
    ).limit(1))
    candidate = get_next_waiting_ticket(db, line, day)
    last_completed = db.scalar(select(QueueTicket.consultation_finished_at).where(
        QueueTicket.organization_id == line.organization_id,
        QueueTicket.center_id == line.center_id, QueueTicket.doctor_id == line.doctor_id,
        QueueTicket.service_date == day,
        QueueTicket.status == "completed", QueueTicket.consultation_finished_at.is_not(None),
    ).order_by(QueueTicket.consultation_finished_at.desc()).limit(1))
    ready_at = last_completed + timedelta(seconds=values["preparation_seconds"]) if last_completed else None
    ready = values["call_mode"] == "manual" or ready_at is None or now >= ready_at
    paused = db.scalar(select(ProviderOperationalPause.id).where(
        ProviderOperationalPause.organization_id == line.organization_id,
        ProviderOperationalPause.center_id == line.center_id,
        ProviderOperationalPause.doctor_id == line.doctor_id,
        ProviderOperationalPause.actual_finished_at.is_(None),
    ).limit(1)) is not None
    reason = None
    if day != queue_service.organization_today(db):
        reason = "wrong_day"
    elif not line.is_active:
        reason = "line_inactive"
    elif not line.center.is_active or not line.doctor.is_active:
        reason = "provider_unavailable"
    elif paused:
        reason = "provider_paused"
    elif in_service is not None:
        reason = "in_service"
    elif called is not None:
        reason = "already_called"
    elif candidate is None:
        reason = "no_waiting"
    elif not ready:
        reason = "preparing"
    return NextCallState(
        queue_line_id=line.id, call_mode=values["call_mode"], preparation_seconds=values["preparation_seconds"],
        provider_paused=paused, current_in_service_ticket_id=in_service,
        next_waiting_ticket_id=candidate.id if candidate else None,
        next_waiting_public_code=candidate.public_code if candidate else None,
        last_service_completed_at=last_completed, ready_at=ready_at, server_now=now,
        ready=ready, can_call=reason is None, block_reason=reason,
    )


def _lock_doctor_then_line(db: Session, line_id: int, user: User | None) -> QueueLine:
    line = line_for_access(db, line_id, user)
    db.scalar(select(User.id).where(User.id == line.doctor_id).with_for_update())
    return line_for_access(db, line_id, user, lock=True)


def call_next(db: Session, line_id: int, day: date, user: User | None, *, automatic: bool = False,
              expected_ticket_id: int | None = None) -> QueueTicket:
    require_policy_schema(db)
    line = _lock_doctor_then_line(db, line_id, user)
    state = next_call_state(db, line, day)
    if automatic and state.call_mode != "automatic":
        raise HTTPException(409, "La línea ya no está en llamada automática")
    if not state.can_call:
        raise HTTPException(409, state.block_reason or "La línea no está lista")
    if expected_ticket_id is not None and state.next_waiting_ticket_id != expected_ticket_id:
        raise HTTPException(409, "Debe llamarse el siguiente turno en espera")
    ticket = db.scalar(select(QueueTicket).where(QueueTicket.id == state.next_waiting_ticket_id).with_for_update())
    if ticket is None or ticket.status != "waiting":
        raise HTTPException(409, "El siguiente turno cambió de estado")
    now = datetime.utcnow()
    ticket.status = "called"
    ticket.first_called_at = ticket.first_called_at or now
    ticket.last_called_at = now
    ticket.called_by_user_id = user.id if user is not None else None
    ticket.call_count += 1
    ticket.updated_at = now
    _event(db, ticket, "CALLED", now, user)
    db.commit()
    db.refresh(ticket)
    return ticket


def auto_call_due_lines(db: Session) -> int:
    """Idempotent across workers: each attempt rechecks policy and state under row locks."""
    if not policy_schema_ready(db):
        return 0
    line_ids = list(db.scalars(select(QueueCallPolicy.queue_line_id).where(
        QueueCallPolicy.call_mode == "automatic",
    )))
    day = queue_service.organization_today(db)
    called = 0
    for line_id in line_ids:
        try:
            call_next(db, line_id, day, None, automatic=True)
            called += 1
        except HTTPException as exc:
            db.rollback()
            if exc.status_code != 409:
                raise
    return called
