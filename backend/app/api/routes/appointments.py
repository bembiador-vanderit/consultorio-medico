from datetime import date
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session
from app.api.deps import require_permission
from app.db import get_db
from app.models import Appointment, CareCenter, Patient, User
from app.models.doctor_availability import DoctorAvailability
from app.schemas.appointment import AppointmentCreate, AppointmentResponse

router = APIRouter(prefix="/appointments", tags=["Citas"])
access = require_permission("patients:access")


def is_role(user: User, code: str) -> bool:
    return any(role.code == code for role in user.roles)


def response(a: Appointment) -> AppointmentResponse:
    return AppointmentResponse(
        id=a.id, patient_id=a.patient_id, doctor_id=a.doctor_id, center_id=a.center_id,
        appointment_date=a.appointment_date, appointment_time=a.appointment_time,
        reason=a.reason, status=a.status, notes=a.notes,
        patient_name=f"{a.patient.first_name} {a.patient.last_name}",
        doctor_name=a.doctor.full_name,
        center_name=a.center.name if a.center else None,
        center_city=a.center.city if a.center else None,
        created_at=a.created_at, updated_at=a.updated_at,
    )


def assigned_center_ids(user: User) -> set[int]:
    return {center.id for center in user.centers if center.is_active}


def doctor_is_available(db: Session, doctor_id: int, center_id: int, appointment_date: date) -> bool:
    center_rule = db.scalar(select(DoctorAvailability).where(
        DoctorAvailability.doctor_id == doctor_id,
        DoctorAvailability.center_id == center_id,
        DoctorAvailability.availability_date == appointment_date,
    ))
    if center_rule is not None:
        return center_rule.is_available
    global_rule = db.scalar(select(DoctorAvailability).where(
        DoctorAvailability.doctor_id == doctor_id,
        DoctorAvailability.center_id.is_(None),
        DoctorAvailability.availability_date == appointment_date,
    ))
    return global_rule.is_available if global_rule is not None else True


@router.get("/doctors")
def list_available_doctors(center_id: int, appointment_date: date, user: User = Depends(access), db: Session = Depends(get_db)):
    center = db.get(CareCenter, center_id)
    if not center or not center.is_active:
        raise HTTPException(status_code=404, detail="Centro de atención no encontrado")
    if is_role(user, "secretary") and center_id not in assigned_center_ids(user):
        raise HTTPException(status_code=403, detail="No tiene acceso a este centro")

    doctors = []
    for doctor in db.scalars(select(User).where(User.is_active.is_(True))).all():
        if not is_role(doctor, "doctor") or center not in doctor.centers:
            continue
        if doctor_is_available(db, doctor.id, center_id, appointment_date):
            doctors.append({"id": doctor.id, "full_name": doctor.full_name})
    return doctors


@router.get("", response_model=list[AppointmentResponse])
def list_appointments(start: date | None = None, end: date | None = None, user: User = Depends(access), db: Session = Depends(get_db)):
    query = select(Appointment).order_by(Appointment.appointment_date, Appointment.appointment_time)
    if start: query = query.where(Appointment.appointment_date >= start)
    if end: query = query.where(Appointment.appointment_date <= end)
    if is_role(user, "secretary"):
        ids = assigned_center_ids(user)
        query = query.where(Appointment.center_id.in_(ids)) if ids else query.where(Appointment.id == -1)
    return [response(a) for a in db.scalars(query).all()]


@router.post("", response_model=AppointmentResponse, status_code=status.HTTP_201_CREATED)
def create_appointment(payload: AppointmentCreate, user: User = Depends(access), db: Session = Depends(get_db)):
    if not db.get(Patient, payload.patient_id):
        raise HTTPException(status_code=404, detail="Paciente no encontrado")

    doctor_id = payload.doctor_id
    center_id = payload.center_id

    if is_role(user, "secretary"):
        if center_id is None or center_id not in assigned_center_ids(user):
            raise HTTPException(status_code=403, detail="La cita debe pertenecer al centro asignado a la secretaria")
        if doctor_id is None:
            raise HTTPException(status_code=422, detail="Debe seleccionar un médico")
    elif is_role(user, "doctor"):
        doctor_id = user.id
        if center_id is None:
            primary = next((c for c in user.centers if c.is_active), None)
            if primary:
                center_id = primary.id
    elif doctor_id is None:
        raise HTTPException(status_code=422, detail="Debe seleccionar un médico")

    doctor = db.get(User, doctor_id) if doctor_id else None
    center = db.get(CareCenter, center_id) if center_id else None
    if not doctor or not doctor.is_active or not is_role(doctor, "doctor"):
        raise HTTPException(status_code=422, detail="Médico inválido")
    if not center or not center.is_active:
        raise HTTPException(status_code=422, detail="Centro de atención inválido")
    if center not in doctor.centers:
        raise HTTPException(status_code=422, detail="El médico no está asignado a este centro")
    if not doctor_is_available(db, doctor.id, center.id, payload.appointment_date):
        raise HTTPException(status_code=409, detail="El médico no está disponible en esta fecha para este centro")

    data = payload.model_dump()
    data["doctor_id"] = doctor.id
    data["center_id"] = center.id
    appointment = Appointment(**data)
    db.add(appointment); db.commit(); db.refresh(appointment)
    return response(appointment)


@router.put("/{appointment_id}", response_model=AppointmentResponse)
def update_appointment(appointment_id: int, payload: AppointmentCreate, user: User = Depends(access), db: Session = Depends(get_db)):
    appointment = db.get(Appointment, appointment_id)
    if not appointment: raise HTTPException(status_code=404, detail="Cita no encontrada")
    if not db.get(Patient, payload.patient_id): raise HTTPException(status_code=404, detail="Paciente no encontrado")
    if is_role(user, "secretary") and appointment.center_id not in assigned_center_ids(user):
        raise HTTPException(status_code=403, detail="No tiene acceso a esta cita")

    doctor_id = payload.doctor_id or appointment.doctor_id
    center_id = payload.center_id or appointment.center_id
    if is_role(user, "doctor"):
        doctor_id = user.id
    if not center_id:
        raise HTTPException(status_code=422, detail="Debe indicar el centro de atención")
    doctor = db.get(User, doctor_id)
    center = db.get(CareCenter, center_id)
    if not doctor or not doctor.is_active or not is_role(doctor, "doctor") or not center or not center.is_active:
        raise HTTPException(status_code=422, detail="Médico o centro inválido")
    if center not in doctor.centers:
        raise HTTPException(status_code=422, detail="El médico no está asignado a este centro")
    if not doctor_is_available(db, doctor.id, center.id, payload.appointment_date):
        raise HTTPException(status_code=409, detail="El médico no está disponible en esta fecha para este centro")

    data = payload.model_dump()
    data["doctor_id"] = doctor.id
    data["center_id"] = center.id
    for field, value in data.items(): setattr(appointment, field, value)
    db.commit(); db.refresh(appointment)
    return response(appointment)


@router.delete("/{appointment_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_appointment(appointment_id: int, user: User = Depends(access), db: Session = Depends(get_db)):
    appointment = db.get(Appointment, appointment_id)
    if not appointment: raise HTTPException(status_code=404, detail="Cita no encontrada")
    if is_role(user, "secretary") and appointment.center_id not in assigned_center_ids(user):
        raise HTTPException(status_code=403, detail="No tiene acceso a esta cita")
    db.delete(appointment); db.commit()
