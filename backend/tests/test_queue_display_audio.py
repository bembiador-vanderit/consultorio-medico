"""0048 speech settings remain presentation-only and tenant scoped."""

import pytest
from fastapi import HTTPException, Response
from pydantic import ValidationError

from app.api.routes.queue_displays import create_display, public_display_state, update_display, update_display_voice
from app.models import QueueTicketEvent, User
from app.schemas.queue_display import QueueDisplayVoiceWrite, QueueDisplayWrite
from app.services.queue import call_next_ticket, issue_arrival, recall_ticket
from test_queue_arrivals import make_line, queue_db, scoped


def payload(center_id, line_id, **audio):
    return QueueDisplayWrite(center_id=center_id, name="Pantalla sintética",
                             lines=[{"queue_line_id": line_id, "destination": "Consultorio 3", "sort_order": 0}],
                             **audio)


def test_audio_defaults_disabled_and_update_does_not_touch_queue(queue_db):
    engine, ids, _ = queue_db
    with scoped(engine) as db:
        admin = db.get(User, ids["admin"])
        line = make_line(db, ids)
        created = create_display(payload(ids["center"], line.id), admin, db)
        assert created.audio_enabled is False
        assert created.audio_volume == created.audio_rate == created.audio_pitch == 1
        assert created.repeat_count == 1 and created.repeat_delay_ms == 1000
        before_events = db.query(QueueTicketEvent).count()
        changed = update_display(created.id, payload(ids["center"], line.id,
            audio_enabled=True, audio_volume=0.7, audio_language="es", audio_rate=1.2,
            audio_pitch=0.8, repeat_count=4, repeat_delay_ms=2500,
            announce_service_name=True, announce_provider_name=True), admin, db)
        assert changed.audio_enabled and changed.audio_volume == 0.7
        assert changed.repeat_count == 4 and changed.repeat_delay_ms == 2500
        assert db.query(QueueTicketEvent).count() == before_events
        # Audio may not expose names unless 0047's visible-name switches are also on.
        public = public_display_state(created.access_token, Response(), db)
        assert public.audio.announce_service_name is False
        assert public.audio.announce_provider_name is False


@pytest.mark.parametrize("change", [
    {"audio_volume": -0.1}, {"audio_volume": 1.1},
    {"audio_rate": 0.4}, {"audio_rate": 2.1},
    {"audio_pitch": 0.4}, {"audio_pitch": 2.1},
    {"repeat_count": 0}, {"repeat_count": 11},
    {"repeat_delay_ms": 999}, {"repeat_delay_ms": 5001},
    {"audio_language": "en-US"},
])
def test_audio_settings_reject_invalid_values(change):
    with pytest.raises(ValidationError):
        payload(1, 1, **change)


def test_call_revision_distinguishes_recall_without_private_data(queue_db, monkeypatch):
    engine, ids, day = queue_db
    monkeypatch.setattr("app.api.routes.queue_displays.organization_today", lambda _: day)
    with scoped(engine) as db:
        admin = db.get(User, ids["admin"])
        line = make_line(db, ids)
        display = create_display(payload(ids["center"], line.id, audio_enabled=True), admin, db)
        issue_arrival(db, ids["appointments"][0], line.id, admin)
        ticket = call_next_ticket(db, line.id, day, admin)
        first = public_display_state(display.access_token, Response(), db)
        assert first.current_calls[0].call_revision == 1
        recall_ticket(db, ticket.id, admin)
        recalled = public_display_state(display.access_token, Response(), db)
        assert recalled.current_calls[0].call_revision == 2
        assert recalled.current_calls[0].ticket_code == first.current_calls[0].ticket_code
        serialized = recalled.model_dump_json()
        assert all(private not in serialized for private in (
            "patient_id", "appointment_id", "clinical_history_id", "actor_user_id",
            "phone", "diagnosis", "insurance",
        ))
        assert db.query(QueueTicketEvent).count() == 4  # arrival, issue, call, recall


def test_foreign_tenant_cannot_modify_audio(queue_db):
    engine, ids, _ = queue_db
    with scoped(engine) as db:
        admin = db.get(User, ids["admin"])
        line = make_line(db, ids)
        display = create_display(payload(ids["center"], line.id), admin, db)
    with scoped(engine, 2) as db:
        admin = db.get(User, ids["admin"])
        with pytest.raises(HTTPException) as denied:
            update_display(display.id, payload(ids["center"], line.id, audio_enabled=True), admin, db)
        assert denied.value.status_code == 404


def test_admin_selects_local_voice_reference_without_changing_queue(queue_db):
    engine, ids, _ = queue_db
    with scoped(engine) as db:
        admin = db.get(User, ids["admin"])
        line = make_line(db, ids)
        display = create_display(payload(ids["center"], line.id, audio_enabled=True), admin, db)
        before_events = db.query(QueueTicketEvent).count()
        selected = update_display_voice(display.id, QueueDisplayVoiceWrite(audio_voice_uri="  local-es-MX-voice  "), admin, db)
        assert selected.audio_voice_uri == "local-es-MX-voice"
        assert public_display_state(display.access_token, Response(), db).audio.audio_voice_uri == "local-es-MX-voice"
        assert db.query(QueueTicketEvent).count() == before_events
        cleared = update_display_voice(display.id, QueueDisplayVoiceWrite(audio_voice_uri=None), admin, db)
        assert cleared.audio_voice_uri is None


def test_voice_choice_remains_admin_and_tenant_scoped(queue_db):
    engine, ids, _ = queue_db
    with scoped(engine) as db:
        admin = db.get(User, ids["admin"])
        line = make_line(db, ids)
        display = create_display(payload(ids["center"], line.id), admin, db)
        secretary = db.get(User, ids["secretary"])
        with pytest.raises(HTTPException) as forbidden:
            update_display_voice(display.id, QueueDisplayVoiceWrite(audio_voice_uri="local-es"), secretary, db)
        assert forbidden.value.status_code == 403
    with scoped(engine, 2) as db:
        admin = db.get(User, ids["admin"])
        with pytest.raises(HTTPException) as hidden:
            update_display_voice(display.id, QueueDisplayVoiceWrite(audio_voice_uri="local-es"), admin, db)
        assert hidden.value.status_code == 404


def test_voice_reference_length_is_bounded():
    with pytest.raises(ValidationError):
        QueueDisplayVoiceWrite(audio_voice_uri="x" * 256)
