from fastapi import APIRouter

router = APIRouter(tags=["Sistema"])


@router.get("/health", summary="Estado del servicio")
def health_check() -> dict[str, str]:
    """Devuelve el estado básico de la API sin exponer datos sensibles."""
    return {"status": "ok", "service": "consultorio-medico-api"}
