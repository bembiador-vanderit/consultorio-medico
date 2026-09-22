from datetime import date, time
from datetime import datetime, timedelta, timezone

import jwt

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool
from sqlalchemy.exc import SQLAlchemyError

from app.api.deps import current_user
from app.api.routes import appointments, clinical_history, insurance, patients, regional
from app.db import Base, get_db
from app.models import Appointment, CareCenter, InsuranceCompany, Patient, PatientInsurance, Permission, Role, SecretaryCenterScope, Specialty, User
from app.services.bootstrap import ROLE_PERMISSIONS
from app.services.clinical_specialties import set_doctor_specialties
from app.core.config import get_settings


@pytest.fixture()
def patient_app():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    db = Session(engine)
    permissions = {code: Permission(code=code, description=code) for _, codes in ROLE_PERMISSIONS.values() for code in codes}
    roles = {code: Role(code=code, name=name, permissions=[permissions[item] for item in codes]) for code, (name, codes) in ROLE_PERMISSIONS.items()}
    centers = [CareCenter(name=f"Centro ficticio {i}", city="Ciudad ficticia", is_active=True) for i in range(2)]
    specialty = Specialty(name="Especialidad ficticia", is_active=True)
    doctor = User(email="doctor@example.test", full_name="Doctor ficticio", password_hash="hash", roles=[roles["doctor"]], centers=centers, is_active=True)
    other = User(email="other@example.test", full_name="Otro doctor", password_hash="hash", roles=[roles["doctor"]], centers=centers, is_active=True)
    secretary = User(email="secretary@example.test", full_name="Secretaria ficticia", password_hash="hash", roles=[roles["secretary"]], centers=[centers[0]], is_active=True)
    admin = User(email="admin@example.test", full_name="Admin ficticio", password_hash="hash", roles=[roles["admin"]], is_active=True)
    no_permission = User(email="no-permission@example.test", full_name="Sin permiso", password_hash="hash", roles=[], is_active=True)
    a = Patient(first_name="Paciente", last_name="Visible", date_of_birth=date(1990, 1, 1), phone="8095550001", email="visible@example.com")
    b = Patient(first_name="Paciente", last_name="Ajeno", date_of_birth=date(1991, 1, 1), phone="8095550002", email="outside@example.com")
    company = InsuranceCompany(name="ARS ficticia", is_active=True)
    db.add_all([*centers, specialty, doctor, other, secretary, admin, no_permission, a, b, company])
    db.flush()
    for user in (doctor, other):
        set_doctor_specialties(db, user, specialty.id, [specialty.id])
    db.add(SecretaryCenterScope(secretary_id=secretary.id, center_id=centers[0].id, manage_all_doctors=False, doctors=[doctor]))
    own = Appointment(patient_id=a.id, doctor_id=doctor.id, center_id=centers[0].id, specialty_id=specialty.id, appointment_date=date(2026, 9, 14), appointment_time=time(8), status="scheduled")
    db.add_all([own, Appointment(patient_id=b.id, doctor_id=other.id, center_id=centers[1].id, specialty_id=specialty.id, appointment_date=date(2026, 9, 14), appointment_time=time(9), status="scheduled")])
    policy = PatientInsurance(patient_id=a.id, insurance_company_id=company.id, member_number="FICTIONAL", is_active=True, is_primary=True)
    db.add(policy)
    db.commit()
    active = {"user": doctor}
    app = FastAPI()
    for module in (patients, appointments, insurance, clinical_history, regional):
        app.include_router(module.router, prefix="/api/v1")
    app.dependency_overrides[current_user] = lambda: active["user"]
    def session():
        try:
            yield db
        finally:
            db.rollback()
    app.dependency_overrides[get_db] = session
    yield {"client": TestClient(app), "db": db, "active": active, "doctor": doctor, "other": other, "secretary": secretary, "admin": admin, "no_permission": no_permission, "roles": roles, "centers": centers, "specialty": specialty, "a": a, "b": b, "policy": policy, "company": company, "own": own}
    db.close()
    engine.dispose()


def appointment_payload(ctx, patient_id, **changes):
    return {"patient_id": patient_id, "doctor_id": ctx["doctor"].id, "center_id": ctx["centers"][0].id, "specialty_id": ctx["specialty"].id, "appointment_date": "2026-09-15", "appointment_time": "10:00:00", "status": "scheduled", **changes}


def identity_payload(patient, **changes):
    return {"first_name": patient.first_name, "last_name": patient.last_name, "date_of_birth": patient.date_of_birth.isoformat(), "phone": patient.phone, "email": patient.email, **changes}


@pytest.mark.parametrize("role", ["doctor", "secretary"])
def test_direct_foreign_patient_id_cannot_manufacture_visibility(patient_app, role):
    ctx = patient_app
    ctx["active"]["user"] = ctx[role]
    client, db, b = ctx["client"], ctx["db"], ctx["b"]
    before = db.scalar(select(func.count()).select_from(Appointment))
    assert client.get(f"/api/v1/patients/{b.id}").status_code == 404
    response = client.post("/api/v1/appointments", json=appointment_payload(ctx, b.id))
    assert response.status_code == 404
    assert db.scalar(select(func.count()).select_from(Appointment)) == before
    assert b.id not in {item["id"] for item in client.get("/api/v1/patients").json()}
    assert client.get(f"/api/v1/patients/{b.id}").status_code == 404


def test_update_cannot_duplicate_another_identity(patient_app):
    ctx = patient_app
    a, b = ctx["a"], ctx["b"]
    response = ctx["client"].put(f"/api/v1/patients/{a.id}", json=identity_payload(a, date_of_birth=b.date_of_birth.isoformat(), phone=b.phone, email=None))
    assert response.status_code == 409
    ctx["db"].refresh(a)
    assert a.phone == "8095550001"


def test_identity_update_omitting_insurance_preserves_it(patient_app):
    ctx = patient_app
    response = ctx["client"].put(f"/api/v1/patients/{ctx['a'].id}", json=identity_payload(ctx["a"], phone="8095550099", email="changed@example.com"))
    assert response.status_code == 200
    ctx["db"].refresh(ctx["policy"])
    assert ctx["policy"].is_active and ctx["policy"].is_primary


@pytest.mark.parametrize("role", ["doctor", "secretary", "admin"])
def test_visible_patient_can_be_scheduled_without_proof(patient_app, role):
    ctx = patient_app
    ctx["active"]["user"] = ctx[role]
    assert ctx["client"].post("/api/v1/appointments", json=appointment_payload(ctx, ctx["a"].id)).status_code == 201


@pytest.mark.parametrize("role", ["doctor", "secretary", "admin"])
def test_authorized_registration_preserves_first_appointment(patient_app, role):
    ctx = patient_app
    ctx["active"]["user"] = ctx[role]
    created = ctx["client"].post("/api/v1/patients", json={"first_name": "Nuevo", "last_name": "Paciente", "date_of_birth": "2000-01-01"})
    assert created.status_code == 201
    patient = created.json()
    if role != "admin":
        assert ctx["client"].get(f"/api/v1/patients/{patient['id']}").status_code == 404
        assert ctx["client"].post("/api/v1/appointments", json=appointment_payload(ctx, patient["id"])).status_code == 404
    assert ctx["client"].post("/api/v1/appointments", json=appointment_payload(ctx, patient["id"], patient_selection_token=patient["selection_token"])).status_code == 201


def search_foreign(ctx, role="doctor"):
    ctx["active"]["user"] = ctx[role]
    b = ctx["b"]
    response = ctx["client"].get("/api/v1/patients/identity-search", params={"date_of_birth": b.date_of_birth.isoformat(), "phone": b.phone, "center_id": ctx["centers"][0].id, "doctor_id": ctx["doctor"].id})
    assert response.status_code == 200
    return response.json()[0]["selection_token"]


@pytest.mark.parametrize("role", ["doctor", "secretary"])
def test_restricted_identity_search_proof_allows_legitimate_existing_patient(patient_app, role):
    ctx = patient_app
    proof = search_foreign(ctx, role)
    assert ctx["client"].get(f"/api/v1/patients/{ctx['b'].id}").status_code == 404  # Search alone does not grant full identity.
    assert ctx["client"].post("/api/v1/appointments", json=appointment_payload(ctx, ctx["b"].id, patient_selection_token=proof)).status_code == 201
    assert ctx["client"].get(f"/api/v1/clinical-history/patients/{ctx['b'].id}").status_code == (403 if role == "secretary" else 200)


@pytest.mark.parametrize("attack", ["missing", "tampered", "expired", "wrong_user", "wrong_patient", "wrong_existing_patient", "wrong_center", "wrong_doctor", "session_token"])
def test_selection_proof_cannot_be_enumerated_reused_or_forged(patient_app, attack):
    ctx = patient_app
    proof = search_foreign(ctx)
    payload = appointment_payload(ctx, ctx["b"].id, patient_selection_token=proof)
    if attack == "missing":
        payload.pop("patient_selection_token")
    elif attack == "tampered":
        payload["patient_selection_token"] = proof + "x"
    elif attack == "expired":
        claims = jwt.decode(proof, get_settings().secret_key, algorithms=["HS256"], audience="patient-selection")
        claims["iat"] = datetime.now(timezone.utc) - timedelta(hours=1)
        claims["exp"] = datetime.now(timezone.utc) - timedelta(minutes=1)
        payload["patient_selection_token"] = jwt.encode(claims, get_settings().secret_key, algorithm="HS256")
    elif attack == "wrong_user":
        ctx["active"]["user"] = ctx["secretary"]
    elif attack == "wrong_patient":
        payload["patient_id"] = 999999
    elif attack == "wrong_existing_patient":
        another = Patient(first_name="Tercero", last_name="Ajeno", date_of_birth=date(1995, 1, 1))
        ctx["db"].add(another)
        ctx["db"].commit()
        payload["patient_id"] = another.id
    elif attack == "wrong_center":
        payload["center_id"] = ctx["centers"][1].id
    elif attack == "wrong_doctor":
        payload["doctor_id"] = ctx["other"].id
    else:
        from app.core.security import create_access_token
        payload["patient_selection_token"] = create_access_token(ctx["doctor"].email)
    before = ctx["db"].scalar(select(func.count()).select_from(Appointment))
    assert ctx["client"].post("/api/v1/appointments", json=payload).status_code == 404
    assert ctx["db"].scalar(select(func.count()).select_from(Appointment)) == before
    assert ctx["client"].get(f"/api/v1/patients/{ctx['b'].id}").status_code == 404


def test_proof_is_not_a_session_token(patient_app):
    from app.api.deps import current_user as authenticate
    from fastapi import HTTPException
    from fastapi.security import HTTPAuthorizationCredentials
    proof = search_foreign(patient_app)
    with pytest.raises(HTTPException) as rejected:
        authenticate(HTTPAuthorizationCredentials(scheme="Bearer", credentials=proof), patient_app["db"])
    assert rejected.value.status_code == 401


def test_new_patient_proof_does_not_bypass_secretary_center_scope(patient_app):
    ctx = patient_app
    ctx["active"]["user"] = ctx["secretary"]
    created = ctx["client"].post("/api/v1/patients", json={"first_name": "Nuevo", "last_name": "Paciente", "date_of_birth": "2000-01-01"}).json()
    payload = appointment_payload(ctx, created["id"], patient_selection_token=created["selection_token"], center_id=ctx["centers"][1].id)
    assert ctx["client"].post("/api/v1/appointments", json=payload).status_code == 403


def test_search_proof_does_not_survive_revoked_secretary_assignment(patient_app):
    ctx = patient_app
    proof = search_foreign(ctx, "secretary")
    scope = ctx["db"].scalar(select(SecretaryCenterScope).where(SecretaryCenterScope.secretary_id == ctx["secretary"].id))
    scope.doctors = []
    ctx["db"].commit()
    assert ctx["client"].post("/api/v1/appointments", json=appointment_payload(ctx, ctx["b"].id, patient_selection_token=proof)).status_code == 403
    assert ctx["client"].get(f"/api/v1/patients/{ctx['b'].id}").status_code == 404


def test_admin_can_schedule_global_identity_without_clinical_authority(patient_app):
    ctx = patient_app
    ctx["active"]["user"] = ctx["admin"]
    assert ctx["client"].post("/api/v1/appointments", json=appointment_payload(ctx, ctx["b"].id)).status_code == 201
    assert ctx["client"].get(f"/api/v1/clinical-history/patients/{ctx['b'].id}").status_code == 404


@pytest.mark.parametrize("extra_role,allowed", [("admin", True), ("secretary", False)])
def test_multirole_preserves_administrative_precedence_and_clinical_scope(patient_app, extra_role, allowed):
    ctx = patient_app
    ctx["doctor"].roles.append(ctx["roles"][extra_role])
    ctx["db"].commit()
    assert ctx["client"].get(f"/api/v1/clinical-history/patients/{ctx['b'].id}").status_code == 404
    response = ctx["client"].post("/api/v1/appointments", json=appointment_payload(ctx, ctx["b"].id))
    assert response.status_code == (201 if allowed else 404)


def test_secretary_cannot_replace_patient_using_direct_id(patient_app):
    ctx = patient_app
    ctx["active"]["user"] = ctx["secretary"]
    payload = appointment_payload(ctx, ctx["b"].id)
    response = ctx["client"].put(f"/api/v1/appointments/{ctx['own'].id}", json=payload)
    assert response.status_code == 404
    ctx["db"].refresh(ctx["own"])
    assert ctx["own"].patient_id == ctx["a"].id
    proof = search_foreign(ctx, "secretary")
    payload["patient_selection_token"] = proof
    assert ctx["client"].put(f"/api/v1/appointments/{ctx['own'].id}", json=payload).status_code == 200


@pytest.mark.parametrize("change", [{}, {"last_name": "Nombre cambiado"}, {"phone": " 8095550001 "}, {"email": "VISIBLE@example.com"}, {"date_of_birth": "1992-02-02"}])
def test_self_match_and_nonconflicting_edits_are_allowed(patient_app, change):
    ctx = patient_app
    assert ctx["client"].put(f"/api/v1/patients/{ctx['a'].id}", json=identity_payload(ctx["a"], **change)).status_code == 200


@pytest.mark.parametrize("identifier", ["phone", "email"])
def test_identity_update_collision_uses_current_dob_and_either_identifier(patient_app, identifier):
    ctx = patient_app
    b = ctx["b"]
    change = {"date_of_birth": b.date_of_birth.isoformat(), identifier: getattr(b, identifier)}
    response = ctx["client"].put(f"/api/v1/patients/{ctx['a'].id}", json=identity_payload(ctx["a"], **change))
    assert response.status_code == 409
    assert b.first_name not in response.json()["detail"]


def test_legacy_without_contact_and_unchanged_existing_duplicate_remain_editable(patient_app):
    ctx = patient_app
    a = ctx["a"]
    ctx["db"].add(Patient(**{key: value for key, value in identity_payload(a).items() if key != "date_of_birth"}, date_of_birth=a.date_of_birth))
    ctx["db"].commit()
    assert ctx["client"].put(f"/api/v1/patients/{a.id}", json=identity_payload(a, last_name="Solo nombre")).status_code == 200
    assert ctx["client"].put(f"/api/v1/patients/{a.id}", json=identity_payload(a, phone=None, email=None)).status_code == 200


def test_user_without_permission_or_scope_cannot_edit(patient_app):
    ctx = patient_app
    ctx["active"]["user"] = ctx["no_permission"]
    assert ctx["client"].put(f"/api/v1/patients/{ctx['a'].id}", json=identity_payload(ctx["a"])).status_code == 403
    ctx["active"]["user"] = ctx["doctor"]
    assert ctx["client"].put(f"/api/v1/patients/{ctx['b'].id}", json=identity_payload(ctx["b"])).status_code == 404


@pytest.mark.parametrize("insurance_fields", [{}, {"insurance": None}, {"has_insurance": True}, {"has_insurance": True, "insurance": None}])
def test_insurance_omission_and_existing_frontend_noop_preserve_every_field(patient_app, insurance_fields):
    ctx = patient_app
    policy = ctx["policy"]
    before = (policy.id, policy.member_number, policy.plan_name, policy.is_active, policy.is_primary, policy.created_at)
    assert ctx["client"].put(f"/api/v1/patients/{ctx['a'].id}", json=identity_payload(ctx["a"], **insurance_fields)).status_code == 200
    ctx["db"].refresh(policy)
    assert (policy.id, policy.member_number, policy.plan_name, policy.is_active, policy.is_primary, policy.created_at) == before
    assert ctx["db"].scalar(select(func.count()).select_from(PatientInsurance)) == 1


@pytest.mark.parametrize("include_flag", [True, False])
def test_explicit_insurance_update_adds_affiliation_and_preserves_history(patient_app, include_flag):
    ctx = patient_app
    fields = {"insurance": {"insurance_company_id": ctx["company"].id, "member_number": "NEW-FICTIONAL", "plan_name": "Plan ficticio"}}
    if include_flag:
        fields["has_insurance"] = True
    assert ctx["client"].put(f"/api/v1/patients/{ctx['a'].id}", json=identity_payload(ctx["a"], **fields)).status_code == 200
    policies = ctx["client"].get(f"/api/v1/insurance/patients/{ctx['a'].id}").json()
    assert len(policies) == 2
    assert policies[0]["member_number"] == "NEW-FICTIONAL" and policies[0]["is_primary"]
    ctx["db"].refresh(ctx["policy"])
    assert ctx["policy"].is_active and not ctx["policy"].is_primary


def test_explicit_insurance_optout_deactivates_without_deleting(patient_app):
    ctx = patient_app
    assert ctx["client"].put(f"/api/v1/patients/{ctx['a'].id}", json=identity_payload(ctx["a"], has_insurance=False)).status_code == 200
    ctx["db"].refresh(ctx["policy"])
    assert not ctx["policy"].is_active and not ctx["policy"].is_primary
    assert ctx["db"].scalar(select(func.count()).select_from(PatientInsurance)) == 1


@pytest.mark.parametrize("invalid", [{"insurance_company_id": 99999, "member_number": "FICTIONAL"}, {"insurance_company_id": 1, "member_number": "   "}, {"insurance_company_id": 1}, {"insurance_company_id": -1, "member_number": "FICTIONAL"}])
def test_invalid_insurance_cannot_partially_update_identity_or_policy(patient_app, invalid):
    ctx = patient_app
    response = ctx["client"].put(f"/api/v1/patients/{ctx['a'].id}", json=identity_payload(ctx["a"], phone="8095559999", insurance=invalid, has_insurance=True))
    assert response.status_code == 422
    ctx["db"].refresh(ctx["a"])
    ctx["db"].refresh(ctx["policy"])
    assert ctx["a"].phone == "8095550001"
    assert ctx["policy"].is_active and ctx["policy"].is_primary
    assert ctx["db"].scalar(select(func.count()).select_from(PatientInsurance)) == 1


def test_conflicting_optout_and_insurance_is_rejected_without_partial_state(patient_app):
    ctx = patient_app
    payload = identity_payload(ctx["a"], phone="8095559999", has_insurance=False, insurance={"insurance_company_id": ctx["company"].id, "member_number": "FICTIONAL"})
    assert ctx["client"].put(f"/api/v1/patients/{ctx['a'].id}", json=payload).status_code == 422
    ctx["db"].refresh(ctx["a"])
    ctx["db"].refresh(ctx["policy"])
    assert ctx["a"].phone == "8095550001"
    assert ctx["policy"].is_active and ctx["policy"].is_primary


@pytest.mark.parametrize("insurance_change", [False, True])
def test_commit_failure_rolls_back_identity_and_insurance(patient_app, monkeypatch, insurance_change):
    ctx = patient_app
    def fail_commit():
        ctx["db"].flush()
        raise SQLAlchemyError("synthetic transaction failure")
    monkeypatch.setattr(ctx["db"], "commit", fail_commit)
    fields = {"has_insurance": False}
    if insurance_change:
        fields = {"has_insurance": True, "insurance": {"insurance_company_id": ctx["company"].id, "member_number": "NEW-FICTIONAL"}}
    assert ctx["client"].put(f"/api/v1/patients/{ctx['a'].id}", json=identity_payload(ctx["a"], phone="8095559999", **fields)).status_code == 500
    ctx["db"].refresh(ctx["a"])
    ctx["db"].refresh(ctx["policy"])
    assert ctx["a"].phone == "8095550001"
    assert ctx["policy"].is_active and ctx["policy"].is_primary
    assert ctx["db"].scalar(select(func.count()).select_from(PatientInsurance)) == 1


def test_invalid_insurance_cannot_leave_created_patient(patient_app):
    ctx = patient_app
    before = ctx["db"].scalar(select(func.count()).select_from(Patient))
    response = ctx["client"].post("/api/v1/patients", json={"first_name": "Nuevo", "last_name": "Paciente", "date_of_birth": "2000-01-01", "has_insurance": True, "insurance": {"insurance_company_id": 99999, "member_number": "FICTIONAL"}})
    assert response.status_code == 422
    assert ctx["db"].scalar(select(func.count()).select_from(Patient)) == before
