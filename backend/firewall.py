from __future__ import annotations

import subprocess

from .utils import validate_port


def rule_name(port: int) -> str:
    return f"MineHost Helper Minecraft TCP {port}"


def check_firewall_rule(port: int) -> dict[str, str | bool | int]:
    validate_port(port)
    name = rule_name(port)
    result = subprocess.run(
        ["netsh", "advfirewall", "firewall", "show", "rule", f"name={name}"],
        capture_output=True,
        text=True,
        check=False,
    )
    return {
        "port": port,
        "rule_name": name,
        "exists": result.returncode == 0 and "No rules match" not in result.stdout,
        "raw": result.stdout.strip() or result.stderr.strip(),
    }


def create_firewall_rule(port: int) -> dict[str, str | bool | int]:
    validate_port(port)
    name = rule_name(port)
    result = subprocess.run(
        [
            "netsh",
            "advfirewall",
            "firewall",
            "add",
            "rule",
            f"name={name}",
            "dir=in",
            "action=allow",
            "protocol=TCP",
            f"localport={port}",
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    return {
        "port": port,
        "rule_name": name,
        "success": result.returncode == 0,
        "message": result.stdout.strip() or result.stderr.strip(),
        "admin_command": (
            f'netsh advfirewall firewall add rule name="{name}" '
            f"dir=in action=allow protocol=TCP localport={port}"
        ),
    }
