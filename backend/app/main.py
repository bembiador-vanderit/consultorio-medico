from app.api.routes import finance
import asyncio
from contextlib import asynccontextmanager, suppress

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes import administration, appointments, auth, centers, clinical_addenda, clinical_catalog, clinical_coverages, clinical_history, clinical_orders, communications, diagnoses, doctor_availability, follow_ups, health, insurance, localities, patients, prescriptions, regional, reports, report_communications, users, vital_signs
from app.core.config import get_settings
from app.db import SessionLocal
from app.services.bootstrap import seed_identity
from app.services.tenancy import bind_scope
from app.models import Organization
from sqlalchemy import select
from app.api.routes import organizations
from app.api.routes import access_schedule
from app.services.reminders import sync_appointment_reminders


async def _reminder_worker(stop_event: asyncio.Event) -> None:
    """Run appointment reminder synchronization periodically.

    The operation is idempotent, so multiple application instances can safely
    run it without creating duplicate in-app notifications.
    """
    while not stop_event.is_set():
        try:
            with SessionLocal() as directory:
                organization_ids = list(directory.scalars(select(Organization.id).where(Organization.is_active.is_(True))))
            for organization_id in organization_ids:
                with SessionLocal() as session:
                    bind_scope(session, "tenant", organization_id)
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
app.include_router(access_schedule.router, prefix="/api/v1")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["X-Access-Schedule"],
)

for router in (finance.router, organizations.router, administration.router, health.router, auth.router, users.router, localities.router, centers.router, regional.router, patients.router, insurance.router, clinical_history.router, clinical_addenda.router, clinical_orders.router, diagnoses.router, prescriptions.router, vital_signs.router, appointments.router, clinical_coverages.router, doctor_availability.router, follow_ups.router, communications.router, clinical_catalog.router, reports.router, report_communications.router):
    app.include_router(router, prefix="/api/v1")
