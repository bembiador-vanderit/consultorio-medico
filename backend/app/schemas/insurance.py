from datetime import date, datetime
from decimal import Decimal
from typing import Annotated, Literal
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

Money = Annotated[Decimal, Field(ge=0, max_digits=12, decimal_places=2)]
AUTHORIZATION_STATES = {"pending": "Pendiente", "authorized": "Autorizada", "rejected": "Rechazada", "not_required": "No requerida"}

class Input(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

class InsuranceCompanyCreate(Input):
    name: str = Field(min_length=2, max_length=150)
    code: str | None = Field(default=None, max_length=50)
    is_active: bool = True

class InsuranceCompanyResponse(InsuranceCompanyCreate):
    id: int
    created_at: datetime
    model_config = ConfigDict(from_attributes=True)

class InsurancePlanCreate(Input):
    insurance_company_id: int
    name: str = Field(min_length=2, max_length=150)
    code: str | None = Field(default=None, max_length=50)
    description: str | None = Field(default=None, max_length=1000)
    is_active: bool = True

class InsurancePlanResponse(InsurancePlanCreate):
    id: int
    model_config = ConfigDict(from_attributes=True)

class PatientInsuranceCreate(Input):
    insurance_company_id: int
    member_number: str = Field(min_length=1, max_length=100)
    plan_id: int | None = None
    plan_name: str | None = Field(default=None, max_length=150)
    policy_holder: str | None = Field(default=None, max_length=150)
    relationship_to_holder: str | None = Field(default=None, max_length=80)
    valid_from: date | None = None
    valid_until: date | None = None
    administrative_notes: str | None = Field(default=None, max_length=1000)
    is_primary: bool = True
    is_active: bool = True

    @model_validator(mode="after")
    def valid_period(self):
        if self.valid_from and self.valid_until and self.valid_until < self.valid_from:
            raise ValueError("La vigencia final debe ser igual o posterior a la inicial")
        if self.is_primary and not self.is_active:
            raise ValueError("Un seguro inactivo no puede ser principal")
        return self

class PatientInsuranceResponse(PatientInsuranceCreate):
    id: int
    insurance_company_name: str
    created_at: datetime
    model_config = ConfigDict(from_attributes=True)

class CoverageFields(Input):
    patient_insurance_id: int | None = None
    service: str = Field(min_length=1, max_length=200)
    currency: str = Field(default="DOP", pattern=r"^[A-Z]{3}$")
    base_amount: Money
    covered_amount: Money
    patient_copay: Money
    authorization_status: Literal["pending", "authorized", "rejected", "not_required"] = "pending"
    authorization_number: str | None = Field(default=None, max_length=100)
    authorized_at: datetime | None = None
    authorized_amount: Money | None = None
    authorization_notes: str | None = Field(default=None, max_length=1000)
    notes: str | None = Field(default=None, max_length=1000)
    revision: int = Field(default=0, ge=0)

class CoverageWrite(CoverageFields):
    @model_validator(mode="after")
    def consistent_amounts(self):
        if self.base_amount != self.covered_amount + self.patient_copay:
            raise ValueError("La tarifa debe ser igual al monto ARS más el copago")
        if self.patient_insurance_id is None and self.covered_amount != 0:
            raise ValueError("Sin seguro el monto ARS debe ser cero")
        if self.authorization_status == "authorized" and not self.authorization_number:
            raise ValueError("Registre el número de autorización")
        if self.authorized_at and self.authorized_at.tzinfo is None:
            raise ValueError("La fecha de autorización debe incluir zona horaria")
        return self

class CoverageResponse(CoverageFields):
    id: int
    appointment_id: int
    insurance_snapshot: dict
    expected_insurer_balance: Decimal
    updated_at: datetime
    model_config = ConfigDict(from_attributes=True)
