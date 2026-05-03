from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator

from .config import DEFAULT_MINECRAFT_PORT
from .utils import sanitize_server_name, validate_port, validate_ram_mb


ServerStatus = Literal["stopped", "starting", "running", "stopping", "error"]


class ServerCreateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    version: str = "latest"
    ram_mb: int = 4096
    port: int = DEFAULT_MINECRAFT_PORT
    world_name: str = "world"
    gamemode: str = "survival"
    difficulty: str = "easy"
    online_mode: bool = True
    whitelist: bool = False
    command_blocks: bool = False
    max_players: int = 10
    motd: str = "A MineHost Helper server"
    pvp: bool = True
    spawn_protection: int = 16
    view_distance: int = 10
    simulation_distance: int = 10
    allow_flight: bool = False
    accepted_eula: bool = False

    @field_validator("name")
    @classmethod
    def clean_name(cls, value: str) -> str:
        return sanitize_server_name(value)

    @field_validator("port")
    @classmethod
    def clean_port(cls, value: int) -> int:
        return validate_port(value)

    @field_validator("ram_mb")
    @classmethod
    def clean_ram(cls, value: int) -> int:
        return validate_ram_mb(value)

    @field_validator("max_players")
    @classmethod
    def clean_max_players(cls, value: int) -> int:
        if not 1 <= value <= 200:
            raise ValueError("Max players must be between 1 and 200")
        return value


class ServerAdoptRequest(BaseModel):
    path: str = Field(min_length=3, max_length=1000)
    name: str | None = Field(default=None, max_length=80)
    ram_mb: int = 4096

    @field_validator("name")
    @classmethod
    def clean_name(cls, value: str | None) -> str | None:
        return sanitize_server_name(value) if value else value

    @field_validator("ram_mb")
    @classmethod
    def clean_ram(cls, value: int) -> int:
        return validate_ram_mb(value)


class ServerInfo(BaseModel):
    id: str
    name: str
    version: str
    ram_mb: int
    port: int
    path: str
    status: ServerStatus = "stopped"
    created_at: str
    updated_at: str
    last_error: str | None = None


class CommandRequest(BaseModel):
    command: str = Field(min_length=1, max_length=500)


class PropertiesUpdateRequest(BaseModel):
    properties: dict[str, Any]


class VersionChangeRequest(BaseModel):
    version: str = Field(min_length=1, max_length=40)


class PlayerActionRequest(BaseModel):
    player: str = Field(min_length=1, max_length=32)
    reason: str | None = Field(default=None, max_length=160)

    @field_validator("player")
    @classmethod
    def clean_player(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned.replace("_", "").isalnum():
            raise ValueError("Player names can contain letters, numbers, and underscores only")
        return cleaned


class FileWriteRequest(BaseModel):
    content: str = Field(max_length=1_000_000)


class BackupScheduleUpdateRequest(BaseModel):
    enabled: bool = False
    interval_hours: int = 24
    retention_count: int = 10

    @field_validator("interval_hours")
    @classmethod
    def clean_interval(cls, value: int) -> int:
        if not 1 <= value <= 168:
            raise ValueError("Backup interval must be between 1 hour and 7 days")
        return value

    @field_validator("retention_count")
    @classmethod
    def clean_retention(cls, value: int) -> int:
        if not 1 <= value <= 100:
            raise ValueError("Retention count must be between 1 and 100")
        return value


class AppSettingsUpdateRequest(BaseModel):
    close_to_tray: bool | None = None
    auto_open_browser: bool | None = None
    start_on_boot: bool | None = None
    auto_start_server_ids: list[str] | None = None


class BackupInfo(BaseModel):
    name: str
    path: str
    size_bytes: int
    created_at: str


class FirewallFixRequest(BaseModel):
    port: int

    @field_validator("port")
    @classmethod
    def clean_port(cls, value: int) -> int:
        return validate_port(value)
