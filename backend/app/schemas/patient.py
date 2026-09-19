from datetime import date, datetime

from pydantic import BaseModel, EmailStr, Field, field_validator

from app.schemas.insurance import PatientInsuranceCreate


class PatientIdentityFields(BaseModel):
    first_name: str = Field(min_length=2, max_length=100)
    last_name: str = Field(min_length=2, max_length=100)
    date_of_birth: date
    phone: str | None = Field(default=None, max_length=30)
    email: EmailStr | None = None

    @field_validator("phone")
    @classmethod
    def trim_phone(cls, value: str | None) -> str | None:
        return (value.strip() or None) if value is not None else None


class PatientCreate(PatientIdentityFields):
    has_insurance: bool = False
    insurance: PatientInsuranceCreate | None = None


class PatientUpdate(PatientIdentityFields):
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


class PatientIdentityResponse(BaseModel):
    id: int
    first_name: str
    last_name: str
    date_of_birth: date
    phone_masked: str | None = None
    email_masked: str | None = None
    selection_token: str


class PatientCreatedResponse(PatientResponse):
    selection_token: str
