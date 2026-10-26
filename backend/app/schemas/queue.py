from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, Field, field_validator


class QueueLineCreate(BaseModel):
    center_id: int
    doctor_id: int
    specialty_id: int | None = None
    name: str = Field(min_length=1, max_length=120)
    prefix: str = Field(pattern=r"^[A-Z0-9]{1,4}$")
    call_on_consultation_start: bool = False

    @field_validator("name")
    @classmethod
    def clean_name(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("Indique un nombre para la línea")
        return cleaned

    @field_validator("prefix", mode="before")
    @classmethod
    def clean_prefix(cls, value: str) -> str:
        return value.strip().upper() if isinstance(value, str) else value


class QueueLineUpdate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    prefix: str = Field(pattern=r"^[A-Z0-9]{1,4}$")
    is_active: bool
    call_on_consultation_start: bool | None = None

    @field_validator("name")
    @classmethod
    def clean_name(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("Indique un nombre para la línea")
        return cleaned

    @field_validator("prefix", mode="before")
    @classmethod
    def clean_prefix(cls, value: str) -> str:
        return value.strip().upper() if isinstance(value, str) else value


class QueueLineRead(BaseModel):
    id: int
    center_id: int
    doctor_id: int
    specialty_id: int | None
    name: str
    prefix: str
    is_active: bool
    call_on_consultation_start: bool
    doctor_name: str
    center_name: str
    waiting_room_id: int | None = None
    model_config = {"from_attributes": True}


class ArrivalCreate(BaseModel):
    queue_line_id: int


class QueueTicketRead(BaseModel):
    id: int
    queue_line_id: int
    appointment_id: int
    patient_id: int
    doctor_id: int
    center_id: int
    specialty_id: int | None
    service_date: date
    sequence_number: int
    public_code: str
    source: Literal["arrival"]
    status: Literal["waiting", "called", "in_service", "completed", "no_response", "left"]
    arrived_at: datetime
    ticket_issued_at: datetime
    arrival_registered_by: int
    ticket_issued_by: int
    first_called_at: datetime | None = None
    last_called_at: datetime | None = None
    called_by_user_id: int | None = None
    call_count: int
    consultation_started_at: datetime | None = None
    consultation_started_by_user_id: int | None = None
    consultation_finished_at: datetime | None = None
    consultation_finished_by_user_id: int | None = None
    left_at: datetime | None = None
    left_by_user_id: int | None = None
    model_config = {"from_attributes": True}


class QueueTicketEventRead(BaseModel):
    id: int
    queue_ticket_id: int
    event_type: Literal["ARRIVED", "ISSUED", "CALLED", "RECALLED", "SERVICE_STARTED", "SERVICE_COMPLETED", "NO_RESPONSE", "LEFT"]
    occurred_at: datetime
    actor_user_id: int | None
    call_source: Literal["manual", "automatic"] | None = None
    created_at: datetime
    model_config = {"from_attributes": True}
