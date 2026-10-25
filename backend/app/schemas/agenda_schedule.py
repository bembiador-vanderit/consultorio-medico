from datetime import date
from typing import Literal

from pydantic import BaseModel, ConfigDict

ScheduleMode = Literal["timed", "queue"]


class ModeChange(BaseModel):
    model_config = ConfigDict(extra="forbid")
    mode: ScheduleMode


class PolicyChange(BaseModel):
    model_config = ConfigDict(extra="forbid")
    allowed_timed: bool
    allowed_queue: bool
    default_mode: ScheduleMode


class AgendaPolicyRead(BaseModel):
    allowed_timed: bool
    allowed_queue: bool
    default_mode: ScheduleMode


class AgendaModeRead(BaseModel):
    doctor_id: int
    center_id: int
    agenda_date: date
    base_mode: ScheduleMode
    exception_mode: ScheduleMode | None
    effective_mode: ScheduleMode
    base_policy: AgendaPolicyRead
    exception_policy: AgendaPolicyRead | None
    effective_policy: AgendaPolicyRead
    queue_line_available: bool
    multimode_enabled: bool
