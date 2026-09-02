import asyncio
from contextlib import asynccontextmanager, suppress

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes import appointments, auth, centers, clinical_catalog, clinical_history, communications, diagnoses, doctor_availability, follow_ups, health, insurance, localities, patients, prescriptions, reports, report_communications, users
from app.core.config import get_settings
from app.db import SessionLocal
from app.services.bootstrap import seed_identity
from app.services.reminders import sync_appointment_reminders


async def _reminder_worker(stop_event: asyncio.Event) -> None:
    """Run appointment reminder synchronization periodically.

    The operation is idempotent, so multiple application instances can safely
    run it without creating duplicate in-app notifications.
    """
    while not stop_event.is_set():
        try:
            with SessionLocal() as session:
                sync_appointment_reminders(session)
        except Exception:
            # Reminder failures must not take down the API process. The next
            # scheduled cycle will retry the synchronization.
            pass
        try:
            await asyncio.wait_for(stop_event.wait(), timeout=300)
        except asyncio.TimeoutError:
            continue


@asynccontextmanager
async def lifespan(_: FastAPI):
    with SessionLocal() as session:
        seed_identity(session)

    stop_event = asyncio.Event()
    worker = asyncio.create_task(_reminder_worker(stop_event))
    try:
        yield
    finally:
        stop_event.set()
        worker.cancel()
        with suppress(asyncio.CancelledError):
            await worker


settings = get_settings()
app = FastAPI(title=settings.app_name, version="0.9.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"]
)

for router in (health.router, auth.router, users.router, localities.router, centers.router, patients.router, insurance.router, clinical_history.router, diagnoses.router, prescriptions.router, appointments.router, doctor_availability.router, follow_ups.router, communications.router, clinical_catalog.router, reports.router, report_communications.router):
    app.include_router(router, prefix="/api/v1")
