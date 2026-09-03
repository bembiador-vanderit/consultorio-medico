from io import BytesIO
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.api.deps import require_permission
from app.db import get_db
from app.models.appointment import Appointment
from app.models.clinical_audit import ClinicalAuditLog
from app.models.center import CareCenter
from app.models.clinical_history import ClinicalHistory
from app.models.diagnosis import Diagnosis
from app.models.identity import User
from app.models.patient import Patient
from app.models.prescription import Prescription
from app.models.requested_tests import RequestedTests
from app.models.vital_signs import VitalSigns
from app.schemas.clinical_history import (
    ClinicalAuditLogResponse,
    ClinicalHistoryCreate,
    ClinicalHistoryResponse,
    ClinicalHistoryUpdate,
)
from app.schemas.requested_tests import RequestedTestCreate, RequestedTestResponse
from app.services.clinical_documents import (
    DiagnosisLine,
    PrescriptionLine,
    build_consultation_summary_pdf,
    build_requested_tests_pdf,
)
from app.services.appointment_scope import ensure_appointment_access
from app.services.clinical_access import (
    add_clinical_audit,
    can_access_history,
    require_history_access,
    scope_histories,
)

router = APIRouter(prefix="/clinical-history", tags=["Historia clínica"])
access = require_permission("clinical:access")
audit_access = require_permission("users:manage")
ATTENDABLE_APPOINTMENT_STATUSES = {"scheduled", "confirmed"}


class ConsultationContextResponse(BaseModel):
    appointment_id: int
    patient_id: int
    doctor_id: int
    center_id: int | None
    appointment_date: str
    appointment_time: str
    appointment_reason: str | None
    appointment_status: str
    previous_consultations: list[ClinicalHistoryResponse]


def _appointment_context(appointment: Appointment, patient_id: int) -> dict[str, int | None]:
    if appointment.patient_id != patient_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="La cita no pertenece al paciente indicado",
        )
    return {
        "appointment_id": appointment.id,
        "doctor_id": appointment.doctor_id,
        "center_id": appointment.center_id,
    }


def _ensure_appointment_attendable(appointment: Appointment) -> None:
    if appointment.status not in ATTENDABLE_APPOINTMENT_STATUSES:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Esta cita no puede ser atendida por su estado actual",
        )


def _resolve_consultation_context(
    appointment_id: int | None,
    patient_id: int,
    db: Session,
    user: User | None = None,
) -> dict[str, int | None]:
    if appointment_id is None:
        return {"appointment_id": None, "doctor_id": None, "center_id": None}

    appointment = db.get(Appointment, appointment_id)
    if appointment is None:
        raise HTTPException(status_code=404, detail="Cita no encontrada")
    if user is not None:
        ensure_appointment_access(user, appointment, db)
        _ensure_appointment_attendable(appointment)
    return _appointment_context(appointment, patient_id)


def _ensure_appointment_available(
    appointment_id: int | None,
    db: Session,
    exclude_history_id: int | None = None,
) -> None:
    if appointment_id is None:
        return

    query = select(ClinicalHistory.id).where(ClinicalHistory.appointment_id == appointment_id)
    if exclude_history_id is not None:
        query = query.where(ClinicalHistory.id != exclude_history_id)
    if db.scalar(query) is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="La cita ya tiene una consulta médica registrada",
        )


@router.get("/audit-logs", response_model=list[ClinicalAuditLogResponse])
def list_clinical_audit_logs(
    history_id: int | None = None,
    limit: int = 100,
    _=Depends(audit_access),
    db: Session = Depends(get_db),
):
    query = select(ClinicalAuditLog).order_by(ClinicalAuditLog.created_at.desc()).limit(min(max(limit, 1), 200))
    if history_id is not None:
        query = query.where(ClinicalAuditLog.clinical_history_id == history_id)
    return list(db.scalars(query).all())


@router.get("/patients/{patient_id}", response_model=list[ClinicalHistoryResponse])
def get_clinical_history(patient_id: int, user: User = Depends(access), db: Session = Depends(get_db)):
    if not db.get(Patient, patient_id):
        raise HTTPException(status_code=404, detail="Paciente no encontrado")
    query = select(ClinicalHistory).where(ClinicalHistory.patient_id == patient_id)
    query = scope_histories(query, user).order_by(ClinicalHistory.consultation_date.desc(), ClinicalHistory.id.desc())
    histories = [history for history in db.scalars(query) if can_access_history(db, user, history)]
    response = []
    for history in histories:
        item = ClinicalHistoryResponse.model_validate(history)
        item.requested_tests = [
            RequestedTestResponse.model_validate(test)
            for test in db.scalars(
                select(RequestedTests)
                .where(RequestedTests.clinical_history_id == history.id)
                .order_by(RequestedTests.id)
            )
        ]
        response.append(item)
    add_clinical_audit(
        db, user, action="history.list", resource_type="patient", resource_id=patient_id,
        context={"records_returned": len(response)},
    )
    db.commit()
    return response


@router.get("/appointments/{appointment_id}/context", response_model=ConsultationContextResponse)
def get_consultation_context(appointment_id: int, user: User = Depends(access), db: Session = Depends(get_db)):
    appointment = db.get(Appointment, appointment_id)
    if appointment is None:
        raise HTTPException(status_code=404, detail="Cita no encontrada")
    ensure_appointment_access(user, appointment, db)
    _ensure_appointment_attendable(appointment)

    histories_query = select(ClinicalHistory).where(ClinicalHistory.patient_id == appointment.patient_id)
    histories_query = scope_histories(histories_query, user).order_by(
        ClinicalHistory.consultation_date.desc(), ClinicalHistory.id.desc()
    )
    histories = [history for history in db.scalars(histories_query) if can_access_history(db, user, history)]

    previous_consultations = []
    for history in histories:
        item = ClinicalHistoryResponse.model_validate(history)
        item.requested_tests = [
            RequestedTestResponse.model_validate(test)
            for test in db.scalars(
                select(RequestedTests)
                .where(RequestedTests.clinical_history_id == history.id)
                .order_by(RequestedTests.id)
            )
        ]
        previous_consultations.append(item)

    result = ConsultationContextResponse(
        appointment_id=appointment.id,
        patient_id=appointment.patient_id,
        doctor_id=appointment.doctor_id,
        center_id=appointment.center_id,
        appointment_date=appointment.appointment_date.isoformat(),
        appointment_time=appointment.appointment_time.isoformat(),
        appointment_reason=appointment.reason,
        appointment_status=appointment.status,
        previous_consultations=previous_consultations,
    )
    add_clinical_audit(
        db, user, action="consultation.context.read", resource_type="appointment",
        resource_id=appointment.id, context={"patient_id": appointment.patient_id},
    )
    db.commit()
    return result


@router.post("/patients/{patient_id}", response_model=ClinicalHistoryResponse, status_code=status.HTTP_201_CREATED)
def create_clinical_history(patient_id: int, payload: ClinicalHistoryCreate, user: User = Depends(access), db: Session = Depends(get_db)):
    if not db.get(Patient, patient_id):
        raise HTTPException(status_code=404, detail="Paciente no encontrado")

    data = payload.model_dump()
    context = _resolve_consultation_context(data.get("appointment_id"), patient_id, db, user)
    _ensure_appointment_available(context["appointment_id"], db)
    data.update(context)

    history = ClinicalHistory(patient_id=patient_id, **data)
    db.add(history)
    db.flush()
    add_clinical_audit(
        db, user, action="history.create", resource_type="clinical_history",
        resource_id=history.id, history_id=history.id,
        context={"appointment_id": history.appointment_id, "doctor_id": history.doctor_id, "center_id": history.center_id},
    )
    db.commit()
    db.refresh(history)
    return history


@router.put("/{history_id}", response_model=ClinicalHistoryResponse)
def update_clinical_history(history_id: int, payload: ClinicalHistoryUpdate, user: User = Depends(access), db: Session = Depends(get_db)):
    history = require_history_access(db, user, history_id, action="history.update", write=True)
    data = payload.model_dump()
    for field, value in data.items():
        setattr(history, field, value)
    add_clinical_audit(
        db, user, action="history.update", resource_type="clinical_history",
        resource_id=history.id, history_id=history.id,
    )
    db.commit()
    db.refresh(history)
    return history


@router.post("/{history_id}/complete", response_model=ClinicalHistoryResponse)
def complete_clinical_history(history_id: int, user: User = Depends(access), db: Session = Depends(get_db)):
    history = require_history_access(db, user, history_id, action="history.complete", write=True)
    if history.appointment_id is None:
        raise HTTPException(status_code=409, detail="La consulta no tiene una cita vinculada")
    appointment = db.get(Appointment, history.appointment_id)
    if appointment is None:
        raise HTTPException(status_code=409, detail="La cita vinculada ya no está disponible")
    ensure_appointment_access(user, appointment, db)
    _ensure_appointment_attendable(appointment)
    if (
        appointment.patient_id != history.patient_id
        or appointment.doctor_id != history.doctor_id
        or appointment.center_id != history.center_id
    ):
        raise HTTPException(status_code=409, detail="El contexto de la consulta no coincide con la cita")

    now = datetime.utcnow()
    history.status = "completed"
    history.completed_at = now
    history.completed_by_id = user.id
    appointment.status = "completed"
    add_clinical_audit(
        db, user, action="history.complete", resource_type="clinical_history",
        resource_id=history.id, history_id=history.id,
        context={"appointment_id": appointment.id},
    )
    try:
        db.commit()
    except SQLAlchemyError:
        db.rollback()
        raise HTTPException(status_code=500, detail="No fue posible finalizar la consulta")
    db.refresh(history)
    return history


@router.get("/{history_id}/summary/pdf")
def get_consultation_summary_pdf(history_id: int, user: User = Depends(access), db: Session = Depends(get_db)):
    history = require_history_access(
        db, user, history_id, action="summary_pdf.read", resource_type="clinical_document", audit_read=True
    )

    patient = db.get(Patient, history.patient_id)
    doctor = db.get(User, history.doctor_id) if history.doctor_id is not None else None
    center = db.get(CareCenter, history.center_id) if history.center_id is not None else None
    if patient is None:
        raise HTTPException(status_code=404, detail="Paciente no encontrado")

    diagnoses = list(
        db.scalars(
            select(Diagnosis)
            .where(Diagnosis.clinical_history_id == history_id)
            .order_by(Diagnosis.is_primary.desc(), Diagnosis.id)
        )
    )
    prescriptions = list(
        db.scalars(
            select(Prescription)
            .where(Prescription.clinical_history_id == history_id)
            .order_by(Prescription.id)
        )
    )
    tests = list(
        db.scalars(
            select(RequestedTests)
            .where(RequestedTests.clinical_history_id == history_id)
            .order_by(RequestedTests.id)
        )
    )
    vital_signs = db.scalar(
        select(VitalSigns).where(VitalSigns.clinical_history_id == history_id)
    )

    def measurement(value, unit: str) -> str:
        normalized = format(value, "f").rstrip("0").rstrip(".")
        return f"{normalized} {unit}"

    vital_lines: list[tuple[str, str]] = []
    if vital_signs is not None:
        if vital_signs.systolic_pressure is not None or vital_signs.diastolic_pressure is not None:
            systolic = vital_signs.systolic_pressure if vital_signs.systolic_pressure is not None else "-"
            diastolic = vital_signs.diastolic_pressure if vital_signs.diastolic_pressure is not None else "-"
            vital_lines.append(("Presión arterial", f"{systolic}/{diastolic} mmHg"))
        values = [
            ("Frecuencia cardíaca", vital_signs.heart_rate, "lpm"),
            ("Frecuencia respiratoria", vital_signs.respiratory_rate, "rpm"),
            ("Temperatura", vital_signs.temperature_c, "°C"),
            ("Saturación de oxígeno", vital_signs.oxygen_saturation, "%"),
            ("Peso", vital_signs.weight_kg, "kg"),
            ("Talla", vital_signs.height_cm, "cm"),
        ]
        vital_lines.extend(
            (label, measurement(value, unit))
            for label, value, unit in values
            if value is not None
        )

    content = build_consultation_summary_pdf(
        history_id=history.id,
        appointment_id=history.appointment_id,
        consultation_date=history.consultation_date,
        patient_name=f"{patient.first_name} {patient.last_name}",
        doctor_name=doctor.full_name if doctor else "Médico no especificado",
        center_name=center.name if center else None,
        center_address=(
            ", ".join(part for part in (center.address, center.city) if part)
            if center
            else None
        ),
        vital_signs=vital_lines,
        clinical_fields=[
            ("Motivo de consulta", history.reason_for_visit),
            ("Enfermedad actual", history.current_illness),
            ("Antecedentes personales", history.personal_history),
            ("Antecedentes familiares", history.family_history),
            ("Alergias", history.allergies),
            ("Medicamentos habituales", history.current_medications),
            ("Cirugías previas", history.previous_surgeries),
            ("Enfermedades crónicas", history.chronic_conditions),
            ("Hábitos", history.habits),
            ("Notas clínicas", history.clinical_notes),
        ],
        diagnosis_lines=[
            DiagnosisLine(
                description=item.description,
                icd10_code=item.icd10_code,
                is_primary=item.is_primary,
            )
            for item in diagnoses
        ],
        prescription_lines=[
            PrescriptionLine(
                medication=item.medication,
                presentation=item.presentation,
                dose=item.dose,
                route=item.route,
                frequency=item.frequency,
                duration=item.duration,
                quantity=item.quantity,
                instructions=item.instructions,
            )
            for item in prescriptions
        ],
        test_names=[item.test_name for item in tests],
    )
    filename = f"resumen-consulta-{history.id}.pdf"
    return StreamingResponse(
        BytesIO(content),
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/{history_id}/requested-tests", response_model=list[RequestedTestResponse])
def get_requested_tests(history_id: int, user: User = Depends(access), db: Session = Depends(get_db)):
    require_history_access(db, user, history_id, action="requested_tests.read", audit_read=True)
    return list(db.scalars(select(RequestedTests).where(RequestedTests.clinical_history_id == history_id).order_by(RequestedTests.id)))


@router.get("/{history_id}/requested-tests/pdf")
def get_requested_tests_pdf(history_id: int, user: User = Depends(access), db: Session = Depends(get_db)):
    history = require_history_access(
        db, user, history_id, action="requested_tests_pdf.read", resource_type="clinical_document", audit_read=True
    )

    tests = list(
        db.scalars(
            select(RequestedTests)
            .where(RequestedTests.clinical_history_id == history_id)
            .order_by(RequestedTests.id)
        )
    )
    if not tests:
        raise HTTPException(status_code=422, detail="La consulta no tiene estudios solicitados")

    patient = db.get(Patient, history.patient_id)
    doctor = db.get(User, history.doctor_id) if history.doctor_id is not None else None
    center = db.get(CareCenter, history.center_id) if history.center_id is not None else None
    if patient is None:
        raise HTTPException(status_code=404, detail="Paciente no encontrado")

    content = build_requested_tests_pdf(
        history_id=history.id,
        consultation_date=history.consultation_date,
        patient_name=f"{patient.first_name} {patient.last_name}",
        doctor_name=doctor.full_name if doctor else "Médico no especificado",
        center_name=center.name if center else None,
        center_address=(
            ", ".join(part for part in (center.address, center.city) if part)
            if center
            else None
        ),
        test_names=[test.test_name for test in tests],
    )
    filename = f"orden-estudios-{history.id}.pdf"
    return StreamingResponse(
        BytesIO(content),
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.post("/{history_id}/requested-tests", response_model=RequestedTestResponse, status_code=status.HTTP_201_CREATED)
def add_requested_test(history_id: int, payload: RequestedTestCreate, user: User = Depends(access), db: Session = Depends(get_db)):
    require_history_access(db, user, history_id, action="requested_test.create", write=True)
    item = RequestedTests(clinical_history_id=history_id, test_name=payload.test_name)
    db.add(item); db.flush()
    add_clinical_audit(db, user, action="requested_test.create", resource_type="requested_test", resource_id=item.id, history_id=history_id)
    db.commit(); db.refresh(item)
    return item


@router.delete("/requested-tests/{test_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_requested_test(test_id: int, user: User = Depends(access), db: Session = Depends(get_db)):
    item = db.get(RequestedTests, test_id)
    if item is None:
        raise HTTPException(status_code=404, detail="Análisis o prueba no encontrado")
    require_history_access(
        db, user, item.clinical_history_id, action="requested_test.delete",
        resource_type="requested_test", resource_id=item.id, write=True,
    )
    history_id = item.clinical_history_id
    db.delete(item)
    add_clinical_audit(db, user, action="requested_test.delete", resource_type="requested_test", resource_id=test_id, history_id=history_id)
    db.commit()
