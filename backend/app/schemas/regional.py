from pydantic import BaseModel, Field


class CountryResponse(BaseModel):
    code: str
    name: str
    model_config = {"from_attributes": True}


class TerritorialLevelResponse(BaseModel):
    id: int
    country_code: str
    position: int
    key: str
    display_label: str
    is_required: bool
    model_config = {"from_attributes": True}


class TerritorialUnitResponse(BaseModel):
    id: int
    country_code: str
    territorial_level_id: int
    parent_id: int | None
    code: str | None
    name: str
    model_config = {"from_attributes": True}


class RegionalSettingsResponse(BaseModel):
    default_country_code: str
    default_country_name: str


class RegionalSettingsUpdate(BaseModel):
    default_country_code: str = Field(min_length=2, max_length=2)