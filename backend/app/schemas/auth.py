from pydantic import BaseModel, EmailStr, Field
class LoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)
class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
class UserResponse(BaseModel):
    id: int
    email: EmailStr
    full_name: str
    is_active: bool
    roles: list[str]
    primary_specialty_id: int | None = None
    specialty_ids: list[int] = Field(default_factory=list)
    specialty_names: list[str] = Field(default_factory=list)
class UserCreate(BaseModel):
    email: EmailStr
    full_name: str = Field(min_length=2, max_length=150)
    password: str = Field(min_length=12, max_length=128)
    role_codes: list[str] = Field(min_length=1)
    primary_specialty_id: int | None = Field(default=None, gt=0)
    specialty_ids: list[int] = Field(default_factory=list)
