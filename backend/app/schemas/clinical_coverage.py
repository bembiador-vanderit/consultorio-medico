from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, model_validator


class ClinicalCoverageCreate(BaseModel):
    substitute_doctor_id: int = Field(gt=0)
    center_id: int = Field(gt=0)
    starts_at: datetime
    ends_at: datetime

    @model_validator(mode="after")
    def validate_period(self):
        if self.starts_at.tzinfo is not None or self.ends_at.tzinfo is not None:
            raise ValueError("Las fechas deben expresarse en la hora local de la instalación")
        if self.ends_at <= self.starts_at:
            raise ValueError("La fecha final debe ser posterior a la inicial")
        return self


class ClinicalCoverageResponse(BaseModel):
    id: int
    principal_doctor_id: int
    principal_doctor_name: str
    substitute_doctor_id: int
    substitute_doctor_name: str
    center_id: int
    center_name: str
    starts_at: datetime
    ends_at: datetime
    revoked_at: datetime | None
    status: Literal["active", "future", "expired", "revoked"]
    created_at: datetime


class EligibleSubstituteResponse(BaseModel):
    id: int
    full_name: str
