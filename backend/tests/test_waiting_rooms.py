"""0052 room ownership, scope intersections, and legacy display compatibility."""

from fastapi import HTTPException, Response
import pytest
from sqlalchemy import select

from app.api.routes.queue_displays import create_display, public_display_state, update_display
from app.api.routes.waiting_rooms import (
    assign_lines, assign_secretaries, create_room, get_room, list_rooms, update_room,
)
from app.models import Appointment, CareCenter, QueueDisplayLine, QueueLine, QueueTicket, QueueTicketEvent, Role, SecretaryCenterScope, User
from app.schemas.queue_display import QueueDisplayWrite
from app.schemas.waiting_room import WaitingRoomLineAssignment, WaitingRoomSecretaryAssignment, WaitingRoomWrite
from app.services.queue import call_next_ticket, issue_arrival
from test_queue_arrivals import make_line, queue_db, scoped


def room_payload(center_id, name="Sala Principal", **changes):
    return WaitingRoomWrite(center_id=center_id, name=name, **changes)


def test_configurable_names_unique_per_center_and_tenant(queue_db):
    engine, ids, _ = queue_db
    with scoped(engine) as db:
        admin = db.get(User, ids["admin"])
        room = create_room(room_payload(ids["center"]), admin, db)
        assert room.name == "Sala Principal" and not room.queue_lines
        assert room.secretaries == [] and room.displays == []
        with pytest.raises(HTTPException) as duplicate:
            create_room(room_payload(ids["center"], "sala principal"), admin, db)
        assert duplicate.value.status_code == 409
        other_center = CareCenter(organization_id=1, name="Otro", city="Prueba")
        db.add(other_center); db.commit()
        second = create_room(room_payload(other_center.id), admin, db)
        assert second.name == room.name and second.id != room.id
        renamed = update_room(room.id, room_payload(ids["center"], "Sala Cardiología", is_active=False), admin, db)
        assert renamed.name == "Sala Cardiología" and not renamed.is_active
        with pytest.raises(HTTPException) as immutable:
            update_room(room.id, room_payload(other_center.id), admin, db)
        assert immutable.value.status_code == 409
    with scoped(engine, 2) as db:
        admin = db.get(User, ids["admin"])
        assert list_rooms(user=admin, db=db) == []
        with pytest.raises(HTTPException) as foreign:
            get_room(room.id, admin, db)
        assert foreign.value.status_code == 404
        assert create_room(room_payload(ids["foreign_center"]), admin, db).name == "Sala Principal"


def test_line_move_keeps_ticket_and_rejects_wrong_scope(queue_db):
    engine, ids, _ = queue_db
    with scoped(engine) as db:
        admin = db.get(User, ids["admin"])
        first = create_room(room_payload(ids["center"]), admin, db)
        second = create_room(room_payload(ids["center"], "Sala B"), admin, db)
        line = make_line(db, ids)
        ticket = issue_arrival(db, ids["appointments"][0], line.id, admin)
        before = (ticket.id, ticket.public_code, ticket.queue_line_id,
                  db.get(Appointment, ticket.appointment_id).appointment_time,
                  db.query(QueueTicketEvent).count())
        assigned = assign_lines(first.id, WaitingRoomLineAssignment(queue_line_ids=[line.id]), admin, db)
        assert [item.id for item in assigned.queue_lines] == [line.id]
        moved = assign_lines(second.id, WaitingRoomLineAssignment(queue_line_ids=[line.id]), admin, db)
        assert [item.id for item in moved.queue_lines] == [line.id]
        assert get_room(first.id, admin, db).queue_lines == []
        assert db.get(QueueLine, line.id).waiting_room_id == second.id
        after_ticket = db.get(QueueTicket, ticket.id)
        assert (after_ticket.id, after_ticket.public_code, after_ticket.queue_line_id,
                db.get(Appointment, ticket.appointment_id).appointment_time,
                db.query(QueueTicketEvent).count()) == before
        other_center = CareCenter(organization_id=1, name="Otro", city="Prueba")
        db.add(other_center); db.commit()
        other_line = QueueLine(organization_id=1, center_id=other_center.id, doctor_id=ids["doctor"],
                               name="Otra", prefix="O", is_active=True)
        db.add(other_line); db.commit()
        with pytest.raises(HTTPException) as cross_center:
            assign_lines(first.id, WaitingRoomLineAssignment(queue_line_ids=[other_line.id]), admin, db)
        assert cross_center.value.status_code == 422
        update_room(first.id, room_payload(ids["center"], is_active=False), admin, db)
        with pytest.raises(HTTPException) as inactive:
            assign_lines(first.id, WaitingRoomLineAssignment(queue_line_ids=[line.id]), admin, db)
        assert inactive.value.status_code == 409
    with scoped(engine, 2) as db:
        admin = db.get(User, ids["admin"])
        with pytest.raises(HTTPException) as cross_tenant:
            assign_lines(first.id, WaitingRoomLineAssignment(queue_line_ids=[line.id]), admin, db)
        assert cross_tenant.value.status_code == 404


def test_secretary_assignments_intersect_existing_doctor_scope(queue_db):
    engine, ids, _ = queue_db
    with scoped(engine) as db:
        admin = db.get(User, ids["admin"])
        secretary = db.get(User, ids["secretary"])
        first = create_room(room_payload(ids["center"]), admin, db)
        second = create_room(room_payload(ids["center"], "Sala B"), admin, db)
        line_a = make_line(db, ids, "C")
        doctor_b = User(email="room-doctor-b@example.com", full_name="Doctor B QA", password_hash="synthetic",
                        centers=[db.get(CareCenter, ids["center"])])
        db.add(doctor_b); db.flush()
        doctor_b.roles = [db.scalar(select(Role).where(Role.code == "doctor"))]
        line_b = QueueLine(organization_id=1, center_id=ids["center"], doctor_id=doctor_b.id,
                           name="Línea T", prefix="T", is_active=True)
        db.add(line_b)
        scope = db.get(SecretaryCenterScope, db.scalar(select(SecretaryCenterScope.id).where(
            SecretaryCenterScope.secretary_id == secretary.id)))
        scope.manage_all_doctors = False
        scope.doctors = [db.get(User, ids["doctor"])]
        db.commit()
        assign_lines(first.id, WaitingRoomLineAssignment(queue_line_ids=[line_a.id, line_b.id]), admin, db)
        for room in (first, second):
            assign_secretaries(room.id, WaitingRoomSecretaryAssignment(secretary_user_ids=[secretary.id]), admin, db)
        visible = list_rooms(user=secretary, db=db)
        assert {item.id for item in visible} == {first.id, second.id}
        assert [item.id for item in get_room(first.id, secretary, db).queue_lines] == [line_a.id]
        assert len(get_room(first.id, admin, db).queue_lines) == 2
        with pytest.raises(HTTPException) as denied:
            assign_secretaries(first.id, WaitingRoomSecretaryAssignment(secretary_user_ids=[]), secretary, db)
        assert denied.value.status_code == 403
    with scoped(engine, 2) as db:
        admin = db.get(User, ids["admin"])
        with pytest.raises(HTTPException) as foreign:
            assign_secretaries(first.id, WaitingRoomSecretaryAssignment(secretary_user_ids=[ids["secretary"]]), admin, db)
        assert foreign.value.status_code == 404


def test_room_display_derives_lines_and_preserves_explicit_override(queue_db, monkeypatch):
    engine, ids, day = queue_db
    monkeypatch.setattr("app.api.routes.queue_displays.organization_today", lambda _: day)
    with scoped(engine) as db:
        admin = db.get(User, ids["admin"])
        room = create_room(room_payload(ids["center"]), admin, db)
        line = make_line(db, ids)
        assign_lines(room.id, WaitingRoomLineAssignment(queue_line_ids=[line.id]), admin, db)
        payload = QueueDisplayWrite(center_id=ids["center"], waiting_room_id=room.id,
                                    name="TV", show_provider_name=True, lines=[])
        display = create_display(payload, admin, db)
        ticket = issue_arrival(db, ids["appointments"][0], line.id, admin)
        call_next_ticket(db, line.id, day, admin)
        state = public_display_state(display.access_token, Response(), db)
        assert state.waiting_room_name == room.name
        assert state.provider_names == [line.doctor_name]
        assert [item.ticket_code for item in state.current_calls] == [ticket.public_code]
        assert state.current_calls[0].destination == line.name
        assert "patient_id" not in state.model_dump_json()
        override = QueueDisplayWrite(center_id=ids["center"], waiting_room_id=room.id,
                                     name="TV", show_provider_name=True,
                                     lines=[{"queue_line_id": line.id, "destination": "Consultorio 3", "sort_order": 0}])
        update_display(display.id, override, admin, db)
        assert db.scalar(select(QueueDisplayLine.id).where(QueueDisplayLine.queue_display_id == display.id)) is not None
        assert public_display_state(display.access_token, Response(), db).current_calls[0].destination == "Consultorio 3"
        other_center = CareCenter(organization_id=1, name="Otro", city="Prueba")
        db.add(other_center); db.commit()
        with pytest.raises(HTTPException) as invalid:
            create_display(QueueDisplayWrite(center_id=other_center.id, waiting_room_id=room.id, name="TV ajena"), admin, db)
        assert invalid.value.status_code == 422
