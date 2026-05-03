from __future__ import annotations

from pathlib import Path

import pytest

from backend.properties_manager import read_properties, write_properties
from backend.storage import JsonStorage
from backend.utils import ensure_child_path, sanitize_server_name, validate_port
from backend.java_manager import class_major_to_java_version, required_java_version_for_jar
import zipfile
import threading


def test_sanitize_server_name_removes_unsafe_characters() -> None:
    assert sanitize_server_name("  My<>Server??  ") == "MyServer"
    assert sanitize_server_name("...") == "Minecraft Server"


def test_validate_port_range() -> None:
    assert validate_port(25565) == 25565
    with pytest.raises(ValueError):
        validate_port(0)
    with pytest.raises(ValueError):
        validate_port(70000)


def test_properties_round_trip(tmp_path: Path) -> None:
    write_properties(
        tmp_path,
        {
            "server-port": 25565,
            "max-players": 12,
            "online-mode": True,
            "motd": "Hello friends",
        },
        make_backup=False,
    )
    props = read_properties(tmp_path)
    assert props["server-port"] == 25565
    assert props["max-players"] == 12
    assert props["online-mode"] is True
    assert props["motd"] == "Hello friends"


def test_storage_read_write(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from backend import storage

    monkeypatch.setattr(storage, "APP_DATA_DIR", tmp_path)
    store = JsonStorage(tmp_path / "state.json")
    store.write({"ok": True})
    assert store.read({}) == {"ok": True}


def test_backup_path_safety(tmp_path: Path) -> None:
    safe = ensure_child_path(tmp_path, tmp_path / "child" / "file.zip")
    assert safe.name == "file.zip"
    with pytest.raises(ValueError):
        ensure_child_path(tmp_path, tmp_path.parent / "escape.zip")


def test_java_class_major_mapping() -> None:
    assert class_major_to_java_version(65) == 21
    assert class_major_to_java_version(69) == 25


def test_required_java_version_for_minecraft_bundler_jar(tmp_path: Path) -> None:
    jar_path = tmp_path / "server.jar"
    header = b"\xca\xfe\xba\xbe" + (0).to_bytes(2, "big") + (69).to_bytes(2, "big")
    with zipfile.ZipFile(jar_path, "w") as archive:
        archive.writestr("net/minecraft/bundler/Main.class", header + b"fake")
    assert required_java_version_for_jar(jar_path) == 25


def test_dashboard_ignores_stale_selected_server(monkeypatch: pytest.MonkeyPatch) -> None:
    from backend import main

    class FakeServerManager:
        def list_servers(self) -> list[dict[str, object]]:
            return [{"id": "real-server", "name": "Real", "port": 25565, "status": "stopped"}]

        def get_server(self, server_id: str) -> dict[str, object]:
            if server_id != "real-server":
                raise KeyError("Server not found")
            return {"id": "real-server", "name": "Real", "port": 25565, "status": "stopped"}

        def read_properties(self, server_id: str) -> dict[str, object]:
            return {"server-port": 25565}

        def process_info(self, server_id: str) -> dict[str, object]:
            return {"running": False}

        def console_lines(self, server_id: str, limit: int) -> list[str]:
            return []

        def check_port(self, server_id: str) -> dict[str, object]:
            return {"port": 25565, "available": True}

    monkeypatch.setattr(main, "server_manager", FakeServerManager())
    monkeypatch.setattr(main.networking, "get_local_ip", lambda: "192.168.1.50")
    monkeypatch.setattr(main.networking, "get_public_ip", lambda: None)

    data = main.dashboard("missing-from-browser-local-storage")

    assert data["selected"]["id"] == "real-server"
    assert data["server_address"] == "PUBLIC_IP:25565"


def test_minecraft_bind_failure_sets_actionable_error() -> None:
    from backend.server_manager import ServerManager

    manager = ServerManager.__new__(ServerManager)
    manager._lock = threading.RLock()
    manager._processes = {}
    manager._operations = {}
    manager._servers = {
        "family": {
            "id": "family",
            "name": "Family Minecraft",
            "status": "starting",
            "last_error": None,
            "updated_at": "",
        }
    }
    manager._save = lambda: None

    manager._handle_console_line("family", "[Server thread/WARN]: **** FAILED TO BIND TO PORT!")

    assert manager._servers["family"]["status"] == "error"
    assert "already using it" in manager._servers["family"]["last_error"]
    assert manager._operations["family"]["title"] == "Port is already in use"
    assert manager._operations["family"]["active"] is False


def test_port_check_returns_resolution_for_conflict(tmp_path: Path) -> None:
    from backend.server_manager import ServerManager

    manager = ServerManager.__new__(ServerManager)
    manager._lock = threading.RLock()
    manager._processes = {}
    manager._operations = {}
    manager._servers = {
        "family": {
            "id": "family",
            "name": "Family Minecraft",
            "path": str(tmp_path),
            "port": 25565,
            "status": "stopped",
            "last_error": None,
            "updated_at": "",
        }
    }
    write_properties(tmp_path, {"server-port": 25565}, make_backup=False)
    manager._server_dir = lambda server_id: tmp_path
    manager._port_is_available = lambda port: False
    manager._next_available_port = lambda port: 25566
    manager._port_owner = lambda port: {"pid": 123, "name": "java.exe", "safe_to_stop": True}

    status = manager.check_port("family")

    assert status["available"] is False
    assert status["can_stop_owner"] is True
    assert status["next_port"] == 25566
    assert "old MineHost Minecraft process" in status["resolution"]


def test_change_version_replaces_server_jar_and_records_version(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from backend import server_manager as server_manager_module
    from backend.server_manager import ServerManager

    runtime_jar = tmp_path / "runtime.jar"
    runtime_jar.write_text("new jar", encoding="utf-8")
    server_jar = tmp_path / "server.jar"
    server_jar.write_text("old jar", encoding="utf-8")

    manager = ServerManager.__new__(ServerManager)
    manager._lock = threading.RLock()
    manager._processes = {}
    manager._operations = {}
    manager._servers = {
        "family": {
            "id": "family",
            "name": "Family Minecraft",
            "path": str(tmp_path),
            "version": "1.21.1",
            "port": 25565,
            "status": "stopped",
            "last_error": None,
            "updated_at": "",
        }
    }
    manager._save = lambda: None
    manager._server_dir = lambda server_id: tmp_path
    monkeypatch.setattr(server_manager_module, "download_server_jar", lambda version: ("1.21.8", runtime_jar))

    updated = manager.change_version("family", "1.21.8")

    assert updated["version"] == "1.21.8"
    assert server_jar.read_text(encoding="utf-8") == "new jar"
    assert list(tmp_path.glob("server-1.21.1-*.jar.bak"))


def test_change_version_requires_stopped_server(tmp_path: Path) -> None:
    from backend.server_manager import ServerManager

    manager = ServerManager.__new__(ServerManager)
    manager._lock = threading.RLock()
    manager._processes = {}
    manager._operations = {}
    manager._servers = {
        "family": {
            "id": "family",
            "name": "Family Minecraft",
            "path": str(tmp_path),
            "version": "1.21.1",
            "port": 25565,
            "status": "running",
            "last_error": None,
            "updated_at": "",
        }
    }
    manager._server_dir = lambda server_id: tmp_path
    manager.refresh_status = lambda server_id: None

    with pytest.raises(RuntimeError, match="Stop the server"):
        manager.change_version("family", "1.21.8")


def test_public_port_status_checks_external_service_when_requested(monkeypatch: pytest.MonkeyPatch) -> None:
    from backend import networking

    monkeypatch.setattr(
        networking,
        "_external_port_test",
        lambda port: {"provider": "Test", "status": "OPEN", "ip": "203.0.113.10", "port": port, "ms": 12},
    )

    status = networking.public_port_status(25565, "203.0.113.10", local_open=True, check_external=True)

    assert status["reachable"] is True
    assert status["checked_externally"] is True
    assert status["state"] == "Publicly reachable"


def test_public_port_status_does_not_check_external_service_by_default(monkeypatch: pytest.MonkeyPatch) -> None:
    from backend import networking

    def fail_if_called(port: int) -> dict[str, object]:
        raise AssertionError("external service should not be called")

    monkeypatch.setattr(networking, "_external_port_test", fail_if_called)

    status = networking.public_port_status(25565, "203.0.113.10", local_open=True)

    assert status["reachable"] is None
    assert status["checked_externally"] is False
    assert status["state"] == "Ready to test"
