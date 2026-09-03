from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from app.api.deps import current_user, require_permission
from app.db import get_db
from app.models import AnatomicalRegion, DoctorProfile, MedicalStudy, Specialty, User
from app.schemas.clinical_catalog import (
    AnatomicalRegionResponse,
    DoctorProfileCreate,
    DoctorProfileResponse,
    MedicalStudyResponse,
    SpecialtyResponse,
)

router = APIRouter(prefix="/clinical-catalog", tags=["Catálogo clínico"])


@router.get("/specialties", response_model=list[SpecialtyResponse])
def list_specialties(_: User = Depends(current_user), db: Session = Depends(get_db)):
    return list(db.scalars(select(Specialty).where(Specialty.is_active).order_by(Specialty.name)))


@router.get("/specialties/{specialty_id}/regions", response_model=list[AnatomicalRegionResponse])
def list_regions(specialty_id: int, _: User = Depends(current_user), db: Session = Depends(get_db)):
    if not db.get(Specialty, specialty_id):
        raise HTTPException(status_code=404, detail="Especialidad no encontrada")
    return list(db.scalars(select(AnatomicalRegion).where(AnatomicalRegion.specialty_id == specialty_id, AnatomicalRegion.is_active).order_by(AnatomicalRegion.name)))


@router.get("/studies", response_model=list[MedicalStudyResponse])
def list_studies(specialty_id: int, region_id: int | None = None, _: User = Depends(current_user), db: Session = Depends(get_db)):
    query = select(MedicalStudy).where(MedicalStudy.specialty_id == specialty_id, MedicalStudy.is_active)
    if region_id is not None:
        query = query.where(MedicalStudy.anatomical_region_id == region_id)
    return list(db.scalars(query.order_by(MedicalStudy.name)))


@router.get("/doctor-profile/me", response_model=DoctorProfileResponse)
def get_my_profile(user: User = Depends(current_user), db: Session = Depends(get_db)):
    profile = db.scalar(select(DoctorProfile).options(joinedload(DoctorProfile.specialty)).where(DoctorProfile.user_id == user.id))
    if profile is None:
        raise HTTPException(status_code=404, detail="El médico todavía no tiene especialidad configurada")
    return profile


@router.put("/doctor-profile/{user_id}", response_model=DoctorProfileResponse)
def set_doctor_profile(user_id: int, payload: DoctorProfileCreate, _: User = Depends(require_permission("users:manage")), db: Session = Depends(get_db)):
    user = db.get(User, user_id)
    specialty = db.get(Specialty, payload.specialty_id)
    if user is None:
        raise HTTPException(status_code=404, detail="Usuario no encontrado")
    if specialty is None or not specialty.is_active:
        raise HTTPException(status_code=404, detail="Especialidad no encontrada")
    if not any(role.code == "doctor" for role in user.roles):
        raise HTTPException(status_code=422, detail="El usuario debe tener el rol de médico")

    profile = db.scalar(select(DoctorProfile).where(DoctorProfile.user_id == user_id))
    if profile is None:
        profile = DoctorProfile(user_id=user_id, specialty_id=payload.specialty_id)
        db.add(profile)
    else:
        profile.specialty_id = payload.specialty_id
    db.commit()
    db.refresh(profile)
    return db.scalar(select(DoctorProfile).options(joinedload(DoctorProfile.specialty)).where(DoctorProfile.id == profile.id))
