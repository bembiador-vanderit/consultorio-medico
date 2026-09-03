from pydantic import BaseModel, EmailStr, Field

from app.schemas.auth import UserResponse


class UserAdminResponse(UserResponse):
    center_ids: list[int]
    primary_center_id: int | None = None


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
