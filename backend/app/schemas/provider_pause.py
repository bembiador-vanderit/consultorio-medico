from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


PauseReason = Literal[
    "ward_rounds", "procedure", "emergency", "meeting", "lunch",
    "temporary_absence", "other",
]


class ProviderPauseStart(BaseModel):
    model_config = ConfigDict(extra="forbid")
    center_id: int
    doctor_id: int | None = None
    reason: PauseReason
    notes: str | None = Field(default=None, max_length=1000)
    planned_start_at: datetime | None = None

    @field_validator("notes")
    @classmethod
    def clean_notes(cls, value: str | None) -> str | None:
        return value.strip() or None if value is not None else None


class ProviderPauseRead(BaseModel):
    id: int
    organization_id: int
    center_id: int
    doctor_id: int
    reason: PauseReason
    notes: str | None
    planned_start_at: datetime | None
    actual_started_at: datetime
    actual_finished_at: datetime | None
    started_by_user_id: int
    finished_by_user_id: int | None
    created_at: datetime
    updated_at: datetime
    duration_seconds: float | None = None
    model_config = {"from_attributes": True}
