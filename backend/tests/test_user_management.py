from datetime import date

import pytest
from fastapi import HTTPException, Response
from sqlalchemy import create_engine, update
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.api.routes.appointments import list_available_doctors
from app.api.routes.auth import login
from app.api.routes.centers import assign_user
from app.api.routes.users import (
    list_users,
    update_user_centers,
    update_user_password,
    update_user_profile,
    update_user_roles,
    update_user_status,
)
from app.core.security import hash_password, verify_password
from app.db import Base
from app.models import CareCenter, Role, User
from app.models.center import user_centers
from app.schemas.auth import LoginRequest
from app.schemas.center import CenterUserAssignment
from app.schemas.user import (
    UserCentersUpdate,
    UserPasswordUpdate,
    UserProfileUpdate,
    UserRolesUpdate,
    UserStatusUpdate,
)


@pytest.fixture
def identity_db():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        admin_role = Role(code="admin", name="Administrador")
        doctor_role = Role(code="doctor", name="Doctor")
        secretary_role = Role(code="secretary", name="Secretaria")
        center_one = CareCenter(name="CEMER", center_type="consultorio", city="Santo Domingo", is_active=True)
        center_two = CareCenter(name="Centro Norte", center_type="clinica", city="Santiago", is_active=True)
        admin = User(
            email="admin@example.com",
            full_name="Administrador Principal",
            password_hash=hash_password("AdminPassword123"),
            is_active=True,
            roles=[admin_role],
        )
        second_admin = User(
            email="admin2@example.com",
            full_name="Administrador Segundo",
            password_hash=hash_password("AdminPassword456"),
            is_active=True,
            roles=[admin_role],
        )
        doctor = User(
            email="doctor@example.com",
            full_name="Doctora Prueba",
            password_hash=hash_password("DoctorPassword123"),
            is_active=True,
            roles=[doctor_role],
            centers=[center_one],
        )
        secretary = User(
            email="secretary@example.com",
            full_name="Secretaria Prueba",
            password_hash=hash_password("SecretaryPass123"),
            is_active=True,
            roles=[secretary_role],
        )
        db.add_all([admin, second_admin, doctor, secretary, center_two])
        db.flush()
        db.execute(
            update(user_centers)
            .where(user_centers.c.user_id == doctor.id, user_centers.c.center_id == center_one.id)
            .values(is_primary=True)
        )
        db.commit()
        yield db, admin, second_admin, doctor, secretary, admin_role, doctor_role, center_one, center_two
    Base.metadata.drop_all(engine)
    engine.dispose()


def test_admin_updates_user_name(identity_db):
    db, admin, _, doctor, *_ = identity_db

    result = update_user_profile(
        doctor.id,
        UserProfileUpdate(full_name="Doctora Actualizada", email=doctor.email),
        admin=admin,
        db=db,
    )

    assert result.full_name == "Doctora Actualizada"


def test_admin_updates_user_email(identity_db):
    db, admin, _, doctor, *_ = identity_db

    result = update_user_profile(
        doctor.id,
        UserProfileUpdate(full_name=doctor.full_name, email="new-doctor@example.com"),
        admin=admin,
        db=db,
    )

    assert str(result.email) == "new-doctor@example.com"


def test_duplicate_email_is_rejected(identity_db):
    db, admin, _, doctor, secretary, *_ = identity_db

    with pytest.raises(HTTPException) as error:
        update_user_profile(
            doctor.id,
            UserProfileUpdate(full_name=doctor.full_name, email=secretary.email.upper()),
            admin=admin,
            db=db,
        )

    assert error.value.status_code == 409


def test_admin_changes_password_and_login_uses_only_new_password(identity_db):
    db, admin, _, doctor, *_ = identity_db
    old_password = "DoctorPassword123"
    new_password = "NewDoctorPassword456"

    result = update_user_password(
        doctor.id,
        UserPasswordUpdate(new_password=new_password),
        admin,
        db,
    )

    assert "password_hash" not in result.model_dump()
    assert verify_password(new_password, doctor.password_hash)
    assert not verify_password(old_password, doctor.password_hash)
    assert login(LoginRequest(email=doctor.email, password=new_password), Response(), db).access_token
    with pytest.raises(HTTPException) as error:
        login(LoginRequest(email=doctor.email, password=old_password), Response(), db)
    assert error.value.status_code == 401


def test_password_hash_is_never_returned(identity_db):
    db, admin, *_ = identity_db

    users = list_users(admin, db)

    assert users
    assert all("password_hash" not in user.model_dump() for user in users)


def test_admin_deactivates_and_reactivates_user(identity_db):
    db, admin, _, doctor, *_, center_one, _ = identity_db

    inactive = update_user_status(doctor.id, UserStatusUpdate(is_active=False), admin, db)

    assert inactive.is_active is False
    with pytest.raises(HTTPException) as error:
        login(LoginRequest(email=doctor.email, password="DoctorPassword123"), Response(), db)
    assert error.value.status_code == 401
    assert list_available_doctors(center_one.id, date(2026, 9, 10), user=admin, db=db) == []

    active = update_user_status(doctor.id, UserStatusUpdate(is_active=True), admin, db)
    assert active.is_active is True


def test_admin_changes_roles_and_unknown_role_is_rejected(identity_db):
    db, admin, _, doctor, _, _, doctor_role, *_ = identity_db

    result = update_user_roles(doctor.id, UserRolesUpdate(role_codes=["doctor", "secretary"]), admin, db)

    assert set(result.roles) == {"doctor", "secretary"}
    with pytest.raises(HTTPException) as error:
        update_user_roles(doctor.id, UserRolesUpdate(role_codes=[doctor_role.code, "unknown"]), admin, db)
    assert error.value.status_code == 422


def test_admin_assigns_primary_center_and_unassigns_center(identity_db):
    db, admin, _, doctor, *_, center_one, center_two = identity_db

    assigned = update_user_centers(
        doctor.id,
        UserCentersUpdate(center_ids=[center_one.id, center_two.id], primary_center_id=center_two.id),
        admin,
        db,
    )
    assert set(assigned.center_ids) == {center_one.id, center_two.id}
    assert assigned.primary_center_id == center_two.id

    unassigned = update_user_centers(
        doctor.id,
        UserCentersUpdate(center_ids=[center_two.id], primary_center_id=None),
        admin,
        db,
    )
    assert unassigned.center_ids == [center_two.id]
    assert unassigned.primary_center_id is None


def test_unknown_center_is_rejected(identity_db):
    db, admin, _, doctor, *_ = identity_db

    with pytest.raises(HTTPException) as error:
        update_user_centers(doctor.id, UserCentersUpdate(center_ids=[999]), admin, db)

    assert error.value.status_code == 422


def test_inactive_user_cannot_receive_new_center_assignment(identity_db):
    db, admin, _, doctor, *_, center_two = identity_db
    update_user_status(doctor.id, UserStatusUpdate(is_active=False), admin, db)

    with pytest.raises(HTTPException) as error:
        assign_user(center_two.id, CenterUserAssignment(user_id=doctor.id), admin, db)

    assert error.value.status_code == 422


def test_last_active_admin_cannot_be_deactivated(identity_db):
    db, admin, second_admin, *_ = identity_db
    second_admin.is_active = False
    db.commit()

    with pytest.raises(HTTPException) as error:
        update_user_status(admin.id, UserStatusUpdate(is_active=False), admin, db)

    assert error.value.status_code == 409
    assert admin.is_active is True


def test_last_active_admin_cannot_lose_admin_role(identity_db):
    db, admin, second_admin, _, _, _, doctor_role, *_ = identity_db
    second_admin.is_active = False
    db.commit()

    with pytest.raises(HTTPException) as error:
        update_user_roles(admin.id, UserRolesUpdate(role_codes=[doctor_role.code]), admin, db)

    assert error.value.status_code == 409
    assert "admin" in {role.code for role in admin.roles}


def test_administrator_cannot_change_own_email_status_or_admin_role(identity_db):
    db, admin, _, _, _, _, doctor_role, *_ = identity_db

    with pytest.raises(HTTPException) as email_error:
        update_user_profile(
            admin.id,
            UserProfileUpdate(full_name=admin.full_name, email="other-admin@example.com"),
            admin,
            db,
        )
    with pytest.raises(HTTPException) as status_error:
        update_user_status(admin.id, UserStatusUpdate(is_active=False), admin, db)
    with pytest.raises(HTTPException) as role_error:
        update_user_roles(admin.id, UserRolesUpdate(role_codes=[doctor_role.code]), admin, db)

    assert email_error.value.status_code == 422
    assert status_error.value.status_code == 422
    assert role_error.value.status_code == 422


def test_active_login_regression(identity_db):
    db, _, _, doctor, *_ = identity_db

    token = login(LoginRequest(email=doctor.email, password="DoctorPassword123"), Response(), db)

    assert token.access_token
