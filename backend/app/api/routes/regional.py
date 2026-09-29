from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session
from app.api.deps import require_permission
from app.db import get_db
from app.models import Country, RegionalSettings, TerritorialLevel, TerritorialUnit, User
from app.schemas.regional import CountryResponse, RegionalSettingsResponse, RegionalSettingsUpdate, TerritorialLevelResponse, TerritorialUnitResponse
router = APIRouter(prefix="/regional", tags=["Configuración regional"])
access = require_permission("patients:access")
manage = require_permission("users:manage")

def _settings(db: Session) -> RegionalSettings:
    settings = db.scalar(select(RegionalSettings))
    if settings is None:
        raise HTTPException(status_code=503, detail="No hay configuración regional disponible")
    return settings

@router.get("/countries", response_model=list[CountryResponse])
def countries(_: User = Depends(access), db: Session = Depends(get_db)):
    return list(db.scalars(select(Country).where(Country.is_active.is_(True)).order_by(Country.name)).all())

@router.get("/countries/{country_code}/levels", response_model=list[TerritorialLevelResponse])
def levels(country_code: str, _: User = Depends(access), db: Session = Depends(get_db)):
    country = db.get(Country, country_code.upper())
    if country is None or not country.is_active:
        raise HTTPException(status_code=404, detail="País no disponible")
    return list(db.scalars(select(TerritorialLevel).where(TerritorialLevel.country_code == country.code, TerritorialLevel.is_active.is_(True)).order_by(TerritorialLevel.position)).all())

@router.get("/territories", response_model=list[TerritorialUnitResponse])
def territories(country_code: str, level: int = Query(gt=0), parent_id: int | None = None, _: User = Depends(access), db: Session = Depends(get_db)):
    country_code = country_code.upper()
    level_row = db.get(TerritorialLevel, level)
    if level_row is None or level_row.country_code != country_code or not level_row.is_active:
        raise HTTPException(status_code=422, detail="Nivel territorial inválido")
    if parent_id is not None:
        parent = db.get(TerritorialUnit, parent_id)
        if parent is None or parent.country_code != country_code or not parent.is_active or parent.level.position != level_row.position - 1:
            raise HTTPException(status_code=422, detail="Jerarquía territorial inválida")
    return list(db.scalars(select(TerritorialUnit).where(TerritorialUnit.country_code == country_code, TerritorialUnit.territorial_level_id == level_row.id, TerritorialUnit.parent_id == parent_id, TerritorialUnit.is_active.is_(True)).order_by(TerritorialUnit.name)).all())

@router.get("/settings", response_model=RegionalSettingsResponse)
def settings(_: User = Depends(access), db: Session = Depends(get_db)):
    item = _settings(db)
    return RegionalSettingsResponse(default_country_code=item.default_country_code, default_country_name=item.default_country.name)

@router.put("/settings", response_model=RegionalSettingsResponse)
def update_settings(payload: RegionalSettingsUpdate, _: User = Depends(manage), db: Session = Depends(get_db)):
    country = db.get(Country, payload.default_country_code.upper())
    if country is None or not country.is_active:
        raise HTTPException(status_code=422, detail="País principal inválido")
    item = _settings(db)
    item.default_country_code = country.code
    db.commit()
    db.refresh(item)
    return RegionalSettingsResponse(default_country_code=item.default_country_code, default_country_name=item.default_country.name)