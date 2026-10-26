from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


DocumentKind = Literal["preoperative", "physical_exam"]
DocumentStatus = Literal["draft", "pending_evaluation", "completed", "signed"]


class DocumentCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    patient_id: int
    doctor_id: int | None = None
    center_id: int | None = None
    appointment_id: int | None = None
    clinical_history_id: int | None = None
    patient_selection_token: str | None = None


class DocumentUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    expected_revision: int = Field(ge=0)
    values: dict[str, str] = Field(default_factory=dict)

    @field_validator("values")
    @classmethod
    def validate_values(cls, values: dict[str, str]) -> dict[str, str]:
        if len(values) > 120:
            raise ValueError("Demasiados campos")
        if any(len(value) > 5000 for value in values.values()):
            raise ValueError("Un campo supera 5000 caracteres")
        return values


class DocumentTransition(BaseModel):
    expected_revision: int = Field(ge=0)


class DocumentLink(BaseModel):
    model_config = ConfigDict(extra="forbid")
    expected_revision: int = Field(ge=0)
    appointment_id: int
    clinical_history_id: int | None = None


class DocumentResponse(BaseModel):
    kind: DocumentKind
    id: int
    patient_id: int
    doctor_id: int
    center_id: int
    appointment_id: int | None
    clinical_history_id: int | None
    document_date: date
    status: DocumentStatus
    revision: int
    created_by_user_id: int
    created_by_name: str
    last_updated_by_user_id: int
    signed_by_user_id: int | None
    created_at: datetime
    updated_at: datetime
    signed_at: datetime | None
    doctor_name: str
    center_name: str
    patient_name: str
    values: dict[str, str] | None = None
    patient_profile: dict | None = None
    template_id: int | None = None
    template_version_id: int | None = None
    template_definition: dict | None = None
    template_admin_fields: list[dict] | None = None
    template_source: str = "legacy_0055"
