from typing import Literal
from pydantic import BaseModel, ConfigDict, Field, field_validator

FeatureCode = Literal["clinical_safety_full", "clinical_safety_critical_alert"]
ContextCode = Literal["ambulatory"]
Audience = Literal["doctor", "secretary"]


class VisibilityChange(BaseModel):
    model_config = ConfigDict(extra="forbid")
    feature_code: FeatureCode
    context_code: ContextCode = "ambulatory"
    audience: Audience
    # null removes an override and resumes inheritance; it is not a third mode.
    visibility_mode: Literal["hidden", "visible"] | None
    revision: int = Field(ge=0)


class VisibilityUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    changes: list[VisibilityChange] = Field(min_length=1, max_length=4)
    reason: str = Field(min_length=5, max_length=500)

    @field_validator("reason")
    @classmethod
    def reason_not_blank(cls, value):
        value = value.strip()
        if len(value) < 5:
            raise ValueError("Indique el motivo del cambio")
        return value

    @field_validator("changes")
    @classmethod
    def distinct_keys(cls, changes):
        keys = {(c.feature_code, c.context_code, c.audience) for c in changes}
        if len(keys) != len(changes):
            raise ValueError("Configuración repetida")
        return changes
