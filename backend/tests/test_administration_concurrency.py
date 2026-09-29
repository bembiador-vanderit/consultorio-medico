"""Run against a disposable PostgreSQL database only."""
import os
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta
from hashlib import sha256
from threading import Barrier

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from app.api.routes.users import update_user_status
from app.db import Base
from app.models import Role, User
from app.models.administration import ReauthenticationGrant, SecurityAudit
from app.schemas.user import UserStatusUpdate
from app.services.administration import authorize_sensitive_write
from app.services.bootstrap import seed_identity

@pytest.fixture
def postgres():
    url = os.environ.get("ADMIN_SECURITY_POSTGRES_URL")
    if not url:
        pytest.skip("Requires disposable administration_security_test PostgreSQL")
    engine = create_engine(url)
    assert engine.url.database == "administration_security_test"
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        seed_identity(db)
        role = db.scalar(select(Role).where(Role.code == "admin"))
        for index in range(2):
            db.add(User(email=f"admin{index}@example.com", full_name=f"Admin {index}", password_hash="unused", roles=[role]))
        db.commit()
        ids = list(db.scalars(select(User.id).order_by(User.id)).all())
        for index, actor_id in enumerate(ids):
            db.add(ReauthenticationGrant(id=sha256(f"proof{index}".encode()).hexdigest(), user_id=actor_id,
                session_version=0, action=f"PUT /api/v1/users/{ids[1-index]}/status",
                expires_at=datetime.utcnow() + timedelta(minutes=1)))
        db.commit()
    yield engine, ids
    Base.metadata.drop_all(engine)
    engine.dispose()


def test_two_admins_cannot_concurrently_disable_each_other(postgres):
    engine, ids = postgres
    barrier = Barrier(2)
    def disable(index):
        with Session(engine) as db:
            actor = db.get(User, ids[index])
            barrier.wait(timeout=10)
            try:
                authorize_sensitive_write(db, actor, f"PUT /api/v1/users/{ids[1-index]}/status", f"proof{index}")
                update_user_status(ids[1-index], UserStatusUpdate(is_active=False), admin=actor, db=db)
                return 200
            except HTTPException as exc:
                db.rollback()
                return exc.status_code
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(disable, [0, 1]))
    assert sorted(results) == [200, 401]
    with Session(engine) as db:
        assert len([user for user in db.scalars(select(User)).all() if user.is_active]) == 1
        assert len(db.scalars(select(SecurityAudit)).all()) == 1


def test_single_use_proof_serializes_concurrent_replays(postgres):
    engine, ids = postgres
    barrier = Barrier(2)
    def write(_):
        with Session(engine) as db:
            actor = db.get(User, ids[0])
            barrier.wait(timeout=10)
            try:
                authorize_sensitive_write(db, actor, f"PUT /api/v1/users/{ids[1]}/status", "proof0")
                update_user_status(ids[1], UserStatusUpdate(is_active=False), admin=actor, db=db)
                return 200
            except HTTPException as exc:
                db.rollback()
                return exc.status_code
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(write, [0, 1]))
    assert sorted(results) == [200, 428]
