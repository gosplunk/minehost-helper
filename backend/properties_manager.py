from __future__ import annotations

import shutil
from datetime import datetime
from pathlib import Path
from typing import Any

from .utils import validate_port


BOOLEAN_KEYS = {
    "allow-flight",
    "allow-nether",
    "enable-command-block",
    "enable-query",
    "enable-rcon",
    "enforce-secure-profile",
    "force-gamemode",
    "hardcore",
    "online-mode",
    "pvp",
    "spawn-animals",
    "spawn-monsters",
    "spawn-npcs",
    "white-list",
}

INTEGER_KEYS = {
    "max-players",
    "server-port",
    "spawn-protection",
    "view-distance",
    "simulation-distance",
    "max-world-size",
    "op-permission-level",
    "player-idle-timeout",
    "query.port",
    "rcon.port",
}

DEFAULT_PROPERTIES: dict[str, Any] = {
    "allow-flight": False,
    "allow-nether": True,
    "difficulty": "easy",
    "enable-command-block": False,
    "enable-query": False,
    "enable-rcon": False,
    "gamemode": "survival",
    "hardcore": False,
    "level-name": "world",
    "max-players": 10,
    "motd": "A MineHost Helper server",
    "online-mode": True,
    "pvp": True,
    "server-ip": "",
    "server-port": 25565,
    "simulation-distance": 10,
    "spawn-protection": 16,
    "view-distance": 10,
    "white-list": False,
}


def _coerce_value(key: str, value: str) -> Any:
    if key in BOOLEAN_KEYS:
        return value.strip().lower() == "true"
    if key in INTEGER_KEYS:
        try:
            return int(value)
        except ValueError:
            return value
    return value


def _serialize_value(value: Any) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    return str(value)


def read_properties(server_dir: Path) -> dict[str, Any]:
    path = server_dir / "server.properties"
    if not path.exists():
        return dict(DEFAULT_PROPERTIES)
    result: dict[str, Any] = {}
    for raw_line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        result[key.strip()] = _coerce_value(key.strip(), value.strip())
    return {**DEFAULT_PROPERTIES, **result}


def validate_properties(properties: dict[str, Any]) -> dict[str, Any]:
    cleaned = dict(properties)
    if "server-port" in cleaned:
        cleaned["server-port"] = validate_port(int(cleaned["server-port"]))
    for key in INTEGER_KEYS:
        if key in cleaned and cleaned[key] != "":
            cleaned[key] = int(cleaned[key])
    for key in BOOLEAN_KEYS:
        if key in cleaned:
            value = cleaned[key]
            if isinstance(value, str):
                cleaned[key] = value.strip().lower() == "true"
            else:
                cleaned[key] = bool(value)
    if cleaned.get("enable-rcon") and not cleaned.get("rcon.password"):
        raise ValueError("RCON needs a strong password before it can be enabled")
    return cleaned


def write_properties(server_dir: Path, properties: dict[str, Any], make_backup: bool = True) -> None:
    server_dir.mkdir(parents=True, exist_ok=True)
    path = server_dir / "server.properties"
    cleaned = validate_properties({**DEFAULT_PROPERTIES, **properties})
    if make_backup and path.exists():
        backup_name = f"server.properties.{datetime.now().strftime('%Y%m%d-%H%M%S')}.bak"
        shutil.copy2(path, server_dir / backup_name)
    lines = [
        "#Minecraft server properties",
        "#Managed by MineHost Helper. Use the app to edit this file safely.",
    ]
    for key in sorted(cleaned):
        lines.append(f"{key}={_serialize_value(cleaned[key])}")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def properties_from_create_request(data: Any) -> dict[str, Any]:
    return {
        **DEFAULT_PROPERTIES,
        "allow-flight": data.allow_flight,
        "difficulty": data.difficulty,
        "enable-command-block": data.command_blocks,
        "gamemode": data.gamemode,
        "level-name": data.world_name,
        "max-players": data.max_players,
        "motd": data.motd,
        "online-mode": data.online_mode,
        "pvp": data.pvp,
        "server-port": data.port,
        "simulation-distance": data.simulation_distance,
        "spawn-protection": data.spawn_protection,
        "view-distance": data.view_distance,
        "white-list": data.whitelist,
    }
