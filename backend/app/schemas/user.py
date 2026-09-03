from pydantic import BaseModel, EmailStr, Field

from app.schemas.auth import UserResponse


class SecretaryDoctorScope(BaseModel):
    center_id: int
    manage_all_doctors: bool = False
    doctor_ids: list[int] = Field(default_factory=list)


class SecretaryDoctorScopesUpdate(BaseModel):
    scopes: list[SecretaryDoctorScope] = Field(default_factory=list)


class UserAdminResponse(UserResponse):
    center_ids: list[int]
    primary_center_id: int | None = None
    secretary_scopes: list[SecretaryDoctorScope] = Field(default_factory=list)


class UserProfileUpdate(BaseModel):
    full_name: str = Field(min_length=2, max_length=150)
    email: EmailStr


class UserPasswordUpdate(BaseModel):
    new_password: str = Field(min_length=12, max_length=128)


class UserStatusUpdate(BaseModel):
    is_active: bool


class UserRolesUpdate(BaseModel):
    role_codes: list[str] = Field(min_length=1)


class UserCentersUpdate(BaseModel):
    center_ids: list[int]
    primary_center_id: int | None = None
