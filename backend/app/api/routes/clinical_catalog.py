from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import case, func, select
from sqlalchemy.orm import Session, joinedload

from app.api.deps import current_user, require_permission
from app.db import get_db
from app.models import AnatomicalRegion, Appointment, ClinicalHistory, DoctorProfile, MedicalStudy, Specialty, User
from app.schemas.clinical_catalog import (
    AnatomicalRegionResponse,
    DoctorProfileCreate,
    DoctorProfileResponse,
    MedicalStudyResponse,
    SpecialtyCreate,
    SpecialtyResponse,
    SpecialtyStatusUpdate,
    SpecialtyUpdate,
)
from app.services.clinical_specialties import set_doctor_specialties

router = APIRouter(prefix="/clinical-catalog", tags=["Catálogo clínico"])
manage = require_permission("users:manage")
HISTORICAL_SPECIALTY_NAME = "No especificada (registro histórico)"


def normalize_specialty_name(name: str) -> str:
    normalized = " ".join(name.split())
    if len(normalized) < 2:
        raise HTTPException(status_code=422, detail="El nombre de la especialidad es obligatorio")
    return normalized


def require_specialty(db: Session, specialty_id: int) -> Specialty:
    specialty = db.get(Specialty, specialty_id)
    if specialty is None:
        raise HTTPException(status_code=404, detail="Especialidad no encontrada")
    return specialty


def ensure_unique_name(db: Session, name: str, specialty_id: int | None = None) -> None:
    query = select(Specialty).where(func.lower(Specialty.name) == name.lower())
    if specialty_id is not None:
        query = query.where(Specialty.id != specialty_id)
    if db.scalar(query):
        raise HTTPException(status_code=409, detail="La especialidad ya existe")


def profile_response(profile: DoctorProfile) -> dict:
    return {
        "user_id": profile.user_id,
        "specialty_id": profile.specialty_id,
        "specialty": profile.specialty,
        "specialties": sorted(profile.user.specialties, key=lambda item: (item.name.lower(), item.id)),
    }


@router.get("/specialties", response_model=list[SpecialtyResponse])
def list_specialties(_: User = Depends(current_user), db: Session = Depends(get_db)):
    return list(db.scalars(select(Specialty).where(Specialty.is_active).order_by(Specialty.name)))


@router.get("/specialties/admin", response_model=list[SpecialtyResponse])
def list_specialties_admin(_: User = Depends(manage), db: Session = Depends(get_db)):
    return list(db.scalars(select(Specialty).order_by(Specialty.name)))


@router.post("/specialties", response_model=SpecialtyResponse, status_code=status.HTTP_201_CREATED)
def create_specialty(payload: SpecialtyCreate, _: User = Depends(manage), db: Session = Depends(get_db)):
    name = normalize_specialty_name(payload.name)
    if name.casefold() == HISTORICAL_SPECIALTY_NAME.casefold():
        raise HTTPException(status_code=422, detail="Ese nombre está reservado para registros históricos")
    ensure_unique_name(db, name)
    specialty = Specialty(name=name, is_active=True)
    db.add(specialty)
    db.commit()
    db.refresh(specialty)
    return specialty


@router.patch("/specialties/{specialty_id}", response_model=SpecialtyResponse)
def update_specialty(specialty_id: int, payload: SpecialtyUpdate, _: User = Depends(manage), db: Session = Depends(get_db)):
    specialty = require_specialty(db, specialty_id)
    if specialty.name == HISTORICAL_SPECIALTY_NAME:
        raise HTTPException(status_code=409, detail="La especialidad histórica reservada no puede editarse")
    if db.scalar(select(Appointment.id).where(Appointment.specialty_id == specialty.id).limit(1)) or db.scalar(
        select(ClinicalHistory.id).where(ClinicalHistory.specialty_id == specialty.id).limit(1)
    ):
        raise HTTPException(status_code=409, detail="No se puede renombrar una especialidad con referencias clínicas")
    name = normalize_specialty_name(payload.name)
    if name.casefold() == HISTORICAL_SPECIALTY_NAME.casefold():
        raise HTTPException(status_code=422, detail="Ese nombre está reservado para registros históricos")
    ensure_unique_name(db, name, specialty.id)
    specialty.name = name
    db.commit()
    db.refresh(specialty)
    return specialty


@router.put("/specialties/{specialty_id}/status", response_model=SpecialtyResponse)
def update_specialty_status(specialty_id: int, payload: SpecialtyStatusUpdate, _: User = Depends(manage), db: Session = Depends(get_db)):
    specialty = require_specialty(db, specialty_id)
    if specialty.name == HISTORICAL_SPECIALTY_NAME and payload.is_active:
        raise HTTPException(status_code=409, detail="La especialidad histórica reservada debe permanecer inactiva")
    specialty.is_active = payload.is_active
    db.commit()
    db.refresh(specialty)
    return specialty


@router.get("/specialties/{specialty_id}/regions", response_model=list[AnatomicalRegionResponse])
def list_regions(specialty_id: int, _: User = Depends(current_user), db: Session = Depends(get_db)):
    if not db.get(Specialty, specialty_id):
        raise HTTPException(status_code=404, detail="Especialidad no encontrada")
    return list(db.scalars(select(AnatomicalRegion).where(AnatomicalRegion.specialty_id == specialty_id, AnatomicalRegion.is_active).order_by(AnatomicalRegion.name)))


@router.get("/studies", response_model=list[MedicalStudyResponse])
def list_studies(
    specialty_id: int | None = None,
    region_id: int | None = None,
    include_all: bool = False,
    _: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    query = select(MedicalStudy).where(MedicalStudy.is_active)
    if specialty_id is not None and not include_all:
        query = query.where(MedicalStudy.specialty_id == specialty_id)
    if region_id is not None:
        query = query.where(MedicalStudy.anatomical_region_id == region_id)
    ordering = []
    if specialty_id is not None and include_all:
        ordering.append(case((MedicalStudy.specialty_id == specialty_id, 0), else_=1))
    return list(db.scalars(query.order_by(*ordering, MedicalStudy.category, MedicalStudy.name)))


@router.get("/doctor-profile/me", response_model=DoctorProfileResponse)
def get_my_profile(user: User = Depends(current_user), db: Session = Depends(get_db)):
    profile = db.scalar(select(DoctorProfile).options(joinedload(DoctorProfile.specialty), joinedload(DoctorProfile.user).joinedload(User.specialties)).where(DoctorProfile.user_id == user.id))
    if profile is None:
        raise HTTPException(status_code=404, detail="El médico todavía no tiene especialidad configurada")
    return profile_response(profile)


@router.put("/doctor-profile/{user_id}", response_model=DoctorProfileResponse)
def set_doctor_profile(user_id: int, payload: DoctorProfileCreate, _: User = Depends(require_permission("users:manage")), db: Session = Depends(get_db)):
    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="Usuario no encontrado")
    if not any(role.code == "doctor" for role in user.roles):
        raise HTTPException(status_code=422, detail="El usuario debe tener el rol de médico")
    primary_specialty_id = payload.primary_specialty_id or payload.specialty_id
    specialty_ids = payload.specialty_ids or ([payload.specialty_id] if payload.specialty_id else [])
    if primary_specialty_id is None:
        raise HTTPException(status_code=422, detail="Debe indicar la especialidad principal")
    profile = set_doctor_specialties(db, user, primary_specialty_id, specialty_ids)
    db.commit()
    profile = db.scalar(select(DoctorProfile).options(joinedload(DoctorProfile.specialty), joinedload(DoctorProfile.user).joinedload(User.specialties)).where(DoctorProfile.id == profile.id))
    return profile_response(profile)
