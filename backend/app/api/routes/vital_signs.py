from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import require_permission
from app.db import get_db
from app.models.vital_signs import VitalSigns
from app.schemas.vital_signs import VitalSignsResponse, VitalSignsUpdate
from app.models.identity import User
from app.services.clinical_access import add_clinical_audit, require_history_access

router = APIRouter(prefix="/clinical-history/{history_id}/vital-signs", tags=["Signos vitales"])
access = require_permission("clinical:access")


@router.get("", response_model=VitalSignsResponse | None)
def get_vital_signs(history_id: int, user: User = Depends(access), db: Session = Depends(get_db)):
    require_history_access(db, user, history_id, action="vital_signs.read", audit_read=True)
    return db.scalar(select(VitalSigns).where(VitalSigns.clinical_history_id == history_id))


@router.put("", response_model=VitalSignsResponse)
def upsert_vital_signs(
    history_id: int,
    payload: VitalSignsUpdate,
    user: User = Depends(access),
    db: Session = Depends(get_db),
):
    require_history_access(db, user, history_id, action="vital_signs.update", write=True)

    vital_signs = db.scalar(select(VitalSigns).where(VitalSigns.clinical_history_id == history_id))
    if vital_signs is None:
        vital_signs = VitalSigns(clinical_history_id=history_id, **payload.model_dump())
        db.add(vital_signs)
    else:
        for field, value in payload.model_dump().items():
            setattr(vital_signs, field, value)

    db.flush()
    add_clinical_audit(
        db, user, action="vital_signs.update", resource_type="vital_signs",
        resource_id=vital_signs.id, history_id=history_id,
    )
    db.commit()
    db.refresh(vital_signs)
    return vital_signs
