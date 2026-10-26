"""Only explicit operational fields may leave the public display endpoint."""

from datetime import datetime

from typing import Literal

from pydantic import BaseModel, Field, field_validator


class QueueDisplayAudio(BaseModel):
    audio_enabled: bool = False
    audio_volume: float = Field(default=1.0, ge=0, le=1, allow_inf_nan=False)
    audio_language: Literal["es-DO", "es"] = "es-DO"
    audio_voice_uri: str | None = Field(default=None, max_length=255)
    audio_rate: float = Field(default=1.0, ge=0.5, le=2, allow_inf_nan=False)
    audio_pitch: float = Field(default=1.0, ge=0.5, le=2, allow_inf_nan=False)
    repeat_count: int = Field(default=1, ge=1, le=10)
    repeat_delay_ms: int = Field(default=1000, ge=1000, le=5000)
    announce_service_name: bool = False
    announce_provider_name: bool = False

    @field_validator("audio_voice_uri")
    @classmethod
    def clean_voice_uri(cls, value: str | None) -> str | None:
        return value.strip() or None if value is not None else None


class QueueDisplayVoiceWrite(BaseModel):
    audio_voice_uri: str | None = Field(default=None, max_length=255)

    @field_validator("audio_voice_uri")
    @classmethod
    def clean_voice_uri(cls, value: str | None) -> str | None:
        return value.strip() or None if value is not None else None


class QueueDisplayLineWrite(BaseModel):
    queue_line_id: int
    destination: str = Field(min_length=1, max_length=80)
    sort_order: int = Field(ge=0)
    is_active: bool = True

    @field_validator("destination")
    @classmethod
    def clean_destination(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("Indique el destino visible")
        return cleaned


class QueueDisplayWrite(QueueDisplayAudio):
    center_id: int
    waiting_room_id: int | None = None
    name: str = Field(min_length=1, max_length=120)
    is_active: bool = True
    show_service_name: bool = False
    show_provider_name: bool = False
    recent_call_limit: int = Field(default=5, ge=3, le=10)
    lines: list[QueueDisplayLineWrite] = Field(default_factory=list)

    @field_validator("name")
    @classmethod
    def clean_name(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("Indique un nombre para la pantalla")
        return cleaned


class QueueDisplayLineRead(QueueDisplayLineWrite):
    line_name: str


class QueueDisplayRead(QueueDisplayAudio):
    id: int
    center_id: int
    center_name: str
    waiting_room_id: int | None = None
    waiting_room_name: str | None = None
    name: str
    is_active: bool
    show_service_name: bool
    show_provider_name: bool
    recent_call_limit: int
    lines: list[QueueDisplayLineRead]


class QueueDisplayToken(QueueDisplayRead):
    access_token: str


class PublicCall(BaseModel):
    ticket_code: str
    destination: str
    called_at: datetime
    call_revision: int
    queue_line_name: str | None = None
    provider_name: str | None = None


class PublicQueueDisplayState(BaseModel):
    display_name: str
    center_name: str
    waiting_room_name: str | None = None
    provider_names: list[str] = Field(default_factory=list)
    service_names: list[str] = Field(default_factory=list)
    current_calls: list[PublicCall]
    recent_calls: list[PublicCall]
    updated_at: datetime
    audio: QueueDisplayAudio
