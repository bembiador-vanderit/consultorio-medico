from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import current_user
from app.db import get_db
from app.models import Organization, User

router = APIRouter(tags=["Contexto de acceso"])


@router.get("/platform/organizations")
def organizations(actor: User = Depends(current_user), db: Session = Depends(get_db)):
    if db.info.get("access_scope") != "platform" or not actor.is_platform_admin:
        raise HTTPException(404, "Recurso no disponible")
    return [{"id": row.id, "name": row.name, "slug": row.slug, "is_active": row.is_active}
            for row in db.scalars(select(Organization).order_by(Organization.id).limit(100))]


@router.get("/organization")
def organization(actor: User = Depends(current_user), db: Session = Depends(get_db)):
    member = actor.tenant_membership()
    if member is None:
        raise HTTPException(404, "Recurso no disponible")
    return {"id": member.organization.id, "name": member.organization.name,
            "membership_state": member.state, "roles": [role.code for role in member.roles]}
