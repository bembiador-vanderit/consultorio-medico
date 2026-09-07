from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import DoctorProfile, Specialty, User


def active_doctor_specialties(doctor: User) -> list[Specialty]:
    return sorted(
        (specialty for specialty in doctor.specialties if specialty.is_active),
        key=lambda specialty: (specialty.name.lower(), specialty.id),
    )


def resolve_appointment_specialty(db: Session, doctor: User, specialty_id: int | None) -> Specialty:
    specialties = active_doctor_specialties(doctor)
    if not specialties:
        raise HTTPException(status_code=422, detail="El médico no tiene especialidades activas asignadas")
    if specialty_id is None:
        if len(specialties) == 1:
            return specialties[0]
        raise HTTPException(status_code=422, detail="Debe seleccionar una especialidad del médico")
    specialty = db.get(Specialty, specialty_id)
    if specialty is None or not specialty.is_active or specialty.id not in {item.id for item in specialties}:
        raise HTTPException(status_code=422, detail="La especialidad no está asignada al médico")
    return specialty


def set_doctor_specialties(
    db: Session,
    doctor: User,
    primary_specialty_id: int,
    specialty_ids: list[int],
) -> DoctorProfile:
    if len(set(specialty_ids)) != len(specialty_ids):
        raise HTTPException(status_code=422, detail="Las especialidades no pueden repetirse")
    if primary_specialty_id not in specialty_ids:
        raise HTTPException(status_code=422, detail="La especialidad principal debe estar entre las asignadas")
    specialties = list(db.scalars(select(Specialty).where(Specialty.id.in_(set(specialty_ids)))).all())
    if len(specialties) != len(specialty_ids) or any(not specialty.is_active for specialty in specialties):
        raise HTTPException(status_code=422, detail="Especialidad inválida o inactiva")

    profile = db.scalar(select(DoctorProfile).where(DoctorProfile.user_id == doctor.id))
    if profile is None:
        profile = DoctorProfile(user_id=doctor.id, specialty_id=primary_specialty_id)
        db.add(profile)
    else:
        profile.specialty_id = primary_specialty_id
    doctor.specialties = specialties
    return profile
