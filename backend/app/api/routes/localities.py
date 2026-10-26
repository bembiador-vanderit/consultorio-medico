from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import require_permission
from app.db import get_db
from app.models import Locality, User
from app.schemas.center import LocalityCreate, LocalityResponse, LocalityUpdate

router = APIRouter(prefix="/localities", tags=["Localidades"])
access = require_permission("centers:access")
manage = require_permission("centers:manage")


@router.get("", response_model=list[LocalityResponse])
def list_localities(_: User = Depends(access), db: Session = Depends(get_db)):
    return list(db.scalars(select(Locality).where(Locality.is_active.is_(True)).order_by(Locality.name)).all())


@router.get("/all", response_model=list[LocalityResponse])
def list_all_localities(_: User = Depends(manage), db: Session = Depends(get_db)):
    return list(db.scalars(select(Locality).order_by(Locality.name)).all())


@router.post("", response_model=LocalityResponse, status_code=status.HTTP_201_CREATED)
def create_locality(payload: LocalityCreate, _: User = Depends(manage), db: Session = Depends(get_db)):
    if db.scalar(select(Locality).where(Locality.name.ilike(payload.name.strip()))):
        raise HTTPException(status_code=409, detail="La localidad ya existe")
    locality = Locality(name=payload.name.strip(), is_active=payload.is_active)
    db.add(locality)
    db.commit()
    db.refresh(locality)
    return locality


@router.put("/{locality_id}", response_model=LocalityResponse)
def update_locality(locality_id: int, payload: LocalityUpdate, _: User = Depends(manage), db: Session = Depends(get_db)):
    locality = db.get(Locality, locality_id)
    if not locality:
        raise HTTPException(status_code=404, detail="Localidad no encontrada")
    duplicate = db.scalar(select(Locality).where(Locality.name.ilike(payload.name.strip()), Locality.id != locality_id))
    if duplicate:
        raise HTTPException(status_code=409, detail="La localidad ya existe")
    locality.name = payload.name.strip()
    locality.is_active = payload.is_active
    db.commit()
    db.refresh(locality)
    return locality
