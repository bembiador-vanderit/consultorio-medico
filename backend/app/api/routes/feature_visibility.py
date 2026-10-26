"""Authenticated UI configuration. Does not participate in clinical authorization."""
from fastapi import APIRouter, Depends, Query, Response
from app.api.deps import current_user, require_permission
from app.db import get_db
from app.schemas.feature_visibility import ContextCode, VisibilityUpdate
from app.services import feature_visibility as service

router = APIRouter(prefix="/feature-visibility", tags=["Visibilidad contextual"])
manage = require_permission("users:manage")


@router.get("/resolved")
def resolved(response: Response, context_code: ContextCode = "ambulatory",
             center_id: int | None = Query(default=None, gt=0), user=Depends(current_user), db=Depends(get_db)):
    service.ensure_tenant(db)
    service.validate_center(db, user, center_id)
    response.headers["Cache-Control"] = "no-store"
    audience = service.audience_for(user)
    return {"audience": audience, "context_code": context_code, "center_id": center_id,
        "features": {feature: service.resolve(db, center_id=center_id, context_code=context_code,
            audience=audience, feature_code=feature)["visible"] for feature in service.FEATURES}}


@router.get("/settings")
def settings(response: Response, center_id: int | None = Query(default=None, gt=0),
             user=Depends(manage), db=Depends(get_db)):
    service.authorize_admin(db, user)
    service.validate_center(db, user, center_id, administrative=True)
    response.headers["Cache-Control"] = "no-store"
    return service.settings_view(db, center_id)


@router.put("/settings")
def save(payload: VisibilityUpdate, response: Response, center_id: int | None = Query(default=None, gt=0),
         user=Depends(manage), db=Depends(get_db)):
    response.headers["Cache-Control"] = "no-store"
    return service.update(db, user, center_id, payload)
