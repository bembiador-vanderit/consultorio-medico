"""Organization-local schedules; UTC half-open intervals and non-renewable shift leases."""
from datetime import datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

from fastapi import HTTPException
from sqlalchemy import select, update

from app.models import AccessBlockedDate, AccessException, OrganizationMembership
from app.services.administration import audit

UTC = timezone.utc


def utcnow():
    return datetime.now(UTC)


def as_utc(value):
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


def local_candidates(value, zone):
    candidates = {value.replace(tzinfo=zone, fold=fold).astimezone(UTC) for fold in (0, 1)}
    return sorted(item for item in candidates if item.astimezone(zone).replace(tzinfo=None) == value)


def exception_instant(value, zone):
    if value.tzinfo is not None:
        return value.astimezone(UTC)
    candidates = local_candidates(value, zone)
    if len(candidates) != 1:
        raise HTTPException(422, "La hora no existe o es ambigua en esta zona; indique una fecha con desplazamiento UTC explícito")
    return candidates[0]


def boundary(day, clock, zone, opening):
    value = datetime.combine(day, time()) + timedelta(minutes=int(clock[:2]) * 60 + int(clock[3:]))
    candidates = local_candidates(value, zone)
    # Fail closed for nonexistent wall times; repeated hours use the narrower interval.
    return (candidates[-1] if opening else candidates[0]) if candidates else None


def access_state(db, member, now=None):
    now = now or utcnow()
    zone = ZoneInfo(member.organization.timezone)
    result = {"restricted": member.restrict_outside_schedule, "timezone": zone.key,
              "allowed": True, "current_until": None, "next_window": None}
    if not member.restrict_outside_schedule:
        return result
    first_day = now.astimezone(zone).date()
    horizon = first_day + timedelta(days=370)
    blocks = set(db.scalars(select(AccessBlockedDate.day).where(
        AccessBlockedDate.membership_id == member.id,
        AccessBlockedDate.day >= first_day, AccessBlockedDate.day <= horizon)))
    exceptions = db.scalars(select(AccessException).where(
        AccessException.membership_id == member.id, AccessException.ends_at > now.replace(tzinfo=None),
        AccessException.starts_at < datetime.combine(horizon, time()))).all()
    intervals = []
    for offset in range(370):
        day = first_day + timedelta(days=offset)
        if day in blocks:
            continue
        day_start = boundary(day, "00:00", zone, True)
        day_end = boundary(day, "24:00", zone, False)
        if day_start is None or day_end is None:
            continue
        for window in member.weekly_schedule or []:
            if window["day"] != day.weekday():
                continue
            start = boundary(day, window["start"], zone, True)
            end = boundary(day, window["end"], zone, False)
            if start is not None and end is not None and start < end and end > now:
                intervals.append((start, end))
        for exception in exceptions:
            start, end = max(day_start, as_utc(exception.starts_at)), min(day_end, as_utc(exception.ends_at))
            if start < end and end > now:
                intervals.append((start, end))
    merged = []
    for start, end in sorted(intervals):
        if merged and start <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(end, merged[-1][1]))
        else:
            merged.append((start, end))
    result["allowed"] = False
    for start, end in merged:
        if start <= now < end:
            result.update(allowed=True, current_until=end)
            break
        if start > now:
            result["next_window"] = {"starts_at": start, "ends_at": end}
            break
    return result


def deny(db, user, member, state, *, expired=False):
    now = utcnow().replace(tzinfo=None)
    # Atomic throttle across processes: one relevant denial per membership / 5 minutes.
    written = db.execute(update(OrganizationMembership).where(
        OrganizationMembership.id == member.id,
        (OrganizationMembership.schedule_denied_at.is_(None)) |
        (OrganizationMembership.schedule_denied_at < now - timedelta(minutes=5)),
    ).values(schedule_denied_at=now))
    if written.rowcount:
        audit(db, user, f"schedule.denied:membership:{member.id}", "denied")
    db.commit()
    message = "Su jornada terminó o su autorización cambió. Vuelva a iniciar sesión." if expired else "No tiene acceso fuera de su horario autorizado."
    window = state["next_window"]
    if window:
        zone = ZoneInfo(state["timezone"])
        message += f" Próximo acceso: {window['starts_at'].astimezone(zone):%d/%m/%Y %H:%M} a {window['ends_at'].astimezone(zone):%d/%m/%Y %H:%M} ({zone.key})."
    elif not state["allowed"]:
        message += " No hay una ventana prevista en los próximos 370 días; contacte a su administrador."
    raise HTTPException(403, message, headers={"X-Access-Schedule": "denied"})


def enforce_schedule(db, user, payload=None):
    member = user.tenant_membership()
    if member is None:
        return {}
    state = access_state(db, member)
    if not state["allowed"]:
        deny(db, user, member, state)
    if payload is not None:
        deadline = payload.get("schedule_until")
        expired = (payload.get("schedule_version", 0) != member.schedule_version or
                   (member.restrict_outside_schedule and
                    (not isinstance(deadline, (int, float)) or utcnow().timestamp() >= deadline)))
        if expired:
            deny(db, user, member, state, expired=True)
    claims = {"schedule_version": member.schedule_version}
    if state["current_until"]:
        limit = state["current_until"].timestamp()
        claims["schedule_until"] = min(limit, payload["schedule_until"]) if payload else limit
    return claims
