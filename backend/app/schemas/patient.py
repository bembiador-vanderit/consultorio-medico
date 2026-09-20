from datetime import date, datetime

from typing import Literal
import unicodedata

from pydantic import BaseModel, EmailStr, Field, field_validator, model_validator

from app.services.patient_demographics import normalize_document

from app.schemas.insurance import PatientInsuranceCreate


class PatientDemographics(BaseModel):
    document_type: Literal["cedula", "passport", "other"] | None = None
    document_number: str | None = Field(default=None, max_length=100)
    registered_sex: Literal["female", "male", "other", "unknown"] | None = None
    blood_type: Literal["A+", "A-", "B+", "B-", "AB+", "AB-", "O+", "O-"] | None = None
    locality_id: int | None = Field(default=None, gt=0)
    home_phone: str | None = Field(default=None, max_length=30)
    address: str | None = Field(default=None, max_length=500)
    province: str | None = Field(default=None, max_length=100)
    nationality: str | None = Field(default=None, max_length=100)
    occupation: str | None = Field(default=None, max_length=150)
    emergency_contact_name: str | None = Field(default=None, max_length=150)
    emergency_contact_relationship: str | None = Field(default=None, max_length=100)
    emergency_contact_mobile: str | None = Field(default=None, max_length=30)
    emergency_contact_home_phone: str | None = Field(default=None, max_length=30)
    guardian_name: str | None = Field(default=None, max_length=150)
    guardian_relationship: str | None = Field(default=None, max_length=100)
    guardian_mobile: str | None = Field(default=None, max_length=30)
    guardian_home_phone: str | None = Field(default=None, max_length=30)

    @field_validator("document_number", mode="before")
    @classmethod
    def canonical_document(cls, value):
        if value is not None and not isinstance(value, str):
            raise ValueError("El documento debe ser texto")
        if value and any(unicodedata.category(char).startswith("C") for char in value):
            raise ValueError("El documento contiene caracteres no permitidos")
        return normalize_document(value)

    @field_validator("home_phone", "address", "province", "nationality", "occupation", "emergency_contact_name", "emergency_contact_relationship", "emergency_contact_mobile", "emergency_contact_home_phone", "guardian_name", "guardian_relationship", "guardian_mobile", "guardian_home_phone")
    @classmethod
    def trim_optional(cls, value):
        return (value.strip() or None) if value is not None else None

    @model_validator(mode="after")
    def document_pair(self):
        # Explicit changes send the complete pair; omitted fields preserve legacy data.
        if (self.document_type is None) != (self.document_number is None):
            raise ValueError("Indique tipo y número de documento, o deje ambos vacíos")
        if self.document_number and not any(char.isalnum() for char in self.document_number):
            raise ValueError("Indique un número de documento válido")
        return self


class PatientIdentityFields(PatientDemographics):
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


class PatientDetailResponse(PatientResponse, PatientDemographics):
    locality_name: str | None = None


class PatientIdentityResponse(BaseModel):
    id: int
    first_name: str
    last_name: str
    date_of_birth: date
    phone_masked: str | None = None
    email_masked: str | None = None
    selection_token: str


class PatientCreatedResponse(PatientDetailResponse):
    selection_token: str
