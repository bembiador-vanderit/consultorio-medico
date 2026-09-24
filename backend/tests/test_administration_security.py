"""HTTP security regression tests; all identities are synthetic."""
from datetime import datetime, timedelta

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.api.routes import administration, auth, centers, follow_ups, users
from app.core.security import hash_password
from app.db import Base, get_db
from app.models import Role, User
from app.models.administration import AdminTransfer, ReauthenticationGrant, SecurityAudit
from app.services.bootstrap import seed_identity

PASSWORD = "SyntheticPassword123"

@pytest.fixture
def api():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        seed_identity(db)
        roles = {role.code: role for role in db.scalars(select(Role)).all()}
        for name, role in (("admin", "admin"), ("other", "admin"), ("doctor", "doctor"), ("secretary", "secretary")):
            db.add(User(email=f"{name}@example.com", full_name=name, password_hash=hash_password(PASSWORD), roles=[roles[role]]))
        db.commit()
        ids = {user.full_name: user.id for user in db.scalars(select(User)).all()}
    app = FastAPI()
    for router in (administration.router, auth.router, users.router, centers.router, follow_ups.router):
        app.include_router(router, prefix="/api/v1")
    def session():
        with Session(engine) as db:
            yield db
    app.dependency_overrides[get_db] = session
    with TestClient(app) as client:
        yield client, engine, ids
    engine.dispose()


def login(client, name="admin"):
    result = client.post("/api/v1/auth/login", json={"email": f"{name}@example.com", "password": PASSWORD})
    assert result.status_code == 200, result.text
    return {"Authorization": f"Bearer {result.json()['access_token']}"}


def proof(client, headers, method, path):
    result = client.post("/api/v1/administration/reauthenticate", headers=headers,
        json={"password": PASSWORD, "method": method, "path": path})
    assert result.status_code == 200, result.text
    return {**headers, "X-Reauthentication": result.json()["proof"]}


def mutate(client, headers, method, path, payload=None):
    return client.request(method, path, headers=proof(client, headers, method, path), json=payload)


def test_backend_denies_operational_roles_and_requires_step_up(api):
    client, _, ids = api
    path = f"/api/v1/users/{ids['doctor']}/status"
    for role in ("doctor", "secretary"):
        headers = login(client, role)
        assert client.get("/api/v1/users", headers=headers).status_code == 403
        assert client.put(path, headers=headers, json={"is_active": False}).status_code == 403
        assert client.get("/api/v1/administration/audit", headers=headers).status_code == 403
    headers = login(client)
    assert client.put(path, headers=headers, json={"is_active": False}).status_code == 428
    # Second membership path must not bypass step-up, even for a non-existent center.
    assert client.post("/api/v1/centers/1/users", headers=headers, json={"user_id": ids['doctor'], "is_primary": False}).status_code == 428


def test_refresh_cannot_be_bearer_and_password_invalidates_sessions(api):
    client, _, ids = api
    old = login(client, "doctor")
    refresh = client.cookies.get("consultorio_refresh")
    assert client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {refresh}"}).status_code == 401
    admin = login(client)
    result = mutate(client, admin, "PUT", f"/api/v1/users/{ids['doctor']}/password", {"new_password": "NewSyntheticPass456"})
    assert result.status_code == 200, result.text
    assert client.get("/api/v1/auth/me", headers=old).status_code == 401
    client.cookies.clear()
    client.cookies.set("consultorio_refresh", refresh)
    assert client.post("/api/v1/auth/refresh").status_code == 401


def test_proof_is_bound_single_use_expiring_and_audited(api):
    client, engine, ids = api
    headers = login(client)
    path = f"/api/v1/users/{ids['doctor']}/status"
    authorized = proof(client, headers, "PUT", path)
    assert client.put(f"/api/v1/users/{ids['secretary']}/status", headers=authorized, json={"is_active": False}).status_code == 428
    assert client.put(path, headers=authorized, json={"is_active": False}).status_code == 200
    assert client.put(path, headers=authorized, json={"is_active": True}).status_code == 428
    authorized = proof(client, headers, "PUT", path)
    with Session(engine) as db:
        grant = db.scalar(select(ReauthenticationGrant))
        grant.expires_at = datetime.utcnow() - timedelta(seconds=1)
        db.commit()
    assert client.put(path, headers=authorized, json={"is_active": True}).status_code == 428
    with Session(engine) as db:
        rows = db.scalars(select(SecurityAudit).where(SecurityAudit.action == f"PUT {path}")).all()
        assert len(rows) == 1 and rows[0].actor_id == ids['admin']
        assert PASSWORD not in str([row.__dict__ for row in db.scalars(select(SecurityAudit)).all()])


def test_block_unblock_does_not_revive_token_and_last_admin_survives(api):
    client, _, ids = api
    old = login(client, "doctor")
    admin = login(client)
    path = f"/api/v1/users/{ids['doctor']}/status"
    assert mutate(client, admin, "PUT", path, {"is_active": False}).status_code == 200
    assert mutate(client, admin, "PUT", path, {"is_active": True}).status_code == 200
    assert client.get("/api/v1/auth/me", headers=old).status_code == 401
    assert mutate(client, admin, "PUT", f"/api/v1/users/{ids['other']}/status", {"is_active": False}).status_code == 200
    assert mutate(client, admin, "PUT", f"/api/v1/users/{ids['admin']}/status", {"is_active": False}).status_code == 409
    assert mutate(client, admin, "PUT", f"/api/v1/users/{ids['admin']}/roles", {"role_codes": ["secretary"]}).status_code == 409


def test_no_admin_checkbox_or_create_escalation_and_individual_denial(api):
    client, _, ids = api
    admin = login(client)
    assert mutate(client, admin, "PUT", f"/api/v1/users/{ids['doctor']}/roles", {"role_codes": ["doctor", "admin"]}).status_code == 422
    assert mutate(client, admin, "POST", "/api/v1/users", {"email": "new@example.com", "full_name": "New Admin", "password": PASSWORD, "role_codes": ["admin"]}).status_code == 422
    path = f"/api/v1/users/{ids['doctor']}/permissions"
    assert mutate(client, admin, "PUT", path, {"denied_permissions": ["users:manage"]}).status_code == 422
    assert mutate(client, admin, "PUT", path, {"denied_permissions": ["clinical:access"]}).status_code == 200
    doctor = login(client, "doctor")
    assert "clinical:access" not in client.get("/api/v1/auth/me", headers=doctor).json()["permissions"]
    assert client.get("/api/v1/follow-ups", headers=doctor).status_code == 403
    assert "clinical:access" not in client.get("/api/v1/auth/me", headers=admin).json()["permissions"]


@pytest.mark.parametrize("replace", [True, False])
def test_transfer_requires_recipient_acceptance_and_revokes_sessions(api, replace):
    client, engine, ids = api
    admin = login(client)
    doctor = login(client, "doctor")
    transfer = mutate(client, admin, "POST", "/api/v1/administration/transfers", {"target_id": ids['doctor'], "replace_initiator": replace})
    assert transfer.status_code == 201, transfer.text
    path = f"/api/v1/administration/transfers/{transfer.json()['id']}/accept"
    assert mutate(client, admin, "POST", path).status_code == 404
    assert client.post(path, headers=doctor).status_code == 428
    assert mutate(client, doctor, "POST", path).status_code == 200
    assert client.get("/api/v1/auth/me", headers=doctor).status_code == 401
    fresh = login(client, "doctor")
    assert mutate(client, fresh, "POST", path).status_code == 409
    with Session(engine) as db:
        assert {role.code for role in db.get(User, ids['doctor']).roles} == {"doctor", "admin"}
        assert ("admin" in {role.code for role in db.get(User, ids['admin']).roles}) is not replace


@pytest.mark.parametrize("invalidator", ["expire", "cancel", "block"])
def test_invalid_transfer_cannot_grant_admin(api, invalidator):
    client, engine, ids = api
    admin = login(client)
    transfer = mutate(client, admin, "POST", "/api/v1/administration/transfers", {"target_id": ids['doctor']}).json()
    if invalidator == "expire":
        with Session(engine) as db:
            db.get(AdminTransfer, transfer['id']).expires_at = datetime.utcnow() - timedelta(seconds=1)
            db.commit()
    elif invalidator == "cancel":
        assert mutate(client, admin, "POST", f"/api/v1/administration/transfers/{transfer['id']}/cancel").status_code == 200
    else:
        assert mutate(client, admin, "PUT", f"/api/v1/users/{ids['doctor']}/status", {"is_active": False}).status_code == 200
        assert mutate(client, admin, "PUT", f"/api/v1/users/{ids['doctor']}/status", {"is_active": True}).status_code == 200
    doctor = login(client, "doctor")
    assert mutate(client, doctor, "POST", f"/api/v1/administration/transfers/{transfer['id']}/accept").status_code == 409


def test_reauthentication_rate_limit_is_persisted(api):
    client, _, _ = api
    admin = login(client)
    payload = {"password": "incorrect", "method": "POST", "path": "/api/v1/users"}
    for _ in range(5):
        assert client.post("/api/v1/administration/reauthenticate", headers=admin, json=payload).status_code == 403
    payload['password'] = PASSWORD
    assert client.post("/api/v1/administration/reauthenticate", headers=admin, json=payload).status_code == 429

def test_recycled_email_does_not_recycle_identity(api):
    client, engine, ids = api
    old = login(client, "doctor")
    with Session(engine) as db:
        former = db.get(User, ids['doctor'])
        former.email = "former@example.com"
        db.commit()
        role = db.scalar(select(Role).where(Role.code == "doctor"))
        db.add(User(email="doctor@example.com", full_name="Replacement", password_hash=hash_password(PASSWORD), roles=[role]))
        db.commit()
    assert client.get("/api/v1/auth/me", headers=old).status_code == 401


def test_failed_mutation_rolls_back_audit_and_consumption(api):
    client, engine, ids = api
    admin = login(client)
    path = f"/api/v1/users/{ids['doctor']}/roles"
    authorized = proof(client, admin, "PUT", path)
    assert client.put(path, headers=authorized, json={"role_codes": ["does-not-exist"]}).status_code == 422
    with Session(engine) as db:
        assert not db.scalar(select(ReauthenticationGrant)).consumed
        assert not db.scalar(select(SecurityAudit).where(SecurityAudit.action == f"PUT {path}"))

@pytest.mark.parametrize("change", ["restriction", "role_removed"])
def test_clinical_notifications_disappear_when_authority_is_removed(api, change):
    from datetime import date
    from app.models import FollowUp, Notification, Patient
    client, engine, ids = api
    with Session(engine) as db:
        patient = Patient(first_name="Paciente", last_name="Ficticio", date_of_birth=date(1990, 1, 1))
        db.add(patient)
        db.flush()
        follow_up = FollowUp(patient_id=patient.id, doctor_id=ids['doctor'], due_at=datetime.utcnow(), reason="Motivo ficticio")
        db.add(follow_up)
        db.flush()
        notification = Notification(user_id=ids['doctor'], follow_up_id=follow_up.id, title="Seguimiento", message="Contenido clínico ficticio")
        db.add(notification)
        db.commit()
        notification_id = notification.id
    doctor = login(client, "doctor")
    assert len(client.get("/api/v1/follow-ups/notifications", headers=doctor).json()) == 1
    admin = login(client)
    if change == "restriction":
        result = mutate(client, admin, "PUT", f"/api/v1/users/{ids['doctor']}/permissions", {"denied_permissions": ["clinical:access"]})
    else:
        result = mutate(client, admin, "PUT", f"/api/v1/users/{ids['doctor']}/roles", {"role_codes": ["secretary"]})
    assert result.status_code == 200, result.text
    doctor = login(client, "doctor")
    assert client.get("/api/v1/follow-ups/notifications", headers=doctor).json() == []
    assert client.post(f"/api/v1/follow-ups/notifications/{notification_id}/read", headers=doctor).status_code == 404


def test_bootstrap_does_not_recreate_initial_admin_in_existing_installation(api, monkeypatch):
    from app.services import bootstrap
    from types import SimpleNamespace
    _, engine, _ = api
    monkeypatch.setattr(bootstrap, "get_settings", lambda: SimpleNamespace(
        initial_admin_email="former-admin@example.com", initial_admin_password=PASSWORD, initial_admin_name="Former admin"))
    with Session(engine) as db:
        seed_identity(db)
        assert db.scalar(select(User).where(User.email == "former-admin@example.com")) is None
