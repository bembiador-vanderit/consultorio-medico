from datetime import datetime
from zoneinfo import ZoneInfo

from app.core.config import get_settings
from app.models.clinical_coverage import ClinicalCoverage


def installation_now() -> datetime:
    """Return the installation wall clock used by naive clinical schedules."""
    return datetime.now(ZoneInfo(get_settings().app_timezone)).replace(tzinfo=None)


def coverage_status(coverage: ClinicalCoverage, now: datetime | None = None) -> str:
    current = now if now is not None else installation_now()
    if coverage.revoked_at is not None:
        return "revoked"
    if current < coverage.starts_at:
        return "future"
    if current >= coverage.ends_at:
        return "expired"
    return "active"


def appointment_is_within_coverage(coverage: ClinicalCoverage, appointment_at: datetime) -> bool:
    return coverage.starts_at <= appointment_at < coverage.ends_at


def coverage_allows_appointment_transfer(
    coverage: ClinicalCoverage,
    appointment_at: datetime,
    now: datetime | None = None,
) -> bool:
    """Allow advance planning while rejecting revoked or already expired grants."""
    return (
        coverage_status(coverage, now) in {"future", "active"}
        and appointment_is_within_coverage(coverage, appointment_at)
    )
