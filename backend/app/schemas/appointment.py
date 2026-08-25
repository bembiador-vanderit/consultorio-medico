from datetime import date, time, datetime
from pydantic import BaseModel, Field

class AppointmentBase(BaseModel):
    patient_id: int
    appointment_date: date
    appointment_time: time
    reason: str | None = Field(default=None, max_length=5000)
    status: str = Field(default="scheduled", pattern="^(scheduled|confirmed|completed|cancelled|no_show)$")
    notes: str | None = Field(default=None, max_length=10000)

class AppointmentCreate(AppointmentBase):
    pass

class AppointmentResponse(AppointmentBase):
    id: int
    doctor_id: int
    patient_name: str
    doctor_name: str
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}
