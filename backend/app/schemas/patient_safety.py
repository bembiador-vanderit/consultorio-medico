from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

EntryType = Literal["allergy", "adverse_reaction", "contraindication", "intolerance_avoid"]
Severity = Literal["unknown", "mild", "moderate", "severe", "critical"]
SafetyStatus = Literal["active", "inactive", "entered_in_error"]
SourceType = Literal["patient_reported", "family_reported", "prior_documentation", "observed_during_care", "physician_confirmed"]


class SafetyContent(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")
    entry_type: EntryType
    substance_or_agent: str = Field(min_length=1, max_length=200)
    reaction_description: str = Field(min_length=1, max_length=3000)
    severity: Severity = "unknown"
    status: SafetyStatus = "active"
    onset_date: date | None = None
    notes: str | None = Field(default=None, max_length=3000)
    source_type: SourceType
    source_description: str | None = Field(default=None, max_length=1000)


class SafetyCreate(SafetyContent):
    clinical_history_id: int | None = Field(default=None, gt=0)
    change_reason: str | None = Field(default=None, min_length=3, max_length=1000)


class SafetyUpdate(SafetyContent):
    revision: int = Field(ge=1)
    change_reason: str | None = Field(default=None, min_length=3, max_length=1000)


class SafetyResponse(SafetyContent):
    model_config = ConfigDict(from_attributes=True)
    id: int
    patient_id: int
    organization_id: int
    clinical_history_id: int | None
    recorded_by_user_id: int
    updated_by_user_id: int
    recorded_by_name: str
    updated_by_name: str
    recorded_at: datetime
    updated_at: datetime
    revision: int
