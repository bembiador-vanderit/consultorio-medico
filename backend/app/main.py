from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.api.routes import auth, health, users
from app.core.config import get_settings
from app.db import Base, engine
from app import models

@asynccontextmanager
async def lifespan(_: FastAPI):
    Base.metadata.create_all(bind=engine)
    yield

settings = get_settings()
app = FastAPI(title=settings.app_name, version="0.1.0", description="API para la gestión segura de consultorios médicos.", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=["http://localhost:5173"], allow_credentials=True, allow_methods=["*"], allow_headers=["*"])
app.include_router(health.router, prefix="/api/v1")
app.include_router(auth.router, prefix="/api/v1")
app.include_router(users.router, prefix="/api/v1")

@app.get("/", tags=["Sistema"])
def root() -> dict[str, str]: return {"message": "API de Consultorio Médico disponible"}
