from datetime import datetime

from pydantic import BaseModel, Field


class PrescriptionCreate(BaseModel):
    medication: str = Field(min_length=1, max_length=255)
    presentation: str | None = Field(default=None, max_length=255)
    dose: str | None = Field(default=None, max_length=255)
    route: str | None = Field(default=None, max_length=100)
    frequency: str | None = Field(default=None, max_length=255)
    duration: str | None = Field(default=None, max_length=255)
    quantity: int | None = Field(default=None, ge=1)
    instructions: str | None = Field(default=None, max_length=5000)


class PrescriptionResponse(PrescriptionCreate):
    id: int
    clinical_history_id: int
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}
