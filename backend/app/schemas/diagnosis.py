from datetime import datetime

from pydantic import BaseModel, Field


class DiagnosisCreate(BaseModel):
    description: str = Field(min_length=1, max_length=5000)
    icd10_code: str | None = Field(default=None, max_length=20)
    is_primary: bool = False


class DiagnosisResponse(DiagnosisCreate):
    id: int
    clinical_history_id: int
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}
