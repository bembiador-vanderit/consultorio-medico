"""Opt-in 0052 assignment race on an explicitly disposable PostgreSQL database."""

import os
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from uuid import uuid4

import pytest
from sqlalchemy import select
from sqlalchemy.engine.url import make_url
from sqlalchemy.orm import Session

from app.api.routes.waiting_rooms import assign_lines
from app.db import engine
from app.models import CareCenter, OrganizationMembership, QueueLine, Role, User, WaitingRoom
from app.schemas.waiting_room import WaitingRoomLineAssignment
from app.services.tenancy import bind_scope


pytestmark = pytest.mark.skipif(
    os.environ.get("ATLAS_0052_PG_VALIDATION") != "1",
    reason="Requires explicit disposable PostgreSQL 0052 validation",
)


def test_two_admins_move_same_line_consistently():
    url = make_url(str(engine.url))
    assert url.host == "atlas-0052-pg-temp" and url.database.startswith("atlas_0052_"), "Disposable PostgreSQL only"
    suffix = uuid4().hex[:8]
    with Session(engine) as db:
        role = db.scalar(select(Role).where(Role.code == "admin"))
        if role is None:
            role = Role(code="admin", name="Administrador QA")
            db.add(role); db.flush()
        center = CareCenter(organization_id=1, name=f"Centro QA concurrencia {suffix}", city="QA")
        db.add(center); db.flush()
        admins = [User(email=f"room-admin-{index}-{suffix}@example.com", full_name=f"Administrador QA {index}",
                       password_hash="synthetic", memberships=[OrganizationMembership(organization_id=1, roles=[role])])
                  for index in (1, 2)]
        db.add_all(admins); db.flush()
        rooms = [WaitingRoom(organization_id=1, center_id=center.id, name=name, is_active=True, sort_order=index)
                 for index, name in enumerate(("Sala Uno", "Sala Dos"))]
        db.add_all(rooms); db.flush()
        line = QueueLine(organization_id=1, center_id=center.id, doctor_id=admins[0].id,
                         name="Línea QA", prefix="Q", is_active=True)
        db.add(line); db.commit()
        room_ids, admin_ids, line_id = [room.id for room in rooms], [user.id for user in admins], line.id

    barrier = Barrier(2)

    def move(pair):
        room_id, admin_id = pair
        with Session(engine) as db:
            bind_scope(db, "tenant", 1)
            user = db.get(User, admin_id)
            barrier.wait(timeout=20)
            return assign_lines(room_id, WaitingRoomLineAssignment(queue_line_ids=[line_id]), user, db).id

    with ThreadPoolExecutor(max_workers=2) as workers:
        results = list(workers.map(move, zip(room_ids, admin_ids)))
    assert set(results) == set(room_ids)
    with Session(engine) as db:
        line = db.get(QueueLine, line_id)
        assert line.waiting_room_id in room_ids  # One FK; never two simultaneous rooms.
        assert sum(db.scalar(select(QueueLine.id).where(QueueLine.id == line_id,
                                                  QueueLine.waiting_room_id == room_id)) is not None
                   for room_id in room_ids) == 1
