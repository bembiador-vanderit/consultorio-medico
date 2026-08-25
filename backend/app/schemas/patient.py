from datetime import date, datetime

from pydantic import BaseModel, EmailStr, Field

from app.schemas.insurance import PatientInsuranceCreate


class PatientCreate(BaseModel):
    first_name: str = Field(min_length=2, max_length=100)
    last_name: str = Field(min_length=2, max_length=100)
    date_of_birth: date
    phone: str | None = Field(default=None, max_length=30)
    email: EmailStr | None = None
    has_insurance: bool = False
    insurance: PatientInsuranceCreate | None = None


class PatientUpdate(BaseModel):
    first_name: str = Field(min_length=2, max_length=100)
    last_name: str = Field(min_length=2, max_length=100)
    date_of_birth: date
    phone: str | None = Field(default=None, max_length=30)
    email: EmailStr | None = None
    has_insurance: bool = False
    insurance: PatientInsuranceCreate | None = None


class PatientResponse(BaseModel):
    id: int
    first_name: str
    last_name: str
    date_of_birth: date
    phone: str | None
    email: EmailStr | None
    created_at: datetime
    model_config = {"from_attributes": True}
