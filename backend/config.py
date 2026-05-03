from __future__ import annotations

import os
import sys
from pathlib import Path


APP_NAME = "MineHost Helper"
DEFAULT_MANAGER_PORT = 48721
DEFAULT_MINECRAFT_PORT = 25565

if getattr(sys, "frozen", False):
    ROOT_DIR = Path(sys.executable).resolve().parent
    BUNDLE_DIR = Path(getattr(sys, "_MEIPASS", ROOT_DIR))
else:
    ROOT_DIR = Path(__file__).resolve().parents[1]
    BUNDLE_DIR = ROOT_DIR

APP_DATA_DIR = ROOT_DIR / "app_data"
SERVERS_DIR = ROOT_DIR / "servers"
BACKUPS_DIR = ROOT_DIR / "backups"
RUNTIMES_DIR = ROOT_DIR / "runtimes"
JAVA_DIR = RUNTIMES_DIR / "java"
MINECRAFT_RUNTIME_DIR = RUNTIMES_DIR / "minecraft"
LOGS_DIR = ROOT_DIR / "logs"
STATIC_DIR = BUNDLE_DIR / "frontend" / "static"

HOST = os.environ.get("MINEHOST_HOST", "127.0.0.1")
PORT = int(os.environ.get("MINEHOST_PORT", str(DEFAULT_MANAGER_PORT)))


def ensure_directories() -> None:
    for path in (
        APP_DATA_DIR,
        SERVERS_DIR,
        BACKUPS_DIR,
        JAVA_DIR,
        MINECRAFT_RUNTIME_DIR,
        LOGS_DIR,
    ):
        path.mkdir(parents=True, exist_ok=True)
