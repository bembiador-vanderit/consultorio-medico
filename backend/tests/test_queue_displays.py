"""0047 public display privacy, configuration, and tenant isolation."""

from datetime import datetime, time, timedelta
from hashlib import sha256

import pytest
from fastapi import HTTPException, Response
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.api.routes.queue_displays import (
    create_display, list_displays, public_display_state, rotate_display_token, update_display,
)
from app.db import get_db
from app.main import app
from app.models import Appointment, CareCenter, DoctorAgendaSetting, QueueDisplay, QueueLine, QueueTicketEvent, Role, User
from app.models.administration import SecurityAudit
from app.schemas.queue_display import QueueDisplayWrite
from app.services.queue import call_next_ticket, issue_arrival
from test_queue_arrivals import make_line, queue_db, scoped


def payload(center_id, lines, **changes):
    return QueueDisplayWrite(center_id=center_id, name="Sala Principal",
                             lines=[{"queue_line_id": line.id, "destination": f"Consultorio {index + 1}",
                                     "sort_order": index} for index, line in enumerate(lines)], **changes)


def test_create_update_rotate_token_and_audit(queue_db):
    engine, ids, _ = queue_db
    with scoped(engine) as db:
        admin = db.get(User, ids["admin"])
        line = make_line(db, ids)
        created = create_display(payload(ids["center"], [line]), admin, db)
        assert len(created.access_token) >= 32
        assert created.lines[0].destination == "Consultorio 1"
        stored = db.get(QueueDisplay, created.id)
        assert stored.token_hash == sha256(created.access_token.encode()).hexdigest()
        assert created.access_token != stored.token_hash
        assert len(list_displays(user=admin, db=db)) == 1
        changed = update_display(created.id, payload(ids["center"], [line],
                                    show_service_name=True, show_provider_name=True,
                                    recent_call_limit=3), admin, db)
        assert changed.show_service_name and changed.show_provider_name
        assert changed.recent_call_limit == 3
        rotated = rotate_display_token(created.id, admin, db)
        assert rotated.access_token != created.access_token
        actions = list(db.scalars(select(SecurityAudit.action).where(SecurityAudit.center_id == ids["center"])))
        assert {f"queue.display.create:{created.id}", f"queue.display.update:{created.id}",
                f"queue.display.rotate_token:{created.id}"}.issubset(set(actions))
        with pytest.raises(HTTPException) as old:
            public_display_state(created.access_token, Response(), db)
        assert old.value.status_code == 404
        assert public_display_state(rotated.access_token, Response(), db).current_calls == []


def test_public_state_three_lines_privacy_order_and_terminal_status(queue_db, monkeypatch):
    engine, ids, day = queue_db
    monkeypatch.setattr("app.api.routes.queue_displays.organization_today", lambda _: day)
    with scoped(engine) as db:
        admin = db.get(User, ids["admin"])
        lines = [make_line(db, ids, prefix) for prefix in ("C", "T", "S")]
        display = create_display(payload(ids["center"], lines), admin, db)
        tickets = [issue_arrival(db, ids["appointments"][index], line.id, admin)
                   for index, line in enumerate(lines)]
        for line in lines:
            call_next_ticket(db, line.id, day, admin)
        now = datetime.utcnow()
        for index, ticket in enumerate(tickets):
            ticket.last_called_at = now + timedelta(seconds=index)
        db.commit()
        before_events = db.query(QueueTicketEvent).count()
        response = Response()
        state = public_display_state(display.access_token, response, db)
        assert response.headers["Cache-Control"] == "no-store"
        assert [call.ticket_code for call in state.current_calls] == ["S-001", "T-001", "C-001"]
        assert [call.destination for call in state.current_calls] == ["Consultorio 3", "Consultorio 2", "Consultorio 1"]
        assert all(call.provider_name is None and call.queue_line_name is None for call in state.current_calls)
        serialized = state.model_dump_json()
        assert all(key not in serialized for key in ("patient_id", "appointment_id", "clinical_history_id", "diagnosis", "phone", "insurance", "Paciente"))
        assert db.query(QueueTicketEvent).count() == before_events
        tickets[1].status = "in_service"
        db.commit()
        state = public_display_state(display.access_token, Response(), db)
        assert [call.ticket_code for call in state.current_calls] == ["S-001", "C-001"]
        assert [call.ticket_code for call in state.recent_calls] == ["T-001"]


def test_invalid_inactive_and_other_tenant_tokens_are_hidden(queue_db):
    engine, ids, _ = queue_db
    with scoped(engine) as db:
        admin = db.get(User, ids["admin"])
        line = make_line(db, ids)
        created = create_display(payload(ids["center"], [line]), admin, db)
        for token in ("invalid", "x" * 43):
            with pytest.raises(HTTPException) as invalid:
                public_display_state(token, Response(), db)
            assert invalid.value.status_code == 404
    with scoped(engine, 2) as db:
        with pytest.raises(HTTPException) as foreign:
            public_display_state(created.access_token, Response(), db)
        assert foreign.value.status_code == 404
    with scoped(engine) as db:
        admin = db.get(User, ids["admin"])
        update_display(created.id, payload(ids["center"], [db.get(QueueLine, line.id)], is_active=False), admin, db)
        with pytest.raises(HTTPException) as inactive:
            public_display_state(created.access_token, Response(), db)
        assert inactive.value.status_code == 404


def test_cross_center_line_and_non_admin_rejected(queue_db):
    engine, ids, _ = queue_db
    with scoped(engine) as db:
        admin = db.get(User, ids["admin"])
        doctor = db.get(User, ids["doctor"])
        line = make_line(db, ids)
        other_center = CareCenter(organization_id=1, name="Centro B", city="Prueba")
        db.add(other_center)
        db.commit()
        with pytest.raises(HTTPException) as cross_center:
            create_display(payload(other_center.id, [line]), admin, db)
        assert cross_center.value.status_code == 422
        with pytest.raises(HTTPException) as denied:
            create_display(payload(ids["center"], [line]), doctor, db)
        assert denied.value.status_code == 403
    with scoped(engine, 2) as db:
        admin = db.get(User, ids["admin"])
        with pytest.raises(HTTPException) as cross_tenant:
            create_display(payload(ids["foreign_center"], [line]), admin, db)
        assert cross_tenant.value.status_code == 404


def test_recent_limit_and_optional_public_names(queue_db, monkeypatch):
    engine, ids, day = queue_db
    monkeypatch.setattr("app.api.routes.queue_displays.organization_today", lambda _: day)
    with scoped(engine) as db:
        admin = db.get(User, ids["admin"])
        line = make_line(db, ids)
        created = create_display(payload(ids["center"], [line], recent_call_limit=3,
                                         show_service_name=True, show_provider_name=True), admin, db)
        for index in range(4):
            ticket = issue_arrival(db, ids["appointments"][index], line.id, admin)
            call_next_ticket(db, line.id, day, admin)
            ticket.status = "completed"
            ticket.last_called_at = datetime(2030, 10, 15, 10, index)
            db.commit()
        state = public_display_state(created.access_token, Response(), db)
        assert not state.current_calls
        assert len(state.recent_calls) == 3
        assert [call.ticket_code for call in state.recent_calls] == ["C-004", "C-003", "C-002"]
        assert state.recent_calls[0].queue_line_name == line.name
        assert state.recent_calls[0].provider_name == line.doctor_name


def test_public_http_response_requires_no_clinical_login_and_is_allowlisted(queue_db, monkeypatch):
    engine, ids, day = queue_db
    monkeypatch.setattr("app.api.routes.queue_displays.organization_today", lambda _: day)
    with scoped(engine) as db:
        admin = db.get(User, ids["admin"])
        line = make_line(db, ids)
        created = create_display(payload(ids["center"], [line]), admin, db)
        issue_arrival(db, ids["appointments"][0], line.id, admin)
        call_next_ticket(db, line.id, day, admin)

    def test_db():
        with scoped(engine) as db:
            yield db

    app.dependency_overrides[get_db] = test_db
    try:
        response = TestClient(app).get(f"/api/v1/queue/displays/{created.access_token}/state")
    finally:
        app.dependency_overrides.pop(get_db, None)
    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store"
    assert set(response.json()) == {"display_name", "center_name", "current_calls", "recent_calls", "updated_at", "audio"}
    assert set(response.json()["current_calls"][0]) == {"ticket_code", "destination", "called_at", "call_revision", "queue_line_name", "provider_name"}


def test_three_distinct_doctors_share_one_center_display(queue_db, monkeypatch):
    engine, ids, day = queue_db
    monkeypatch.setattr("app.api.routes.queue_displays.organization_today", lambda _: day)
    with scoped(engine) as db:
        admin = db.get(User, ids["admin"])
        center = db.get(CareCenter, ids["center"])
        doctor_role = db.scalar(select(Role).where(Role.code == "doctor"))
        first_line = make_line(db, ids, "C")
        doctors = [db.get(User, ids["doctor"])]
        appointments = [ids["appointments"][0]]
        lines = [first_line]
        for index, prefix in enumerate(("T", "S"), start=1):
            doctor = User(email=f"doctor-{index}@synthetic.test", full_name=f"Médico {index}",
                          password_hash="synthetic", centers=[center])
            db.add(doctor)
            db.flush()
            doctor.roles = [doctor_role]
            db.add(DoctorAgendaSetting(organization_id=1, doctor_id=doctor.id,
                                       center_id=center.id, base_mode="queue"))
            original = db.get(Appointment, ids["appointments"][index])
            appointment = Appointment(organization_id=1, patient_id=original.patient_id,
                                      doctor_id=doctor.id, center_id=center.id,
                                      appointment_date=day, appointment_time=time(12, index),
                                      schedule_mode="queue", status="scheduled")
            db.add(appointment)
            line = QueueLine(organization_id=1, center_id=center.id, doctor_id=doctor.id,
                             name=f"Servicio {prefix}", prefix=prefix, is_active=True)
            db.add(line)
            db.flush()
            doctors.append(doctor)
            appointments.append(appointment.id)
            lines.append(line)
        db.commit()
        display = create_display(payload(ids["center"], lines, show_provider_name=True), admin, db)
        for line, appointment_id in zip(lines, appointments):
            issue_arrival(db, appointment_id, line.id, admin)
            call_next_ticket(db, line.id, day, admin)
        state = public_display_state(display.access_token, Response(), db)
        assert {call.ticket_code for call in state.current_calls} == {"C-001", "T-001", "S-001"}
        assert {call.provider_name for call in state.current_calls} == {doctor.full_name for doctor in doctors}
