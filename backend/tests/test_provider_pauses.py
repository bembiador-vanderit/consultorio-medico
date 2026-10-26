from datetime import date, datetime, timedelta

import pytest
from fastapi import HTTPException
from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.routes.provider_pauses import _read
from app.models import Appointment, CareCenter, ClinicalHistory, OrganizationMembership, Permission, ProviderOperationalPause, Role, User
from app.schemas.provider_pause import ProviderPauseStart
from app.services.provider_pause import current_pause, finish_pause, is_provider_paused, pause_history, start_pause
from test_queue_arrivals import make_line, queue_db, scoped


def grant_clinical(engine):
    with Session(engine) as db:
        permission = Permission(code="clinical:access", description="clinical:access")
        role = db.scalar(select(Role).where(Role.code == "doctor"))
        role.permissions.append(permission)
        db.commit()


def request(ids, reason="lunch"):
    return ProviderPauseStart(center_id=ids["center"], reason=reason, notes="  Pausa sintética  ")


def test_pause_lifecycle_history_server_timestamps_and_unchanged_queue(queue_db):
    engine, ids, _ = queue_db
    grant_clinical(engine)
    with scoped(engine) as db:
        line = make_line(db, ids)
        admin = db.get(User, ids["admin"])
        doctor = db.get(User, ids["doctor"])
        from app.services.queue import issue_arrival
        ticket = issue_arrival(db, ids["appointments"][0], line.id, admin)
        appointment = db.get(Appointment, ticket.appointment_id)
        original_ticket = (ticket.status, ticket.arrived_at, ticket.sequence_number)
        original_appointment = (appointment.status, appointment.appointment_time)
        original_history_ids = list(db.scalars(select(ClinicalHistory.id)))

        before = datetime.utcnow()
        pause = start_pause(db, request(ids), doctor)
        assert before <= pause.actual_started_at <= datetime.utcnow()
        assert pause.started_by_user_id == doctor.id and pause.finished_by_user_id is None
        assert pause.notes == "Pausa sintética"
        assert current_pause(db, ids["center"], doctor.id, admin).id == pause.id
        assert is_provider_paused(db, doctor.id, ids["center"])
        assert pause_history(db, ids["center"], doctor.id, doctor)[0].id == pause.id
        assert pause_history(db, ids["center"], doctor.id, doctor, date.today())[0].id == pause.id
        assert pause_history(db, ids["center"], doctor.id, doctor, date.today() - timedelta(days=3)) == []
        with pytest.raises(HTTPException) as duplicate:
            start_pause(db, request(ids, "meeting"), doctor)
        assert duplicate.value.status_code == 409
        assert db.scalar(select(ProviderOperationalPause.id).where(ProviderOperationalPause.actual_finished_at.is_(None))) == pause.id

        finished = finish_pause(db, pause.id, doctor)
        assert finished.actual_finished_at >= finished.actual_started_at
        assert finished.finished_by_user_id == doctor.id
        assert _read(finished).duration_seconds >= 0
        assert current_pause(db, ids["center"], doctor.id, doctor) is None
        assert not is_provider_paused(db, doctor.id, ids["center"])
        with pytest.raises(HTTPException) as repeated:
            finish_pause(db, pause.id, doctor)
        assert repeated.value.status_code == 409
        second = start_pause(db, request(ids, "procedure"), doctor)
        assert second.id != pause.id and len(pause_history(db, ids["center"], doctor.id, doctor)) == 2
        db.refresh(ticket); db.refresh(appointment)
        assert (ticket.status, ticket.arrived_at, ticket.sequence_number) == original_ticket
        assert (appointment.status, appointment.appointment_time) == original_appointment
        assert list(db.scalars(select(ClinicalHistory.id))) == original_history_ids


def test_pause_roles_scopes_denials_and_tenant_isolation(queue_db):
    engine, ids, _ = queue_db
    grant_clinical(engine)
    with Session(engine) as db:
        colleague = User(
            email="colleague@synthetic.test", full_name="Otro médico", password_hash="synthetic",
            centers=[db.get(CareCenter, ids["center"])],
            memberships=[OrganizationMembership(
                organization_id=1,
                roles=[db.scalar(select(Role).where(Role.code == "doctor"))],
            )],
        )
        db.add(colleague)
        db.commit()
        colleague_id = colleague.id
    with scoped(engine) as db:
        doctor = db.get(User, ids["doctor"])
        secretary = db.get(User, ids["secretary"])
        admin = db.get(User, ids["admin"])
        other_doctor = db.get(User, colleague_id)
        pause = start_pause(db, request(ids, "emergency"), doctor)
        pause_id = pause.id
        assert current_pause(db, ids["center"], doctor.id, secretary).id == pause.id
        assert len(pause_history(db, ids["center"], doctor.id, secretary)) == 1
        for operation in (
            lambda: start_pause(db, request(ids), secretary),
            lambda: finish_pause(db, pause.id, secretary),
            lambda: finish_pause(db, pause.id, other_doctor),
            lambda: start_pause(db, ProviderPauseStart(center_id=ids["foreign_center"], reason="lunch"), doctor),
        ):
            with pytest.raises(HTTPException) as forbidden:
                operation()
            assert forbidden.value.status_code in (403, 404)
        doctor.denied_permissions = ["clinical:access"]
        db.commit()
        with pytest.raises(HTTPException) as denied:
            finish_pause(db, pause.id, doctor)
        assert denied.value.status_code == 403
        assert finish_pause(db, pause.id, admin).finished_by_user_id == admin.id
        managed = start_pause(db, ProviderPauseStart(
            center_id=ids["center"], doctor_id=doctor.id, reason="meeting",
        ), admin)
        assert managed.started_by_user_id == admin.id and managed.doctor_id == doctor.id
        assert finish_pause(db, managed.id, admin).finished_by_user_id == admin.id
        secretary.centers.clear()
        db.commit()
        with pytest.raises(HTTPException) as no_scope:
            current_pause(db, ids["center"], doctor.id, secretary)
        assert no_scope.value.status_code == 403

    with scoped(engine, 2) as db:
        other_admin = db.get(User, ids["admin"])
        with pytest.raises(HTTPException) as hidden:
            finish_pause(db, pause_id, other_admin)
        assert hidden.value.status_code == 404
        assert db.get(ProviderOperationalPause, pause_id) is None


def test_pause_start_rejects_client_timestamp_and_bad_reason():
    for payload in (
        {"center_id": 1, "reason": "lunch", "actual_started_at": "2030-01-01T00:00:00"},
        {"center_id": 1, "reason": "texto libre"},
    ):
        with pytest.raises(ValidationError):
            ProviderPauseStart.model_validate(payload)
