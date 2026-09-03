from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import require_permission
from app.db import get_db
from app.models.clinical_history import ClinicalHistory
from app.models.vital_signs import VitalSigns
from app.schemas.vital_signs import VitalSignsResponse, VitalSignsUpdate

router = APIRouter(prefix="/clinical-history/{history_id}/vital-signs", tags=["Signos vitales"])
access = require_permission("clinical:access")


@router.get("", response_model=VitalSignsResponse | None)
def get_vital_signs(history_id: int, _=Depends(access), db: Session = Depends(get_db)):
    if db.get(ClinicalHistory, history_id) is None:
        raise HTTPException(status_code=404, detail="Registro de historia clínica no encontrado")
    return db.scalar(select(VitalSigns).where(VitalSigns.clinical_history_id == history_id))


@router.put("", response_model=VitalSignsResponse)
def upsert_vital_signs(
    history_id: int,
    payload: VitalSignsUpdate,
    _=Depends(access),
    db: Session = Depends(get_db),
):
    if db.get(ClinicalHistory, history_id) is None:
        raise HTTPException(status_code=404, detail="Registro de historia clínica no encontrado")

    vital_signs = db.scalar(select(VitalSigns).where(VitalSigns.clinical_history_id == history_id))
    if vital_signs is None:
        vital_signs = VitalSigns(clinical_history_id=history_id, **payload.model_dump())
        db.add(vital_signs)
    else:
        for field, value in payload.model_dump().items():
            setattr(vital_signs, field, value)

    db.commit()
    db.refresh(vital_signs)
    return vital_signs
