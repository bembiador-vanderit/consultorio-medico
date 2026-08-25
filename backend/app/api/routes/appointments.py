from datetime import date
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session
from app.api.deps import require_permission
from app.db import get_db
from app.models import Appointment, Patient, User
from app.schemas.appointment import AppointmentCreate, AppointmentResponse

router = APIRouter(prefix="/appointments", tags=["Citas"])
access = require_permission("patients:access")


def response(a: Appointment) -> AppointmentResponse:
    return AppointmentResponse(
        id=a.id, patient_id=a.patient_id, doctor_id=a.doctor_id,
        appointment_date=a.appointment_date, appointment_time=a.appointment_time,
        reason=a.reason, status=a.status, notes=a.notes,
        patient_name=f"{a.patient.first_name} {a.patient.last_name}",
        doctor_name=a.doctor.full_name, created_at=a.created_at, updated_at=a.updated_at,
    )

@router.get("", response_model=list[AppointmentResponse])
def list_appointments(start: date | None = None, end: date | None = None, _=Depends(access), db: Session = Depends(get_db)):
    query = select(Appointment).order_by(Appointment.appointment_date, Appointment.appointment_time)
    if start: query = query.where(Appointment.appointment_date >= start)
    if end: query = query.where(Appointment.appointment_date <= end)
    return [response(a) for a in db.scalars(query).all()]

@router.post("", response_model=AppointmentResponse, status_code=status.HTTP_201_CREATED)
def create_appointment(payload: AppointmentCreate, user: User = Depends(access), db: Session = Depends(get_db)):
    if not db.get(Patient, payload.patient_id):
        raise HTTPException(status_code=404, detail="Paciente no encontrado")
    appointment = Appointment(doctor_id=user.id, **payload.model_dump())
    db.add(appointment); db.commit(); db.refresh(appointment)
    return response(appointment)

@router.put("/{appointment_id}", response_model=AppointmentResponse)
def update_appointment(appointment_id: int, payload: AppointmentCreate, user: User = Depends(access), db: Session = Depends(get_db)):
    appointment = db.get(Appointment, appointment_id)
    if not appointment: raise HTTPException(status_code=404, detail="Cita no encontrada")
    if not db.get(Patient, payload.patient_id): raise HTTPException(status_code=404, detail="Paciente no encontrado")
    for field, value in payload.model_dump().items(): setattr(appointment, field, value)
    db.commit(); db.refresh(appointment)
    return response(appointment)

@router.delete("/{appointment_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_appointment(appointment_id: int, _=Depends(access), db: Session = Depends(get_db)):
    appointment = db.get(Appointment, appointment_id)
    if not appointment: raise HTTPException(status_code=404, detail="Cita no encontrada")
    db.delete(appointment); db.commit()
