from datetime import date, time

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.api.routes import appointment_contacts as routes
from app.api.routes.appointments import delete_appointment, update_appointment
from app.db import Base
from app.models import (
    Appointment, AppointmentContactAttempt, CareCenter, Organization,
    OrganizationMembership, Patient, Role, SecretaryCenterScope, User,
)
from app.schemas.appointment_contact import ContactAttemptCreate
from app.schemas.appointment import AppointmentCreate
from app.services.tenancy import bind_scope


@pytest.fixture
def contacts_db():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        secretary_role = Role(code="secretary", name="Secretaria")
        doctor_role = Role(code="doctor", name="Doctor")
        admin_role = Role(code="admin", name="Admin")
        db.add_all([secretary_role, doctor_role, admin_role, Organization(id=1, slug="one", name="Uno"), Organization(id=2, slug="two", name="Dos")])
        db.flush()
        center = CareCenter(organization_id=1, name="Centro sintético", city="Prueba")
        db.add(center)
        db.flush()
        admin = User(email="admin@synthetic.test", full_name="Administradora", password_hash="synthetic",
                     memberships=[OrganizationMembership(organization_id=1, roles=[admin_role]), OrganizationMembership(organization_id=2, roles=[admin_role])])
        doctor = User(email="doctor@synthetic.test", full_name="Doctora", password_hash="synthetic",
                      centers=[center], memberships=[OrganizationMembership(organization_id=1, roles=[doctor_role])])
        secretary = User(email="secretary@synthetic.test", full_name="Secretaria", password_hash="synthetic",
                         centers=[center], memberships=[OrganizationMembership(organization_id=1, roles=[secretary_role])])
        first = Patient(organization_id=1, first_name="Ana", last_name="Prueba", phone="809-000-0001", date_of_birth=date(1990, 1, 1))
        second = Patient(organization_id=1, first_name="Bea", last_name="Prueba", phone="809-000-0002", date_of_birth=date(1990, 1, 1))
        db.add_all([admin, doctor, secretary, first, second])
        db.flush()
        db.add(SecretaryCenterScope(organization_id=1, secretary_id=secretary.id,
                                    center_id=center.id, manage_all_doctors=True))
        day = date(2030, 10, 15)
        one = Appointment(organization_id=1, patient_id=first.id, doctor_id=doctor.id, center_id=center.id,
                          appointment_date=day, appointment_time=time(9, 0), status="scheduled")
        two = Appointment(organization_id=1, patient_id=second.id, doctor_id=doctor.id, center_id=center.id,
                          appointment_date=day, appointment_time=time(10, 0), status="scheduled")
        db.add_all([one, two])
        db.commit()
        ids = (admin.id, doctor.id, secretary.id, one.id, two.id)
    yield engine, ids, day
    engine.dispose()


def session(engine, organization_id=1):
    db = Session(engine)
    bind_scope(db, "tenant", organization_id)
    return db


def test_append_only_history_latest_totals_and_no_appointment_side_effects(contacts_db):
    engine, (admin_id, _, _, first_id, second_id), day = contacts_db
    with session(engine) as db:
        admin = db.get(User, admin_id)
        pending = routes.daily_contacts(day, user=admin, db=db, result=None)
        assert pending.totals.total_expected == pending.totals.not_contacted == 2
        assert [item.patient_phone for item in pending.items] == ["809-000-0001", "809-000-0002"]
        assert all(item.latest_contact is None for item in pending.items)
        original = db.get(Appointment, first_id)
        original_time, original_status = original.appointment_time, original.status
        for result in ("no_answer", "retry", "will_attend"):
            routes.record_contact(first_id, ContactAttemptCreate(result=result, contact_value="809-000-0001"), admin, db)
        routes.record_contact(second_id, ContactAttemptCreate(result="will_not_attend"), admin, db)
        history = routes.list_contact_history(first_id, admin, db)
        assert [item.result for item in history] == ["no_answer", "retry", "will_attend"]
        assert all(item.contacted_by_user_id == admin_id for item in history)
        daily = routes.daily_contacts(day, user=admin, db=db, result=None)
        assert (daily.totals.contacted, daily.totals.not_contacted, daily.totals.will_attend, daily.totals.will_not_attend) == (2, 0, 1, 1)
        assert [item.latest_contact.result for item in daily.items] == ["will_attend", "will_not_attend"]
        assert [item.appointment_id for item in routes.daily_contacts(day, user=admin, db=db, result="will_attend").items] == [first_id]
        assert routes.daily_contacts(day, user=admin, db=db, result="no_answer").items == []
        assert (original.status, original.appointment_time) == (original_status, original_time)
        assert db.scalar(select(AppointmentContactAttempt).where(AppointmentContactAttempt.appointment_id == first_id)) is not None
        with pytest.raises(HTTPException) as blocked:
            delete_appointment(first_id, admin, db)
        assert blocked.value.status_code == 409
        with pytest.raises(HTTPException) as blocked:
            update_appointment(first_id, AppointmentCreate(
                patient_id=db.get(Appointment, second_id).patient_id,
                doctor_id=original.doctor_id, center_id=original.center_id,
                appointment_date=day, appointment_time=original_time,
            ), admin, db)
        assert blocked.value.status_code == 409


def test_scope_and_write_role_enforced(contacts_db):
    engine, (admin_id, doctor_id, secretary_id, first_id, _), day = contacts_db
    with session(engine) as db:
        secretary = db.get(User, secretary_id)
        recorded = routes.record_contact(first_id, ContactAttemptCreate(result="no_answer"), secretary, db)
        assert recorded.contacted_by_user_id == secretary_id
        assert routes.daily_contacts(day, user=secretary, db=db, result="no_answer").totals.total_expected == 2
    with session(engine) as db:
        doctor = db.get(User, doctor_id)
        with pytest.raises(HTTPException) as forbidden:
            routes.record_contact(first_id, ContactAttemptCreate(result="retry"), doctor, db)
        assert forbidden.value.status_code == 403
    with session(engine, 2) as db:
        admin = db.get(User, admin_id)
        assert routes.daily_contacts(day, user=admin, db=db, result=None).totals.total_expected == 0
        for operation in (
            lambda: routes.record_contact(first_id, ContactAttemptCreate(result="retry"), admin, db),
            lambda: routes.list_contact_history(first_id, admin, db),
        ):
            with pytest.raises(HTTPException) as hidden:
                operation()
            assert hidden.value.status_code == 404
