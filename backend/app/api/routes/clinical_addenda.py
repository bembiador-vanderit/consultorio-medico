from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import require_permission
from app.db import get_db
from app.models.clinical_addendum import ClinicalAddendum
from app.models.identity import User
from app.schemas.clinical_addendum import ClinicalAddendumCreate, ClinicalAddendumResponse
from app.services.clinical_access import (
    add_clinical_audit,
    has_normal_history_access,
    require_history_access,
)

router = APIRouter(prefix="/clinical-history", tags=["Notas clínicas adicionales"])
access = require_permission("clinical:access")


@router.get("/{history_id}/addenda", response_model=list[ClinicalAddendumResponse])
def list_addenda(history_id: int, user: User = Depends(access), db: Session = Depends(get_db)):
    require_history_access(
        db, user, history_id, action="addendum.list",
        resource_id=history_id, audit_read=True,
    )
    return list(db.scalars(
        select(ClinicalAddendum)
        .where(ClinicalAddendum.clinical_history_id == history_id)
        .order_by(ClinicalAddendum.created_at, ClinicalAddendum.id)
    ).all())


@router.post(
    "/{history_id}/addenda",
    response_model=ClinicalAddendumResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_addendum(
    history_id: int,
    payload: ClinicalAddendumCreate,
    user: User = Depends(access),
    db: Session = Depends(get_db),
):
    history = require_history_access(
        db, user, history_id, action="addendum.create", resource_id=history_id,
    )
    if not user.is_active or not has_normal_history_access(db, user, history):
        add_clinical_audit(
            db, user, action="addendum.create", resource_type="clinical_history",
            resource_id=history.id, history_id=history.id, outcome="denied",
            context={"reason": "addendum_authority_required"},
        )
        db.commit()
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Solo el médico responsable puede agregar notas posteriores al cierre",
        )
    if history.status != "completed":
        add_clinical_audit(
            db, user, action="addendum.create", resource_type="clinical_history",
            resource_id=history.id, history_id=history.id, outcome="denied",
            context={"reason": "consultation_not_completed"},
        )
        db.commit()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Las notas adicionales solo pueden agregarse a consultas finalizadas",
        )

    addendum = ClinicalAddendum(
        clinical_history_id=history.id,
        author_user_id=user.id,
        reason=payload.reason,
        note=payload.note,
    )
    db.add(addendum)
    db.flush()
    add_clinical_audit(
        db, user, action="addendum.create", resource_type="clinical_addendum",
        resource_id=addendum.id, history_id=history.id,
    )
    db.commit()
    db.refresh(addendum)
    return addendum
