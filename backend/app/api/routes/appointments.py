from app.models.finance import Invoice
from app.models.insurance import AppointmentCoverage
from datetime import date, datetime
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload, object_session
from app.api.deps import require_permission
from app.db import get_db
from app.models import Appointment, AppointmentContactAttempt, CareCenter, ClinicalHistory, Patient, QueueTicket, Specialty, User
from app.models.doctor_availability import DoctorAvailability
from app.schemas.appointment import AppointmentArrivalCreate, AppointmentCreate, AppointmentResponse, AppointmentScopeOptions
from app.services.appointment_arrivals import arrival_record, arrival_values, register_arrival
from app.services.appointment_scope import (
    apply_appointment_scope,
    assigned_center_ids,
    ensure_appointment_access,
    is_role,
    secretary_can_manage,
    secretary_doctor_ids_by_center,
)
from app.services.clinical_specialties import active_doctor_specialties, resolve_appointment_specialty
from app.services.clinical_coverage import coverage_allows_appointment_transfer
from app.services.reminders import sync_in_app_appointment_reminder
from app.services.patient_scope import require_patient_selection
from app.services.agenda_schedule import (
    effective_policy, ensure_booking_mode, ensure_legacy_day_consistent,
    lock_center, multimode_schema_ready, queue_line_available,
)
from app.services.appointment_booking import booking_schema_ready, next_booking_order
from app.services.appointment_slots import ensure_slot_available, slot_write

router = APIRouter(prefix="/appointments", tags=["Citas"])
access = require_permission("patients:access")


def response(a: Appointment, *, booking_ready: bool | None = None) -> AppointmentResponse:
    session = object_session(a) if hasattr(a, "_sa_instance_state") else None
    if booking_ready is None:
        booking_ready = session is not None and booking_schema_ready(session)
    return AppointmentResponse(
        **arrival_values(session, a),
        id=a.id, patient_id=a.patient_id, doctor_id=a.doctor_id, center_id=a.center_id,
        specialty_id=a.specialty_id, specialty_name=a.specialty.name if a.specialty else "No especificada (registro histórico)",
        appointment_date=a.appointment_date, appointment_time=a.appointment_time,
        schedule_mode=a.schedule_mode,
        daily_booking_order=a.daily_booking_order if booking_ready else None,
        reason=a.reason, status=a.status, notes=a.notes,
        patient_name=f"{a.patient.first_name} {a.patient.last_name}",
        patient_phone=a.patient.phone,
        patient_date_of_birth=a.patient.date_of_birth,
        doctor_name=a.doctor.full_name,
        center_name=a.center.name if a.center else None,
        center_city=a.center.city if a.center else None,
        coverage_id=a.coverage_transfer.coverage_id if a.coverage_transfer else None,
        original_doctor_id=a.coverage_transfer.original_doctor_id if a.coverage_transfer else None,
        original_doctor_name=(a.coverage_transfer.coverage.principal.full_name if a.coverage_transfer else None),
        has_clinical_history=a.clinical_history is not None,
        clinical_history_id=a.clinical_history.id if a.clinical_history else None,
        clinical_history_status=a.clinical_history.status if a.clinical_history else None,
        clinical_history_doctor_id=a.clinical_history.doctor_id if a.clinical_history else None,
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
    specialty_id: int | None = None,
    secretary_scope_doctor_id: int | None = None,
) -> tuple[User, CareCenter, Specialty]:
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
    if is_role(user, "doctor") and not is_role(user, "admin") and not is_role(user, "secretary") and doctor.id != user.id:
        raise HTTPException(status_code=403, detail="El médico solo puede crear y gestionar sus propias citas")
    if center not in doctor.centers:
        raise HTTPException(status_code=422, detail="El médico no está asignado a este centro")
    if is_role(user, "secretary") and not is_role(user, "admin") and not secretary_can_manage(
        user, center.id, secretary_scope_doctor_id or doctor.id, db
    ):
        raise HTTPException(status_code=403, detail="No tiene autorización para gestionar citas de este médico")
    if not doctor_is_available(db, doctor.id, center.id, appointment_date):
        raise HTTPException(status_code=409, detail="El médico no está disponible en esta fecha para este centro")
    specialty = resolve_appointment_specialty(db, doctor, specialty_id)
    return doctor, center, specialty


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
        if not doctor.is_active:
            continue
        if is_role(user, "doctor") and not is_role(user, "admin") and not is_role(user, "secretary") and doctor.id != user.id:
            continue
        if not is_role(doctor, "doctor") or center not in doctor.centers:
            continue
        if secretary_scope is not None and doctor.id not in secretary_scope:
            continue
        specialties = active_doctor_specialties(doctor)
        if doctor_is_available(db, doctor.id, center_id, appointment_date) and specialties:
            doctors.append({
                "id": doctor.id,
                "full_name": doctor.full_name,
                "specialties": [{"id": item.id, "name": item.name} for item in specialties],
            })
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
        specialties = active_doctor_specialties(doctor)
        if not specialties:
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
            doctors.append({
                "id": doctor.id,
                "full_name": doctor.full_name,
                "center_ids": sorted(doctor_centers),
                "specialties": [{"id": item.id, "name": item.name} for item in specialties],
            })

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
    query = select(Appointment).options(joinedload(Appointment.patient)).order_by(Appointment.appointment_date, Appointment.appointment_time)
    if start: query = query.where(Appointment.appointment_date >= start)
    if end: query = query.where(Appointment.appointment_date <= end)
    if center_id: query = query.where(Appointment.center_id == center_id)
    if doctor_id: query = query.where(Appointment.doctor_id == doctor_id)
    query = apply_appointment_scope(query, user, db)
    booking_ready = booking_schema_ready(db)
    return [response(a, booking_ready=booking_ready) for a in db.scalars(query).all()]


@router.post("", response_model=AppointmentResponse, status_code=status.HTTP_201_CREATED)
@slot_write
def create_appointment(payload: AppointmentCreate, user: User = Depends(access), db: Session = Depends(get_db)):
    follow_up_context = None
    if payload.follow_up_id is not None:
        from app.services.clinical_follow_up import for_booking
        follow_up_context = for_booking(db, user, payload.follow_up_id, payload)
    if payload.status == "completed":
        raise HTTPException(
            status_code=409,
            detail="Una cita nueva no puede crearse como completada",
        )
    require_patient_selection(db, user, payload.patient_id, center_id=payload.center_id, doctor_id=payload.doctor_id, token=payload.patient_selection_token)

    doctor, center, specialty = validate_appointment_assignment(
        db, user, payload.doctor_id, payload.center_id, payload.appointment_date, payload.specialty_id
    )
    lock_center(db, center.id)
    mode = payload.schedule_mode or effective_policy(db, doctor.id, center.id, payload.appointment_date).default_mode
    ensure_booking_mode(db, doctor.id, center.id, payload.appointment_date, mode, specialty.id)
    ensure_legacy_day_consistent(db, doctor.id, center.id, payload.appointment_date, mode)
    booking_ready = booking_schema_ready(db)
    if mode == "timed" and payload.appointment_time is None:
        raise HTTPException(422, "Las citas por hora requieren Hora")
    if mode == "queue" and not booking_ready and payload.appointment_time is None:
        raise HTTPException(409, "La captura por turnos sin hora requiere activar la migración 0053")

    data = payload.model_dump(exclude={"patient_selection_token", "schedule_mode", "follow_up_id"})
    data["doctor_id"] = doctor.id
    data["center_id"] = center.id
    data["specialty_id"] = specialty.id
    data["schedule_mode"] = mode
    if mode == "queue" and booking_ready:
        data["appointment_time"] = None
        data["daily_booking_order"] = next_booking_order(
            db, organization_id=center.organization_id, center_id=center.id,
            doctor_id=doctor.id, day=payload.appointment_date,
        )
    ensure_slot_available(db, organization_id=center.organization_id, center_id=center.id,
        doctor_id=doctor.id, day=payload.appointment_date, start_time=data["appointment_time"],
        schedule_mode=mode, status=payload.status)
    appointment = Appointment(**data)
    db.add(appointment); db.flush()
    if follow_up_context:
        from app.services.clinical_follow_up import link_booking
        link_booking(db, user, *follow_up_context, appointment)
    sync_in_app_appointment_reminder(db, appointment)
    db.commit(); db.refresh(appointment)
    return response(appointment, booking_ready=booking_ready)


@router.put("/{appointment_id}", response_model=AppointmentResponse)
@slot_write
def update_appointment(appointment_id: int, payload: AppointmentCreate, user: User = Depends(access), db: Session = Depends(get_db)):
    if payload.follow_up_id is not None:
        raise HTTPException(422, "El seguimiento se vincula al crear la cita de retorno")
    appointment = db.scalar(select(Appointment).where(Appointment.id == appointment_id).with_for_update())
    if not appointment: raise HTTPException(status_code=404, detail="Cita no encontrada")
    ensure_appointment_access(user, appointment, db)
    requested_specialty_id = payload.specialty_id if payload.specialty_id is not None else appointment.specialty_id
    identity_context_changed = (
        payload.patient_id != appointment.patient_id
        or payload.doctor_id != appointment.doctor_id
        or payload.center_id != appointment.center_id
    )
    if identity_context_changed and db.scalar(select(AppointmentContactAttempt.id).where(
        AppointmentContactAttempt.appointment_id == appointment_id
    )) is not None:
        raise HTTPException(409, "Una cita con historial de contacto conserva paciente, médico y centro")
    if identity_context_changed and db.scalar(select(Invoice.id).where(Invoice.appointment_id == appointment_id)) is not None:
        raise HTTPException(409, "Una cita facturada conserva su paciente, médico y centro")
    if identity_context_changed and db.scalar(select(AppointmentCoverage.id).where(AppointmentCoverage.appointment_id == appointment_id)) is not None:
        raise HTTPException(409, "Una cita con cobertura de seguro conserva su paciente, médico y centro")
    specialty_changed = requested_specialty_id != appointment.specialty_id
    context_changed = identity_context_changed or specialty_changed
    schedule_changed = (
        payload.appointment_date != appointment.appointment_date
        or (payload.schedule_mode is not None and payload.schedule_mode != appointment.schedule_mode)
        or (payload.appointment_time != appointment.appointment_time and not (
            appointment.schedule_mode == "queue" and appointment.appointment_time is not None
            and payload.appointment_time is None
        ))
    )
    if arrival_record(db, appointment_id) is not None and (
        context_changed or schedule_changed or payload.status in {"cancelled", "no_show"}
    ):
        raise HTTPException(409, "Una cita con llegada registrada conserva su contexto y horario")
    if db.scalar(select(QueueTicket.id).where(QueueTicket.appointment_id == appointment_id)) is not None and (
        context_changed or schedule_changed or payload.status in {"cancelled", "no_show"}
    ):
        raise HTTPException(409, "Una cita con turno emitido conserva su contexto y jornada")
    coverage = db.scalar(select(AppointmentCoverage).where(AppointmentCoverage.appointment_id == appointment_id))
    if schedule_changed and coverage:
        snapshot = coverage.insurance_snapshot
        if (snapshot.get("valid_from") and payload.appointment_date < date.fromisoformat(snapshot["valid_from"])) or (snapshot.get("valid_until") and payload.appointment_date > date.fromisoformat(snapshot["valid_until"])):
            raise HTTPException(409, "La fecha está fuera de la vigencia de la cobertura registrada")
    if appointment.status == "completed" and context_changed:
        raise HTTPException(status_code=409, detail="El contexto de una cita finalizada es inmutable")
    if appointment.status == "completed" and payload.status != "completed":
        raise HTTPException(status_code=409, detail="Una cita finalizada no puede reabrirse desde la edición")
    if appointment.status == "completed" and (
        payload.reason != appointment.reason or payload.notes != appointment.notes
    ):
        raise HTTPException(
            status_code=409,
            detail="El motivo y las notas de una cita finalizada son de solo lectura; use una nota clínica adicional",
        )
    transfer = appointment.coverage_transfer
    if transfer is not None and context_changed:
        raise HTTPException(status_code=409, detail="Una cita transferida conserva su contexto clínico autorizado")
    if transfer is not None and schedule_changed:
        if not is_role(user, "secretary") or is_role(user, "admin"):
            raise HTTPException(status_code=409, detail="Solo la secretaria autorizada puede reprogramar esta cita transferida")
        if payload.appointment_time is None:
            raise HTTPException(409, "La transferencia por cobertura requiere una cita con hora")
        appointment_at = datetime.combine(payload.appointment_date, payload.appointment_time)
        if not coverage_allows_appointment_transfer(transfer.coverage, appointment_at):
            raise HTTPException(status_code=409, detail="El nuevo horario está fuera del período de cobertura")
    if is_role(user, "doctor") and not is_role(user, "admin") and not is_role(user, "secretary") and identity_context_changed:
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
        if schedule_changed:
            raise HTTPException(status_code=409, detail="Una cita con consulta clínica no puede reprogramarse")
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

    doctor, center, specialty = validate_appointment_assignment(
        db,
        user,
        payload.doctor_id,
        payload.center_id,
        payload.appointment_date,
        requested_specialty_id,
        secretary_scope_doctor_id=(
            transfer.original_doctor_id
            if transfer is not None and is_role(user, "secretary") and not is_role(user, "admin")
            else None
        ),
    )
    lock_center(db, center.id)
    changed_journey = (
        appointment.doctor_id != doctor.id
        or appointment.center_id != center.id
        or appointment.appointment_date != payload.appointment_date
    )
    mode = payload.schedule_mode or (
        effective_policy(db, doctor.id, center.id, payload.appointment_date).default_mode
        if changed_journey else appointment.schedule_mode
    )
    mode_changed = mode != appointment.schedule_mode
    if mode_changed and appointment.status not in {"scheduled", "confirmed"}:
        raise HTTPException(409, "La modalidad de una cita ya atendida o cerrada no puede modificarse")
    if mode_changed and db.scalar(select(QueueTicket.id).where(QueueTicket.appointment_id == appointment.id)) is not None:
        raise HTTPException(409, "Una cita con turno emitido no puede cambiar de modalidad")
    if changed_journey or mode_changed:
        ensure_booking_mode(db, doctor.id, center.id, payload.appointment_date, mode, specialty.id)
    ensure_legacy_day_consistent(db, doctor.id, center.id, payload.appointment_date, mode, exclude_id=appointment.id)
    booking_ready = booking_schema_ready(db)
    if mode == "timed" and payload.appointment_time is None:
        raise HTTPException(422, "Las citas por hora requieren Hora")
    if mode == "queue" and not booking_ready and payload.appointment_time is None:
        raise HTTPException(409, "La captura por turnos sin hora requiere activar la migración 0053")

    if payload.patient_id != appointment.patient_id:
        require_patient_selection(db, user, payload.patient_id, center_id=center.id, doctor_id=doctor.id, token=payload.patient_selection_token)
    data = payload.model_dump(exclude={"patient_selection_token", "schedule_mode", "follow_up_id"})
    data["doctor_id"] = doctor.id
    data["center_id"] = center.id
    data["specialty_id"] = specialty.id
    data["schedule_mode"] = mode
    if mode == "queue" and booking_ready:
        data["appointment_time"] = None
        data["daily_booking_order"] = (next_booking_order(
            db, organization_id=center.organization_id, center_id=center.id,
            doctor_id=doctor.id, day=payload.appointment_date,
        ) if changed_journey or mode_changed else appointment.daily_booking_order)
    elif booking_ready:
        data["daily_booking_order"] = None
    else:
        data["appointment_time"] = payload.appointment_time
    if mode == "queue" and booking_ready and not changed_journey and not mode_changed and appointment.appointment_time is not None:
        # Keep the historical time snapshot when editing a pre-0053 queue appointment.
        data["appointment_time"] = appointment.appointment_time
    ensure_slot_available(db, organization_id=center.organization_id, center_id=center.id,
        doctor_id=doctor.id, day=payload.appointment_date, start_time=data["appointment_time"],
        schedule_mode=mode, status=payload.status, exclude_id=appointment.id)
    for field, value in data.items(): setattr(appointment, field, value)
    db.flush()
    sync_in_app_appointment_reminder(db, appointment, refresh_existing=schedule_changed)
    db.commit(); db.refresh(appointment)
    return response(appointment, booking_ready=booking_ready)


@router.get("/queue-capabilities")
def queue_capabilities(user: User = Depends(access), db: Session = Depends(get_db)):
    return {"booking_order_enabled": booking_schema_ready(db)}


@router.post("/{appointment_id}/arrival", response_model=AppointmentResponse)
def check_in(appointment_id: int, payload: AppointmentArrivalCreate,
             user: User = Depends(access), db: Session = Depends(get_db)):
    return response(register_arrival(db, appointment_id, user, payload.queue_line_id))


@router.get("/effective-mode")
def appointment_effective_mode(
    doctor_id: int, center_id: int, day: date,
    user: User = Depends(access), db: Session = Depends(get_db),
    specialty_id: int | None = None,
):
    if db.get(CareCenter, center_id) is None:
        raise HTTPException(404, "Centro no disponible")
    doctor = db.get(User, doctor_id)
    specialties = active_doctor_specialties(doctor) if doctor is not None else []
    validate_appointment_assignment(db, user, doctor_id, center_id, day,
                                    specialty_id if specialty_id is not None else (specialties[0].id if specialties else None))
    policy = effective_policy(db, doctor_id, center_id, day)
    return {
        "schedule_mode": policy.default_mode,
        "allowed_timed": policy.allowed_timed, "allowed_queue": policy.allowed_queue,
        "default_mode": policy.default_mode,
        "queue_line_available": queue_line_available(db, doctor_id, center_id, specialty_id),
        "multimode_enabled": multimode_schema_ready(db),
    }


@router.delete("/{appointment_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_appointment(appointment_id: int, user: User = Depends(access), db: Session = Depends(get_db)):
    appointment = db.scalar(select(Appointment).where(Appointment.id == appointment_id).with_for_update())
    if not appointment: raise HTTPException(status_code=404, detail="Cita no encontrada")
    ensure_appointment_access(user, appointment, db)
    if arrival_record(db, appointment_id) is not None:
        raise HTTPException(409, "No se puede eliminar una cita con llegada registrada")
    if db.scalar(select(ClinicalHistory.id).where(ClinicalHistory.appointment_id == appointment.id)) is not None:
        raise HTTPException(status_code=409, detail="No se puede eliminar una cita con consulta clínica")
    if appointment.coverage_transfer is not None:
        raise HTTPException(status_code=409, detail="No se puede eliminar una cita con trazabilidad de cobertura")
    if db.scalar(select(AppointmentCoverage.id).where(AppointmentCoverage.appointment_id == appointment_id)) is not None:
        raise HTTPException(409, "No se puede eliminar una cita con cobertura de seguro; puede cancelarla")
    if db.scalar(select(Invoice.id).where(Invoice.appointment_id == appointment_id)) is not None:
        raise HTTPException(409, "No se puede eliminar una cita con historial financiero")
    if db.scalar(select(AppointmentContactAttempt.id).where(AppointmentContactAttempt.appointment_id == appointment_id)) is not None:
        raise HTTPException(409, "No se puede eliminar una cita con historial de contacto; puede cancelarla")
    if db.scalar(select(QueueTicket.id).where(QueueTicket.appointment_id == appointment_id)) is not None:
        raise HTTPException(409, "No se puede eliminar una cita con turno emitido")
    db.delete(appointment); db.commit()
