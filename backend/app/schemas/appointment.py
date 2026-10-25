from datetime import date, time, datetime
from pydantic import BaseModel, Field
from typing import Literal

class AppointmentBase(BaseModel):
    patient_id: int
    doctor_id: int | None = None
    center_id: int | None = None
    specialty_id: int | None = Field(default=None, gt=0)
    appointment_date: date
    appointment_time: time | None = None
    reason: str | None = Field(default=None, max_length=5000)
    status: str = Field(default="scheduled", pattern="^(scheduled|confirmed|completed|cancelled|no_show)$")
    notes: str | None = Field(default=None, max_length=10000)

class AppointmentCreate(AppointmentBase):
    follow_up_id: int | None = Field(default=None, gt=0)
    schedule_mode: Literal["timed", "queue"] | None = None
    patient_selection_token: str | None = Field(default=None, max_length=2048)

class AppointmentResponse(AppointmentBase):
    arrival_enabled: bool = False
    arrived_at: datetime | None = None
    arrival_registered_by: int | None = None
    id: int
    schedule_mode: Literal["timed", "queue"]
    daily_booking_order: int | None = None
    doctor_id: int
    center_id: int | None
    specialty_id: int | None
    specialty_name: str
    patient_name: str
    patient_phone: str | None
    patient_date_of_birth: date
    doctor_name: str
    center_name: str | None
    center_city: str | None
    coverage_id: int | None = None
    original_doctor_id: int | None = None
    original_doctor_name: str | None = None
    has_clinical_history: bool = False
    clinical_history_id: int | None = None
    clinical_history_status: str | None = None
    clinical_history_doctor_id: int | None = None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class AppointmentScopeCenter(BaseModel):
    id: int
    name: str
    city: str | None = None


class AppointmentArrivalCreate(BaseModel):
    queue_line_id: int | None = Field(default=None, gt=0)


class AppointmentScopeDoctor(BaseModel):
    id: int
    full_name: str
    center_ids: list[int]
    specialties: list["AppointmentScopeSpecialty"]


class AppointmentScopeSpecialty(BaseModel):
    id: int
    name: str


class AppointmentScopeOptions(BaseModel):
    centers: list[AppointmentScopeCenter]
    doctors: list[AppointmentScopeDoctor]
