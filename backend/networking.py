from __future__ import annotations

import socket
import json
import time
import urllib.request
from typing import Any

from .utils import validate_port

PUBLIC_PORT_TEST_URL = "https://api.networktools.dev/v1/port-test?port={port}"
_PUBLIC_IP_CACHE: dict[str, Any] = {"value": None, "expires_at": 0.0}


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
    now = time.time()
    if _PUBLIC_IP_CACHE["value"] and now < float(_PUBLIC_IP_CACHE["expires_at"]):
        return str(_PUBLIC_IP_CACHE["value"])
    for url in ("https://api.ipify.org", "https://ifconfig.me/ip"):
        try:
            with urllib.request.urlopen(url, timeout=4) as response:
                public_ip = response.read().decode("utf-8").strip()
                _PUBLIC_IP_CACHE.update({"value": public_ip, "expires_at": now + 600})
                return public_ip
        except Exception:
            continue
    return None


def is_local_port_open(port: int, host: str = "127.0.0.1") -> bool:
    try:
        with socket.create_connection((host, port), timeout=2):
            return True
    except OSError:
        return False


def _external_port_test(port: int) -> dict[str, Any]:
    request = urllib.request.Request(
        PUBLIC_PORT_TEST_URL.format(port=port),
        headers={
            "Accept": "application/json",
            "User-Agent": "MineHostHelper/0.1 (+https://github.com/gosplunk/minehost-helper)",
        },
    )
    with urllib.request.urlopen(request, timeout=12) as response:
        payload = json.loads(response.read().decode("utf-8"))
    status = str(payload.get("status", "")).upper()
    return {
        "provider": "NetworkTools.dev",
        "status": status,
        "ip": payload.get("ip"),
        "port": payload.get("port", port),
        "ms": payload.get("ms"),
    }


def public_port_status(port: int, public_ip: str | None, local_open: bool, check_external: bool = False) -> dict[str, Any]:
    validate_port(port)
    if not local_open:
        return {
            "state": "Local server not running",
            "reachable": False,
            "checked_externally": False,
            "details": "Start the Minecraft server before testing public access.",
        }
    if not public_ip:
        return {
            "state": "Unknown",
            "reachable": None,
            "checked_externally": False,
            "details": "Public IP lookup failed. Check your internet connection and try again.",
        }
    if not check_external:
        return {
            "state": "Ready to test",
            "reachable": None,
            "checked_externally": False,
            "details": (
                "Click Test Public Port to ask an outside service whether friends can reach your Minecraft port. "
                "Only run this after the Minecraft server is started."
            ),
        }
    try:
        external = _external_port_test(port)
    except Exception as exc:
        return {
            "state": "Unknown",
            "reachable": None,
            "checked_externally": False,
            "details": (
                "The outside port-check service could not be reached, so MineHost Helper could not confirm public access. "
                f"Ask a friend outside your house to try {public_ip}:{port}, or try again in a minute. "
                f"Service error: {exc}"
            ),
        }
    status = external["status"]
    checked_ip = external.get("ip") or public_ip
    if status == "OPEN":
        return {
            "state": "Publicly reachable",
            "reachable": True,
            "checked_externally": True,
            "provider": external["provider"],
            "details": (
                f"An outside service confirmed TCP port {port} is open on {checked_ip}. "
                f"Friends outside your house should be able to connect to {checked_ip}:{port}."
            ),
            "raw": external,
        }
    if status in {"CLOSED", "TIMEOUT"}:
        reason = "rejected the connection" if status == "CLOSED" else "did not answer from the public internet"
        return {
            "state": "Router forwarding likely missing",
            "reachable": False,
            "checked_externally": True,
            "provider": external["provider"],
            "details": (
                f"An outside service reached your public IP but TCP port {port} {reason}. "
                "Check Windows Firewall, router port forwarding, double NAT, or CGNAT."
            ),
            "raw": external,
        }
    return {
        "state": "Unknown",
        "reachable": None,
        "checked_externally": True,
        "provider": external["provider"],
        "details": (
            f"The outside port-check service returned an unexpected status: {status or 'empty'}. "
            f"Ask a friend outside your house to try {public_ip}:{port}, or try again."
        ),
        "raw": external,
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
