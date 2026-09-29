from functools import lru_cache
import json
from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    app_name: str = "Consultorio Médico API"
    environment: str = "development"
    database_url: str
    secret_key: str
    access_token_expire_minutes: int = 30
    tenant_hosts_json: str = ""
    platform_hosts_json: str = ""
    app_timezone: str = "America/Santo_Domingo"
    initial_admin_email: str | None = None
    initial_admin_password: str | None = None
    initial_admin_name: str = "Administrador inicial"
    smtp_host: str | None = None
    smtp_port: int = 587
    smtp_username: str | None = None
    smtp_password: str | None = None
    smtp_from: str | None = None
    smtp_use_tls: bool = True
    smtp_use_ssl: bool = False
    whatsapp_access_token: str | None = None
    whatsapp_phone_number_id: str | None = None
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    @property
    def tenant_hosts(self) -> dict[str, str]:
        hosts = json.loads(self.tenant_hosts_json) if self.tenant_hosts_json else {"localhost": "pilot", "127.0.0.1": "pilot"}
        if not isinstance(hosts, dict) or not all(isinstance(host, str) and isinstance(slug, str) for host, slug in hosts.items()):
            raise ValueError("TENANT_HOSTS_JSON must map hosts to organization slugs")
        return hosts

    @property
    def platform_hosts(self) -> list[str]:
        hosts = json.loads(self.platform_hosts_json) if self.platform_hosts_json else []
        if not isinstance(hosts, list) or not all(isinstance(host, str) for host in hosts):
            raise ValueError("PLATFORM_HOSTS_JSON must be a list of hosts")
        return hosts

@lru_cache
def get_settings() -> Settings:
    return Settings()
