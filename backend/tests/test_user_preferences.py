"""User-owned preferences on disposable SQLite; never touches the official DB."""
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.routes import user_preferences
from app.models import OrganizationMembership, Role, User, UserPreference
from app.services.administration import effective_permissions
from app.services.user_preferences import DASHBOARD_WIDGET_IDS, GESTION_MENU_IDS, defaults
from test_organization_isolation import PASSWORD, sign_in, tenant_api

BASE = "/api/v1/me/preferences"


def preference_client(tenant_api):
    app, engine, _ = tenant_api
    app.include_router(user_preferences.router, prefix="/api/v1")
    return app, engine


def test_defaults_do_not_insert_a_row(tenant_api):
    app, engine = preference_client(tenant_api)
    with TestClient(app, base_url="http://one.example.test") as client:
        result = client.get(BASE, headers=sign_in(client))
        assert result.status_code == 200
        assert result.json() == defaults()
    with Session(engine) as db:
        assert db.scalar(select(func.count()).select_from(UserPreference)) == 0


def test_pending_migration_returns_503_without_writing(tenant_api):
    app, engine = preference_client(tenant_api)
    UserPreference.__table__.drop(engine)
    with TestClient(app, base_url="http://one.example.test") as client:
        headers = sign_in(client)
        assert client.get(BASE, headers=headers).status_code == 503
        assert client.put(BASE, headers=headers, json=defaults()).status_code == 503


def test_create_update_idempotency_and_cross_session_client(tenant_api):
    app, engine = preference_client(tenant_api)
    payload = {"gestion_menu_order": ["patients", "appointments", "dashboard"],
               "dashboard_widget_order": ["users", "centers", "patients", "agenda", "reports"],
               "accent_theme": "turquoise"}
    with TestClient(app, base_url="http://one.example.test") as first:
        headers = sign_in(first)
        assert first.put(BASE, headers=headers, json=payload).json() == payload
        with Session(engine) as db:
            original = db.scalar(select(UserPreference))
            assert original.user_id and original.created_at and original.updated_at
            previous_update = original.updated_at
        assert first.put(BASE, headers=headers, json=payload).json() == payload
        with Session(engine) as db:
            assert db.scalar(select(func.count()).select_from(UserPreference)) == 1
            assert db.scalar(select(UserPreference)).updated_at == previous_update
        assert first.post("/api/v1/auth/logout").status_code == 204
        assert first.get(BASE, headers=sign_in(first)).json() == payload
    with TestClient(app, base_url="http://one.example.test") as second:
        assert second.get(BASE, headers=sign_in(second)).json() == payload
        changed = {**payload, "dashboard_widget_order": ["agenda-today", "metric-appointments"], "accent_theme": "indigo"}
        assert second.put(BASE, headers=sign_in(second), json=changed).json() == changed
        assert second.get(BASE, headers=sign_in(second)).json() == changed


def test_invalid_ids_duplicates_accent_and_owner_spoof_rejected(tenant_api):
    app, engine = preference_client(tenant_api)
    with TestClient(app, base_url="http://one.example.test") as client:
        headers = sign_in(client)
        valid = {"gestion_menu_order": list(GESTION_MENU_IDS),
                 "dashboard_widget_order": list(DASHBOARD_WIDGET_IDS), "accent_theme": "classic"}
        invalid = [
            {**valid, "gestion_menu_order": ["clinical-secret", "patients"]},
            {**valid, "gestion_menu_order": ["patients", "patients"]},
            {**valid, "dashboard_widget_order": ["unknown"]},
            {**valid, "dashboard_widget_order": ["patients", "patients"]},
            {**valid, "accent_theme": "url(javascript:unsafe)"},
            {**valid, "user_id": 999},
        ]
        for payload in invalid:
            assert client.put(BASE, headers=headers, json=payload).status_code == 422
        assert client.get(BASE).status_code in (401, 403)
    with Session(engine) as db:
        assert db.scalar(select(func.count()).select_from(UserPreference)) == 0


def test_multi_user_isolation_and_permissions_remain_authoritative(tenant_api):
    app, engine = preference_client(tenant_api)
    with Session(engine) as db:
        original = db.scalar(select(User).where(User.email == "shared@example.com"))
        doctor = db.scalar(select(Role).where(Role.code == "doctor"))
        second = User(email="prefs-second@example.com", full_name="Second QA", password_hash=original.password_hash,
                      memberships=[OrganizationMembership(organization_id=1, roles=[doctor])])
        db.add(second)
        db.commit()
        second_id = second.id
        before = effective_permissions(original)
    with TestClient(app, base_url="http://one.example.test") as client:
        first_headers = sign_in(client)
        login = client.post("/api/v1/auth/login", json={"email": "prefs-second@example.com", "password": PASSWORD})
        assert login.status_code == 200
        second_headers = {"Authorization": f"Bearer {login.json()['access_token']}"}
        first = {"gestion_menu_order": ["patients", "appointments", "dashboard"],
                 "dashboard_widget_order": ["users", "centers", "patients"], "accent_theme": "turquoise"}
        second = {"gestion_menu_order": ["dashboard", "finance", "patients"],
                  "dashboard_widget_order": ["new-appointment", "agenda", "reports"], "accent_theme": "indigo"}
        assert client.put(BASE, headers=first_headers, json=first).status_code == 200
        assert client.put(BASE, headers=second_headers, json=second).status_code == 200
        assert client.get(BASE, headers=first_headers, params={"user_id": second_id}).json() == first
        assert client.get(BASE, headers=second_headers).json() == second
        assert client.put(BASE, headers=first_headers, json={**second, "user_id": second_id}).status_code == 422
        assert client.get(BASE, headers=second_headers).json() == second
    with Session(engine) as db:
        assert db.scalar(select(func.count()).select_from(UserPreference)) == 2
        assert effective_permissions(db.scalar(select(User).where(User.email == "shared@example.com"))) == before
