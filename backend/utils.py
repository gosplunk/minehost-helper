from __future__ import annotations

import re
import socket
import subprocess
from pathlib import Path


SAFE_NAME_RE = re.compile(r"[^a-zA-Z0-9._ -]+")


def sanitize_server_name(name: str) -> str:
    cleaned = SAFE_NAME_RE.sub("", name.strip())
    cleaned = re.sub(r"\s+", " ", cleaned).strip(" .")
    if not cleaned:
        return "Minecraft Server"
    return cleaned[:60]


def slugify_name(name: str) -> str:
    cleaned = sanitize_server_name(name).lower()
    cleaned = re.sub(r"[^a-z0-9]+", "-", cleaned).strip("-")
    return cleaned or "minecraft-server"


def ensure_child_path(base: Path, candidate: Path) -> Path:
    base_resolved = base.resolve()
    candidate_resolved = candidate.resolve()
    if base_resolved != candidate_resolved and base_resolved not in candidate_resolved.parents:
        raise ValueError("Unsafe path outside application folder")
    return candidate_resolved


def validate_port(port: int) -> int:
    if not isinstance(port, int) or not 1 <= port <= 65535:
        raise ValueError("Port must be between 1 and 65535")
    return port


def validate_ram_mb(ram_mb: int) -> int:
    if not isinstance(ram_mb, int) or not 512 <= ram_mb <= 65536:
        raise ValueError("RAM must be between 512 MB and 65536 MB")
    return ram_mb


def find_free_port(start: int, host: str = "127.0.0.1", limit: int = 100) -> int:
    for port in range(start, start + limit):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            try:
                sock.bind((host, port))
                return port
            except OSError:
                continue
    raise RuntimeError(f"No free port found from {start} to {start + limit - 1}")


def hidden_subprocess_kwargs() -> dict[str, int | subprocess.STARTUPINFO]:
    """Keep helper probes from flashing console windows in the packaged Windows app."""
    if not hasattr(subprocess, "CREATE_NO_WINDOW"):
        return {}
    startupinfo = subprocess.STARTUPINFO()
    startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
    startupinfo.wShowWindow = 0
    return {
        "creationflags": subprocess.CREATE_NO_WINDOW,
        "startupinfo": startupinfo,
    }
