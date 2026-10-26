import pytest
from fastapi import HTTPException
from sqlalchemy import select

from app.models import QueueLine, QueueTicket, QueueTicketEvent, User
from app.services.queue import (
    call_next_ticket,
    call_ticket,
    issue_arrival,
    mark_left,
    mark_no_response,
    recall_ticket,
    start_consultation,
)
from test_queue_arrivals import make_line, queue_db, scoped


def test_call_recall_start_and_terminal_events_preserve_order(queue_db):
    engine, ids, day = queue_db
    with scoped(engine) as db:
        line = make_line(db, ids)
        admin = db.get(User, ids["admin"])
        doctor = db.get(User, ids["doctor"])
        tickets = [issue_arrival(db, appointment_id, line.id, admin) for appointment_id in ids["appointments"][:3]]

        first = call_next_ticket(db, line.id, day, admin)
        assert first.id == tickets[0].id and first.status == "called" and first.call_count == 1
        recalled = recall_ticket(db, first.id, admin)
        assert recalled.first_called_at is not None and recalled.last_called_at is not None
        assert recalled.call_count == 2 and recalled.status == "called"
        started = start_consultation(db, first.id, doctor)
        assert started.status == "in_service" and started.consultation_started_at is not None

        second = call_next_ticket(db, line.id, day, admin)
        assert second.id == tickets[1].id
        assert mark_no_response(db, second.id, admin).status == "no_response"
        third = call_next_ticket(db, line.id, day, admin)
        assert third.id == tickets[2].id
        assert mark_left(db, third.id, admin).status == "left"

        events = list(db.scalars(select(QueueTicketEvent).where(QueueTicketEvent.queue_ticket_id == first.id).order_by(QueueTicketEvent.id)))
        assert [event.event_type for event in events] == ["ARRIVED", "ISSUED", "CALLED", "RECALLED", "SERVICE_STARTED"]
        assert db.get(first.__class__, first.id).status == "in_service"


def test_start_waiting_requires_explicit_call_by_default(queue_db):
    engine, ids, day = queue_db
    with scoped(engine) as db:
        line = make_line(db, ids)
        admin = db.get(User, ids["admin"])
        doctor = db.get(User, ids["doctor"])
        ticket = issue_arrival(db, ids["appointments"][0], line.id, admin)
        with pytest.raises(Exception) as error:
            start_consultation(db, ticket.id, doctor)
        assert getattr(error.value, "status_code", None) == 409

        db.get(QueueLine, line.id).call_on_consultation_start = True
        db.commit()
        ticket = start_consultation(db, ticket.id, doctor)
        assert ticket.status == "in_service" and ticket.call_count == 1


def test_call_waiting_success_and_recall_called_success(queue_db):
    engine, ids, _ = queue_db
    with scoped(engine) as db:
        line = make_line(db, ids)
        secretary = db.get(User, ids["secretary"])
        doctor = db.get(User, ids["doctor"])
        ticket = issue_arrival(db, ids["appointments"][0], line.id, secretary)
        first = call_ticket(db, ticket.id, secretary)
        assert first.status == "called" and first.call_count == 1
        assert first.first_called_at == first.last_called_at
        assert first.called_by_user_id == secretary.id
        first_time = first.first_called_at

        recalled = recall_ticket(db, ticket.id, doctor)
        assert recalled.status == "called" and recalled.call_count == 2
        assert recalled.first_called_at == first_time
        assert recalled.last_called_at >= first_time
        assert recalled.called_by_user_id == doctor.id
        events = list(db.scalars(select(QueueTicketEvent).where(QueueTicketEvent.queue_ticket_id == ticket.id).order_by(QueueTicketEvent.id)))
        assert [event.event_type for event in events] == ["ARRIVED", "ISSUED", "CALLED", "RECALLED"]
        assert [event.actor_user_id for event in events[2:]] == [secretary.id, doctor.id]


def test_call_already_called_conflict_and_failed_call_does_not_create_event(queue_db):
    engine, ids, _ = queue_db
    with scoped(engine) as db:
        line = make_line(db, ids)
        secretary = db.get(User, ids["secretary"])
        ticket = issue_arrival(db, ids["appointments"][0], line.id, secretary)
        called = call_ticket(db, ticket.id, secretary)
        original = (called.first_called_at, called.last_called_at, called.called_by_user_id, called.call_count)
        with pytest.raises(HTTPException) as error:
            call_ticket(db, ticket.id, secretary)
        assert error.value.status_code == 409
        db.expire_all()
        unchanged = db.get(QueueTicket, ticket.id)
        assert (unchanged.first_called_at, unchanged.last_called_at, unchanged.called_by_user_id, unchanged.call_count) == original
        events = list(db.scalars(select(QueueTicketEvent.event_type).where(QueueTicketEvent.queue_ticket_id == ticket.id)))
        assert events.count("CALLED") == 1 and "RECALLED" not in events


def test_recall_waiting_conflict(queue_db):
    engine, ids, _ = queue_db
    with scoped(engine) as db:
        line = make_line(db, ids)
        secretary = db.get(User, ids["secretary"])
        ticket = issue_arrival(db, ids["appointments"][0], line.id, secretary)
        with pytest.raises(HTTPException) as error:
            recall_ticket(db, ticket.id, secretary)
        assert error.value.status_code == 409
        db.expire_all()
        unchanged = db.get(QueueTicket, ticket.id)
        assert unchanged.status == "waiting" and unchanged.call_count == 0
        assert not db.scalar(select(QueueTicketEvent.id).where(QueueTicketEvent.queue_ticket_id == ticket.id, QueueTicketEvent.event_type == "RECALLED"))


@pytest.mark.parametrize("terminal", ["in_service", "no_response", "left"])
def test_call_and_recall_reject_advanced_states(queue_db, terminal):
    engine, ids, _ = queue_db
    with scoped(engine) as db:
        line = make_line(db, ids)
        secretary = db.get(User, ids["secretary"])
        doctor = db.get(User, ids["doctor"])
        ticket = issue_arrival(db, ids["appointments"][0], line.id, secretary)
        call_ticket(db, ticket.id, secretary)
        if terminal == "in_service":
            start_consultation(db, ticket.id, doctor)
        elif terminal == "no_response":
            mark_no_response(db, ticket.id, secretary)
        else:
            mark_left(db, ticket.id, secretary)
        before = db.scalar(select(QueueTicketEvent.id).where(QueueTicketEvent.queue_ticket_id == ticket.id).order_by(QueueTicketEvent.id.desc()))
        for operation in (call_ticket, recall_ticket):
            with pytest.raises(HTTPException) as error:
                operation(db, ticket.id, secretary)
            assert error.value.status_code == 409
        db.expire_all()
        assert db.get(QueueTicket, ticket.id).status == terminal
        after = db.scalar(select(QueueTicketEvent.id).where(QueueTicketEvent.queue_ticket_id == ticket.id).order_by(QueueTicketEvent.id.desc()))
        assert after == before
