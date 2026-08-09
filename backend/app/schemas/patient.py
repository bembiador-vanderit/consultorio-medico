from datetime import date, datetime
from pydantic import BaseModel, EmailStr, Field
class PatientCreate(BaseModel):
    first_name: str = Field(min_length=2, max_length=100)
    last_name: str = Field(min_length=2, max_length=100)
    date_of_birth: date
    phone: str | None = Field(default=None, max_length=30)
    email: EmailStr | None = None
class PatientUpdate(PatientCreate): pass
class PatientResponse(PatientCreate):
    id: int
    created_at: datetime
    model_config = {"from_attributes": True}
