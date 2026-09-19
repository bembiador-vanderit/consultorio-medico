from pydantic import BaseModel, Field


class RequestedTestCreate(BaseModel):
    test_name: str = Field(min_length=1, max_length=500)


class RequestedTestResponse(RequestedTestCreate):
    id: int
    clinical_history_id: int

    model_config = {"from_attributes": True}
