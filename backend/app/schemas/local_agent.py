from typing import Literal
from uuid import UUID
from pydantic import BaseModel, ConfigDict, Field, field_validator


class StrictInput(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class WorkgroupCreate(StrictInput):
    center_id: int = Field(gt=0)
    name: str = Field(min_length=1, max_length=100)


class PairingCodeCreate(StrictInput):
    workgroup_id: int = Field(gt=0)


class StationInfo(StrictInput):
    agent_uuid: UUID
    display_code: str = Field(pattern=r"^[A-Z0-9][A-Z0-9-]{1,31}$")
    station_name: str = Field(min_length=1, max_length=100)
    version: str = Field(min_length=1, max_length=40)
    protocol_version: int = Field(ge=3, le=3)
    fingerprint: str = Field(pattern=r"^[a-f0-9]{64}$")

    @field_validator("agent_uuid")
    @classmethod
    def nonzero_uuid(cls, value):
        if not value.int:
            raise ValueError("Identidad vacía no permitida")
        return value

    @field_validator("station_name", "version")
    @classmethod
    def no_controls(cls, value):
        if any(ord(c) < 32 or ord(c) == 127 for c in value):
            raise ValueError("Caracteres de control no permitidos")
        return value


class PairRequest(StationInfo):
    code: str = Field(pattern=r"^[A-Z2-7-]{26,40}$", repr=False)


class DeviceSummary(StrictInput):
    printers: int = Field(default=0, ge=0, le=100)
    default_printers: int = Field(default=0, ge=0, le=100)


class Heartbeat(StationInfo):
    health: Literal["online", "degraded"] = "online"
    device_summary: DeviceSummary = Field(default_factory=DeviceSummary)


class PaperReport(StrictInput):
    name: str = Field(min_length=1, max_length=100)
    width_tenths_millimeter: int | None = Field(default=None, ge=1, le=100000)
    height_tenths_millimeter: int | None = Field(default=None, ge=1, le=100000)
    raw_kind: int | None = Field(default=None, ge=0, le=65535)


class PrinterReport(StrictInput):
    local_id: str = Field(pattern=r"^printer-[A-Fa-f0-9]{64}$")
    display_name: str = Field(min_length=1, max_length=200)
    driver: str | None = Field(default=None, max_length=200)
    is_default: bool
    connection: Literal["Local", "Network", "Unknown"]
    is_virtual: bool
    status: str = Field(min_length=1, max_length=80)
    papers: list[PaperReport] = Field(default_factory=list, max_length=512)

    @field_validator("local_id")
    @classmethod
    def canonical_local_id(cls, value):
        return "printer-" + value[8:].upper()

    @field_validator("papers")
    @classmethod
    def bounded_papers(cls, value):
        import json
        if len(json.dumps([item.model_dump() for item in value])) > 65536:
            raise ValueError("Capacidades demasiado grandes")
        return value


class PrinterSync(StrictInput):
    printers: list[PrinterReport] = Field(max_length=100)


class RegistryChange(StrictInput):
    station_name: str = Field(min_length=1, max_length=100)
    workgroup_id: int = Field(gt=0)
    reason: str = Field(min_length=5, max_length=300)


class Reason(StrictInput):
    reason: str = Field(min_length=5, max_length=300)


class ScopeChange(Reason):
    target_id: int = Field(gt=0)
    allowed: bool
