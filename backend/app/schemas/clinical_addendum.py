from datetime import datetime

from pydantic import BaseModel, Field, field_validator, model_validator


class ClinicalAddendumCreate(BaseModel):
    reason: str | None = Field(default=None, max_length=5000)
    note: str | None = Field(default=None, max_length=10000)

    model_config = {"extra": "forbid"}

    @field_validator("reason")
    @classmethod
    def normalize_reason(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = value.strip()
        return value or None

    @field_validator("note")
    @classmethod
    def normalize_note(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = value.strip()
        return value or None

    @model_validator(mode="after")
    def require_content(self):
        if self.reason is None and self.note is None:
            raise ValueError("Indique un motivo adicional o una nota adicional")
        return self


class ClinicalAddendumResponse(BaseModel):
    id: int
    clinical_history_id: int
    author_user_id: int | None
    author_name: str
    reason: str | None
    note: str
    created_at: datetime

    model_config = {"from_attributes": True}
