"""Synthetic host-bound HTTP checks, including both token types and DST edges."""
from datetime import datetime, timezone

import jwt
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.routes import access_schedule
from app.core.config import get_settings
from app.core.security import hash_password
from app.models import AccessBlockedDate, AccessException, Organization, OrganizationMembership, Role, User
from app.models.administration import SecurityAudit
from app.services.access_schedule import access_state
from app.services.tenancy import bind_scope
from test_organization_isolation import PASSWORD, sign_in, tenant_api


@pytest.fixture
def scheduled(tenant_api, monkeypatch):
    app, engine, _ = tenant_api
    app.include_router(access_schedule.router, prefix="/api/v1")
    clock = [datetime(2030, 1, 7, 13, tzinfo=timezone.utc)]  # Monday 09:00 in Santo Domingo
    monkeypatch.setattr("app.services.access_schedule.utcnow", lambda: clock[0])
    monkeypatch.setattr("app.api.routes.access_schedule.utcnow", lambda: clock[0])
    with Session(engine) as db:
        secretary = db.scalar(select(Role).where(Role.code == "secretary"))
        user = User(email="hours@example.com", full_name="Horario de prueba", password_hash=hash_password(PASSWORD),
                    memberships=[OrganizationMembership(organization_id=1, roles=[secretary]), OrganizationMembership(organization_id=2, roles=[secretary])])
        foreign = User(email="foreign@example.com", full_name="Otro tenant", password_hash=hash_password(PASSWORD),
                       memberships=[OrganizationMembership(organization_id=2, roles=[secretary])])
        db.add_all([user, foreign]); db.commit()
        uid, foreign_id = user.id, foreign.id
        member = db.scalar(select(OrganizationMembership).where(OrganizationMembership.user_id == uid, OrganizationMembership.organization_id == 1))
        member.restrict_outside_schedule = True
        member.weekly_schedule = [{"day": 0, "start": "08:00", "end": "17:00"}, {"day": 1, "start": "08:00", "end": "17:00"}]
        db.commit()
    with TestClient(app, base_url="http://one.example.test") as client:
        yield client, engine, clock, uid, foreign_id, app


def login(client):
    return client.post("/api/v1/auth/login", json={"email": "hours@example.com", "password": PASSWORD})


def headers(response):
    assert response.status_code == 200, response.text
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def mutate(client, admin, method, path, data=None):
    proof = client.post("/api/v1/administration/reauthenticate", headers=admin,
                        json={"password": PASSWORD, "method": method, "path": path})
    assert proof.status_code == 200, proof.text
    return client.request(method, path, headers={**admin, "X-Reauthentication": proof.json()["proof"]}, json=data)


def test_login_outside_and_wrong_password_do_not_leak_schedule(scheduled):
    client, engine, clock, *_ = scheduled
    clock[0] = datetime(2030, 1, 7, 11, tzinfo=timezone.utc)
    result = login(client)
    assert result.status_code == 403
    assert result.headers["X-Access-Schedule"] == "denied"
    assert "07/01/2030 08:00" in result.json()["detail"]
    assert "America/Santo_Domingo" in result.text
    assert "consultorio_refresh" not in client.cookies
    invalid = client.post("/api/v1/auth/login", json={"email": "hours@example.com", "password": "WrongPassword123"})
    assert invalid.status_code == 401
    assert "Próximo" not in invalid.text
    login(client)
    with Session(engine) as db:
        rows = db.scalars(select(SecurityAudit).where(SecurityAudit.outcome == "denied")).all()
        assert len(rows) == 1
        assert rows[0].organization_id == 1
        assert PASSWORD not in rows[0].action


def test_session_and_refresh_end_exactly_at_close_and_never_revive(scheduled):
    client, _, clock, *_ = scheduled
    token = headers(login(client))
    clock[0] = datetime(2030, 1, 7, 20, 59, 59, tzinfo=timezone.utc)
    assert client.get("/api/v1/auth/me", headers=token).status_code == 200
    refreshed = client.post("/api/v1/auth/refresh")
    renewed = headers(refreshed)
    claims = jwt.decode(refreshed.json()["access_token"], get_settings().secret_key, algorithms=["HS256"])
    assert claims["schedule_until"] == datetime(2030, 1, 7, 21, tzinfo=timezone.utc).timestamp()
    clock[0] = datetime(2030, 1, 7, 21, tzinfo=timezone.utc)
    assert client.get("/api/v1/patients", headers=token).status_code == 403
    assert client.get("/api/v1/auth/me", headers=renewed).status_code == 403
    assert client.post("/api/v1/auth/refresh").status_code == 403
    clock[0] = datetime(2030, 1, 8, 13, tzinfo=timezone.utc)
    assert client.get("/api/v1/auth/me", headers=token).status_code == 403
    assert client.post("/api/v1/auth/refresh").status_code == 403
    assert login(client).status_code == 200


def test_unrestricted_user_and_legacy_pilot_tokens_stay_usable(scheduled):
    client, engine, clock, uid, *_ = scheduled
    with Session(engine) as db:
        member = db.scalar(select(OrganizationMembership).where(OrganizationMembership.user_id == uid, OrganizationMembership.organization_id == 1))
        member.restrict_outside_schedule = False; db.commit()
    clock[0] = datetime(2030, 1, 6, 2, tzinfo=timezone.utc)
    result = login(client)
    payload = jwt.decode(result.json()["access_token"], get_settings().secret_key, algorithms=["HS256"])
    assert "schedule_until" not in payload
    payload.pop("schedule_version")
    old = jwt.encode(payload, get_settings().secret_key, algorithm="HS256")
    assert client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {old}"}).status_code == 200


def test_exception_allows_overtime_and_blocked_date_wins(scheduled):
    client, engine, clock, uid, *_ = scheduled
    admin = sign_in(client)
    clock[0] = datetime(2030, 1, 7, 22, tzinfo=timezone.utc)
    path = f"/api/v1/administration/access-schedules/{uid}"
    added = mutate(client, admin, "POST", path + "/exceptions", {"starts_at": "2030-01-07T17:30", "ends_at": "2030-01-07T20:00", "reason": "Cierre administrativo"})
    assert added.status_code == 201, added.text
    assert datetime.fromisoformat(added.json()["exceptions"][0]["starts_at"]) == datetime(2030, 1, 7, 21, 30, tzinfo=timezone.utc)
    token = headers(login(client))
    blocked = mutate(client, admin, "POST", path + "/blocked-dates", {"day": "2030-01-07", "reason": "Licencia"})
    assert blocked.status_code == 201, blocked.text
    assert login(client).status_code == 403
    assert client.get("/api/v1/auth/me", headers=token).status_code == 403
    exception_id = added.json()["exceptions"][0]["id"]
    block_id = blocked.json()["blocked_dates"][0]["id"]
    assert mutate(client, admin, "DELETE", path + f"/blocked-dates/{block_id}").status_code == 200
    assert login(client).status_code == 200
    assert mutate(client, admin, "DELETE", path + f"/exceptions/{exception_id}").status_code == 200
    assert login(client).status_code == 403
    with Session(engine) as db:
        actions = [row.action for row in db.scalars(select(SecurityAudit))]
        for name in ("exception.created", "block.created", "block.removed", "exception.removed"):
            assert any(f"schedule.{name}" in action for action in actions)


def test_reauthentication_schedule_update_and_disable_revoke_old_tokens(scheduled):
    client, engine, _, uid, *_ = scheduled
    admin, token = sign_in(client), headers(login(client))
    path = f"/api/v1/administration/access-schedules/{uid}"
    data = {"restrict_outside_schedule": False, "weekly_schedule": []}
    assert client.put(path, headers=admin, json=data).status_code == 428
    saved = mutate(client, admin, "PUT", path, data)
    assert saved.status_code == 200, saved.text
    assert saved.json()["restrict_outside_schedule"] is False
    assert client.get("/api/v1/auth/me", headers=token).status_code == 403
    assert login(client).status_code == 200
    with Session(engine) as db:
        assert any("restricted:False" in row.action for row in db.scalars(select(SecurityAudit)))


def test_cross_tenant_admin_cannot_read_write_or_discover_and_changes_are_local(scheduled):
    client, engine, clock, uid, foreign_id, app = scheduled
    admin = sign_in(client)  # Platform authority also set on this identity.
    path = "/api/v1/administration/access-schedules/"
    assert client.get(path + str(foreign_id), headers=admin).status_code == 404
    assert mutate(client, admin, "PUT", path + str(foreign_id), {"restrict_outside_schedule": True, "weekly_schedule": []}).status_code == 404
    own = client.get(path + str(uid) + "?organization_id=2", headers={**admin, "X-Tenant": "second"}).json()
    assert own["restrict_outside_schedule"] is True
    assert "memberships" not in own
    with TestClient(app, base_url="http://two.example.test") as second:
        second_token = headers(login(second))
        changed = mutate(client, admin, "PUT", path + str(uid), {"restrict_outside_schedule": True, "weekly_schedule": []})
        assert changed.status_code == 200
        assert second.get("/api/v1/auth/me", headers=second_token).status_code == 200
        assert login(client).status_code == 403


def test_timezone_is_configurable_scoped_and_invalid_names_rejected(scheduled):
    client, engine, _, uid, *_ = scheduled
    admin = sign_in(client)
    path = "/api/v1/administration/access-schedules/timezone"
    assert mutate(client, admin, "PUT", path, {"timezone": "Invalid/Nowhere"}).status_code == 422
    result = mutate(client, admin, "PUT", path, {"timezone": "Asia/Tokyo"})
    assert result.status_code == 200, result.text
    assert login(client).status_code == 403  # 22:00 local, same UTC instant.
    assert client.get("/api/v1/auth/me", headers=admin).status_code == 403
    with Session(engine) as db:
        assert db.get(Organization, 1).timezone == "Asia/Tokyo"
        assert db.get(Organization, 2).timezone == "UTC"


@pytest.mark.parametrize("data", [
    {"restrict_outside_schedule": True, "weekly_schedule": [{"day": 7, "start": "08:00", "end": "17:00"}]},
    {"restrict_outside_schedule": True, "weekly_schedule": [{"day": 0, "start": "17:00", "end": "08:00"}]},
    {"restrict_outside_schedule": True, "weekly_schedule": [{"day": 0, "start": "08:00", "end": "17:00"}, {"day": 0, "start": "16:00", "end": "18:00"}]},
])
def test_invalid_weekly_windows_rejected(scheduled, data):
    client, _, _, uid, *_ = scheduled
    assert mutate(client, sign_in(client), "PUT", f"/api/v1/administration/access-schedules/{uid}", data).status_code == 422


def test_multiple_windows_have_midday_cutoff(scheduled):
    client, _, clock, uid, *_ = scheduled
    assert mutate(client, sign_in(client), "PUT", f"/api/v1/administration/access-schedules/{uid}", {
        "restrict_outside_schedule": True,
        "weekly_schedule": [{"day": 0, "start": "08:00", "end": "12:00"}, {"day": 0, "start": "13:00", "end": "17:00"}],
    }).status_code == 200
    token = headers(login(client))
    clock[0] = datetime(2030, 1, 7, 16, tzinfo=timezone.utc)
    assert "13:00" in login(client).json()["detail"]
    clock[0] = datetime(2030, 1, 7, 17, tzinfo=timezone.utc)
    assert client.get("/api/v1/auth/me", headers=token).status_code == 403
    assert login(client).status_code == 200


def test_dst_missing_and_repeated_hours_fail_closed(scheduled):
    _, engine, _, uid, *_ = scheduled
    with Session(engine) as db:
        db.get(Organization, 1).timezone = "America/New_York"
        member = db.scalar(select(OrganizationMembership).where(OrganizationMembership.user_id == uid, OrganizationMembership.organization_id == 1))
        member.weekly_schedule = [{"day": 6, "start": "02:30", "end": "04:00"}]
        db.commit()
        missing = access_state(db, member, datetime(2030, 3, 10, 7, 30, tzinfo=timezone.utc))
        assert missing["allowed"] is False
        member.weekly_schedule = [{"day": 6, "start": "01:30", "end": "02:30"}]
        assert access_state(db, member, datetime(2030, 11, 3, 5, 45, tzinfo=timezone.utc))["allowed"] is False
        assert access_state(db, member, datetime(2030, 11, 3, 6, 45, tzinfo=timezone.utc))["allowed"] is True


def test_exception_validation_and_normal_user_forbidden(scheduled):
    client, _, _, uid, *_ = scheduled
    path = f"/api/v1/administration/access-schedules/{uid}"
    user_token = headers(login(client))
    assert client.get(path, headers=user_token).status_code == 403
    assert client.post(path + "/exceptions", headers=user_token, json={"starts_at": "2030-01-07T18:00", "ends_at": "2030-01-07T19:00", "reason": "Test"}).status_code == 403
    admin = sign_in(client)
    assert mutate(client, admin, "POST", path + "/exceptions", {"starts_at": "2030-01-07T19:00", "ends_at": "2030-01-07T18:00", "reason": "Test"}).status_code == 422
    assert mutate(client, admin, "POST", path + "/exceptions", {"starts_at": "2030-01-07T18:00", "ends_at": "2030-01-07T19:00", "reason": " "}).status_code == 422


def test_foreign_exception_ids_and_forged_organization_are_rejected(scheduled):
    client, engine, _, uid, *_ = scheduled
    with Session(engine) as db:
        member = db.scalar(select(OrganizationMembership).where(OrganizationMembership.user_id == uid, OrganizationMembership.organization_id == 2))
        row = AccessException(organization_id=2, membership_id=member.id, starts_at=datetime(2030, 1, 7, 12),
                              ends_at=datetime(2030, 1, 7, 23), reason="Private foreign reason", authorized_by=uid)
        db.add(row); db.commit(); foreign_id = row.id
    admin = sign_in(client)
    path = f"/api/v1/administration/access-schedules/{uid}"
    assert "Private foreign reason" not in client.get(path, headers=admin).text
    assert mutate(client, admin, "DELETE", path + f"/exceptions/{foreign_id}").status_code == 404
    assert mutate(client, admin, "PUT", path, {"organization_id": 2, "restrict_outside_schedule": False, "weekly_schedule": []}).status_code == 422
    with Session(engine) as db:
        bind_scope(db, "tenant", 1)
        org = db.get(Organization, 1)
        org.timezone = "UTC"
        org.name = "Unauthorized rename"
        with pytest.raises(Exception):
            db.flush()
