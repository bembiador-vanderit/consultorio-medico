from fastapi import FastAPI

from app.api.routes.health import router as health_router
from app.core.config import get_settings

settings = get_settings()

app = FastAPI(
    title=settings.app_name,
    version="0.1.0",
    description="API para la gestión segura de consultorios médicos.",
)

app.include_router(health_router, prefix="/api/v1")


@app.get("/", tags=["Sistema"])
def root() -> dict[str, str]:
    return {"message": "API de Consultorio Médico disponible"}
