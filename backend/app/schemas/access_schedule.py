from datetime import date, datetime
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class ScheduleWindow(BaseModel):
    model_config = ConfigDict(extra="forbid")
    day: int = Field(ge=0, le=6)  # Monday = 0
    start: str = Field(pattern=r"^(?:[01]\d|2[0-3]):[0-5]\d$")
    end: str = Field(pattern=r"^(?:(?:[01]\d|2[0-3]):[0-5]\d|24:00)$")

    @model_validator(mode="after")
    def ordered(self):
        if self.start >= self.end:
            raise ValueError("El fin debe ser posterior al inicio; divida los turnos nocturnos en dos días")
        return self


class ScheduleUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    restrict_outside_schedule: bool
    weekly_schedule: list[ScheduleWindow] = Field(max_length=28)

    @model_validator(mode="after")
    def no_overlap(self):
        ordered = sorted(self.weekly_schedule, key=lambda w: (w.day, w.start))
        for previous, current in zip(ordered, ordered[1:]):
            if previous.day == current.day and previous.end > current.start:
                raise ValueError("Las ventanas de un día no deben superponerse")
        return self


class TimezoneUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    timezone: str = Field(max_length=64)

    @field_validator("timezone")
    @classmethod
    def valid_zone(cls, value):
        try:
            ZoneInfo(value)
        except (ZoneInfoNotFoundError, ValueError):
            raise ValueError("Seleccione una zona horaria IANA válida")
        return value


class ExceptionCreate(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    starts_at: datetime
    ends_at: datetime
    reason: str = Field(min_length=1, max_length=300)


class BlockedDateCreate(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    day: date
    reason: str = Field(min_length=1, max_length=300)
