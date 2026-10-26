from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.services.user_preferences import ACCENT_THEMES, DASHBOARD_WIDGET_IDS, GESTION_MENU_IDS


class UserPreferencesPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    gestion_menu_order: list[str] = Field(max_length=32)
    dashboard_widget_order: list[str] = Field(max_length=64)
    accent_theme: str

    @field_validator("gestion_menu_order")
    @classmethod
    def valid_menu_order(cls, values: list[str]) -> list[str]:
        if len(values) != len(set(values)) or any(value not in GESTION_MENU_IDS for value in values):
            raise ValueError("El orden de Gestión contiene IDs duplicados o desconocidos")
        return values

    @field_validator("dashboard_widget_order")
    @classmethod
    def valid_widget_order(cls, values: list[str]) -> list[str]:
        if len(values) != len(set(values)) or any(value not in DASHBOARD_WIDGET_IDS for value in values):
            raise ValueError("El orden del Dashboard contiene IDs duplicados o desconocidos")
        return values

    @field_validator("accent_theme")
    @classmethod
    def valid_accent(cls, value: str) -> str:
        if value not in ACCENT_THEMES:
            raise ValueError("El tema de acento no está aprobado")
        return value


class UserPreferencesResponse(UserPreferencesPayload):
    pass
