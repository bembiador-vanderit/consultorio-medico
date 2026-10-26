from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.api.deps import require_permission
from app.db import get_db
from app.models import CareCenter, Locality, User
from app.models.center import user_centers
from app.schemas.center import (
    CareCenterCreate,
    CareCenterManagementResponse,
    CareCenterResponse,
    CareCenterUpdate,
    CenterUserAssignment,
)
from app.services.appointment_scope import remove_center_membership_from_scopes

router = APIRouter(prefix="/centers", tags=["Centros de atención"])
access = require_permission("centers:access")
manage = require_permission("centers:manage")


def is_role(user: User, code: str) -> bool:
    return any(role.code == code for role in user.roles)


@router.get("/mine", response_model=list[CareCenterResponse])
def list_my_centers(user: User = Depends(access), db: Session = Depends(get_db)):
    if is_role(user, "admin"):
        return list(db.scalars(select(CareCenter).where(CareCenter.is_active.is_(True)).order_by(CareCenter.city, CareCenter.name)).all())
    return sorted([center for center in user.centers if center.is_active], key=lambda center: (center.city, center.name))


def management_response(center: CareCenter) -> CareCenterManagementResponse:
    data = CareCenterResponse.model_validate(center).model_dump()
    return CareCenterManagementResponse(
        **data,
        assigned_user_ids=[user.id for user in center.users],
    )


@router.get("", response_model=list[CareCenterManagementResponse])
def list_centers(_: User = Depends(manage), db: Session = Depends(get_db)):
    centers = db.scalars(select(CareCenter).order_by(CareCenter.city, CareCenter.name)).all()
    return [management_response(center) for center in centers]


@router.post("", response_model=CareCenterResponse, status_code=status.HTTP_201_CREATED)
def create_center(payload: CareCenterCreate, _: User = Depends(manage), db: Session = Depends(get_db)):
    locality = db.get(Locality, payload.locality_id)
    if not locality or not locality.is_active:
        raise HTTPException(status_code=422, detail="Localidad inválida o inactiva")
    center = CareCenter(**payload.model_dump(), city=locality.name)
    db.add(center)
    db.commit()
    db.refresh(center)
    return center


@router.put("/{center_id}", response_model=CareCenterResponse)
def update_center(center_id: int, payload: CareCenterUpdate, _: User = Depends(manage), db: Session = Depends(get_db)):
    center = db.get(CareCenter, center_id)
    locality = db.get(Locality, payload.locality_id)
    if not center:
        raise HTTPException(status_code=404, detail="Centro de atención no encontrado")
    if not locality or not locality.is_active:
        raise HTTPException(status_code=422, detail="Localidad inválida o inactiva")
    data = payload.model_dump(); data["city"] = locality.name
    for field, value in data.items(): setattr(center, field, value)
    db.commit(); db.refresh(center)
    return center


@router.post("/{center_id}/users", response_model=CareCenterResponse)
def assign_user(center_id: int, payload: CenterUserAssignment, _: User = Depends(manage), db: Session = Depends(get_db)):
    center = db.get(CareCenter, center_id); user = db.get(User, payload.user_id)
    if not center: raise HTTPException(status_code=404, detail="Centro de atención no encontrado")
    if not user: raise HTTPException(status_code=404, detail="Usuario no encontrado")
    if not user.is_active: raise HTTPException(status_code=422, detail="No se puede asignar un usuario inactivo")
    if center not in user.centers:
        user.centers.append(center); db.flush()
    if payload.is_primary:
        db.execute(update(user_centers).where(user_centers.c.user_id == user.id).values(is_primary=False))
        db.execute(update(user_centers).where(user_centers.c.user_id == user.id, user_centers.c.center_id == center.id).values(is_primary=True))
    db.commit(); db.refresh(center)
    return center


@router.delete("/{center_id}/users/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
def unassign_user(center_id: int, user_id: int, _: User = Depends(manage), db: Session = Depends(get_db)):
    center = db.get(CareCenter, center_id); user = db.get(User, user_id)
    if not center or not user: raise HTTPException(status_code=404, detail="Centro o usuario no encontrado")
    if center in user.centers:
        remove_center_membership_from_scopes(db, user, {center.id})
        user.centers.remove(center)
    db.commit()
