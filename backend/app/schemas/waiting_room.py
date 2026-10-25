from datetime import datetime

from pydantic import BaseModel, Field, field_validator


class WaitingRoomWrite(BaseModel):
    center_id: int = Field(gt=0)
    name: str = Field(min_length=1, max_length=120)
    code: str | None = Field(default=None, max_length=30)
    description: str | None = Field(default=None, max_length=500)
    is_active: bool = True
    sort_order: int = Field(default=0, ge=0)

    @field_validator("name")
    @classmethod
    def clean_name(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Indique un nombre para la sala")
        return value

    @field_validator("code", "description")
    @classmethod
    def clean_optional(cls, value: str | None) -> str | None:
        return value.strip() or None if value is not None else None


class WaitingRoomLine(BaseModel):
    id: int
    name: str
    prefix: str
    provider_name: str
    specialty_id: int | None


class WaitingRoomSecretaryRead(BaseModel):
    user_id: int
    full_name: str


class WaitingRoomDisplayRead(BaseModel):
    id: int
    name: str
    is_active: bool


class WaitingRoomRead(WaitingRoomWrite):
    id: int
    created_at: datetime
    updated_at: datetime
    queue_lines: list[WaitingRoomLine] = Field(default_factory=list)
    secretaries: list[WaitingRoomSecretaryRead] = Field(default_factory=list)
    displays: list[WaitingRoomDisplayRead] = Field(default_factory=list)


class WaitingRoomLineAssignment(BaseModel):
    queue_line_ids: list[int] = Field(default_factory=list)


class WaitingRoomSecretaryAssignment(BaseModel):
    secretary_user_ids: list[int] = Field(default_factory=list)
