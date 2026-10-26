from datetime import datetime

from pydantic import BaseModel, Field, model_validator


class VitalSignsUpdate(BaseModel):
    systolic_pressure: int | None = Field(default=None, ge=40, le=300)
    diastolic_pressure: int | None = Field(default=None, ge=20, le=200)
    heart_rate: int | None = Field(default=None, ge=20, le=300)
    respiratory_rate: int | None = Field(default=None, ge=5, le=80)
    temperature_c: float | None = Field(default=None, ge=25, le=45)
    oxygen_saturation: float | None = Field(default=None, ge=0, le=100)
    weight_kg: float | None = Field(default=None, ge=1, le=500)
    height_cm: float | None = Field(default=None, ge=20, le=300)

    @model_validator(mode="after")
    def validate_measurements(self):
        values = (
            self.systolic_pressure,
            self.diastolic_pressure,
            self.heart_rate,
            self.respiratory_rate,
            self.temperature_c,
            self.oxygen_saturation,
            self.weight_kg,
            self.height_cm,
        )
        if all(value is None for value in values):
            raise ValueError("Debe registrar al menos un signo vital")
        if (
            self.systolic_pressure is not None
            and self.diastolic_pressure is not None
            and self.systolic_pressure <= self.diastolic_pressure
        ):
            raise ValueError("La presión sistólica debe ser mayor que la diastólica")
        return self


class VitalSignsResponse(VitalSignsUpdate):
    id: int
    clinical_history_id: int
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}
