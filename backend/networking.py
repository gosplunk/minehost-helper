from __future__ import annotations

import socket
import urllib.request
from typing import Any


def get_local_ip() -> str | None:
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
            sock.connect(("8.8.8.8", 80))
            return sock.getsockname()[0]
    except OSError:
        try:
            return socket.gethostbyname(socket.gethostname())
        except OSError:
            return None


def get_public_ip() -> str | None:
    for url in ("https://api.ipify.org", "https://ifconfig.me/ip"):
        try:
            with urllib.request.urlopen(url, timeout=4) as response:
                return response.read().decode("utf-8").strip()
        except Exception:
            continue
    return None


def is_local_port_open(port: int, host: str = "127.0.0.1") -> bool:
    try:
        with socket.create_connection((host, port), timeout=2):
            return True
    except OSError:
        return False


def public_port_status(port: int, public_ip: str | None, local_open: bool) -> dict[str, Any]:
    if not local_open:
        return {
            "state": "Local server not running",
            "reachable": False,
            "details": "Start the Minecraft server before testing public access.",
        }
    if not public_ip:
        return {
            "state": "Unknown",
            "reachable": None,
            "details": "Public IP lookup failed. Check your internet connection and try again.",
        }
    return {
        "state": "Unknown",
        "reachable": None,
        "details": (
            "MineHost Helper does not use fragile third-party port-check websites for a definitive result yet. "
            "After firewall and router forwarding are set, ask a friend outside your house to connect to "
            f"{public_ip}:{port}."
        ),
    }


def router_instructions(port: int, local_ip: str | None) -> list[str]:
    lan = local_ip or "your PC local IP"
    return [
        "Open your router app or router admin page.",
        "Find Port Forwarding, NAT, Gaming, or Advanced.",
        "Add a rule named Minecraft.",
        "Set Protocol to TCP.",
        f"Set External Port to {port}.",
        f"Set Internal Port to {port}.",
        f"Set Internal IP to {lan}.",
        "Save. Restart the router only if it asks you to.",
        "Come back to MineHost Helper and test again.",
    ]
