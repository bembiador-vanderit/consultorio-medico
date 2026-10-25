"""0046 policy, readiness, pause, and audit on isolated test data."""

from datetime import datetime, timedelta

import pytest
from fastapi import HTTPException
from sqlalchemy import select

from app.models import QueueLine, QueueTicket, QueueTicketEvent, User
from app.api.routes import queue as queue_routes
from app.schemas.provider_pause import ProviderPauseStart
from app.schemas.queue_call import QueueCallPolicyWrite
from app.schemas.queue import QueueTicketEventRead
from app.services.provider_pause import finish_pause, start_pause
from app.services.queue import complete_consultation, issue_arrival, start_consultation
from app.services.queue_call import auto_call_due_lines, call_next, line_for_access, next_call_state, policy_values, save_policy
from test_queue_arrivals import make_line, queue_db, scoped


def test_manual_default_serialized_next_and_assisted_preparation(queue_db):
    engine, ids, day = queue_db
    with scoped(engine) as db:
        line = db.get(QueueLine, make_line(db, ids).id)
        admin = db.get(User, ids["admin"])
        secretary = db.get(User, ids["secretary"])
        doctor = db.get(User, ids["doctor"])
        tickets = [issue_arrival(db, appointment_id, line.id, secretary)
                   for appointment_id in ids["appointments"][:2]]
        assert policy_values(db, line)["call_mode"] == "manual"
        assert policy_values(db, line)["preparation_seconds"] == 60
        first = call_next(db, line.id, day, secretary)
        assert first.id == tickets[0].id and first.called_by_user_id == secretary.id
        with pytest.raises(HTTPException, match="already_called"):
            call_next(db, line.id, day, doctor)
        start_consultation(db, first.id, doctor)
        assert next_call_state(db, line, day).block_reason == "in_service"
        complete_consultation(db, first.id, doctor)
        save_policy(db, line, QueueCallPolicyWrite(call_mode="assisted", preparation_seconds=60), admin)
        state = next_call_state(db, line, day)
        assert state.ready_at == first.consultation_finished_at + timedelta(seconds=60)
        assert state.block_reason == "preparing" and not state.can_call
        assert next_call_state(db, line, day, now=state.ready_at).can_call
        assert db.get(QueueTicket, tickets[1].id).status == "waiting"  # Assisted does not call.
        save_policy(db, line, QueueCallPolicyWrite(call_mode="assisted", preparation_seconds=0), admin)
        second = call_next(db, line.id, day, doctor)
        assert second.id == tickets[1].id and second.called_by_user_id == doctor.id
        events = list(db.scalars(select(QueueTicketEvent).where(
            QueueTicketEvent.queue_ticket_id == second.id, QueueTicketEvent.event_type == "CALLED")))
        assert len(events) == 1 and events[0].actor_user_id == doctor.id and events[0].call_source == "manual"


def test_automatic_waits_for_pause_and_records_no_fake_actor(queue_db):
    engine, ids, day = queue_db
    with scoped(engine) as db:
        line = db.get(QueueLine, make_line(db, ids).id)
        admin = db.get(User, ids["admin"])
        doctor = db.get(User, ids["doctor"])
        ticket = issue_arrival(db, ids["appointments"][0], line.id, admin)
        save_policy(db, line, QueueCallPolicyWrite(call_mode="automatic", preparation_seconds=0), admin)
        pause = start_pause(db, ProviderPauseStart(center_id=line.center_id, doctor_id=doctor.id, reason="lunch"), admin)
        assert next_call_state(db, line, day).block_reason == "provider_paused"
        assert auto_call_due_lines(db) == 0
        assert db.get(QueueTicket, ticket.id).status == "waiting"
        finish_pause(db, pause.id, admin)
        assert auto_call_due_lines(db) == 1
        assert auto_call_due_lines(db) == 0
        db.refresh(ticket)
        assert ticket.status == "called" and ticket.called_by_user_id is None
        events = list(db.scalars(select(QueueTicketEvent).where(
            QueueTicketEvent.queue_ticket_id == ticket.id, QueueTicketEvent.event_type == "CALLED")))
        assert len(events) == 1 and events[0].actor_user_id is None and events[0].call_source == "automatic"
        assert QueueTicketEventRead.model_validate(events[0]).call_source == "automatic"


def test_automatic_preparation_is_not_triggered_by_completion(queue_db):
    engine, ids, day = queue_db
    with scoped(engine) as db:
        line = db.get(QueueLine, make_line(db, ids).id)
        admin = db.get(User, ids["admin"])
        doctor = db.get(User, ids["doctor"])
        first, second = [issue_arrival(db, appointment_id, line.id, admin)
                         for appointment_id in ids["appointments"][:2]]
        call_next(db, line.id, day, admin)
        start_consultation(db, first.id, doctor)
        complete_consultation(db, first.id, doctor)
        assert db.get(QueueTicket, second.id).status == "waiting"
        save_policy(db, line, QueueCallPolicyWrite(call_mode="automatic", preparation_seconds=60), admin)
        assert next_call_state(db, line, day).block_reason == "preparing"
        assert auto_call_due_lines(db) == 0
        assert db.get(QueueTicket, second.id).status == "waiting"
        save_policy(db, line, QueueCallPolicyWrite(call_mode="automatic", preparation_seconds=0), admin)
        assert auto_call_due_lines(db) == 1
        assert db.get(QueueTicket, second.id).status == "called"


def test_another_line_of_same_doctor_cannot_call_during_service(queue_db):
    engine, ids, day = queue_db
    with scoped(engine) as db:
        first_line = db.get(QueueLine, make_line(db, ids, "C").id)
        second_line = db.get(QueueLine, make_line(db, ids, "T").id)
        admin = db.get(User, ids["admin"])
        doctor = db.get(User, ids["doctor"])
        first = issue_arrival(db, ids["appointments"][0], first_line.id, admin)
        second = issue_arrival(db, ids["appointments"][1], second_line.id, admin)
        call_next(db, first_line.id, day, admin)
        assert next_call_state(db, second_line, day).block_reason == "already_called"
        start_consultation(db, first.id, doctor)
        assert next_call_state(db, second_line, day).block_reason == "in_service"
        with pytest.raises(HTTPException, match="in_service"):
            call_next(db, second_line.id, day, admin)
        assert db.get(QueueTicket, second.id).status == "waiting"


def test_recall_is_blocked_during_provider_pause(queue_db):
    engine, ids, day = queue_db
    with scoped(engine) as db:
        line = db.get(QueueLine, make_line(db, ids).id)
        admin = db.get(User, ids["admin"])
        ticket = issue_arrival(db, ids["appointments"][0], line.id, admin)
        call_next(db, line.id, day, admin)
        pause = start_pause(db, ProviderPauseStart(center_id=line.center_id, doctor_id=line.doctor_id, reason="lunch"), admin)
        with pytest.raises(HTTPException, match="provider_paused"):
            queue_routes.recall(ticket.id, admin, db)
        assert db.get(QueueTicket, ticket.id).call_count == 1
        finish_pause(db, pause.id, admin)
        assert queue_routes.recall(ticket.id, admin, db).call_count == 2


def test_policy_validation_and_tenant_isolation(queue_db):
    engine, ids, day = queue_db
    with scoped(engine) as db:
        line = make_line(db, ids)
        secretary = db.get(User, ids["secretary"])
        with pytest.raises(ValueError):
            QueueCallPolicyWrite(call_mode="automatic", preparation_seconds=-1)
        with pytest.raises(ValueError):
            QueueCallPolicyWrite(call_mode="unknown", preparation_seconds=60)
        assert line_for_access(db, line.id, secretary).id == line.id
    with scoped(engine, 2) as db:
        with pytest.raises(HTTPException) as error:
            line_for_access(db, line.id, db.get(User, ids["admin"]))
        assert error.value.status_code == 404
