from io import BytesIO

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import require_permission
from app.db import get_db
from app.models.appointment import Appointment
from app.models.center import CareCenter
from app.models.clinical_history import ClinicalHistory
from app.models.identity import User
from app.models.patient import Patient
from app.models.requested_tests import RequestedTests
from app.schemas.clinical_history import ClinicalHistoryCreate, ClinicalHistoryResponse
from app.schemas.requested_tests import RequestedTestCreate, RequestedTestResponse
from app.services.clinical_documents import build_requested_tests_pdf

router = APIRouter(prefix="/clinical-history", tags=["Historia clínica"])
access = require_permission("patients:access")


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


def _resolve_consultation_context(
    appointment_id: int | None,
    patient_id: int,
    db: Session,
) -> dict[str, int | None]:
    if appointment_id is None:
        return {"appointment_id": None, "doctor_id": None, "center_id": None}

    appointment = db.get(Appointment, appointment_id)
    if appointment is None:
        raise HTTPException(status_code=404, detail="Cita no encontrada")
    return _appointment_context(appointment, patient_id)


@router.get("/patients/{patient_id}", response_model=list[ClinicalHistoryResponse])
def get_clinical_history(patient_id: int, _=Depends(access), db: Session = Depends(get_db)):
    if not db.get(Patient, patient_id):
        raise HTTPException(status_code=404, detail="Paciente no encontrado")
    histories = list(
        db.scalars(
            select(ClinicalHistory)
            .where(ClinicalHistory.patient_id == patient_id)
            .order_by(ClinicalHistory.consultation_date.desc(), ClinicalHistory.id.desc())
        )
    )
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
    return response


@router.get("/appointments/{appointment_id}/context", response_model=ConsultationContextResponse)
def get_consultation_context(appointment_id: int, _=Depends(access), db: Session = Depends(get_db)):
    appointment = db.get(Appointment, appointment_id)
    if appointment is None:
        raise HTTPException(status_code=404, detail="Cita no encontrada")

    histories = list(
        db.scalars(
            select(ClinicalHistory)
            .where(ClinicalHistory.patient_id == appointment.patient_id)
            .order_by(ClinicalHistory.consultation_date.desc(), ClinicalHistory.id.desc())
        )
    )

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

    return ConsultationContextResponse(
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


@router.post("/patients/{patient_id}", response_model=ClinicalHistoryResponse, status_code=status.HTTP_201_CREATED)
def create_clinical_history(patient_id: int, payload: ClinicalHistoryCreate, _=Depends(access), db: Session = Depends(get_db)):
    if not db.get(Patient, patient_id):
        raise HTTPException(status_code=404, detail="Paciente no encontrado")

    data = payload.model_dump()
    context = _resolve_consultation_context(data.get("appointment_id"), patient_id, db)
    data.update(context)

    history = ClinicalHistory(patient_id=patient_id, **data)
    db.add(history)
    db.commit()
    db.refresh(history)
    return history


@router.put("/{history_id}", response_model=ClinicalHistoryResponse)
def update_clinical_history(history_id: int, payload: ClinicalHistoryCreate, _=Depends(access), db: Session = Depends(get_db)):
    history = db.get(ClinicalHistory, history_id)
    if history is None:
        raise HTTPException(status_code=404, detail="Registro de historia clínica no encontrado")

    data = payload.model_dump()
    context = _resolve_consultation_context(data.get("appointment_id"), history.patient_id, db)
    data.update(context)

    for field, value in data.items():
        setattr(history, field, value)
    db.commit()
    db.refresh(history)
    return history


@router.get("/{history_id}/requested-tests", response_model=list[RequestedTestResponse])
def get_requested_tests(history_id: int, _=Depends(access), db: Session = Depends(get_db)):
    if not db.get(ClinicalHistory, history_id):
        raise HTTPException(status_code=404, detail="Registro de historia clínica no encontrado")
    return list(db.scalars(select(RequestedTests).where(RequestedTests.clinical_history_id == history_id).order_by(RequestedTests.id)))


@router.get("/{history_id}/requested-tests/pdf")
def get_requested_tests_pdf(history_id: int, _=Depends(access), db: Session = Depends(get_db)):
    history = db.get(ClinicalHistory, history_id)
    if history is None:
        raise HTTPException(status_code=404, detail="Registro de historia clínica no encontrado")

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
def add_requested_test(history_id: int, payload: RequestedTestCreate, _=Depends(access), db: Session = Depends(get_db)):
    if not db.get(ClinicalHistory, history_id):
        raise HTTPException(status_code=404, detail="Registro de historia clínica no encontrado")
    item = RequestedTests(clinical_history_id=history_id, test_name=payload.test_name)
    db.add(item); db.commit(); db.refresh(item)
    return item


@router.delete("/requested-tests/{test_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_requested_test(test_id: int, _=Depends(access), db: Session = Depends(get_db)):
    item = db.get(RequestedTests, test_id)
    if item is None:
        raise HTTPException(status_code=404, detail="Análisis o prueba no encontrado")
    db.delete(item); db.commit()
