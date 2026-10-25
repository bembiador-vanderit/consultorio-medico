from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


CallMode = Literal["manual", "assisted", "automatic"]


class QueueCallPolicyWrite(BaseModel):
    call_mode: CallMode
    preparation_seconds: int = Field(ge=0, le=3600)
    start_consultation_can_call: bool = False


class QueueCallPolicyRead(QueueCallPolicyWrite):
    queue_line_id: int
    center_id: int


class NextCallState(BaseModel):
    queue_line_id: int
    call_mode: CallMode
    preparation_seconds: int
    provider_paused: bool
    current_in_service_ticket_id: int | None
    next_waiting_ticket_id: int | None
    next_waiting_public_code: str | None
    last_service_completed_at: datetime | None
    ready_at: datetime | None
    server_now: datetime
    ready: bool
    can_call: bool
    block_reason: str | None
