from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Any

from .config import ROOT_DIR
from .storage import settings_store

RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
RUN_VALUE_NAME = "MineHost Helper"

DEFAULT_SETTINGS: dict[str, Any] = {
    "close_to_tray": True,
    "auto_open_browser": True,
    "start_on_boot": False,
    "auto_start_server_ids": [],
}


def _app_executable() -> Path:
    return Path(sys.executable if getattr(sys, "frozen", False) else ROOT_DIR / "Start MineHost Helper.bat").resolve()


def _startup_command() -> str:
    return f'"{_app_executable()}" --minimized'


def _read_startup_registry() -> bool:
    if os.name != "nt":
        return False
    try:
        import winreg

        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY) as key:
            value, _ = winreg.QueryValueEx(key, RUN_VALUE_NAME)
        return bool(value)
    except FileNotFoundError:
        return False
    except OSError:
        return False


def _write_startup_registry(enabled: bool) -> None:
    if os.name != "nt":
        return
    import winreg

    if enabled:
        with winreg.CreateKey(winreg.HKEY_CURRENT_USER, RUN_KEY) as key:
            winreg.SetValueEx(key, RUN_VALUE_NAME, 0, winreg.REG_SZ, _startup_command())
        return
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY, 0, winreg.KEY_SET_VALUE) as key:
            winreg.DeleteValue(key, RUN_VALUE_NAME)
    except FileNotFoundError:
        pass


def get_settings() -> dict[str, Any]:
    saved = settings_store.read({})
    settings = {**DEFAULT_SETTINGS, **saved}
    settings["auto_start_server_ids"] = [
        str(server_id) for server_id in settings.get("auto_start_server_ids", []) if server_id
    ]
    settings["start_on_boot"] = _read_startup_registry()
    settings["startup_command"] = _startup_command()
    return settings


def update_settings(data: dict[str, Any]) -> dict[str, Any]:
    current = get_settings()
    updated = dict(current)
    for key in ("close_to_tray", "auto_open_browser", "start_on_boot"):
        if key in data:
            updated[key] = bool(data[key])
    if "auto_start_server_ids" in data:
        updated["auto_start_server_ids"] = [
            str(server_id) for server_id in data.get("auto_start_server_ids", []) if server_id
        ]
    _write_startup_registry(bool(updated["start_on_boot"]))
    persisted = {key: updated[key] for key in DEFAULT_SETTINGS}
    settings_store.write(persisted)
    return get_settings()
