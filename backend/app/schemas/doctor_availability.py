from datetime import date, datetime
from pydantic import BaseModel


class DoctorAvailabilityCreate(BaseModel):
    availability_date: date
    center_id: int | None = None
    is_available: bool = False


class DoctorAvailabilityResponse(DoctorAvailabilityCreate):
    id: int
    doctor_id: int
    created_at: datetime

    model_config = {"from_attributes": True}
