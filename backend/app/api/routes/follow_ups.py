from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import current_user, require_permission
from app.db import get_db
from app.models import FollowUp, Notification, User
from app.schemas.follow_up import FollowUpCreate, FollowUpRead, NotificationRead

router = APIRouter(prefix="/follow-ups", tags=["follow-ups"])


def _doctor_for_request(payload: FollowUpCreate, user: User) -> int:
    if payload.doctor_id is not None:
        if user.id != payload.doctor_id and not any(role.code == "admin" for role in user.roles):
            raise HTTPException(status_code=403, detail="No puede crear seguimientos para otro médico")
        return payload.doctor_id
    if any(role.code == "doctor" for role in user.roles):
        return user.id
    raise HTTPException(status_code=400, detail="Debe indicar el médico responsable")


@router.get("", response_model=list[FollowUpRead])
def list_follow_ups(db: Session = Depends(get_db), user: User = Depends(current_user)):
    stmt = select(FollowUp).order_by(FollowUp.due_at.asc())
    if not any(role.code == "admin" for role in user.roles):
        stmt = stmt.where(FollowUp.doctor_id == user.id)
    return list(db.scalars(stmt).all())


@router.post("", response_model=FollowUpRead, status_code=201)
def create_follow_up(payload: FollowUpCreate, db: Session = Depends(get_db), user: User = Depends(current_user)):
    doctor_id = _doctor_for_request(payload, user)
    follow_up = FollowUp(**payload.model_dump(exclude={"doctor_id"}), doctor_id=doctor_id)
    db.add(follow_up)
    db.flush()
    db.add(Notification(
        user_id=doctor_id,
        follow_up_id=follow_up.id,
        title="Nuevo seguimiento programado",
        message=f"{payload.reason} — programado para {payload.due_at:%d/%m/%Y %H:%M}",
        notification_type="follow_up",
    ))
    db.commit()
    db.refresh(follow_up)
    return follow_up


@router.post("/{follow_up_id}/complete", response_model=FollowUpRead)
def complete_follow_up(follow_up_id: int, db: Session = Depends(get_db), user: User = Depends(current_user)):
    follow_up = db.get(FollowUp, follow_up_id)
    if not follow_up:
        raise HTTPException(status_code=404, detail="Seguimiento no encontrado")
    if follow_up.doctor_id != user.id and not any(role.code == "admin" for role in user.roles):
        raise HTTPException(status_code=403, detail="No puede modificar este seguimiento")
    follow_up.status = "completed"
    follow_up.completed_at = datetime.utcnow()
    db.commit()
    db.refresh(follow_up)
    return follow_up


@router.get("/notifications", response_model=list[NotificationRead])
def list_notifications(db: Session = Depends(get_db), user: User = Depends(current_user)):
    stmt = select(Notification).where(Notification.user_id == user.id).order_by(Notification.created_at.desc())
    return list(db.scalars(stmt).all())


@router.post("/notifications/{notification_id}/read", response_model=NotificationRead)
def mark_notification_read(notification_id: int, db: Session = Depends(get_db), user: User = Depends(current_user)):
    notification = db.get(Notification, notification_id)
    if not notification or notification.user_id != user.id:
        raise HTTPException(status_code=404, detail="Notificación no encontrada")
    notification.is_read = True
    notification.read_at = datetime.utcnow()
    db.commit()
    db.refresh(notification)
    return notification
