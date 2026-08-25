from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.api.deps import require_permission
from app.db import get_db
from app.models import CareCenter, User
from app.models.center import user_centers
from app.schemas.center import CareCenterCreate, CareCenterResponse, CareCenterUpdate, CenterUserAssignment

router = APIRouter(prefix="/centers", tags=["Centros de atención"])
access = require_permission("centers:access")
manage = require_permission("centers:manage")


@router.get("/mine", response_model=list[CareCenterResponse])
def list_my_centers(user: User = Depends(access)):
    return [center for center in user.centers if center.is_active]


@router.get("", response_model=list[CareCenterResponse])
def list_centers(_: User = Depends(manage), db: Session = Depends(get_db)):
    return list(db.scalars(select(CareCenter).order_by(CareCenter.city, CareCenter.name)).all())


@router.post("", response_model=CareCenterResponse, status_code=status.HTTP_201_CREATED)
def create_center(payload: CareCenterCreate, _: User = Depends(manage), db: Session = Depends(get_db)):
    center = CareCenter(**payload.model_dump())
    db.add(center)
    db.commit()
    db.refresh(center)
    return center


@router.put("/{center_id}", response_model=CareCenterResponse)
def update_center(center_id: int, payload: CareCenterUpdate, _: User = Depends(manage), db: Session = Depends(get_db)):
    center = db.get(CareCenter, center_id)
    if not center:
        raise HTTPException(status_code=404, detail="Centro de atención no encontrado")
    for field, value in payload.model_dump().items():
        setattr(center, field, value)
    db.commit()
    db.refresh(center)
    return center


@router.post("/{center_id}/users", response_model=CareCenterResponse)
def assign_user(center_id: int, payload: CenterUserAssignment, _: User = Depends(manage), db: Session = Depends(get_db)):
    center = db.get(CareCenter, center_id)
    user = db.get(User, payload.user_id)
    if not center:
        raise HTTPException(status_code=404, detail="Centro de atención no encontrado")
    if not user:
        raise HTTPException(status_code=404, detail="Usuario no encontrado")

    if center not in user.centers:
        user.centers.append(center)
        db.flush()

    if payload.is_primary:
        db.execute(
            update(user_centers)
            .where(user_centers.c.user_id == user.id)
            .values(is_primary=False)
        )
        db.execute(
            update(user_centers)
            .where(
                user_centers.c.user_id == user.id,
                user_centers.c.center_id == center.id,
            )
            .values(is_primary=True)
        )

    db.commit()
    db.refresh(center)
    return center


@router.delete("/{center_id}/users/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
def unassign_user(center_id: int, user_id: int, _: User = Depends(manage), db: Session = Depends(get_db)):
    center = db.get(CareCenter, center_id)
    user = db.get(User, user_id)
    if not center or not user:
        raise HTTPException(status_code=404, detail="Centro o usuario no encontrado")
    if center in user.centers:
        user.centers.remove(center)
    db.commit()
