from datetime import date, datetime, time
from typing import Literal

from pydantic import BaseModel, Field, field_validator


ContactResult = Literal["will_attend", "will_not_attend", "no_answer", "retry"]
ContactFilter = Literal["pending", "will_attend", "will_not_attend", "no_answer", "retry"]


class ContactAttemptCreate(BaseModel):
    result: ContactResult
    channel: Literal["phone"] = "phone"
    contact_value: str | None = Field(default=None, max_length=30)
    notes: str | None = Field(default=None, max_length=2000)

    @field_validator("contact_value", "notes")
    @classmethod
    def blank_to_none(cls, value: str | None) -> str | None:
        return value.strip() or None if value is not None else None


class ContactAttemptResponse(BaseModel):
    id: int
    appointment_id: int
    contacted_by_user_id: int
    contacted_by_name: str
    contacted_at: datetime
    channel: str
    contact_value: str | None
    result: ContactResult
    notes: str | None
    created_at: datetime


class DailyContactItem(BaseModel):
    appointment_id: int
    patient_name: str
    patient_phone: str | None
    appointment_date: date
    appointment_time: time | None
    doctor_name: str
    center_name: str | None
    status: str
    latest_contact: ContactAttemptResponse | None


class DailyContactTotals(BaseModel):
    total_expected: int
    contacted: int
    not_contacted: int
    will_attend: int
    will_not_attend: int
    no_answer: int
    retry: int


class DailyContactResponse(BaseModel):
    date: date
    totals: DailyContactTotals
    items: list[DailyContactItem]
