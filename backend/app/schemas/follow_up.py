from datetime import datetime
from pydantic import BaseModel, ConfigDict, Field


class FollowUpCreate(BaseModel):
    patient_id: int
    doctor_id: int | None = None
    clinical_history_id: int | None = None
    center_id: int | None = None
    due_at: datetime
    reason: str = Field(min_length=1, max_length=255)
    priority: str = Field(default="normal", pattern="^(low|normal|high|urgent)$")
    notes: str | None = None


class FollowUpRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    patient_id: int
    doctor_id: int
    clinical_history_id: int | None
    center_id: int | None
    due_at: datetime
    reason: str
    priority: str
    status: str
    notes: str | None
    created_at: datetime
    completed_at: datetime | None


class NotificationRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    follow_up_id: int | None
    title: str
    message: str
    notification_type: str
    is_read: bool
    created_at: datetime
    read_at: datetime | None
