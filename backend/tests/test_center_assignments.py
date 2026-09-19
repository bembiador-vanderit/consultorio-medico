from datetime import datetime

from app.api.routes.centers import assign_user, list_centers, unassign_user
from app.models import CareCenter, Role, User
from app.schemas.center import CenterUserAssignment


def _center() -> CareCenter:
    return CareCenter(
        id=5,
        name="CEMER",
        center_type="consultorio",
        city="Santo Domingo",
        locality_id=2,
        is_active=True,
        created_at=datetime(2026, 9, 3, 10, 0),
        users=[],
    )


def _user(user_id: int, role_code: str) -> User:
    return User(
        id=user_id,
        full_name=f"Usuario {user_id}",
        email=f"usuario{user_id}@example.test",
        is_active=True,
        roles=[Role(code=role_code, name=role_code)],
        centers=[],
    )


class CenterDB:
    def __init__(self, center: CareCenter, users: list[User]):
        self.center = center
        self.users = {user.id: user for user in users}

    def get(self, model, object_id):
        if model is CareCenter:
            return self.center if object_id == self.center.id else None
        if model is User:
            return self.users.get(object_id)
        return None

    def scalars(self, _query):
        return self

    def all(self):
        return [self.center]

    def flush(self):
        pass

    def execute(self, _query):
        pass

    def commit(self):
        pass

    def refresh(self, _object):
        pass


def test_center_management_response_exposes_real_assignments_after_reload():
    center = _center()
    doctor = _user(11, "doctor")
    db = CenterDB(center, [doctor])

    assign_user(center.id, CenterUserAssignment(user_id=doctor.id), db=db)
    reloaded = list_centers(None, db)

    assert doctor.id in reloaded[0].assigned_user_ids


def test_unassign_removes_user_from_management_response_after_reload():
    center = _center()
    secretary = _user(21, "secretary")
    secretary.centers.append(center)
    db = CenterDB(center, [secretary])

    unassign_user(center.id, secretary.id, db=db)
    reloaded = list_centers(None, db)

    assert secretary.id not in reloaded[0].assigned_user_ids
