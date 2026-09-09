from io import BytesIO

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.api.deps import require_permission
from app.db import get_db
from app.models import (
    CareCenter,
    LaboratoryOrder,
    LaboratoryOrderItem,
    LaboratoryTest,
    MedicalStudy,
    Patient,
    Specialty,
    StudyOrder,
    StudyOrderItem,
    User,
)
from app.schemas.clinical_order import (
    LaboratoryOrderInput,
    LaboratoryOrderResponse,
    LaboratoryTestResponse,
    StudyOrderInput,
    StudyOrderResponse,
)
from app.services.clinical_access import add_clinical_audit, has_normal_history_access, require_history_access
from app.services.clinical_documents import build_laboratory_order_pdf, build_study_order_pdf


router = APIRouter(tags=["Órdenes clínicas"])
access = require_permission("clinical:access")


@router.get("/laboratory-tests", response_model=list[LaboratoryTestResponse])
def list_laboratory_tests(q: str | None = None, _: User = Depends(access), db: Session = Depends(get_db)):
    query = select(LaboratoryTest).where(LaboratoryTest.is_active)
    normalized = " ".join((q or "").split()).lower()
    if normalized:
        query = query.where(or_(
            func.lower(LaboratoryTest.name).contains(normalized),
            func.lower(LaboratoryTest.category).contains(normalized),
            func.lower(func.coalesce(LaboratoryTest.code, "")).contains(normalized),
        ))
    return list(db.scalars(query.order_by(
        LaboratoryTest.category, LaboratoryTest.sort_order, LaboratoryTest.name
    )))


def _context(db: Session, history) -> dict:
    patient = db.get(Patient, history.patient_id)
    doctor = db.get(User, history.doctor_id) if history.doctor_id is not None else None
    center = db.get(CareCenter, history.center_id) if history.center_id is not None else None
    specialty = db.get(Specialty, history.specialty_id) if history.specialty_id is not None else None
    if patient is None or doctor is None:
        raise HTTPException(status_code=409, detail="La consulta no tiene un contexto clínico completo")
    return {
        "clinical_history_id": history.id,
        "appointment_id": history.appointment_id,
        "patient_id": patient.id,
        "doctor_id": doctor.id,
        "center_id": center.id if center else None,
        "specialty_id": specialty.id if specialty else None,
        "patient_name": f"{patient.first_name} {patient.last_name}",
        "doctor_name": doctor.full_name,
        "center_name": center.name if center else None,
        "specialty_name": specialty.name if specialty else "No especificada (registro histórico)",
        "status": "ordered",
    }


def _require_additional_order_authority(db: Session, user: User, history_id: int, *, action: str):
    history = require_history_access(db, user, history_id, action=action, resource_id=history_id)
    if not user.is_active or not has_normal_history_access(db, user, history):
        add_clinical_audit(
            db, user, action=action, resource_type="clinical_history",
            resource_id=history.id, history_id=history.id, outcome="denied",
            context={"reason": "additional_order_authority_required"},
        )
        db.commit()
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Solo el médico responsable puede emitir una orden adicional",
        )
    if history.status != "completed":
        add_clinical_audit(
            db, user, action=action, resource_type="clinical_history",
            resource_id=history.id, history_id=history.id, outcome="denied",
            context={"reason": "consultation_not_completed"},
        )
        db.commit()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Las órdenes adicionales solo pueden emitirse después de finalizar la consulta",
        )
    return history


def _laboratory_items(db: Session, payload: LaboratoryOrderInput) -> list[LaboratoryOrderItem]:
    ids = [item.laboratory_test_id for item in payload.items]
    if len(ids) != len(set(ids)):
        raise HTTPException(status_code=422, detail="Una prueba de laboratorio no puede repetirse en la misma orden")
    tests = {item.id: item for item in db.scalars(select(LaboratoryTest).where(LaboratoryTest.id.in_(ids)))}
    if len(tests) != len(ids):
        raise HTTPException(status_code=422, detail="La orden contiene una prueba de laboratorio inexistente")
    if any(not tests[test_id].is_active for test_id in ids):
        raise HTTPException(status_code=422, detail="Una prueba de laboratorio inactiva no puede utilizarse en una orden nueva")
    return [
        LaboratoryOrderItem(
            laboratory_test_id=test.id,
            test_code=test.code,
            test_name=test.name,
            test_category=test.category,
            custom_note=item.custom_note,
        )
        for item in payload.items
        for test in [tests[item.laboratory_test_id]]
    ]


def _study_items(db: Session, history, payload: StudyOrderInput) -> list[StudyOrderItem]:
    ids = [item.medical_study_id for item in payload.items]
    if len(ids) != len(set(ids)):
        raise HTTPException(status_code=422, detail="Un estudio no puede repetirse en la misma orden")
    studies = {item.id: item for item in db.scalars(select(MedicalStudy).where(MedicalStudy.id.in_(ids)))}
    if len(studies) != len(ids):
        raise HTTPException(status_code=422, detail="La orden contiene un estudio inexistente")
    if any(not studies[study_id].is_active for study_id in ids):
        raise HTTPException(status_code=422, detail="Un estudio inactivo no puede utilizarse en una orden nueva")
    if history.specialty_id is not None and any(studies[study_id].specialty_id != history.specialty_id for study_id in ids):
        raise HTTPException(status_code=422, detail="El estudio no corresponde a la especialidad de la consulta")
    return [
        StudyOrderItem(
            medical_study_id=study.id,
            modality=study.category,
            study_name=study.name,
            region_description=item.region_description,
            contrast=item.contrast,
            clinical_notes=item.clinical_notes,
        )
        for item in payload.items
        for study in [studies[item.medical_study_id]]
    ]


@router.get("/clinical-history/{history_id}/laboratory-orders", response_model=list[LaboratoryOrderResponse])
def list_laboratory_orders(history_id: int, user: User = Depends(access), db: Session = Depends(get_db)):
    require_history_access(db, user, history_id, action="laboratory_order.list", audit_read=True)
    return list(db.scalars(
        select(LaboratoryOrder)
        .where(LaboratoryOrder.clinical_history_id == history_id)
        .order_by(LaboratoryOrder.created_at, LaboratoryOrder.id)
    ))


@router.post("/clinical-history/{history_id}/laboratory-orders", response_model=LaboratoryOrderResponse, status_code=status.HTTP_201_CREATED)
def create_laboratory_order(history_id: int, payload: LaboratoryOrderInput, user: User = Depends(access), db: Session = Depends(get_db)):
    history = require_history_access(db, user, history_id, action="laboratory_order.create", write=True)
    order = LaboratoryOrder(**_context(db, history), notes=payload.notes, items=_laboratory_items(db, payload))
    db.add(order)
    db.flush()
    add_clinical_audit(db, user, action="laboratory_order.create", resource_type="laboratory_order", resource_id=order.id, history_id=history.id)
    db.commit()
    db.refresh(order)
    return order


@router.post(
    "/clinical-history/{history_id}/laboratory-orders/additional",
    response_model=LaboratoryOrderResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_additional_laboratory_order(
    history_id: int, payload: LaboratoryOrderInput,
    user: User = Depends(access), db: Session = Depends(get_db),
):
    history = _require_additional_order_authority(
        db, user, history_id, action="laboratory_order.additional.create"
    )
    order = LaboratoryOrder(
        **_context(db, history), notes=payload.notes, is_additional=True,
        items=_laboratory_items(db, payload),
    )
    db.add(order)
    db.flush()
    add_clinical_audit(
        db, user, action="laboratory_order.additional.create",
        resource_type="laboratory_order", resource_id=order.id, history_id=history.id,
    )
    db.commit()
    db.refresh(order)
    return order


@router.put("/clinical-history/{history_id}/laboratory-orders/{order_id}", response_model=LaboratoryOrderResponse)
def update_laboratory_order(history_id: int, order_id: int, payload: LaboratoryOrderInput, user: User = Depends(access), db: Session = Depends(get_db)):
    history = require_history_access(db, user, history_id, action="laboratory_order.update", write=True)
    order = db.get(LaboratoryOrder, order_id)
    if order is None or order.clinical_history_id != history.id:
        raise HTTPException(status_code=404, detail="Orden de laboratorio no encontrada")
    order.notes = payload.notes
    order.items.clear()
    db.flush()
    order.items = _laboratory_items(db, payload)
    add_clinical_audit(db, user, action="laboratory_order.update", resource_type="laboratory_order", resource_id=order.id, history_id=history.id)
    db.commit()
    db.refresh(order)
    return order


@router.get("/clinical-history/{history_id}/study-orders", response_model=list[StudyOrderResponse])
def list_study_orders(history_id: int, user: User = Depends(access), db: Session = Depends(get_db)):
    require_history_access(db, user, history_id, action="study_order.list", audit_read=True)
    return list(db.scalars(
        select(StudyOrder).where(StudyOrder.clinical_history_id == history_id).order_by(StudyOrder.created_at, StudyOrder.id)
    ))


@router.post("/clinical-history/{history_id}/study-orders", response_model=StudyOrderResponse, status_code=status.HTTP_201_CREATED)
def create_study_order(history_id: int, payload: StudyOrderInput, user: User = Depends(access), db: Session = Depends(get_db)):
    history = require_history_access(db, user, history_id, action="study_order.create", write=True)
    order = StudyOrder(**_context(db, history), notes=payload.notes, items=_study_items(db, history, payload))
    db.add(order)
    db.flush()
    add_clinical_audit(db, user, action="study_order.create", resource_type="study_order", resource_id=order.id, history_id=history.id)
    db.commit()
    db.refresh(order)
    return order


@router.post(
    "/clinical-history/{history_id}/study-orders/additional",
    response_model=StudyOrderResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_additional_study_order(
    history_id: int, payload: StudyOrderInput,
    user: User = Depends(access), db: Session = Depends(get_db),
):
    history = _require_additional_order_authority(
        db, user, history_id, action="study_order.additional.create"
    )
    order = StudyOrder(
        **_context(db, history), notes=payload.notes, is_additional=True,
        items=_study_items(db, history, payload),
    )
    db.add(order)
    db.flush()
    add_clinical_audit(
        db, user, action="study_order.additional.create",
        resource_type="study_order", resource_id=order.id, history_id=history.id,
    )
    db.commit()
    db.refresh(order)
    return order


@router.put("/clinical-history/{history_id}/study-orders/{order_id}", response_model=StudyOrderResponse)
def update_study_order(history_id: int, order_id: int, payload: StudyOrderInput, user: User = Depends(access), db: Session = Depends(get_db)):
    history = require_history_access(db, user, history_id, action="study_order.update", write=True)
    order = db.get(StudyOrder, order_id)
    if order is None or order.clinical_history_id != history.id:
        raise HTTPException(status_code=404, detail="Orden de estudios no encontrada")
    order.notes = payload.notes
    order.items.clear()
    db.flush()
    order.items = _study_items(db, history, payload)
    add_clinical_audit(db, user, action="study_order.update", resource_type="study_order", resource_id=order.id, history_id=history.id)
    db.commit()
    db.refresh(order)
    return order


def _laboratory_pdf_lines(order: LaboratoryOrder) -> list[str]:
    return [f"{item.test_name}{f' — {item.custom_note}' if item.custom_note else ''}" for item in order.items]


def _study_pdf_lines(order: StudyOrder) -> list[str]:
    contrast_labels = {"yes": "Sí", "no": "No", "not_applicable": "No aplica"}
    lines = []
    for item in order.items:
        parts = [item.study_name, f"Modalidad: {item.modality}"]
        if item.region_description:
            parts.append(f"Región/descripción: {item.region_description}")
        parts.append(f"Contraste: {contrast_labels[item.contrast]}")
        if item.clinical_notes:
            parts.append(f"Observaciones: {item.clinical_notes}")
        lines.append(" | ".join(parts))
    return lines


@router.get("/laboratory-orders/{order_id}/pdf")
def laboratory_order_pdf(order_id: int, user: User = Depends(access), db: Session = Depends(get_db)):
    order = db.get(LaboratoryOrder, order_id)
    if order is None:
        raise HTTPException(status_code=404, detail="Orden de laboratorio no encontrada")
    require_history_access(db, user, order.clinical_history_id, action="laboratory_order.pdf", resource_type="laboratory_order", resource_id=order.id, audit_read=True)
    content = build_laboratory_order_pdf(
        order_id=order.id, created_at=order.created_at, patient_name=order.patient_name,
        doctor_name=order.doctor_name, center_name=order.center_name, specialty_name=order.specialty_name,
        item_lines=_laboratory_pdf_lines(order), notes=order.notes,
    )
    return StreamingResponse(BytesIO(content), media_type="application/pdf", headers={"Content-Disposition": f'attachment; filename="orden-laboratorio-{order.id}.pdf"'})


@router.get("/study-orders/{order_id}/pdf")
def study_order_pdf(order_id: int, user: User = Depends(access), db: Session = Depends(get_db)):
    order = db.get(StudyOrder, order_id)
    if order is None:
        raise HTTPException(status_code=404, detail="Orden de estudios no encontrada")
    require_history_access(db, user, order.clinical_history_id, action="study_order.pdf", resource_type="study_order", resource_id=order.id, audit_read=True)
    content = build_study_order_pdf(
        order_id=order.id, created_at=order.created_at, patient_name=order.patient_name,
        doctor_name=order.doctor_name, center_name=order.center_name, specialty_name=order.specialty_name,
        item_lines=_study_pdf_lines(order), notes=order.notes,
    )
    return StreamingResponse(BytesIO(content), media_type="application/pdf", headers={"Content-Disposition": f'attachment; filename="orden-estudios-{order.id}.pdf"'})
