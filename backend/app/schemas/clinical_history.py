from datetime import datetime

from pydantic import BaseModel, Field


class ClinicalHistoryBase(BaseModel):
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
    pass


class ClinicalHistoryResponse(ClinicalHistoryBase):
    id: int
    patient_id: int
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}
