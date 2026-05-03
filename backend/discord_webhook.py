from __future__ import annotations

import json
import urllib.error
import urllib.request
from typing import Any

from .storage import discord_store

ALLOWED_PREFIXES = (
    "https://discord.com/api/webhooks/",
    "https://discordapp.com/api/webhooks/",
)


def _validate_webhook_url(webhook_url: str) -> str:
    cleaned = webhook_url.strip()
    if not cleaned:
        raise ValueError("Paste the Discord webhook URL first.")
    if not cleaned.startswith(ALLOWED_PREFIXES):
        raise ValueError("Use a Discord webhook URL from Server Settings > Integrations > Webhooks.")
    if len(cleaned) > 500:
        raise ValueError("Discord webhook URL is too long.")
    return cleaned


def get_settings() -> dict[str, Any]:
    saved = discord_store.read({})
    webhook_url = str(saved.get("webhook_url") or "")
    return {
        "enabled": bool(saved.get("enabled", False) and webhook_url),
        "configured": bool(webhook_url),
        "webhook_name": saved.get("webhook_name") or "MineHost Helper",
    }


def update_settings(data: dict[str, Any]) -> dict[str, Any]:
    saved = discord_store.read({})
    if data.get("clear"):
        discord_store.write({"enabled": False, "webhook_url": "", "webhook_name": "MineHost Helper"})
        return get_settings()
    if "webhook_url" in data and str(data.get("webhook_url") or "").strip():
        saved["webhook_url"] = _validate_webhook_url(str(data.get("webhook_url") or ""))
    if "enabled" in data:
        saved["enabled"] = bool(data["enabled"])
    if "webhook_name" in data:
        name = str(data.get("webhook_name") or "MineHost Helper").strip()[:80]
        saved["webhook_name"] = name or "MineHost Helper"
    if saved.get("enabled") and not saved.get("webhook_url"):
        raise ValueError("Add a Discord webhook URL before enabling Discord notifications.")
    discord_store.write(saved)
    return get_settings()


def _post(webhook_url: str, payload: dict[str, Any]) -> None:
    body = json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(
        webhook_url,
        data=body,
        headers={"Content-Type": "application/json", "User-Agent": "MineHostHelper"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=8) as response:
            if response.status >= 400:
                raise ValueError(f"Discord returned HTTP {response.status}.")
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")[:240]
        raise ValueError(f"Discord rejected the webhook: HTTP {exc.code}. {detail}") from exc
    except urllib.error.URLError as exc:
        raise ValueError(f"Could not reach Discord: {exc.reason}") from exc


def send_message(content: str) -> dict[str, Any]:
    saved = discord_store.read({})
    webhook_url = str(saved.get("webhook_url") or "")
    if not webhook_url:
        raise ValueError("Discord webhook is not configured yet.")
    _post(
        webhook_url,
        {
            "username": str(saved.get("webhook_name") or "MineHost Helper")[:80],
            "content": content[:1900],
        },
    )
    return {"ok": True}


def test_message() -> dict[str, Any]:
    return send_message("MineHost Helper Discord notifications are connected.")


def notify_event(message: str) -> None:
    settings = get_settings()
    if not settings["enabled"]:
        return
    try:
        send_message(message)
    except Exception:
        # Notifications must never block local server control.
        return
