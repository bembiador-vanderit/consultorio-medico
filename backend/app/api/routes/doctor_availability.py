from datetime import date
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import require_permission
from app.db import get_db
from app.models import CareCenter, User
from app.models.doctor_availability import DoctorAvailability
from app.schemas.doctor_availability import DoctorAvailabilityCreate, DoctorAvailabilityResponse

router = APIRouter(prefix="/doctor-availability", tags=["Disponibilidad médica"])
access = require_permission("patients:access")


def is_doctor(user: User) -> bool:
    return any(role.code == "doctor" for role in user.roles)


@router.get("", response_model=list[DoctorAvailabilityResponse])
def list_availability(start: date | None = None, end: date | None = None, user: User = Depends(access), db: Session = Depends(get_db)):
    query = select(DoctorAvailability).where(DoctorAvailability.doctor_id == user.id).order_by(DoctorAvailability.availability_date)
    if start:
        query = query.where(DoctorAvailability.availability_date >= start)
    if end:
        query = query.where(DoctorAvailability.availability_date <= end)
    return list(db.scalars(query).all())


@router.post("", response_model=DoctorAvailabilityResponse, status_code=status.HTTP_201_CREATED)
def set_availability(payload: DoctorAvailabilityCreate, user: User = Depends(access), db: Session = Depends(get_db)):
    if not is_doctor(user):
        raise HTTPException(status_code=403, detail="Solo los médicos pueden configurar su disponibilidad")
    if payload.center_id is not None and payload.center_id not in {c.id for c in user.centers if c.is_active}:
        raise HTTPException(status_code=403, detail="No está asignado a este centro")
    existing = db.scalar(select(DoctorAvailability).where(
        DoctorAvailability.doctor_id == user.id,
        DoctorAvailability.center_id == payload.center_id,
        DoctorAvailability.availability_date == payload.availability_date,
    ))
    if existing:
        existing.is_available = payload.is_available
        db.commit()
        db.refresh(existing)
        return existing
    item = DoctorAvailability(doctor_id=user.id, **payload.model_dump())
    db.add(item)
    db.commit()
    db.refresh(item)
    return item
