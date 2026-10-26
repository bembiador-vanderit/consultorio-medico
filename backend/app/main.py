from app.api.routes import finance, ars
import asyncio
import logging
from contextlib import asynccontextmanager, suppress

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes import administration, agenda_schedule, appointment_contacts, appointments, auth, centers, clinical_addenda, clinical_catalog, clinical_coverages, clinical_forms, clinical_history, clinical_orders, clinical_patient_documents, communications, diagnoses, doctor_availability, follow_ups, health, insurance, localities, patients, prescriptions, provider_pauses, queue, queue_displays, regional, reports, report_communications, users, vital_signs, waiting_rooms
from app.core.config import get_settings
from app.db import SessionLocal
from app.services.bootstrap import seed_identity
from app.services.tenancy import bind_scope
from app.models import Organization
from sqlalchemy import select
from app.api.routes import organizations, patient_safety, patient_care
from app.api.routes import clinical_sharing
from app.api.routes import cardiology, clinical_follow_up
from app.api.routes import feature_visibility
from app.api.routes import access_schedule
from app.api.routes import document_designer
from app.api.routes import local_agents
from app.api.routes import user_preferences
from app.services.reminders import sync_appointment_reminders
from app.services.queue_call import auto_call_due_lines

logger = logging.getLogger(__name__)


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


async def _auto_call_worker(stop_event: asyncio.Event) -> None:
    """Poll persisted readiness; safe with multiple API workers and restarts."""
    while not stop_event.is_set():
        try:
            with SessionLocal() as directory:
                organization_ids = list(directory.scalars(select(Organization.id).where(Organization.is_active.is_(True))))
            for organization_id in organization_ids:
                with SessionLocal() as session:
                    bind_scope(session, "tenant", organization_id)
                    auto_call_due_lines(session)
        except Exception:
            # Never print patient data or connection strings; retry on the next cycle.
            logger.warning("Automatic queue-call evaluation failed; retrying")
        try:
            await asyncio.wait_for(stop_event.wait(), timeout=5)
        except asyncio.TimeoutError:
            continue


@asynccontextmanager
async def lifespan(_: FastAPI):
    with SessionLocal() as session:
        seed_identity(session)

    stop_event = asyncio.Event()
    worker = asyncio.create_task(_reminder_worker(stop_event))
    call_worker = asyncio.create_task(_auto_call_worker(stop_event))
    try:
        yield
    finally:
        stop_event.set()
        worker.cancel()
        call_worker.cancel()
        with suppress(asyncio.CancelledError):
            await worker
        with suppress(asyncio.CancelledError):
            await call_worker


settings = get_settings()
app = FastAPI(title=settings.app_name, version="0.9.0", lifespan=lifespan)
app.include_router(patient_safety.router, prefix="/api/v1")
app.include_router(patient_care.router, prefix="/api/v1")
app.include_router(clinical_sharing.router, prefix="/api/v1")
app.include_router(cardiology.router, prefix="/api/v1")
app.include_router(clinical_follow_up.router, prefix="/api/v1")
app.include_router(feature_visibility.router, prefix="/api/v1")
app.include_router(access_schedule.router, prefix="/api/v1")
app.include_router(document_designer.router, prefix="/api/v1")
app.include_router(local_agents.router, prefix="/api/v1")
app.include_router(user_preferences.router, prefix="/api/v1")
from app.api.routes import official_print_routing
app.include_router(official_print_routing.router, prefix="/api/v1")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["X-Access-Schedule"],
)

for router in (ars.router, finance.router, organizations.router, administration.router, agenda_schedule.router, health.router, auth.router, users.router, localities.router, centers.router, regional.router, patients.router, insurance.router, clinical_history.router, clinical_addenda.router, clinical_orders.router, clinical_patient_documents.router, clinical_forms.router, diagnoses.router, prescriptions.router, vital_signs.router, appointments.router, appointment_contacts.router, queue.router, queue_displays.router, waiting_rooms.router, provider_pauses.router, clinical_coverages.router, doctor_availability.router, follow_ups.router, communications.router, clinical_catalog.router, reports.router, report_communications.router):
    app.include_router(router, prefix="/api/v1")
