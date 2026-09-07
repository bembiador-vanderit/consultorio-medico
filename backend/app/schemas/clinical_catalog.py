from pydantic import BaseModel, Field


class SpecialtyResponse(BaseModel):
    id: int
    name: str
    is_active: bool
    model_config = {"from_attributes": True}


class AnatomicalRegionResponse(BaseModel):
    id: int
    specialty_id: int
    name: str
    is_active: bool
    model_config = {"from_attributes": True}


class MedicalStudyResponse(BaseModel):
    id: int
    specialty_id: int
    anatomical_region_id: int | None
    name: str
    category: str
    is_active: bool
    model_config = {"from_attributes": True}


class DoctorProfileCreate(BaseModel):
    primary_specialty_id: int | None = Field(default=None, gt=0)
    specialty_ids: list[int] = Field(default_factory=list)
    # Compatibilidad con el contrato anterior de una sola especialidad.
    specialty_id: int | None = Field(default=None, gt=0)


class DoctorProfileResponse(BaseModel):
    user_id: int
    specialty_id: int
    specialty: SpecialtyResponse
    specialties: list[SpecialtyResponse]
    model_config = {"from_attributes": True}
