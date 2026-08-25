from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes import appointments, auth, centers, clinical_history, health, insurance, patients, users
from app.core.config import get_settings
from app.db import SessionLocal
from app.services.bootstrap import seed_identity

@asynccontextmanager
async def lifespan(_: FastAPI):
    with SessionLocal() as session:
        seed_identity(session)
    yield

settings = get_settings()
app = FastAPI(title=settings.app_name, version="0.6.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

for router in (health.router, auth.router, users.router, centers.router, patients.router, insurance.router, clinical_history.router, appointments.router):
    app.include_router(router, prefix="/api/v1")
