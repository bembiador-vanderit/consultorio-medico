from datetime import datetime
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field

RelationshipType = Literal["treating", "consultant", "specialist_followup", "primary"]
RelationshipStatus = Literal["active", "follow_up", "historical", "ended"]


class RelationshipFields(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    relationship_type: RelationshipType = "treating"
    status: RelationshipStatus = "active"
    center_id: int | None = Field(default=None, gt=0)
    specialty_id: int | None = Field(default=None, gt=0)


class RelationshipCreate(RelationshipFields):
    doctor_id: int = Field(gt=0)
    reason: str = Field(min_length=3, max_length=1000)


class RelationshipUpdate(RelationshipFields):
    revision: int = Field(ge=1)
    reason: str = Field(min_length=3, max_length=1000)


class RelationshipResponse(RelationshipFields):
    model_config = ConfigDict(from_attributes=True)
    id: int
    patient_id: int
    organization_id: int
    doctor_id: int
    doctor_name: str
    center_name: str | None
    specialty_name: str | None
    organization_name: str
    origin: str
    started_at: datetime
    first_seen_at: datetime | None
    last_seen_at: datetime | None
    ended_at: datetime | None
    created_from_clinical_history_id: int | None
    last_clinical_history_id: int | None
    created_by_user_id: int
    updated_by_user_id: int
    created_at: datetime
    updated_at: datetime
    revision: int
