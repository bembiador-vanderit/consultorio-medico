import pytest
from fastapi import Depends, FastAPI, HTTPException
from fastapi.testclient import TestClient

from app.api.deps import current_user, require_permission
from app.models import Permission, Role, User
from app.services.bootstrap import ROLE_PERMISSIONS


def user_with_permissions(*permission_codes: str) -> User:
    permissions = [
        Permission(code=code, description=code)
        for code in permission_codes
    ]
    role = Role(code="test-role", name="Rol de prueba", permissions=permissions)
    return User(
        email="usuario-prueba@example.com",
        full_name="Usuario de prueba",
        password_hash="hash-de-prueba",
        roles=[role],
    )


def test_clinical_permission_is_reserved_for_doctors_and_admins():
    assert "clinical:access" in ROLE_PERMISSIONS["admin"][1]
    assert "clinical:access" in ROLE_PERMISSIONS["doctor"][1]
    assert "clinical:access" not in ROLE_PERMISSIONS["secretary"][1]
    assert "patients:access" in ROLE_PERMISSIONS["secretary"][1]


def test_clinical_access_accepts_an_authorized_user():
    user = user_with_permissions("patients:access", "clinical:access")

    assert require_permission("clinical:access")(user) is user


def test_clinical_access_rejects_a_secretary_permission_set():
    user = user_with_permissions("patients:access", "centers:access")

    with pytest.raises(HTTPException) as error:
        require_permission("clinical:access")(user)

    assert error.value.status_code == 403
    assert error.value.detail == "No tiene permiso para esta operación"


def test_secretary_receives_http_403_from_a_clinical_endpoint():
    app = FastAPI()
    clinical_access = require_permission("clinical:access")
    secretary = user_with_permissions("patients:access", "centers:access")

    @app.get("/clinical")
    def protected_endpoint(_: User = Depends(clinical_access)):
        return {"ok": True}

    app.dependency_overrides[current_user] = lambda: secretary

    response = TestClient(app).get("/clinical")

    assert response.status_code == 403
    assert response.json() == {"detail": "No tiene permiso para esta operación"}
