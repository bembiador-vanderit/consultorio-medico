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
    specialty_id: int = Field(gt=0)


class DoctorProfileResponse(BaseModel):
    user_id: int
    specialty_id: int
    specialty: SpecialtyResponse
    model_config = {"from_attributes": True}
