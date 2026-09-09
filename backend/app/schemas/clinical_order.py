from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, field_validator


class LaboratoryTestResponse(BaseModel):
    id: int
    code: str | None
    name: str
    category: str
    is_active: bool
    sort_order: int
    model_config = {"from_attributes": True}


class LaboratoryOrderItemInput(BaseModel):
    laboratory_test_id: int = Field(gt=0)
    custom_note: str | None = Field(default=None, max_length=2000)

    @field_validator("custom_note")
    @classmethod
    def normalize_note(cls, value: str | None) -> str | None:
        return (value.strip() or None) if value else None


class LaboratoryOrderInput(BaseModel):
    items: list[LaboratoryOrderItemInput] = Field(min_length=1, max_length=100)
    notes: str | None = Field(default=None, max_length=5000)
    model_config = {"extra": "forbid"}

    @field_validator("notes")
    @classmethod
    def normalize_notes(cls, value: str | None) -> str | None:
        return (value.strip() or None) if value else None


class LaboratoryOrderItemResponse(BaseModel):
    id: int
    laboratory_test_id: int
    test_code: str | None
    test_name: str
    test_category: str
    custom_note: str | None
    model_config = {"from_attributes": True}


class LaboratoryOrderResponse(BaseModel):
    id: int
    clinical_history_id: int
    appointment_id: int | None
    patient_id: int
    doctor_id: int | None
    center_id: int | None
    specialty_id: int | None
    patient_name: str
    doctor_name: str
    center_name: str | None
    specialty_name: str
    status: Literal["ordered"]
    notes: str | None
    created_at: datetime
    updated_at: datetime
    items: list[LaboratoryOrderItemResponse]
    model_config = {"from_attributes": True}


class StudyOrderItemInput(BaseModel):
    medical_study_id: int = Field(gt=0)
    region_description: str | None = Field(default=None, max_length=250)
    contrast: Literal["yes", "no", "not_applicable"] = "not_applicable"
    clinical_notes: str | None = Field(default=None, max_length=5000)

    @field_validator("region_description", "clinical_notes")
    @classmethod
    def normalize_optional_text(cls, value: str | None) -> str | None:
        return (value.strip() or None) if value else None


class StudyOrderInput(BaseModel):
    items: list[StudyOrderItemInput] = Field(min_length=1, max_length=50)
    notes: str | None = Field(default=None, max_length=5000)
    model_config = {"extra": "forbid"}

    @field_validator("notes")
    @classmethod
    def normalize_notes(cls, value: str | None) -> str | None:
        return (value.strip() or None) if value else None


class StudyOrderItemResponse(BaseModel):
    id: int
    medical_study_id: int
    modality: str
    study_name: str
    region_description: str | None
    contrast: Literal["yes", "no", "not_applicable"]
    clinical_notes: str | None
    model_config = {"from_attributes": True}


class StudyOrderResponse(BaseModel):
    id: int
    clinical_history_id: int
    appointment_id: int | None
    patient_id: int
    doctor_id: int | None
    center_id: int | None
    specialty_id: int | None
    patient_name: str
    doctor_name: str
    center_name: str | None
    specialty_name: str
    status: Literal["ordered"]
    notes: str | None
    created_at: datetime
    updated_at: datetime
    items: list[StudyOrderItemResponse]
    model_config = {"from_attributes": True}
