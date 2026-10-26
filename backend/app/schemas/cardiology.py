from datetime import date as Date
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field, model_validator

SYMPTOMS = {"chest_pain":"Dolor torácico", "dyspnea":"Disnea", "palpitations":"Palpitaciones", "syncope":"Síncope",
    "dizziness":"Mareos", "edema":"Edema", "orthopnea":"Ortopnea", "pnd":"Disnea paroxística nocturna", "claudication":"Claudicación", "fatigue":"Fatiga"}
BACKGROUND = {"hypertension":"HTA", "ischemic_heart_disease":"Cardiopatía isquémica", "prior_mi":"IAM previo", "stroke":"ACV",
    "arrhythmia":"Arritmias", "heart_failure":"Insuficiencia cardíaca", "valvular_disease":"Valvulopatías", "procedures":"Procedimientos cardiovasculares", "devices":"Marcapasos / dispositivos", "other":"Otros"}
EXAM = {"general":"Estado general", "rhythm":"Ritmo cardíaco", "heart_sounds":"Ruidos cardíacos", "murmurs":"Soplos", "pulses":"Pulsos", "edema":"Edema", "jugular":"Yugulares", "lungs":"Pulmones", "findings":"Hallazgos relevantes"}

class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")

class Finding(StrictModel):
    present: bool | None = None
    detail: str | None = Field(default=None, max_length=1000)

class ReviewedStudy(StrictModel):
    category: Literal["ecg","echo","holter","mapa","laboratory","radiograph","stress_test","other"]
    status: Literal["reviewed","requested","pending"]
    note: str | None = Field(default=None,max_length=2000)
    study_order_id: int | None = Field(default=None,gt=0)

class FollowUpIndication(StrictModel):
    kind: Literal["none","days","weeks","months","studies","date"] = "none"
    value: int | None = Field(default=None,ge=1,le=365)
    date: Date | None = None
    reason: str | None = Field(default=None,max_length=255)
    condition: str | None = Field(default=None,max_length=2000)
    @model_validator(mode="after")
    def valid(self):
        if self.kind != "none" and not (self.reason or "").strip():
            raise ValueError("Indique el motivo del seguimiento")
        if self.kind in {"days","weeks","months"} and self.value is None:
            raise ValueError("Indique el plazo de seguimiento")
        if self.kind == "date" and self.date is None:
            raise ValueError("Indique la fecha de retorno")
        return self

class CardiologyWrite(StrictModel):
    expected_revision: int = Field(ge=0)
    symptoms: dict[str,Finding] = Field(default_factory=dict)
    cardiovascular_history: dict[str,Finding] = Field(default_factory=dict)
    examination: dict[str,str] = Field(default_factory=dict)
    impression: str | None = Field(default=None,max_length=10000)
    plan: str | None = Field(default=None,max_length=10000)
    studies: list[ReviewedStudy] = Field(default_factory=list,max_length=30)
    follow_up: FollowUpIndication = Field(default_factory=FollowUpIndication)
    @model_validator(mode="after")
    def keys(self):
        if set(self.symptoms)-SYMPTOMS.keys() or set(self.cardiovascular_history)-BACKGROUND.keys() or set(self.examination)-EXAM.keys():
            raise ValueError("Campo cardiológico no reconocido")
        if any(len(v)>2000 for v in self.examination.values()):
            raise ValueError("Hallazgo demasiado largo")
        return self

class FollowUpContactWrite(StrictModel):
    result: Literal["contacted","no_answer","retry","studies_ready","studies_pending","declined","scheduled"]
    note: str | None = Field(default=None,max_length=2000)
