"""Presence is not a queue ticket, a call, or a clinical consultation."""
from datetime import datetime

from fastapi import HTTPException
from sqlalchemy import inspect, select

from app.models import Appointment, AppointmentArrival, CareCenter, ClinicalAuditLog, ClinicalHistory, Patient, QueueTicket, User
from app.services.agenda_schedule import organization_today
from app.services.appointment_scope import ensure_appointment_access, is_role


def arrival_schema_ready(db):
    if db is None or not hasattr(db, "get_bind"):
        return False
    if "appointment_arrival_ready" not in db.info:
        db.info["appointment_arrival_ready"] = inspect(db.connection()).has_table("appointment_arrivals")
    return db.info["appointment_arrival_ready"]


def arrival_record(db, appointment_id):
    if not arrival_schema_ready(db):
        return None
    return db.scalar(select(AppointmentArrival).where(AppointmentArrival.appointment_id == appointment_id))


def arrival_values(db, appointment):
    ready = arrival_schema_ready(db)
    row = (db.scalar(select(QueueTicket).where(QueueTicket.appointment_id == appointment.id))
           if db is not None and hasattr(db, "get_bind") and appointment.schedule_mode == "queue"
           else arrival_record(db, appointment.id))
    return {"arrival_enabled": ready if appointment.schedule_mode == "timed" else True,
            "arrived_at": row.arrived_at if row else None,
            "arrival_registered_by": (row.arrival_registered_by if isinstance(row, QueueTicket)
                                      else row.registered_by_user_id) if row else None}


def register_arrival(db, appointment_id, user, queue_line_id=None):
    if (not user.is_active or db.info.get("access_scope") == "platform"
            or not (is_role(user, "secretary") or is_role(user, "admin"))):
        raise HTTPException(403, "Solo secretaría o administración puede registrar llegadas")
    appointment = db.scalar(select(Appointment).where(Appointment.id == appointment_id)
                            .with_for_update().execution_options(populate_existing=True))
    if appointment is None:
        raise HTTPException(404, "Cita no encontrada")
    ensure_appointment_access(user, appointment, db)
    if appointment.schedule_mode == "queue":
        if queue_line_id is None:
            raise HTTPException(422, "Seleccione una línea de turnos")
        from app.services.queue import issue_arrival
        issue_arrival(db, appointment.id, queue_line_id, user)
        return appointment
    if queue_line_id is not None:
        raise HTTPException(422, "Las citas por hora no requieren una línea ni un número de turno")
    patient = db.get(Patient, appointment.patient_id)
    center = db.get(CareCenter, appointment.center_id) if appointment.center_id is not None else None
    doctor = db.get(User, appointment.doctor_id)
    if patient is None or patient.organization_id != appointment.organization_id:
        raise HTTPException(404, "Paciente no disponible en este contexto")
    if (center is None or center.organization_id != appointment.organization_id or not center.is_active
            or doctor is None or not doctor.is_active or center not in doctor.centers):
        raise HTTPException(409, "El médico o centro de la cita no está disponible")
    if appointment.status not in {"scheduled", "confirmed"}:
        raise HTTPException(409, "La cita no está prevista para atención")
    if appointment.appointment_date != organization_today(db):
        raise HTTPException(409, "La llegada solo puede registrarse el día de atención")
    if not arrival_schema_ready(db):
        raise HTTPException(503, "Registrar llegada por hora requiere activar 0064_appointment_arrivals")
    if arrival_record(db, appointment.id) is not None:
        return appointment  # Same locked appointment: no second event or success audit.
    if db.scalar(select(ClinicalHistory.id).where(ClinicalHistory.appointment_id == appointment.id)) is not None:
        raise HTTPException(409, "La consulta ya está iniciada; no se registra llegada retrospectivamente")
    now = datetime.utcnow()
    db.add(AppointmentArrival(organization_id=appointment.organization_id, appointment_id=appointment.id,
                             arrived_at=now, registered_by_user_id=user.id))
    db.add(ClinicalAuditLog(organization_id=appointment.organization_id, center_id=appointment.center_id,
        user_id=user.id, resource_type="appointment", resource_id=appointment.id,
        action="appointment.arrival", outcome="success", created_at=now,
        context={"patient_id":appointment.patient_id, "doctor_id":appointment.doctor_id,
                 "schedule_mode":appointment.schedule_mode,
                 "before":{"status":appointment.status, "arrived_at":None},
                 "after":{"status":appointment.status, "arrived_at":now.isoformat()}}))
    db.commit()
    return appointment
