from datetime import date, datetime

from pydantic import BaseModel, Field

from app.schemas.requested_tests import RequestedTestResponse


class ClinicalHistoryBase(BaseModel):
    consultation_date: date
    reason_for_visit: str | None = Field(default=None, max_length=5000)
    current_illness: str | None = Field(default=None, max_length=10000)
    personal_history: str | None = Field(default=None, max_length=10000)
    family_history: str | None = Field(default=None, max_length=10000)
    allergies: str | None = Field(default=None, max_length=5000)
    current_medications: str | None = Field(default=None, max_length=10000)
    previous_surgeries: str | None = Field(default=None, max_length=10000)
    chronic_conditions: str | None = Field(default=None, max_length=10000)
    habits: str | None = Field(default=None, max_length=10000)
    clinical_notes: str | None = Field(default=None, max_length=10000)


class ClinicalHistoryCreate(ClinicalHistoryBase):
    appointment_id: int | None = None
    doctor_id: int | None = None
    center_id: int | None = None


class ClinicalHistoryResponse(ClinicalHistoryBase):
    id: int
    patient_id: int
    appointment_id: int | None = None
    doctor_id: int | None = None
    center_id: int | None = None
    created_at: datetime
    updated_at: datetime
    requested_tests: list[RequestedTestResponse] = Field(default_factory=list)

    model_config = {"from_attributes": True}
