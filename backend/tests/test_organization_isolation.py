"""Synthetic HTTP and persistence checks for host-bound tenant authority."""
from datetime import date, datetime
from types import SimpleNamespace

import pytest
from fastapi import FastAPI, Request
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.api.routes import administration, auth, centers, organizations, patients, users
from app.core.security import hash_password
from app.db import Base, get_db
from app.models import CareCenter, FollowUp, Locality, Organization, OrganizationMembership, Patient, Role, User
from app.models.administration import SecurityAudit
from app.services.administration import audit
from app.services.bootstrap import seed_identity
from app.services.tenancy import bind_scope, resolve_request

PASSWORD = "SyntheticPassword123"


@pytest.fixture
def tenant_api(monkeypatch):
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        seed_identity(db)
        db.add(Organization(id=2, slug="second", name="Organización de prueba"))
        db.flush()
        admin = db.scalar(select(Role).where(Role.code == "admin"))
        shared = User(email="shared@example.com", full_name="Shared", password_hash=hash_password(PASSWORD),
                      is_platform_admin=True, memberships=[
                          OrganizationMembership(organization_id=1, roles=[admin]),
                          OrganizationMembership(organization_id=2, roles=[admin]),
                      ])
        db.add(shared)
        locality_one = Locality(organization_id=1, name="Place one")
        locality_two = Locality(organization_id=2, name="Place two")
        db.add_all([locality_one, locality_two])
        db.flush()
        db.add_all([
            Patient(organization_id=1, first_name="One", last_name="Patient", date_of_birth=date(1990, 1, 1),
                    document_type="cedula", document_number="00000000000"),
            Patient(organization_id=2, first_name="Two", last_name="Patient", date_of_birth=date(1990, 1, 1),
                    document_type="cedula", document_number="00000000000"),
            CareCenter(organization_id=1, name="One", city="Test", locality_id=locality_one.id),
            CareCenter(organization_id=2, name="Two", city="Test", locality_id=locality_two.id),
        ])
        db.commit()
        ids = {p.organization_id: p.id for p in db.scalars(select(Patient)).all()}
    monkeypatch.setattr("app.services.tenancy.get_settings", lambda: SimpleNamespace(
        platform_hosts=["admin.example.test"], tenant_hosts={"one.example.test": "pilot", "two.example.test": "second"}))
    app = FastAPI()
    for router in (administration.router, auth.router, users.router, patients.router, centers.router, organizations.router):
        app.include_router(router, prefix="/api/v1")

    def session(request: Request):
        with Session(engine) as db:
            resolve_request(db, request)
            yield db

    app.dependency_overrides[get_db] = session
    yield app, engine, ids
    engine.dispose()


def sign_in(client):
    response = client.post("/api/v1/auth/login", json={"email": "shared@example.com", "password": PASSWORD})
    assert response.status_code == 200, response.text
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def test_two_hosts_isolate_records_roles_and_platform_scope(tenant_api):
    app, _, ids = tenant_api
    with TestClient(app, base_url="http://one.example.test") as one, TestClient(app, base_url="http://two.example.test") as two, TestClient(app, base_url="http://admin.example.test") as platform:
        h1, h2, hp = sign_in(one), sign_in(two), sign_in(platform)
        assert one.get("/api/v1/auth/me", headers=h1).json()["organization"]["id"] == 1
        assert two.get("/api/v1/auth/me", headers=h2).json()["organization"]["id"] == 2
        assert one.get("/api/v1/patients/count", headers=h1).json() == {"count": 1}
        assert [item["first_name"] for item in two.get("/api/v1/patients", headers=h2).json()] == ["Two"]
        assert one.get(f"/api/v1/patients/{ids[2]}", headers=h1).status_code == 404
        assert [item["name"] for item in one.get("/api/v1/centers", headers=h1).json()] == ["One"]
        assert one.get("/api/v1/platform/organizations", headers=h1).status_code == 404
        assert len(platform.get("/api/v1/platform/organizations", headers=hp).json()) == 2
        assert platform.get("/api/v1/patients", headers=hp).status_code == 403
        assert two.get("/api/v1/auth/me", headers=h1).status_code == 401
        assert one.get("/api/v1/auth/me", headers=hp).status_code == 401
        assert two.post("/api/v1/auth/refresh", cookies={"consultorio_refresh": one.cookies.get("consultorio_refresh")}).status_code == 401


def test_membership_suspension_and_scoped_write(tenant_api):
    app, engine, ids = tenant_api
    with TestClient(app, base_url="http://one.example.test") as one, TestClient(app, base_url="http://two.example.test") as two:
        h1, h2 = sign_in(one), sign_in(two)
        with Session(engine) as db:
            bind_scope(db, "tenant", 1)
            assert db.get(Patient, ids[2]) is None
            patient = db.get(Patient, ids[1])
            patient.organization_id = 2
            with pytest.raises(Exception):
                db.flush()
            db.rollback()
        with Session(engine) as db:
            bind_scope(db, "tenant", 1)
            user_id = db.scalar(select(User.id).where(User.email == "shared@example.com"))
            db.add(FollowUp(organization_id=1, patient_id=ids[2], doctor_id=user_id,
                due_at=datetime(2026, 10, 1), reason="Synthetic"))
            with pytest.raises(Exception):
                db.flush()
            db.rollback()
        with Session(engine) as db:
            member = db.scalar(select(OrganizationMembership).where(OrganizationMembership.organization_id == 1))
            member.state = "suspended"
            db.commit()
        assert one.get("/api/v1/auth/me", headers=h1).status_code == 401
        assert two.get("/api/v1/auth/me", headers=h2).status_code == 401
        assert two.get("/api/v1/auth/me", headers=sign_in(two)).status_code == 200


def test_unknown_host_and_untrusted_tenant_header(tenant_api):
    app, _, _ = tenant_api
    with TestClient(app, base_url="http://unknown.example.test") as unknown:
        assert unknown.post("/api/v1/auth/login", headers={"X-Tenant": "pilot", "X-Forwarded-Host": "one.example.test"},
            json={"email": "shared@example.com", "password": PASSWORD}).status_code == 404


def test_role_changes_are_local_to_membership(tenant_api):
    app, engine, _ = tenant_api
    with Session(engine) as db:
        member = db.scalar(select(OrganizationMembership).where(OrganizationMembership.organization_id == 2))
        secretary = db.scalar(select(Role).where(Role.code == "secretary"))
        member.roles = [secretary]
        db.commit()
    with TestClient(app, base_url="http://one.example.test") as one, TestClient(app, base_url="http://two.example.test") as two:
        assert one.get("/api/v1/users", headers=sign_in(one)).status_code == 200
        assert two.get("/api/v1/users", headers=sign_in(two)).status_code == 403


def test_new_user_receives_only_the_current_tenant_membership(tenant_api):
    app, engine, _ = tenant_api
    with Session(engine) as db:
        bind_scope(db, "tenant", 2)
        secretary = db.scalar(select(Role).where(Role.code == "secretary"))
        db.add(User(email="new@example.com", full_name="New User", password_hash=hash_password(PASSWORD), roles=[secretary]))
        db.commit()
    with TestClient(app, base_url="http://one.example.test") as one, TestClient(app, base_url="http://two.example.test") as two:
        assert one.post("/api/v1/auth/login", json={"email": "new@example.com", "password": PASSWORD}).status_code == 401
        response = two.post("/api/v1/auth/login", json={"email": "new@example.com", "password": PASSWORD})
        assert response.status_code == 200, response.text
        me = two.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {response.json()['access_token']}"}).json()
        assert me["organization"]["id"] == 2
        assert me["roles"] == ["secretary"]


def test_audit_records_tenant_and_center_without_cross_tenant_visibility(tenant_api):
    _, engine, _ = tenant_api
    with Session(engine) as db:
        bind_scope(db, "tenant", 1)
        actor = db.scalar(select(User).where(User.email == "shared@example.com"))
        center = db.scalar(select(CareCenter))
        audit(db, actor, f"PUT /api/v1/centers/{center.id}")
        db.commit()
        row = db.scalar(select(SecurityAudit))
        assert (row.organization_id, row.center_id) == (1, center.id)
    with Session(engine) as db:
        bind_scope(db, "tenant", 2)
        assert db.scalar(select(SecurityAudit)) is None


def test_administrative_center_write_checks_tenant(tenant_api):
    app, engine, _ = tenant_api
    with Session(engine) as db:
        user_id = db.scalar(select(User.id).where(User.email == "shared@example.com"))
        centers_by_org = {center.organization_id: center.id for center in db.scalars(select(CareCenter))}
    with TestClient(app, base_url="http://one.example.test") as one:
        headers = sign_in(one)
        path = f"/api/v1/users/{user_id}/centers"
        def authorized():
            proof = one.post("/api/v1/administration/reauthenticate", headers=headers,
                json={"password": PASSWORD, "method": "PUT", "path": path})
            assert proof.status_code == 200, proof.text
            return {**headers, "X-Reauthentication": proof.json()["proof"]}
        foreign = one.put(path, headers=authorized(), json={"center_ids": [centers_by_org[2]], "primary_center_id": centers_by_org[2]})
        assert foreign.status_code == 422
        valid = one.put(path, headers=authorized(), json={"center_ids": [centers_by_org[1]], "primary_center_id": centers_by_org[1]})
        assert valid.status_code == 200, valid.text
        assert valid.json()["center_ids"] == [centers_by_org[1]]
