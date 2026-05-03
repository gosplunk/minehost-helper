from __future__ import annotations

import threading
import time
from datetime import datetime, timedelta, timezone
from typing import Any

from .storage import backup_settings_store

DEFAULT_SETTINGS = {
    "enabled": False,
    "interval_hours": 24,
    "retention_count": 10,
    "last_run_at": None,
    "next_run_at": None,
}


def get_schedule(server_id: str) -> dict[str, Any]:
    all_settings = backup_settings_store.read({})
    return {**DEFAULT_SETTINGS, **all_settings.get(server_id, {})}


def update_schedule(server_id: str, settings: dict[str, Any]) -> dict[str, Any]:
    all_settings = backup_settings_store.read({})
    current = {**DEFAULT_SETTINGS, **all_settings.get(server_id, {})}
    current.update({
        "enabled": bool(settings.get("enabled", False)),
        "interval_hours": int(settings.get("interval_hours", 24)),
        "retention_count": int(settings.get("retention_count", 10)),
    })
    if current["enabled"] and not current.get("next_run_at"):
        current["next_run_at"] = (datetime.now(timezone.utc) + timedelta(hours=current["interval_hours"])).isoformat()
    if not current["enabled"]:
        current["next_run_at"] = None
    all_settings[server_id] = current
    backup_settings_store.write(all_settings)
    return current


def _write_schedule(server_id: str, settings: dict[str, Any]) -> None:
    all_settings = backup_settings_store.read({})
    all_settings[server_id] = settings
    backup_settings_store.write(all_settings)


def _parse_time(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return None


def _trim_backups(server_manager: Any, server_id: str, retention_count: int) -> None:
    backups = server_manager.list_backups(server_id)
    for backup in backups[retention_count:]:
        try:
            server_manager.delete_backup(server_id, backup["name"])
        except Exception:
            pass


def run_scheduler(server_manager: Any, stop_event: threading.Event) -> None:
    while not stop_event.wait(60):
        now = datetime.now(timezone.utc)
        for server in server_manager.list_servers():
            server_id = server["id"]
            settings = get_schedule(server_id)
            if not settings.get("enabled"):
                continue
            next_run = _parse_time(settings.get("next_run_at")) or now
            if next_run > now:
                continue
            if server.get("status") in ("starting", "running", "stopping"):
                settings["next_run_at"] = (now + timedelta(minutes=15)).isoformat()
                _write_schedule(server_id, settings)
                continue
            try:
                server_manager.create_backup(server_id)
                _trim_backups(server_manager, server_id, int(settings.get("retention_count", 10)))
                settings["last_run_at"] = now.isoformat()
                settings["next_run_at"] = (now + timedelta(hours=int(settings.get("interval_hours", 24)))).isoformat()
                _write_schedule(server_id, settings)
            except Exception:
                settings["next_run_at"] = (now + timedelta(hours=1)).isoformat()
                _write_schedule(server_id, settings)
