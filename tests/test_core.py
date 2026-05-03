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


def test_java_download_detects_windows_certificate_errors() -> None:
    from backend import java_manager

    error = RuntimeError("SSL: CERTIFICATE_VERIFY_FAILED unable to get local issuer certificate")

    assert java_manager._is_certificate_error(error) is True


def test_installer_parses_java_feature_versions() -> None:
    from installer.bootstrap_installer import parse_java_feature_version

    assert parse_java_feature_version('openjdk version "25.0.3" 2026-04-15') == 25
    assert parse_java_feature_version('java version "1.8.0_421"') == 8
    assert parse_java_feature_version("not a java version") is None


def test_installer_writes_reusable_auth_file(tmp_path: Path) -> None:
    from installer.bootstrap_installer import read_existing_auth_username, write_auth_file

    write_auth_file(tmp_path, "family_host", "correct horse")

    assert read_existing_auth_username(tmp_path) == "family_host"
    assert (tmp_path / "app_data" / "auth.json").exists()


def test_auth_manager_hashes_password_and_validates_session(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from backend import auth_manager, storage

    monkeypatch.setattr(storage, "APP_DATA_DIR", tmp_path)
    monkeypatch.setattr(auth_manager, "auth_store", JsonStorage(tmp_path / "auth.json"))

    auth_manager.setup("family_host", "correct horse")
    token = auth_manager.create_session("family_host", "correct horse")

    assert auth_manager.verify("family_host", "wrong password") is False
    assert auth_manager.validate_session(token) is True
    auth_manager.clear_session(token)
    assert auth_manager.validate_session(token) is False


def test_discord_webhook_validation_rejects_non_discord_urls(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from backend import discord_webhook, storage

    monkeypatch.setattr(storage, "APP_DATA_DIR", tmp_path)
    monkeypatch.setattr(discord_webhook, "discord_store", JsonStorage(tmp_path / "discord.json"))

    with pytest.raises(ValueError, match="Discord webhook URL"):
        discord_webhook.update_settings({"enabled": True, "webhook_url": "https://example.com/hook"})


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

        def player_lists(self, server_id: str) -> dict[str, object]:
            return {"online": []}

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


def test_admin_command_builds_safe_minecraft_commands() -> None:
    from backend.server_manager import ServerManager

    sent: list[str] = []
    manager = ServerManager.__new__(ServerManager)
    manager.send_command = lambda server_id, command: sent.append(command)

    result = manager.admin_command("family", {"action": "teleport-to-player", "player": "Steve_1", "target": "Alex_2"})
    assert result["command"] == "tp Steve_1 Alex_2"
    assert sent[-1] == "tp Steve_1 Alex_2"

    result = manager.admin_command("family", {"action": "weather-clear"})
    assert result["command"] == "weather clear"


def test_admin_command_rejects_unsafe_player_names() -> None:
    from backend.server_manager import ServerManager

    manager = ServerManager.__new__(ServerManager)
    manager.send_command = lambda server_id, command: None

    with pytest.raises(ValueError, match="Minecraft username"):
        manager.admin_command("family", {"action": "ban", "player": "@a"})


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


def test_discovery_finds_existing_server_folder(tmp_path: Path) -> None:
    from backend.server_discovery import find_server_jar, server_candidate

    write_properties(tmp_path, {"server-port": 25570, "level-name": "family-world"}, make_backup=False)
    (tmp_path / "paper-1.21.jar").write_text("fake jar", encoding="utf-8")
    (tmp_path / "eula.txt").write_text("eula=true\n", encoding="utf-8")
    (tmp_path / "family-world").mkdir()

    assert find_server_jar(tmp_path).name == "paper-1.21.jar"
    candidate = server_candidate(tmp_path)

    assert candidate["port"] == 25570
    assert candidate["jar_name"] == "paper-1.21.jar"
    assert candidate["eula_accepted"] is True
    assert candidate["world_exists"] is True


def test_manual_browse_existing_server_folder_returns_candidate(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from backend import main

    write_properties(tmp_path, {"server-port": 25572, "level-name": "family-world"}, make_backup=False)
    (tmp_path / "server.jar").write_text("fake jar", encoding="utf-8")

    class FakeServerManager:
        def list_servers(self) -> list[dict[str, object]]:
            return []

    monkeypatch.setattr(main, "server_manager", FakeServerManager())
    monkeypatch.setattr(main, "browse_for_server_folder", lambda: tmp_path)

    candidate = main.browse_server_folder()

    assert candidate["manual"] is True
    assert candidate["already_added"] is False
    assert candidate["path"] == str(tmp_path.resolve())
    assert candidate["port"] == 25572


def test_manual_path_existing_server_folder_returns_candidate(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from backend import main
    from backend.models import ServerDiscoveryPathRequest

    write_properties(tmp_path, {"server-port": 25573}, make_backup=False)
    (tmp_path / "paper-server.jar").write_text("fake jar", encoding="utf-8")

    class FakeServerManager:
        def list_servers(self) -> list[dict[str, object]]:
            return []

    monkeypatch.setattr(main, "server_manager", FakeServerManager())

    candidate = main.manual_server_folder(ServerDiscoveryPathRequest(path=str(tmp_path)))

    assert candidate["manual"] is True
    assert candidate["jar_name"] == "paper-server.jar"
    assert candidate["port"] == 25573


def test_manual_path_accepts_direct_server_jar_path(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from backend import main
    from backend.models import ServerDiscoveryPathRequest

    write_properties(tmp_path, {"server-port": 25574}, make_backup=False)
    jar_path = tmp_path / "minecraft_server.1.21.8.jar"
    jar_path.write_text("fake jar", encoding="utf-8")

    class FakeServerManager:
        def list_servers(self) -> list[dict[str, object]]:
            return []

    monkeypatch.setattr(main, "server_manager", FakeServerManager())

    candidate = main.manual_server_folder(ServerDiscoveryPathRequest(path=str(jar_path)))

    assert candidate["manual"] is True
    assert candidate["jar_name"] == "minecraft_server.1.21.8.jar"
    assert candidate["port"] == 25574


def test_discovery_finds_nested_server_jar_layout(tmp_path: Path) -> None:
    from backend.server_discovery import find_server_jar, server_candidate

    write_properties(tmp_path, {"server-port": 25575}, make_backup=False)
    nested = tmp_path / "libraries" / "net" / "minecraftforge" / "forge" / "1.20.1"
    nested.mkdir(parents=True)
    (nested / "forge-1.20.1-server.jar").write_text("fake jar", encoding="utf-8")

    jar = find_server_jar(tmp_path)
    candidate = server_candidate(tmp_path)

    assert jar is not None
    assert jar.name == "forge-1.20.1-server.jar"
    assert candidate["jar_name"] == "libraries/net/minecraftforge/forge/1.20.1/forge-1.20.1-server.jar"


def test_adopt_existing_server_records_external_path_and_jar(tmp_path: Path) -> None:
    from backend.models import ServerAdoptRequest
    from backend.server_manager import ServerManager

    write_properties(tmp_path, {"server-port": 25571}, make_backup=False)
    (tmp_path / "fabric-server.jar").write_text("fake jar", encoding="utf-8")

    manager = ServerManager.__new__(ServerManager)
    manager._lock = threading.RLock()
    manager._processes = {}
    manager._operations = {}
    manager._servers = {}
    manager._save = lambda: None

    adopted = manager.adopt_server(ServerAdoptRequest(path=str(tmp_path), name="Imported Server", ram_mb=2048))

    assert adopted["external"] is True
    assert adopted["path"] == str(tmp_path.resolve())
    assert adopted["jar_name"] == "fabric-server.jar"
    assert adopted["port"] == 25571
    assert manager._server_jar_path(adopted["id"]).name == "fabric-server.jar"


def test_file_manager_sandboxes_and_backs_up_text_files(tmp_path: Path) -> None:
    from backend.server_manager import ServerManager

    (tmp_path / "server.properties").write_text("motd=old\n", encoding="utf-8")
    manager = ServerManager.__new__(ServerManager)
    manager._servers = {"family": {"id": "family", "path": str(tmp_path), "jar_name": "server.jar"}}

    listing = manager.list_files("family")
    assert any(item["name"] == "server.properties" and item["editable"] for item in listing["entries"])

    updated = manager.write_file("family", "server.properties", "motd=new\n")
    assert updated["content"] == "motd=new\n"
    assert list(tmp_path.glob("server.properties.bak-*"))

    with pytest.raises(ValueError):
        manager.read_file("family", "../outside.txt")


def test_world_map_scans_vanilla_region_headers(tmp_path: Path) -> None:
    from backend.world_map import scan_dimension

    write_properties(tmp_path, {"level-name": "world"}, make_backup=False)
    region_dir = tmp_path / "world" / "region"
    region_dir.mkdir(parents=True)
    header = bytearray(4096)
    # Local chunk 0,0 in region 1,-2 -> global chunk 32,-64.
    header[0:4] = b"\x00\x00\x02\x01"
    # Local chunk 5,3 index 101 -> global chunk 37,-61.
    offset = 101 * 4
    header[offset:offset + 4] = b"\x00\x00\x03\x01"
    (region_dir / "r.1.-2.mca").write_bytes(bytes(header) + b"\x00" * 4096)

    data = scan_dimension(tmp_path, "overworld")

    assert data["available"] is True
    assert data["chunk_count"] == 2
    assert {"x": 32, "z": -64} in data["chunks"]
    assert {"x": 37, "z": -61} in data["chunks"]
    assert data["bounds"] == {"min_x": 32, "max_x": 37, "min_z": -64, "max_z": -61}


def test_world_map_reports_missing_dimension(tmp_path: Path) -> None:
    from backend.world_map import scan_dimension

    write_properties(tmp_path, {"level-name": "world"}, make_backup=False)

    data = scan_dimension(tmp_path, "nether")

    assert data["available"] is False
    assert data["chunks"] == []


def test_world_map_finds_imported_world_when_level_name_is_wrong(tmp_path: Path) -> None:
    from backend.world_map import scan_dimension

    write_properties(tmp_path, {"level-name": "missing-world"}, make_backup=False)
    region_dir = tmp_path / "RealWorld" / "region"
    region_dir.mkdir(parents=True)
    header = bytearray(4096)
    header[0:4] = b"\x00\x00\x02\x01"
    (region_dir / "r.0.0.mca").write_bytes(bytes(header) + b"\x00" * 4096)

    data = scan_dimension(tmp_path, "overworld")

    assert data["available"] is True
    assert data["world_name"] == "RealWorld"
    assert data["configured_world_name"] == "missing-world"
    assert data["region_files_found"] == 1
    assert data["chunk_count"] == 1


def test_world_map_discovers_vanilla_nether_dimension(tmp_path: Path) -> None:
    from backend.world_map import scan_dimension

    write_properties(tmp_path, {"level-name": "FamilyWorld"}, make_backup=False)
    region_dir = tmp_path / "FamilyWorld" / "DIM-1" / "region"
    region_dir.mkdir(parents=True)
    header = bytearray(4096)
    header[0:4] = b"\x00\x00\x02\x01"
    (region_dir / "r.-1.2.mca").write_bytes(bytes(header) + b"\x00" * 4096)

    data = scan_dimension(tmp_path, "nether")

    assert data["available"] is True
    assert data["world_name"] == "FamilyWorld"
    assert {"x": -32, "z": 64} in data["chunks"]
    assert any(item["id"] == "nether" and item["available"] for item in data["dimensions"])


def test_world_map_discovers_separate_nether_world_folder(tmp_path: Path) -> None:
    from backend.world_map import scan_dimension

    write_properties(tmp_path, {"level-name": "world"}, make_backup=False)
    region_dir = tmp_path / "world_nether" / "region"
    region_dir.mkdir(parents=True)
    header = bytearray(4096)
    header[4:8] = b"\x00\x00\x02\x01"
    (region_dir / "r.0.0.mca").write_bytes(bytes(header) + b"\x00" * 4096)

    data = scan_dimension(tmp_path, "nether")

    assert data["available"] is True
    assert data["world_name"] == "world_nether"
    assert {"x": 1, "z": 0} in data["chunks"]


def test_diagnostics_explains_common_errors() -> None:
    from backend.diagnostics import explain_lines

    findings = explain_lines(["java.lang.UnsupportedClassVersionError: newer version required"])

    assert findings[0]["title"] == "Java is too old"


def test_backup_schedule_update_validates_and_persists(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from backend import backup_scheduler, storage

    monkeypatch.setattr(storage, "APP_DATA_DIR", tmp_path)
    store = storage.JsonStorage(tmp_path / "backup_settings.json")
    monkeypatch.setattr(backup_scheduler, "backup_settings_store", store)

    settings = backup_scheduler.update_schedule("family", {"enabled": True, "interval_hours": 6, "retention_count": 3})

    assert settings["enabled"] is True
    assert settings["interval_hours"] == 6
    assert settings["retention_count"] == 3
    assert backup_scheduler.get_schedule("family")["next_run_at"]
