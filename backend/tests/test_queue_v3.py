from datetime import datetime

import pytest
from fastapi import HTTPException
from sqlalchemy import select

from app.models import Appointment, ClinicalHistory, QueueTicket, QueueTicketEvent, User
from app.services.queue import (
    call_ticket, complete_consultation, issue_arrival, mark_left,
    mark_no_response, start_consultation,
)
from test_queue_arrivals import make_line, queue_db, scoped


def test_explicit_completion_preserves_appointment_history_and_prior_events(queue_db):
    engine, ids, _ = queue_db
    with scoped(engine) as db:
        line = make_line(db, ids)
        secretary = db.get(User, ids["secretary"])
        doctor = db.get(User, ids["doctor"])
        ticket = issue_arrival(db, ids["appointments"][0], line.id, secretary)
        call_ticket(db, ticket.id, secretary)
        start_consultation(db, ticket.id, doctor)
        appointment = db.get(Appointment, ticket.appointment_id)
        original_appointment = (appointment.status, appointment.appointment_time)
        original_ticket = (
            ticket.arrived_at, ticket.first_called_at, ticket.last_called_at,
            ticket.call_count, ticket.sequence_number, ticket.consultation_started_at,
        )
        history = ClinicalHistory(
            organization_id=appointment.organization_id, patient_id=appointment.patient_id,
            appointment_id=appointment.id, doctor_id=appointment.doctor_id,
            center_id=appointment.center_id, consultation_date=appointment.appointment_date,
            status="in_progress", clinical_notes="Nota sintética",
        )
        db.add(history)
        db.commit()
        history_id = history.id
        before = datetime.utcnow()

        completed = complete_consultation(db, ticket.id, doctor)
        assert completed.status == "completed"
        assert completed.consultation_finished_by_user_id == doctor.id
        assert completed.consultation_started_at <= completed.consultation_finished_at <= datetime.utcnow()
        assert completed.consultation_finished_at >= before
        assert (
            completed.arrived_at, completed.first_called_at, completed.last_called_at,
            completed.call_count, completed.sequence_number, completed.consultation_started_at,
        ) == original_ticket
        assert (appointment.status, appointment.appointment_time) == original_appointment
        assert db.scalar(select(ClinicalHistory.id).where(ClinicalHistory.appointment_id == appointment.id)) == history_id
        assert (history.status, history.clinical_notes, history.completed_at) == ("in_progress", "Nota sintética", None)
        events = list(db.scalars(select(QueueTicketEvent).where(
            QueueTicketEvent.queue_ticket_id == ticket.id,
        ).order_by(QueueTicketEvent.id)))
        assert [event.event_type for event in events] == [
            "ARRIVED", "ISSUED", "CALLED", "SERVICE_STARTED", "SERVICE_COMPLETED",
        ]
        assert events[-1].actor_user_id == doctor.id
        assert events[-1].occurred_at == completed.consultation_finished_at
        assert (completed.consultation_finished_at - completed.consultation_started_at).total_seconds() >= 0
        assert (completed.consultation_finished_at - completed.arrived_at).total_seconds() >= 0


@pytest.mark.parametrize("initial_state", ["waiting", "called", "no_response", "left", "completed"])
def test_completion_rejects_other_states_without_side_effects(queue_db, initial_state):
    engine, ids, _ = queue_db
    with scoped(engine) as db:
        line = make_line(db, ids)
        secretary = db.get(User, ids["secretary"])
        doctor = db.get(User, ids["doctor"])
        ticket = issue_arrival(db, ids["appointments"][0], line.id, secretary)
        if initial_state != "waiting":
            call_ticket(db, ticket.id, secretary)
        if initial_state == "no_response":
            mark_no_response(db, ticket.id, secretary)
        elif initial_state == "left":
            mark_left(db, ticket.id, secretary)
        elif initial_state == "completed":
            start_consultation(db, ticket.id, doctor)
            complete_consultation(db, ticket.id, doctor)
        db.expire_all()
        before = db.get(QueueTicket, ticket.id)
        baseline = (
            before.status, before.consultation_finished_at, before.consultation_finished_by_user_id,
            before.updated_at,
        )
        event_ids = list(db.scalars(select(QueueTicketEvent.id).where(QueueTicketEvent.queue_ticket_id == ticket.id)))
        with pytest.raises(HTTPException) as error:
            complete_consultation(db, ticket.id, doctor)
        assert error.value.status_code == 409
        db.expire_all()
        after = db.get(QueueTicket, ticket.id)
        assert (after.status, after.consultation_finished_at, after.consultation_finished_by_user_id, after.updated_at) == baseline
        assert list(db.scalars(select(QueueTicketEvent.id).where(QueueTicketEvent.queue_ticket_id == ticket.id))) == event_ids


def test_only_assigned_doctor_may_complete(queue_db):
    engine, ids, _ = queue_db
    with scoped(engine) as db:
        line = make_line(db, ids)
        secretary = db.get(User, ids["secretary"])
        admin = db.get(User, ids["admin"])
        doctor = db.get(User, ids["doctor"])
        ticket = issue_arrival(db, ids["appointments"][0], line.id, secretary)
        call_ticket(db, ticket.id, secretary)
        start_consultation(db, ticket.id, doctor)
        for actor in (secretary, admin):
            with pytest.raises(HTTPException) as error:
                complete_consultation(db, ticket.id, actor)
            assert error.value.status_code == 403
        assert db.get(QueueTicket, ticket.id).status == "in_service"
        assert complete_consultation(db, ticket.id, doctor).status == "completed"
