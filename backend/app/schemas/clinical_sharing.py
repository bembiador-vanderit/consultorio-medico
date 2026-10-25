from typing import Literal
from pydantic import BaseModel, Field

Resource = Literal["clinical_history", "clinical_documents", "patient_safety"]
Mode = Literal["assigned", "active_relationship", "same_center", "organization"]


class PolicyUpdate(BaseModel):
    mode: Mode = "assigned"
    limit_to_same_center: bool = True
    clinical_history: bool = False
    clinical_documents: bool = False
    patient_safety: bool = False
    revision: int = Field(ge=0)
    reason: str = Field(min_length=5, max_length=500)
    model_config = {"extra": "forbid"}
