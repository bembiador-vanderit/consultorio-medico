from datetime import datetime

from pydantic import BaseModel, Field, field_validator


class InsuranceCompanyCreate(BaseModel):
    name: str = Field(min_length=2, max_length=150)
    code: str | None = Field(default=None, max_length=50)


class InsuranceCompanyResponse(InsuranceCompanyCreate):
    id: int
    is_active: bool
    created_at: datetime
    model_config = {"from_attributes": True}


class PatientInsuranceCreate(BaseModel):
    insurance_company_id: int
    member_number: str = Field(min_length=1, max_length=100)
    plan_name: str | None = Field(default=None, max_length=150)
    is_primary: bool = True

    @field_validator("member_number")
    @classmethod
    def nonblank_member_number(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Debe registrar el número de afiliado")
        return value


class PatientInsuranceResponse(BaseModel):
    id: int
    insurance_company_id: int
    insurance_company_name: str
    member_number: str
    plan_name: str | None
    is_primary: bool
    is_active: bool
    created_at: datetime
