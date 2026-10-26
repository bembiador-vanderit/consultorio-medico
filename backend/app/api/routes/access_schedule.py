from datetime import timedelta
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import require_permission
from app.db import get_db
from app.models import AccessBlockedDate, AccessException, OrganizationMembership, User
from app.schemas.access_schedule import BlockedDateCreate, ExceptionCreate, ScheduleUpdate, TimezoneUpdate
from app.services.access_schedule import access_state, as_utc, exception_instant, utcnow
from app.services.administration import audit

router = APIRouter(prefix="/administration/access-schedules", tags=["Horarios de acceso"])
manage = require_permission("users:manage")


def membership(db, user_id):
    if db.info.get("access_scope") != "tenant":
        raise HTTPException(404, "Recurso no disponible")
    member = db.scalar(select(OrganizationMembership).where(OrganizationMembership.user_id == user_id))
    if member is None:
        raise HTTPException(404, "Usuario no disponible")
    return member


def snapshot(db, member):
    exceptions = db.scalars(select(AccessException).where(AccessException.membership_id == member.id,
        AccessException.ends_at > utcnow().replace(tzinfo=None)).order_by(AccessException.starts_at)).all()
    blocks = db.scalars(select(AccessBlockedDate).where(AccessBlockedDate.membership_id == member.id,
        AccessBlockedDate.day >= utcnow().astimezone(ZoneInfo(member.organization.timezone)).date()).order_by(AccessBlockedDate.day)).all()
    return {"user_id": member.user_id, "restrict_outside_schedule": member.restrict_outside_schedule,
            "weekly_schedule": member.weekly_schedule, **access_state(db, member),
            "exceptions": [{"id": row.id, "starts_at": as_utc(row.starts_at), "ends_at": as_utc(row.ends_at),
                            "reason": row.reason, "authorized_by": row.authorized_by} for row in exceptions],
            "blocked_dates": [{"id": row.id, "day": row.day, "reason": row.reason, "authorized_by": row.authorized_by} for row in blocks]}


@router.put("/timezone")
def set_timezone(payload: TimezoneUpdate, actor: User = Depends(manage), db: Session = Depends(get_db)):
    member = membership(db, actor.id)
    org = member.organization
    org.timezone = payload.timezone
    for item in db.scalars(select(OrganizationMembership)):
        item.schedule_version += 1
    audit(db, actor, f"schedule.timezone:{payload.timezone}")
    db.commit()
    return {"timezone": org.timezone}


@router.get("/{user_id}")
def get_schedule(user_id: int, actor: User = Depends(manage), db: Session = Depends(get_db)):
    return snapshot(db, membership(db, user_id))


@router.put("/{user_id}")
def put_schedule(user_id: int, payload: ScheduleUpdate, actor: User = Depends(manage), db: Session = Depends(get_db)):
    member = membership(db, user_id)
    member.weekly_schedule = [window.model_dump() for window in payload.weekly_schedule]
    member.restrict_outside_schedule = payload.restrict_outside_schedule
    member.schedule_version += 1
    audit(db, actor, f"schedule.updated:membership:{member.id}:restricted:{payload.restrict_outside_schedule}")
    db.commit()
    return snapshot(db, member)


@router.post("/{user_id}/exceptions", status_code=201)
def add_exception(user_id: int, payload: ExceptionCreate, actor: User = Depends(manage), db: Session = Depends(get_db)):
    member = membership(db, user_id)
    zone = ZoneInfo(member.organization.timezone)
    start, end = exception_instant(payload.starts_at, zone), exception_instant(payload.ends_at, zone)
    if end <= start or end - start > timedelta(days=31) or start > utcnow() + timedelta(days=366) or end <= utcnow():
        raise HTTPException(422, "Indique un período futuro válido de hasta 31 días, con inicio dentro del próximo año")
    row = AccessException(membership_id=member.id, starts_at=start.replace(tzinfo=None), ends_at=end.replace(tzinfo=None), reason=payload.reason, authorized_by=actor.id)
    db.add(row)
    member.schedule_version += 1
    db.flush()
    audit(db, actor, f"schedule.exception.created:{row.id}:membership:{member.id}")
    db.commit()
    return snapshot(db, member)


@router.post("/{user_id}/blocked-dates", status_code=201)
def add_block(user_id: int, payload: BlockedDateCreate, actor: User = Depends(manage), db: Session = Depends(get_db)):
    member = membership(db, user_id)
    if db.scalar(select(AccessBlockedDate.id).where(AccessBlockedDate.membership_id == member.id, AccessBlockedDate.day == payload.day)):
        raise HTTPException(409, "Esta fecha ya está bloqueada")
    row = AccessBlockedDate(membership_id=member.id, day=payload.day, reason=payload.reason, authorized_by=actor.id)
    db.add(row)
    member.schedule_version += 1
    db.flush()
    audit(db, actor, f"schedule.block.created:{row.id}:membership:{member.id}")
    db.commit()
    return snapshot(db, member)


def remove_entry(db, actor, user_id, entry_id, model, kind):
    member = membership(db, user_id)
    row = db.scalar(select(model).where(model.id == entry_id, model.membership_id == member.id))
    if row is None:
        raise HTTPException(404, "Registro no disponible")
    db.delete(row)
    member.schedule_version += 1
    audit(db, actor, f"schedule.{kind}.removed:{entry_id}:membership:{member.id}")
    db.commit()
    return snapshot(db, member)


@router.delete("/{user_id}/exceptions/{entry_id}")
def remove_exception(user_id: int, entry_id: int, actor: User = Depends(manage), db: Session = Depends(get_db)):
    return remove_entry(db, actor, user_id, entry_id, AccessException, "exception")


@router.delete("/{user_id}/blocked-dates/{entry_id}")
def remove_block(user_id: int, entry_id: int, actor: User = Depends(manage), db: Session = Depends(get_db)):
    return remove_entry(db, actor, user_id, entry_id, AccessBlockedDate, "block")
