from datetime import datetime

from pydantic import BaseModel, Field


class LocalityBase(BaseModel):
    name: str = Field(min_length=2, max_length=100)
    is_active: bool = True


class LocalityCreate(LocalityBase):
    pass


class LocalityUpdate(LocalityBase):
    pass


class LocalityResponse(LocalityBase):
    id: int
    created_at: datetime
    model_config = {"from_attributes": True}


class CareCenterBase(BaseModel):
    name: str = Field(min_length=2, max_length=150)
    center_type: str = Field(default="consultorio", pattern="^(consultorio|clinica|hospital|domicilio|otro)$")
    locality_id: int
    address: str | None = Field(default=None, max_length=250)
    is_active: bool = True


class CareCenterCreate(CareCenterBase):
    pass


class CareCenterUpdate(CareCenterBase):
    pass


class CareCenterResponse(CareCenterBase):
    id: int
    city: str
    created_at: datetime
    locality: LocalityResponse | None = None
    model_config = {"from_attributes": True}


class CenterUserAssignment(BaseModel):
    user_id: int
    is_primary: bool = False


class UserCenterResponse(BaseModel):
    user_id: int
    center_id: int
    is_primary: bool
