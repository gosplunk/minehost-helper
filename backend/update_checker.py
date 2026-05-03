from __future__ import annotations

import json
import urllib.request
from typing import Any

CURRENT_VERSION = "0.1.21"
LATEST_RELEASE_URL = "https://api.github.com/repos/gosplunk/minehost-helper/releases/latest"


def _version_tuple(value: str) -> tuple[int, ...]:
    cleaned = value.lower().lstrip("v").split("-", 1)[0]
    parts: list[int] = []
    for part in cleaned.split("."):
        try:
            parts.append(int(part))
        except ValueError:
            parts.append(0)
    return tuple(parts)


def check_for_updates() -> dict[str, Any]:
    request = urllib.request.Request(
        LATEST_RELEASE_URL,
        headers={"Accept": "application/vnd.github+json", "User-Agent": "MineHostHelper/0.1"},
    )
    with urllib.request.urlopen(request, timeout=8) as response:
        data = json.loads(response.read().decode("utf-8"))
    latest = data.get("tag_name") or CURRENT_VERSION
    return {
        "current_version": CURRENT_VERSION,
        "latest_version": latest,
        "update_available": _version_tuple(latest) > _version_tuple(CURRENT_VERSION),
        "release_url": data.get("html_url"),
        "download_url": "https://github.com/gosplunk/minehost-helper/releases/latest/download/MineHostHelperSetup.exe",
        "notes": data.get("body") or "",
    }
