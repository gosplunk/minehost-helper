from __future__ import annotations

import os
import re
import shutil
import socket
import subprocess
import threading
import time
import zipfile
from collections import deque
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

try:
    import psutil
except Exception:  # pragma: no cover - psutil is optional at runtime.
    psutil = None

from .config import BACKUPS_DIR, LOGS_DIR, SERVERS_DIR, ensure_directories
from .java_manager import get_java_path, install_temurin_jre, required_java_version_for_jar
from .minecraft_downloader import download_server_jar
from .models import ServerAdoptRequest, ServerCreateRequest
from .properties_manager import properties_from_create_request, read_properties, write_properties
from .server_discovery import find_server_jar, server_candidate
from .storage import servers_store
from .utils import ensure_child_path, slugify_name
from .world_map import scan_dimension

EDITABLE_EXTENSIONS = {".txt", ".json", ".properties", ".yml", ".yaml", ".toml", ".cfg", ".conf", ".log"}


class ManagedProcess:
    def __init__(self, process: subprocess.Popen[str], server_id: str):
        self.process = process
        self.server_id = server_id
        self.started_at = time.time()
        self.lines: deque[str] = deque(maxlen=1000)


class ServerManager:
    def __init__(self) -> None:
        ensure_directories()
        self._lock = threading.RLock()
        self._processes: dict[str, ManagedProcess] = {}
        self._operations: dict[str, dict[str, Any]] = {}
        self._servers: dict[str, dict[str, Any]] = {
            item["id"]: item for item in servers_store.read([])
        }

    def _save(self) -> None:
        servers_store.write(list(self._servers.values()))

    def _now(self) -> str:
        return datetime.now(timezone.utc).isoformat()

    def _server_dir(self, server_id: str) -> Path:
        if server_id not in self._servers:
            raise KeyError("Server not found")
        stored = Path(self._servers[server_id]["path"])
        if stored.is_absolute():
            return stored.resolve()
        return ensure_child_path(SERVERS_DIR, stored)

    def _server_jar_name(self, server_id: str) -> str:
        return str(self._servers[server_id].get("jar_name") or "server.jar")

    def _server_jar_path(self, server_id: str) -> Path:
        server_dir = self._server_dir(server_id)
        jar_name = self._server_jar_name(server_id)
        return ensure_child_path(server_dir, server_dir / jar_name)

    def _set_status(self, server_id: str, status: str, error: str | None = None) -> None:
        with self._lock:
            server = self._servers[server_id]
            server["status"] = status
            server["last_error"] = error
            server["updated_at"] = self._now()
            self._save()

    def _set_operation(
        self,
        server_id: str,
        title: str,
        message: str,
        percent: int | None = None,
        active: bool = True,
    ) -> None:
        with self._lock:
            existing = self._operations.get(server_id, {})
            self._operations[server_id] = {
                "title": title,
                "message": message,
                "percent": max(0, min(100, percent)) if isinstance(percent, int) else None,
                "active": active,
                "started_at": existing.get("started_at") or time.time(),
                "updated_at": time.time(),
            }

    def _operation_for(self, server_id: str) -> dict[str, Any] | None:
        operation = self._operations.get(server_id)
        if not operation:
            return None
        age = int(time.time() - float(operation.get("started_at", time.time())))
        return {**operation, "age_seconds": age}

    def _port_owner(self, port: int) -> dict[str, Any] | None:
        if psutil:
            try:
                for connection in psutil.net_connections(kind="inet"):
                    if not connection.laddr or connection.status != psutil.CONN_LISTEN:
                        continue
                    if int(connection.laddr.port) != port:
                        continue
                    name = "unknown process"
                    executable = None
                    command_line = ""
                    cwd = None
                    if connection.pid:
                        try:
                            proc = psutil.Process(connection.pid)
                            name = proc.name()
                            executable = proc.exe()
                            command_line = " ".join(proc.cmdline())
                            cwd = proc.cwd()
                        except Exception:
                            pass
                    details = " ".join(str(value or "") for value in (name, executable, command_line, cwd)).lower()
                    is_minecraft = "server.jar" in command_line.lower() and "nogui" in command_line.lower()
                    is_minehost = "minehosthelper" in details or "minehost helper" in details
                    return {
                        "pid": connection.pid,
                        "name": name,
                        "executable": executable,
                        "command_line": command_line,
                        "cwd": cwd,
                        "safe_to_stop": bool(connection.pid and is_minecraft and is_minehost),
                    }
            except Exception:
                pass
        return None

    def _port_is_available(self, port: int) -> bool:
        for host in ("127.0.0.1", "::1", "0.0.0.0"):
            family = socket.AF_INET6 if ":" in host else socket.AF_INET
            with socket.socket(family, socket.SOCK_STREAM) as sock:
                sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                try:
                    sock.bind((host, port))
                except OSError:
                    return False
        return True

    def _next_available_port(self, start: int) -> int | None:
        for port in range(max(1, start + 1), 65536):
            if self._port_is_available(port):
                return port
        return None

    def _port_conflict_message(self, port: int) -> str:
        owner = self._port_owner(port)
        if owner:
            pid = f" (PID {owner['pid']})" if owner.get("pid") else ""
            if owner.get("safe_to_stop"):
                return (
                    f"Port {port} is already in use by an old MineHost Minecraft process: {owner['name']}{pid}. "
                    "Use Stop Old Server Process, then click Start Server again."
                )
            return (
                f"Port {port} is already in use by {owner['name']}{pid}. "
                "Use an open port, close that app manually, or change this server's port in Server Settings."
            )
        return (
            f"Port {port} is already in use. Stop the other app using that port, "
            "or use the next open port from the Dashboard."
        )

    def check_port(self, server_id: str) -> dict[str, Any]:
        server_dir = self._server_dir(server_id)
        properties = read_properties(server_dir)
        port = int(properties.get("server-port", self._servers[server_id].get("port", 25565)))
        available = self._port_is_available(port)
        owner = None if available else self._port_owner(port)
        next_port = None if available else self._next_available_port(port)
        resolution = "Ready to start."
        if not available:
            if owner and owner.get("safe_to_stop"):
                resolution = "This looks like an old MineHost Minecraft process. Use Stop old process, then Start Server again."
            else:
                resolution = "Use the next open port, or close the app that is already using this port."
        return {
            "port": port,
            "available": available,
            "owner": owner,
            "next_port": next_port,
            "can_stop_owner": bool(owner and owner.get("safe_to_stop")),
            "message": "Port is available." if available else self._port_conflict_message(port),
            "resolution": resolution,
        }

    def stop_port_owner(self, server_id: str) -> dict[str, Any]:
        status = self.check_port(server_id)
        owner = status.get("owner")
        if status["available"]:
            return status
        if not owner or not owner.get("safe_to_stop") or not owner.get("pid"):
            raise RuntimeError("MineHost Helper will not stop this process automatically. Use the next open port or close the app manually.")
        if not psutil:
            raise RuntimeError("Process tools are not available. Close the other Java process manually or use the next open port.")
        proc = psutil.Process(int(owner["pid"]))
        proc.terminate()
        try:
            proc.wait(timeout=10)
        except psutil.TimeoutExpired:
            proc.kill()
            proc.wait(timeout=10)
        self._set_operation(server_id, "Port is free", "Stopped the old MineHost Minecraft process. You can start the server now.", 100, active=False)
        self._set_status(server_id, "stopped")
        return self.check_port(server_id)

    def use_next_available_port(self, server_id: str) -> dict[str, Any]:
        status = self.check_port(server_id)
        next_port = status.get("next_port")
        if status["available"]:
            return self.get_server(server_id)
        if not next_port:
            raise RuntimeError("Could not find an open port. Close another app and try again.")
        properties = read_properties(self._server_dir(server_id))
        properties["server-port"] = int(next_port)
        self.write_properties(server_id, properties)
        self._set_operation(
            server_id,
            "Port changed",
            f"Changed this server to port {next_port}. Friends should connect with :{next_port} instead of :{status['port']}.",
            100,
            active=False,
        )
        return self.get_server(server_id)

    def list_servers(self) -> list[dict[str, Any]]:
        with self._lock:
            for server_id in list(self._servers):
                self.refresh_status(server_id)
            result: list[dict[str, Any]] = []
            for server_id, server in self._servers.items():
                item = dict(server)
                item["operation"] = self._operation_for(server_id)
                result.append(item)
            return result

    def get_server(self, server_id: str) -> dict[str, Any]:
        with self._lock:
            if server_id not in self._servers:
                raise KeyError("Server not found")
            self.refresh_status(server_id)
            server = dict(self._servers[server_id])
            server["operation"] = self._operation_for(server_id)
            return server

    def create_server(self, data: ServerCreateRequest) -> dict[str, Any]:
        if not data.accepted_eula:
            raise ValueError("You must accept the Minecraft EULA before creating a server")
        ensure_directories()
        base_slug = slugify_name(data.name)
        slug = base_slug
        counter = 2
        while slug in self._servers or (SERVERS_DIR / slug).exists():
            slug = f"{base_slug}-{counter}"
            counter += 1
        server_dir = ensure_child_path(SERVERS_DIR, SERVERS_DIR / slug)
        server_dir.mkdir(parents=True, exist_ok=False)

        version_id, jar_path = download_server_jar(data.version)
        shutil.copy2(jar_path, server_dir / "server.jar")
        write_properties(server_dir, properties_from_create_request(data), make_backup=False)
        (server_dir / "eula.txt").write_text(
            "# Accepted through MineHost Helper\n"
            "# By changing this to true you indicate your agreement to the Minecraft EULA.\n"
            "eula=true\n",
            encoding="utf-8",
        )
        now = self._now()
        server = {
            "id": slug,
            "name": data.name,
            "version": version_id,
            "ram_mb": data.ram_mb,
            "port": data.port,
            "path": str(server_dir),
            "status": "stopped",
            "created_at": now,
            "updated_at": now,
            "last_error": None,
        }
        with self._lock:
            self._servers[slug] = server
            self._save()
        return dict(server)

    def adopt_server(self, data: ServerAdoptRequest) -> dict[str, Any]:
        server_dir = Path(data.path).expanduser().resolve()
        if not server_dir.exists() or not server_dir.is_dir():
            raise ValueError("Existing server folder was not found")
        if not (server_dir / "server.properties").exists():
            raise ValueError("This folder does not contain server.properties")
        jar = find_server_jar(server_dir)
        if not jar:
            raise ValueError("This folder does not contain a Minecraft server .jar file")
        candidate = server_candidate(server_dir)
        properties = read_properties(server_dir)
        base_slug = slugify_name(data.name or candidate["name"])
        slug = base_slug
        counter = 2
        with self._lock:
            existing_paths = {str(Path(item["path"]).resolve()).lower() for item in self._servers.values()}
            if str(server_dir).lower() in existing_paths:
                raise ValueError("This server folder has already been added to MineHost Helper")
            while slug in self._servers:
                slug = f"{base_slug}-{counter}"
                counter += 1
            now = self._now()
            server = {
                "id": slug,
                "name": data.name or candidate["name"],
                "version": "existing",
                "ram_mb": data.ram_mb,
                "port": int(properties.get("server-port", candidate["port"])),
                "path": str(server_dir),
                "jar_name": jar.name,
                "external": True,
                "status": "stopped",
                "created_at": now,
                "updated_at": now,
                "last_error": None,
            }
            self._servers[slug] = server
            self._save()
        return dict(server)

    def _reader_thread(self, managed: ManagedProcess, log_path: Path) -> None:
        with log_path.open("a", encoding="utf-8", errors="replace") as log_file:
            assert managed.process.stdout is not None
            for line in managed.process.stdout:
                text = line.rstrip()
                managed.lines.append(text)
                self._handle_console_line(managed.server_id, text)
                log_file.write(text + "\n")
                log_file.flush()

    def _handle_console_line(self, server_id: str, line: str) -> None:
        plain = re.sub(r"\x1b\[[0-9;]*m", "", line)
        lower = plain.lower()
        if "failed to bind to port" in lower or "address already in use" in lower:
            message = (
                "Minecraft could not use the configured port because another app is already using it. "
                "Stop the other Minecraft/Java server, or change this server's port in Server Settings, then start again."
            )
            self._set_status(server_id, "error", message)
            self._set_operation(server_id, "Port is already in use", message, None, active=False)
            return
        if "unpacking " in lower and ".jar" in lower:
            self._set_operation(
                server_id,
                "Preparing Minecraft",
                "Minecraft is unpacking its own server files. This is normal on first start and can take a few minutes.",
                35,
            )
            return
        if "starting minecraft server version" in lower:
            self._set_operation(server_id, "Starting Minecraft", plain, 45)
            return
        if "loading properties" in lower or "default game type" in lower:
            self._set_operation(server_id, "Loading settings", "Minecraft is reading server.properties and preparing the world.", 55)
            return
        if "preparing level" in lower:
            self._set_operation(server_id, "Preparing world", "Minecraft is preparing the world folder.", 65)
            return
        match = re.search(r"preparing spawn area:\s*(\d+)%", lower)
        if match:
            percent = int(match.group(1))
            self._set_operation(server_id, "Preparing spawn", f"Preparing spawn area: {percent}%", 70 + int(percent * 0.25))
            return
        if "done (" in lower and "for help" in lower:
            self._set_status(server_id, "running")
            self._set_operation(server_id, "Server ready", "Minecraft is running. Friends can connect once networking is configured.", 100, active=False)
            return

    def refresh_status(self, server_id: str) -> None:
        managed = self._processes.get(server_id)
        if not managed:
            return
        code = managed.process.poll()
        if code is None:
            if self._servers[server_id].get("status") not in ("starting", "stopping"):
                self._servers[server_id]["status"] = "running"
            return
        self._processes.pop(server_id, None)
        if self._servers[server_id]["status"] not in ("stopping", "stopped"):
            self._servers[server_id]["status"] = "error"
            self._servers[server_id]["last_error"] = f"Minecraft exited with code {code}"
        else:
            self._servers[server_id]["status"] = "stopped"
            self._set_operation(server_id, "Stopped", "Minecraft is not running.", 0, active=False)
        self._servers[server_id]["updated_at"] = self._now()
        self._save()

    def start(self, server_id: str) -> dict[str, Any]:
        with self._lock:
            server = self.get_server(server_id)
            if server_id in self._processes and self._processes[server_id].process.poll() is None:
                return server
            server_dir = self._server_dir(server_id)
            jar_path = self._server_jar_path(server_id)
            required_java = required_java_version_for_jar(jar_path)
            java = get_java_path(required_java)
            if not java:
                try:
                    self._set_operation(
                        server_id,
                        "Installing Java",
                        f"Downloading a compatible Java runtime{f' {required_java}' if required_java else ''}. This can take a few minutes.",
                        10,
                    )
                    install_temurin_jre(required_java or 25)
                    java = get_java_path(required_java)
                except Exception as exc:
                    version_text = f" Java {required_java} or newer is required." if required_java else ""
                    self._set_status(server_id, "error", f"Java is missing or too old.{version_text} Could not download a compatible runtime: {exc}")
                    raise
            if not java:
                version_text = f" Java {required_java} or newer is required." if required_java else ""
                raise RuntimeError(f"Java is not available or is too old.{version_text}")
            eula = (server_dir / "eula.txt").read_text(encoding="utf-8", errors="ignore")
            if "eula=true" not in eula.lower():
                raise RuntimeError("Minecraft EULA is not accepted for this server")
            properties = read_properties(server_dir)
            port = int(properties.get("server-port", server.get("port", 25565)))
            if not self._port_is_available(port):
                message = self._port_conflict_message(port)
                self._set_status(server_id, "error", message)
                self._set_operation(server_id, "Port is already in use", message, None, active=False)
                raise RuntimeError(message)
            self._set_status(server_id, "starting")
            self._set_operation(server_id, "Starting server", "Launching Minecraft. The first start may pause while Minecraft unpacks files.", 20)
            ram_mb = int(server["ram_mb"])
            command = [
                str(java),
                f"-Xmx{ram_mb}M",
                f"-Xms{ram_mb}M",
                "-jar",
                jar_path.name,
                "nogui",
            ]
            creationflags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
            process = subprocess.Popen(
                command,
                cwd=server_dir,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
                creationflags=creationflags,
            )
            managed = ManagedProcess(process, server_id)
            self._processes[server_id] = managed
            log_path = LOGS_DIR / f"{server_id}-console.log"
            threading.Thread(target=self._reader_thread, args=(managed, log_path), daemon=True).start()
            return self.get_server(server_id)

    def stop(self, server_id: str, timeout: int = 30) -> dict[str, Any]:
        managed = self._processes.get(server_id)
        if not managed or managed.process.poll() is not None:
            self._set_status(server_id, "stopped")
            self._set_operation(server_id, "Stopped", "Minecraft is not running.", 0, active=False)
            return self.get_server(server_id)
        self._set_status(server_id, "stopping")
        self._set_operation(server_id, "Stopping server", "Sending Minecraft the safe stop command.", 25)
        if managed.process.stdin:
            managed.process.stdin.write("stop\n")
            managed.process.stdin.flush()
        try:
            managed.process.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            self._set_status(server_id, "error", "Server did not stop within 30 seconds")
            self._set_operation(server_id, "Stop needs attention", "Minecraft did not stop within 30 seconds. Use Emergency Kill only if needed.", None, active=False)
            raise RuntimeError("Server did not stop gracefully. Use force kill only if needed.")
        self._processes.pop(server_id, None)
        self._set_status(server_id, "stopped")
        self._set_operation(server_id, "Stopped", "Minecraft stopped safely.", 100, active=False)
        return self.get_server(server_id)

    def restart(self, server_id: str) -> dict[str, Any]:
        self.stop(server_id)
        return self.start(server_id)

    def kill(self, server_id: str) -> dict[str, Any]:
        managed = self._processes.get(server_id)
        if managed and managed.process.poll() is None:
            managed.process.kill()
            managed.process.wait(timeout=10)
        self._processes.pop(server_id, None)
        self._set_status(server_id, "stopped")
        return self.get_server(server_id)

    def stop_all(self, timeout: int = 15) -> None:
        for server_id in list(self._processes):
            try:
                self.stop(server_id, timeout=timeout)
            except Exception:
                try:
                    self.kill(server_id)
                except Exception:
                    pass

    def send_command(self, server_id: str, command: str) -> None:
        managed = self._processes.get(server_id)
        if not managed or managed.process.poll() is not None or not managed.process.stdin:
            raise RuntimeError("Server is not running")
        managed.process.stdin.write(command.strip() + "\n")
        managed.process.stdin.flush()

    def _clean_player_name(self, value: str | None, label: str = "Player") -> str:
        cleaned = (value or "").strip()
        if not re.fullmatch(r"[A-Za-z0-9_]{3,16}", cleaned):
            raise ValueError(f"{label} must be a Minecraft username with 3 to 16 letters, numbers, or underscores")
        return cleaned

    def _clean_command_text(self, value: str | None, label: str, max_length: int) -> str:
        cleaned = (value or "").strip()
        if not cleaned:
            raise ValueError(f"{label} is required")
        cleaned = re.sub(r"[\r\n]+", " ", cleaned).strip()
        if len(cleaned) > max_length:
            raise ValueError(f"{label} is too long")
        return cleaned

    def admin_command(self, server_id: str, data: dict[str, Any]) -> dict[str, Any]:
        action = str(data.get("action") or "").strip()
        commands = {
            "time-day": "time set day",
            "time-noon": "time set noon",
            "time-night": "time set night",
            "time-midnight": "time set midnight",
            "weather-clear": "weather clear",
            "weather-rain": "weather rain",
            "weather-thunder": "weather thunder",
            "save-all": "save-all",
            "list-players": "list",
            "whitelist-reload": "whitelist reload",
            "keep-inventory-on": "gamerule keepInventory true",
            "keep-inventory-off": "gamerule keepInventory false",
            "daylight-cycle-on": "gamerule doDaylightCycle true",
            "daylight-cycle-off": "gamerule doDaylightCycle false",
            "weather-cycle-on": "gamerule doWeatherCycle true",
            "weather-cycle-off": "gamerule doWeatherCycle false",
        }
        if action in commands:
            command = commands[action]
        elif action == "kick":
            player = self._clean_player_name(data.get("player"))
            reason = (data.get("reason") or "").strip()
            command = f"kick {player} {self._clean_command_text(reason, 'Reason', 120)}" if reason else f"kick {player}"
        elif action == "ban":
            player = self._clean_player_name(data.get("player"))
            reason = (data.get("reason") or "").strip()
            command = f"ban {player} {self._clean_command_text(reason, 'Reason', 120)}" if reason else f"ban {player}"
        elif action == "pardon":
            command = f"pardon {self._clean_player_name(data.get('player'))}"
        elif action == "teleport-to-player":
            player = self._clean_player_name(data.get("player"))
            target = self._clean_player_name(data.get("target"), "Destination player")
            command = f"tp {player} {target}"
        elif action == "op":
            command = f"op {self._clean_player_name(data.get('player'))}"
        elif action == "deop":
            command = f"deop {self._clean_player_name(data.get('player'))}"
        elif action == "whitelist-add":
            command = f"whitelist add {self._clean_player_name(data.get('player'))}"
        elif action == "announce":
            message = self._clean_command_text(data.get("message"), "Announcement", 200)
            command = f"say {message}"
        else:
            raise ValueError("Unsupported admin command")
        self.send_command(server_id, command)
        return {"ok": True, "command": command}

    def player_action(self, server_id: str, action: str, player: str, reason: str | None = None) -> None:
        commands = {
            "op": f"op {player}",
            "deop": f"deop {player}",
            "whitelist-add": f"whitelist add {player}",
            "whitelist-remove": f"whitelist remove {player}",
            "ban": f"ban {player} {reason or ''}".strip(),
            "pardon": f"pardon {player}",
            "kick": f"kick {player} {reason or ''}".strip(),
        }
        if action not in commands:
            raise ValueError("Unsupported player action")
        self.send_command(server_id, commands[action])

    def resource_snapshot(self, server_id: str) -> dict[str, Any]:
        process = self.process_info(server_id)
        disk = self.server_disk_usage(server_id)
        system: dict[str, Any] = {"available": False}
        if psutil:
            try:
                memory = psutil.virtual_memory()
                disk_usage = psutil.disk_usage(str(self._server_dir(server_id).anchor or self._server_dir(server_id)))
                system = {
                    "available": True,
                    "cpu_percent": psutil.cpu_percent(interval=0.0),
                    "memory_total_mb": round(memory.total / (1024 * 1024), 1),
                    "memory_used_mb": round(memory.used / (1024 * 1024), 1),
                    "memory_percent": memory.percent,
                    "disk_total_gb": round(disk_usage.total / (1024 * 1024 * 1024), 1),
                    "disk_free_gb": round(disk_usage.free / (1024 * 1024 * 1024), 1),
                    "disk_percent": disk_usage.percent,
                }
            except Exception:
                system = {"available": False}
        return {
            "process": process,
            "server_disk": disk,
            "system": system,
        }

    def world_map(self, server_id: str, dimension: str = "overworld") -> dict[str, Any]:
        server = self.get_server(server_id)
        data = scan_dimension(self._server_dir(server_id), dimension)
        data["server_status"] = server.get("status", "stopped")
        data["safe_refresh_note"] = (
            "If the server is running, this reads saved region headers only. Use Refresh Map after players explore new areas."
        )
        return data

    def player_lists(self, server_id: str) -> dict[str, Any]:
        server_dir = self._server_dir(server_id)

        def read_json_file(name: str) -> list[dict[str, Any]]:
            path = server_dir / name
            if not path.exists():
                return []
            try:
                import json
                data = json.loads(path.read_text(encoding="utf-8"))
                return data if isinstance(data, list) else []
            except Exception:
                return []

        online: list[str] = []
        for line in self.console_lines(server_id, 300):
            joined = re.search(r":\s*([A-Za-z0-9_]{3,16}) joined the game", line)
            left = re.search(r":\s*([A-Za-z0-9_]{3,16}) left the game", line)
            if joined and joined.group(1) not in online:
                online.append(joined.group(1))
            if left and left.group(1) in online:
                online.remove(left.group(1))
        return {
            "online": online,
            "whitelist": read_json_file("whitelist.json"),
            "ops": read_json_file("ops.json"),
            "banned_players": read_json_file("banned-players.json"),
            "requires_running_for_changes": True,
        }

    def console_lines(self, server_id: str, limit: int = 200) -> list[str]:
        managed = self._processes.get(server_id)
        lines = list(managed.lines)[-limit:] if managed else []
        latest = self._server_dir(server_id) / "logs" / "latest.log"
        if latest.exists():
            try:
                disk_lines = latest.read_text(encoding="utf-8", errors="replace").splitlines()[-limit:]
                lines = (disk_lines + lines)[-limit:]
            except OSError:
                pass
        return lines

    def log_file(self, server_id: str) -> Path | None:
        latest = self._server_dir(server_id) / "logs" / "latest.log"
        if latest.exists():
            return latest
        console = LOGS_DIR / f"{server_id}-console.log"
        return console if console.exists() else None

    def diagnose(self, server_id: str) -> list[dict[str, str]]:
        from .diagnostics import explain_lines

        return explain_lines(self.console_lines(server_id, 500))

    def server_disk_usage(self, server_id: str) -> dict[str, Any]:
        server_dir = self._server_dir(server_id)
        total = 0
        files = 0
        for path in server_dir.rglob("*"):
            try:
                if path.is_file():
                    total += path.stat().st_size
                    files += 1
            except OSError:
                pass
        return {"bytes": total, "files": files}

    def _safe_relative_path(self, server_id: str, relative_path: str) -> Path:
        if not relative_path or relative_path in {".", "/"}:
            return self._server_dir(server_id)
        candidate = self._server_dir(server_id) / relative_path.replace("/", os.sep)
        return ensure_child_path(self._server_dir(server_id), candidate)

    def list_files(self, server_id: str, relative_path: str = "") -> dict[str, Any]:
        base = self._server_dir(server_id)
        folder = self._safe_relative_path(server_id, relative_path)
        if not folder.exists() or not folder.is_dir():
            raise ValueError("Folder was not found")
        entries = []
        for child in sorted(folder.iterdir(), key=lambda path: (not path.is_dir(), path.name.lower())):
            try:
                stat = child.stat()
            except OSError:
                continue
            rel = child.relative_to(base).as_posix()
            entries.append({
                "name": child.name,
                "path": rel,
                "type": "folder" if child.is_dir() else "file",
                "size_bytes": stat.st_size if child.is_file() else None,
                "editable": child.is_file() and child.suffix.lower() in EDITABLE_EXTENSIONS and stat.st_size <= 1_000_000,
            })
        return {"path": folder.relative_to(base).as_posix() if folder != base else "", "entries": entries}

    def read_file(self, server_id: str, relative_path: str) -> dict[str, Any]:
        path = self._safe_relative_path(server_id, relative_path)
        if not path.exists() or not path.is_file():
            raise ValueError("File was not found")
        if path.suffix.lower() not in EDITABLE_EXTENSIONS:
            raise ValueError("MineHost Helper only opens safe text/config files")
        if path.stat().st_size > 1_000_000:
            raise ValueError("This file is too large to edit safely")
        return {"path": path.relative_to(self._server_dir(server_id)).as_posix(), "content": path.read_text(encoding="utf-8", errors="replace")}

    def write_file(self, server_id: str, relative_path: str, content: str) -> dict[str, Any]:
        path = self._safe_relative_path(server_id, relative_path)
        if not path.exists() or not path.is_file():
            raise ValueError("File was not found")
        if path.suffix.lower() not in EDITABLE_EXTENSIONS:
            raise ValueError("MineHost Helper only edits safe text/config files")
        backup = path.with_suffix(path.suffix + f".bak-{datetime.now().strftime('%Y%m%d-%H%M%S')}")
        shutil.copy2(path, backup)
        path.write_text(content, encoding="utf-8")
        return self.read_file(server_id, relative_path)

    def process_info(self, server_id: str) -> dict[str, Any]:
        managed = self._processes.get(server_id)
        if not managed or managed.process.poll() is not None:
            return {"running": False}
        info: dict[str, Any] = {"running": True, "uptime_seconds": int(time.time() - managed.started_at)}
        if psutil:
            try:
                proc = psutil.Process(managed.process.pid)
                info["cpu_percent"] = proc.cpu_percent(interval=0.0)
                info["memory_mb"] = round(proc.memory_info().rss / (1024 * 1024), 1)
            except Exception:
                pass
        return info

    def read_properties(self, server_id: str) -> dict[str, Any]:
        return read_properties(self._server_dir(server_id))

    def write_properties(self, server_id: str, properties: dict[str, Any]) -> dict[str, Any]:
        server_dir = self._server_dir(server_id)
        write_properties(server_dir, properties, make_backup=True)
        port = int(properties.get("server-port", self._servers[server_id]["port"]))
        self._servers[server_id]["port"] = port
        self._servers[server_id]["updated_at"] = self._now()
        self._save()
        return self.get_server(server_id)

    def change_version(self, server_id: str, version: str) -> dict[str, Any]:
        with self._lock:
            server = self.get_server(server_id)
            if server["status"] in ("running", "starting", "stopping"):
                raise RuntimeError("Stop the server before changing Minecraft versions.")
            self._set_operation(
                server_id,
                "Changing Minecraft version",
                "Downloading the selected Mojang server jar and backing up the current jar.",
                20,
            )
            version_id, jar_path = download_server_jar(version)
            server_dir = self._server_dir(server_id)
            current_jar = self._server_jar_path(server_id)
            if current_jar.exists():
                timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
                backup_name = f"server-{server.get('version', 'unknown')}-{timestamp}.jar.bak"
                shutil.copy2(current_jar, server_dir / backup_name)
            shutil.copy2(jar_path, current_jar)
            self._servers[server_id]["version"] = version_id
            self._servers[server_id]["updated_at"] = self._now()
            self._servers[server_id]["status"] = "stopped"
            self._servers[server_id]["last_error"] = None
            self._save()
            self._set_operation(
                server_id,
                "Minecraft version changed",
                f"Updated this server to Minecraft {version_id}. Start the server when you are ready.",
                100,
                active=False,
            )
            return self.get_server(server_id)

    def create_backup(self, server_id: str) -> dict[str, Any]:
        server_dir = self._server_dir(server_id)
        backup_dir = BACKUPS_DIR / server_id
        backup_dir.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        zip_path = backup_dir / f"{server_id}-{timestamp}.zip"
        skip_names = {"server.jar", self._server_jar_name(server_id), "libraries", "crash-reports", "cache", "versions"}
        with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            for path in server_dir.rglob("*"):
                relative = path.relative_to(server_dir)
                if relative.parts and relative.parts[0] in skip_names:
                    continue
                if path.is_file():
                    archive.write(path, relative.as_posix())
        return self._backup_info(zip_path)

    def _backup_info(self, path: Path) -> dict[str, Any]:
        stat = path.stat()
        return {
            "name": path.name,
            "path": str(path),
            "size_bytes": stat.st_size,
            "created_at": datetime.fromtimestamp(stat.st_mtime, timezone.utc).isoformat(),
        }

    def list_backups(self, server_id: str) -> list[dict[str, Any]]:
        backup_dir = BACKUPS_DIR / server_id
        if not backup_dir.exists():
            return []
        return [self._backup_info(path) for path in sorted(backup_dir.glob("*.zip"), reverse=True)]

    def delete_backup(self, server_id: str, backup_name: str) -> None:
        path = ensure_child_path(BACKUPS_DIR / server_id, BACKUPS_DIR / server_id / backup_name)
        if path.suffix.lower() != ".zip":
            raise ValueError("Only MineHost Helper zip backups can be deleted")
        path.unlink(missing_ok=True)

    def restore_backup(self, server_id: str, backup_name: str) -> dict[str, Any]:
        server = self.get_server(server_id)
        if server["status"] == "running":
            raise RuntimeError("Stop the server before restoring a backup")
        server_dir = self._server_dir(server_id)
        backup_path = ensure_child_path(BACKUPS_DIR / server_id, BACKUPS_DIR / server_id / backup_name)
        if backup_path.suffix.lower() != ".zip" or not backup_path.exists():
            raise ValueError("Backup was not found")
        safety_backup = self.create_backup(server_id)
        for child in server_dir.iterdir():
            if child.name == self._server_jar_name(server_id):
                continue
            if child.is_dir():
                shutil.rmtree(child)
            else:
                child.unlink()
        shutil.unpack_archive(str(backup_path), server_dir, "zip")
        self._servers[server_id]["updated_at"] = self._now()
        self._save()
        restored = self.get_server(server_id)
        restored["safety_backup"] = safety_backup
        return restored


server_manager = ServerManager()
