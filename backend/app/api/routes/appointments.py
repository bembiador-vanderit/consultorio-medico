from datetime import date
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session
from app.api.deps import require_permission
from app.db import get_db
from app.models import Appointment, CareCenter, ClinicalHistory, Patient, User
from app.models.doctor_availability import DoctorAvailability
from app.schemas.appointment import AppointmentCreate, AppointmentResponse, AppointmentScopeOptions
from app.services.appointment_scope import (
    apply_appointment_scope,
    assigned_center_ids,
    ensure_appointment_access,
    is_role,
    secretary_can_manage,
    secretary_doctor_ids_by_center,
)

router = APIRouter(prefix="/appointments", tags=["Citas"])
access = require_permission("patients:access")


def response(a: Appointment) -> AppointmentResponse:
    return AppointmentResponse(
        id=a.id, patient_id=a.patient_id, doctor_id=a.doctor_id, center_id=a.center_id,
        appointment_date=a.appointment_date, appointment_time=a.appointment_time,
        reason=a.reason, status=a.status, notes=a.notes,
        patient_name=f"{a.patient.first_name} {a.patient.last_name}",
        patient_date_of_birth=a.patient.date_of_birth,
        doctor_name=a.doctor.full_name,
        center_name=a.center.name if a.center else None,
        center_city=a.center.city if a.center else None,
        coverage_id=a.coverage_transfer.coverage_id if a.coverage_transfer else None,
        original_doctor_id=a.coverage_transfer.original_doctor_id if a.coverage_transfer else None,
        original_doctor_name=(a.coverage_transfer.coverage.principal.full_name if a.coverage_transfer else None),
        created_at=a.created_at, updated_at=a.updated_at,
    )


def ensure_center_access(user: User, center_id: int) -> None:
    if is_role(user, "admin"):
        return
    if center_id not in assigned_center_ids(user):
        raise HTTPException(status_code=403, detail="No tiene acceso a este centro")


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


def validate_appointment_assignment(
    db: Session,
    user: User,
    doctor_id: int | None,
    center_id: int | None,
    appointment_date: date,
) -> tuple[User, CareCenter]:
    if center_id is None:
        raise HTTPException(status_code=422, detail="Debe indicar el centro de atención")
    if doctor_id is None:
        raise HTTPException(status_code=422, detail="Debe seleccionar un médico")

    center = db.get(CareCenter, center_id)
    if not center or not center.is_active:
        raise HTTPException(status_code=422, detail="Centro de atención inválido")
    ensure_center_access(user, center.id)

    doctor = db.get(User, doctor_id)
    if not doctor or not doctor.is_active or not is_role(doctor, "doctor"):
        raise HTTPException(status_code=422, detail="Médico inválido")
    if center not in doctor.centers:
        raise HTTPException(status_code=422, detail="El médico no está asignado a este centro")
    if is_role(user, "secretary") and not is_role(user, "admin") and not secretary_can_manage(
        user, center.id, doctor.id, db
    ):
        raise HTTPException(status_code=403, detail="No tiene autorización para gestionar citas de este médico")
    if not doctor_is_available(db, doctor.id, center.id, appointment_date):
        raise HTTPException(status_code=409, detail="El médico no está disponible en esta fecha para este centro")
    return doctor, center


@router.get("/doctors")
def list_available_doctors(center_id: int, appointment_date: date, user: User = Depends(access), db: Session = Depends(get_db)):
    center = db.get(CareCenter, center_id)
    if not center or not center.is_active:
        raise HTTPException(status_code=404, detail="Centro de atención no encontrado")
    ensure_center_access(user, center_id)

    doctors = []
    secretary_scope = (
        secretary_doctor_ids_by_center(user, db).get(center_id, set())
        if is_role(user, "secretary") and not is_role(user, "admin")
        else None
    )
    for doctor in db.scalars(select(User).where(User.is_active.is_(True))).all():
        if not is_role(doctor, "doctor") or center not in doctor.centers:
            continue
        if secretary_scope is not None and doctor.id not in secretary_scope:
            continue
        if doctor_is_available(db, doctor.id, center_id, appointment_date):
            doctors.append({"id": doctor.id, "full_name": doctor.full_name})
    return doctors


@router.get("/scope-options", response_model=AppointmentScopeOptions)
def appointment_scope_options(user: User = Depends(access), db: Session = Depends(get_db)):
    active_centers = sorted(
        ([center for center in db.scalars(select(CareCenter).where(CareCenter.is_active.is_(True))).all()]
         if is_role(user, "admin") else [center for center in user.centers if center.is_active]),
        key=lambda center: (center.name.lower(), center.id),
    )
    center_ids = {center.id for center in active_centers}
    secretary_scope = (
        secretary_doctor_ids_by_center(user, db)
        if is_role(user, "secretary") and not is_role(user, "admin") else {}
    )

    if is_role(user, "doctor") and not is_role(user, "admin") and not is_role(user, "secretary"):
        candidates = [user]
    else:
        candidates = list(db.scalars(select(User).where(User.is_active.is_(True))).all())

    doctors = []
    for doctor in candidates:
        if not doctor.is_active or not is_role(doctor, "doctor"):
            continue
        doctor_centers = []
        for center in doctor.centers:
            if center.id not in center_ids or not center.is_active:
                continue
            if secretary_scope:
                allowed = secretary_scope.get(center.id, set())
                if allowed is not None and doctor.id not in allowed:
                    continue
            elif is_role(user, "secretary") and not is_role(user, "admin"):
                continue
            doctor_centers.append(center.id)
        if doctor_centers:
            doctors.append({"id": doctor.id, "full_name": doctor.full_name, "center_ids": sorted(doctor_centers)})

    return {
        "centers": [{"id": center.id, "name": center.name, "city": center.city} for center in active_centers],
        "doctors": sorted(doctors, key=lambda doctor: (doctor["full_name"].lower(), doctor["id"])),
    }


@router.get("", response_model=list[AppointmentResponse])
def list_appointments(
    start: date | None = None,
    end: date | None = None,
    center_id: int | None = None,
    doctor_id: int | None = None,
    user: User = Depends(access),
    db: Session = Depends(get_db),
):
    query = select(Appointment).order_by(Appointment.appointment_date, Appointment.appointment_time)
    if start: query = query.where(Appointment.appointment_date >= start)
    if end: query = query.where(Appointment.appointment_date <= end)
    if center_id: query = query.where(Appointment.center_id == center_id)
    if doctor_id: query = query.where(Appointment.doctor_id == doctor_id)
    query = apply_appointment_scope(query, user, db)
    return [response(a) for a in db.scalars(query).all()]


@router.post("", response_model=AppointmentResponse, status_code=status.HTTP_201_CREATED)
def create_appointment(payload: AppointmentCreate, user: User = Depends(access), db: Session = Depends(get_db)):
    if payload.status == "completed":
        raise HTTPException(
            status_code=409,
            detail="Una cita nueva no puede crearse como completada",
        )
    if not db.get(Patient, payload.patient_id):
        raise HTTPException(status_code=404, detail="Paciente no encontrado")

    doctor, center = validate_appointment_assignment(
        db, user, payload.doctor_id, payload.center_id, payload.appointment_date
    )

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
    ensure_appointment_access(user, appointment, db)
    if not db.get(Patient, payload.patient_id): raise HTTPException(status_code=404, detail="Paciente no encontrado")
    context_changed = (
        payload.patient_id != appointment.patient_id
        or payload.doctor_id != appointment.doctor_id
        or payload.center_id != appointment.center_id
    )
    schedule_changed = (
        payload.appointment_date != appointment.appointment_date
        or payload.appointment_time != appointment.appointment_time
    )
    if appointment.status == "completed" and context_changed:
        raise HTTPException(status_code=409, detail="El contexto de una cita finalizada es inmutable")
    if appointment.status == "completed" and payload.status != "completed":
        raise HTTPException(status_code=409, detail="Una cita finalizada no puede reabrirse desde la edición")
    if appointment.coverage_transfer is not None and (context_changed or schedule_changed):
        raise HTTPException(status_code=409, detail="Una cita transferida conserva su contexto y horario autorizados")
    if is_role(user, "doctor") and not is_role(user, "admin") and context_changed:
        raise HTTPException(status_code=403, detail="El médico no puede reasignar una cita desde la edición ordinaria")
    if payload.status == "completed" and appointment.status != "completed":
        raise HTTPException(
            status_code=409,
            detail="La cita debe completarse mediante la finalización de su consulta clínica",
        )
    clinical_history = db.scalar(
        select(ClinicalHistory).where(ClinicalHistory.appointment_id == appointment.id)
    )
    if clinical_history is not None:
        if context_changed:
            raise HTTPException(
                status_code=409,
                detail="El contexto de una cita con consulta clínica no puede modificarse",
            )
        if payload.status in {"cancelled", "no_show"}:
            raise HTTPException(
                status_code=409,
                detail="Una cita con consulta clínica iniciada no puede cancelarse ni marcarse ausente",
            )

    doctor, center = validate_appointment_assignment(
        db, user, payload.doctor_id, payload.center_id, payload.appointment_date
    )

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
    ensure_appointment_access(user, appointment, db)
    if db.scalar(select(ClinicalHistory.id).where(ClinicalHistory.appointment_id == appointment.id)) is not None:
        raise HTTPException(status_code=409, detail="No se puede eliminar una cita con consulta clínica")
    if appointment.coverage_transfer is not None:
        raise HTTPException(status_code=409, detail="No se puede eliminar una cita con trazabilidad de cobertura")
    db.delete(appointment); db.commit()
