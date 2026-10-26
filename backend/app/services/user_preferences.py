"""Stable presentation IDs only; effective access remains governed by permissions."""

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.user_preference import UserPreference

GESTION_MENU_IDS = ("dashboard", "appointments", "reports", "patients", "finance")
DASHBOARD_WIDGET_IDS = (
    "users", "centers", "new-appointment", "patients", "agenda", "reports", "follow-ups", "availability", "coverages",
    "metric-appointments", "metric-patients", "metric-notifications", "metric-follow-ups", "metric-users", "metric-centers",
    "agenda-today", "notifications-panel",
)
ACCENT_THEMES = ("classic", "blue", "turquoise", "clinical-green", "indigo", "violet")


def defaults() -> dict:
    return {
        "gestion_menu_order": list(GESTION_MENU_IDS),
        "dashboard_widget_order": list(DASHBOARD_WIDGET_IDS),
        "accent_theme": "classic",
    }


def get_preferences(db: Session, user_id: int) -> dict:
    row = db.scalar(select(UserPreference).where(UserPreference.user_id == user_id))
    if row is None:
        return defaults()
    return {
        "gestion_menu_order": row.gestion_menu_order,
        "dashboard_widget_order": row.dashboard_widget_order,
        "accent_theme": row.accent_theme,
    }


def put_preferences(db: Session, user_id: int, values: dict) -> dict:
    from datetime import datetime, timezone

    row = db.scalar(select(UserPreference).where(UserPreference.user_id == user_id))
    if row is None:
        row = UserPreference(user_id=user_id, **values)
        db.add(row)
    elif any(getattr(row, key) != value for key, value in values.items()):
        for key, value in values.items():
            setattr(row, key, value)
        row.updated_at = datetime.now(timezone.utc)
    db.commit()
    return values
