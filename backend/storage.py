from __future__ import annotations

import json
import tempfile
from pathlib import Path
from typing import Any

from .config import APP_DATA_DIR, ensure_directories
from .utils import ensure_child_path


class JsonStorage:
    def __init__(self, path: Path):
        ensure_directories()
        self.path = ensure_child_path(APP_DATA_DIR, path)
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def read(self, default: Any) -> Any:
        if not self.path.exists():
            return default
        try:
            return json.loads(self.path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return default

    def write(self, data: Any) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(
            "w", encoding="utf-8", dir=self.path.parent, delete=False
        ) as handle:
            json.dump(data, handle, indent=2)
            handle.write("\n")
            temp_path = Path(handle.name)
        temp_path.replace(self.path)


servers_store = JsonStorage(APP_DATA_DIR / "servers.json")
settings_store = JsonStorage(APP_DATA_DIR / "settings.json")
backup_settings_store = JsonStorage(APP_DATA_DIR / "backup_settings.json")
