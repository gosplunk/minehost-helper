from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path
from typing import Any

from .properties_manager import read_properties
from .utils import sanitize_server_name
from .utils import hidden_subprocess_kwargs

SERVER_JAR_HINTS = ("server", "minecraft_server", "paper", "spigot", "fabric", "forge", "purpur", "bukkit")
MAX_SCAN_DEPTH = 5
MAX_CANDIDATES = 80


def common_search_roots() -> list[Path]:
    roots: list[Path] = []
    home = Path.home()
    for name in ("Desktop", "Downloads", "Documents", "OneDrive", "Games"):
        roots.append(home / name)
    for env_name in ("USERPROFILE", "APPDATA", "LOCALAPPDATA"):
        value = os.environ.get(env_name)
        if value:
            roots.append(Path(value))
    for drive in ("D:\\", "C:\\"):
        dev = Path(drive) / "Dev"
        if dev.exists():
            roots.append(dev)
    unique: list[Path] = []
    seen: set[str] = set()
    for root in roots:
        try:
            resolved = root.expanduser().resolve()
        except OSError:
            continue
        key = str(resolved).lower()
        if resolved.exists() and resolved.is_dir() and key not in seen:
            seen.add(key)
            unique.append(resolved)
    return unique


def find_server_jar(server_dir: Path) -> Path | None:
    jars = [path for path in server_dir.glob("*.jar") if path.is_file()]
    if not jars:
        return None
    hinted = [
        jar for jar in jars
        if any(hint in jar.name.lower() for hint in SERVER_JAR_HINTS)
    ]
    return sorted(hinted or jars, key=lambda path: path.stat().st_size if path.exists() else 0, reverse=True)[0]


def looks_like_minecraft_server(path: Path) -> bool:
    if not path.is_dir():
        return False
    if not (path / "server.properties").exists():
        return False
    return find_server_jar(path) is not None


def _depth_from(root: Path, candidate: Path) -> int:
    try:
        return len(candidate.relative_to(root).parts)
    except ValueError:
        return MAX_SCAN_DEPTH + 1


def _safe_walk(root: Path) -> list[Path]:
    found: list[Path] = []
    stack = [root]
    ignored = {
        "$recycle.bin",
        ".git",
        ".venv",
        "__pycache__",
        "node_modules",
        "windows",
        "program files",
        "program files (x86)",
    }
    while stack and len(found) < MAX_CANDIDATES:
        current = stack.pop()
        if _depth_from(root, current) > MAX_SCAN_DEPTH:
            continue
        try:
            if looks_like_minecraft_server(current):
                found.append(current)
                continue
            children = list(current.iterdir())
        except (OSError, PermissionError):
            continue
        for child in children:
            if child.is_dir() and child.name.lower() not in ignored:
                stack.append(child)
    return found


def server_candidate(path: Path) -> dict[str, Any]:
    server_dir = path.expanduser().resolve()
    props = read_properties(server_dir)
    jar = find_server_jar(server_dir)
    eula_path = server_dir / "eula.txt"
    eula_accepted = "eula=true" in eula_path.read_text(encoding="utf-8", errors="ignore").lower() if eula_path.exists() else False
    world_name = str(props.get("level-name", "world"))
    world_exists = (server_dir / world_name).exists()
    return {
        "path": str(server_dir),
        "name": sanitize_server_name(server_dir.name),
        "port": int(props.get("server-port", 25565)),
        "motd": props.get("motd", ""),
        "jar_name": jar.name if jar else None,
        "eula_accepted": eula_accepted,
        "world_name": world_name,
        "world_exists": world_exists,
    }


def scan_existing_servers() -> list[dict[str, Any]]:
    results: dict[str, dict[str, Any]] = {}
    for root in common_search_roots():
        for path in _safe_walk(root):
            try:
                candidate = server_candidate(path)
            except Exception:
                continue
            results[candidate["path"].lower()] = candidate
            if len(results) >= MAX_CANDIDATES:
                break
    return sorted(results.values(), key=lambda item: item["name"].lower())


def _powershell_quote(value: str | Path) -> str:
    return str(value).replace("'", "''")


def browse_for_server_folder(initial_dir: str | None = None) -> Path | None:
    """Open a native Windows folder picker and return the selected folder.

    Browsers intentionally do not expose absolute local folder paths. Because
    MineHost Helper is a local-only manager, the backend can safely open the
    picker on the same PC and validate the result before importing anything.
    """
    powershell = shutil.which("powershell.exe") or shutil.which("powershell")
    if not powershell:
        raise RuntimeError("Windows folder picker needs PowerShell, but PowerShell was not found.")

    selected_path = ""
    if initial_dir:
        try:
            candidate = Path(initial_dir).expanduser().resolve()
            if candidate.exists() and candidate.is_dir():
                selected_path = str(candidate)
        except OSError:
            selected_path = ""

    script = f"""
$ErrorActionPreference = 'Stop'
Add-Type -AssemblyName System.Windows.Forms
$dialog = New-Object System.Windows.Forms.FolderBrowserDialog
$dialog.Description = 'Select the folder that contains server.properties and your Minecraft server .jar'
$dialog.ShowNewFolderButton = $false
if ('{_powershell_quote(selected_path)}') {{
  $dialog.SelectedPath = '{_powershell_quote(selected_path)}'
}}
$result = $dialog.ShowDialog()
if ($result -eq [System.Windows.Forms.DialogResult]::OK) {{
  [Console]::OutputEncoding = [System.Text.Encoding]::UTF8
  Write-Output $dialog.SelectedPath
}}
"""
    result = subprocess.run(
        [powershell, "-NoLogo", "-NoProfile", "-STA", "-ExecutionPolicy", "Bypass", "-Command", script],
        capture_output=True,
        text=True,
        timeout=300,
        check=False,
        **hidden_subprocess_kwargs(),
    )
    if result.returncode != 0:
        output = (result.stderr or result.stdout or "").strip()
        raise RuntimeError(f"Could not open the Windows folder picker: {output or result.returncode}")
    chosen = (result.stdout or "").strip().splitlines()
    if not chosen:
        return None
    return Path(chosen[-1]).expanduser().resolve()
