from __future__ import annotations

from pathlib import Path
import threading
from typing import Any
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles

from . import app_settings, auth_manager, backup_scheduler, discord_webhook, firewall, java_manager, minecraft_downloader, networking, update_checker
from .server_discovery import scan_existing_servers
from .config import APP_NAME, HOST, PORT, STATIC_DIR, ensure_directories
from .models import (
    AdminCommandRequest,
    AuthRequest,
    AuthSetupRequest,
    CommandRequest,
    AppSettingsUpdateRequest,
    BackupScheduleUpdateRequest,
    DiscordSettingsUpdateRequest,
    FileWriteRequest,
    FirewallFixRequest,
    PlayerActionRequest,
    PropertiesUpdateRequest,
    ServerAdoptRequest,
    ServerCreateRequest,
    VersionChangeRequest,
)
from .server_manager import server_manager

ensure_directories()

_scheduler_stop = threading.Event()
_scheduler_thread: threading.Thread | None = None


@asynccontextmanager
async def lifespan(app_instance: FastAPI):
    global _scheduler_thread
    if not _scheduler_thread or not _scheduler_thread.is_alive():
        _scheduler_stop.clear()
        _scheduler_thread = threading.Thread(target=backup_scheduler.run_scheduler, args=(server_manager, _scheduler_stop), daemon=True)
        _scheduler_thread.start()
    try:
        yield
    finally:
        _scheduler_stop.set()


app = FastAPI(
    title=APP_NAME,
    description="Local Windows-first Minecraft Java server manager.",
    version=update_checker.CURRENT_VERSION,
    lifespan=lifespan,
)


@app.middleware("http")
async def require_local_login(request: Request, call_next):
    path = request.url.path
    public_paths = (
        "/",
        "/favicon.ico",
        "/api/health",
        "/api/auth/status",
        "/api/auth/login",
        "/api/auth/setup",
    )
    if path.startswith("/static/") or path in public_paths:
        return await call_next(request)
    if auth_manager.validate_session(request.cookies.get(auth_manager.COOKIE_NAME)):
        return await call_next(request)
    if path.startswith("/api/"):
        return JSONResponse({"detail": {"message": "Sign in to MineHost Helper first."}}, status_code=401)
    return JSONResponse({"detail": "Sign in to MineHost Helper first."}, status_code=401)


def _api_error(exc: Exception) -> HTTPException:
    return HTTPException(status_code=400, detail={"message": str(exc), "try_next": "Check the page guidance and try again."})


def _to_int(value: Any, fallback: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return fallback


def _selected_server(server_id: str | None, servers: list[dict[str, Any]]) -> dict[str, Any] | None:
    if not servers:
        return None
    candidate_ids = [server_id, servers[0]["id"]]
    for candidate_id in candidate_ids:
        if not candidate_id:
            continue
        try:
            return server_manager.get_server(candidate_id)
        except KeyError:
            continue
    return None


@app.get("/api/health")
def health() -> dict[str, Any]:
    return {"ok": True, "app": APP_NAME, "host": HOST, "port": PORT}


@app.get("/api/auth/status")
def auth_status(request: Request) -> dict[str, Any]:
    status = auth_manager.status()
    status["authenticated"] = auth_manager.validate_session(request.cookies.get(auth_manager.COOKIE_NAME))
    return status


@app.post("/api/auth/setup")
def auth_setup(data: AuthSetupRequest) -> dict[str, Any]:
    try:
        return auth_manager.setup(data.username, data.password)
    except Exception as exc:
        raise _api_error(exc)


@app.post("/api/auth/login")
def auth_login(data: AuthRequest) -> Response:
    try:
        token = auth_manager.create_session(data.username, data.password)
    except Exception as exc:
        raise HTTPException(status_code=401, detail={"message": str(exc)})
    response = JSONResponse({"ok": True, "username": data.username})
    response.set_cookie(
        auth_manager.COOKIE_NAME,
        token,
        max_age=auth_manager.SESSION_SECONDS,
        httponly=True,
        samesite="strict",
    )
    return response


@app.post("/api/auth/logout")
def auth_logout(request: Request) -> Response:
    auth_manager.clear_session(request.cookies.get(auth_manager.COOKIE_NAME))
    response = JSONResponse({"ok": True})
    response.delete_cookie(auth_manager.COOKIE_NAME)
    return response


@app.get("/favicon.ico", include_in_schema=False)
def favicon() -> Response:
    svg = (
        "<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 64 64'>"
        "<rect width='64' height='64' rx='12' fill='#5b3822'/>"
        "<path d='M0 0h64v30H0z' fill='#49a343'/>"
        "<path d='M0 27h64v8H0z' fill='#257538' opacity='.65'/>"
        "<path d='M12 42h8v8h-8zm16-6h8v8h-8zm18 8h8v8h-8z' fill='#8b5a35'/>"
        "</svg>"
    )
    return Response(svg, media_type="image/svg+xml")


@app.get("/api/java/status")
def java_status() -> dict[str, Any]:
    return java_manager.status()


@app.post("/api/java/install")
def java_install() -> dict[str, Any]:
    try:
        return java_manager.install_temurin_jre()
    except Exception as exc:
        raise _api_error(exc)


@app.get("/api/minecraft/versions")
def minecraft_versions() -> dict[str, Any]:
    try:
        return minecraft_downloader.list_versions()
    except Exception as exc:
        raise _api_error(exc)


@app.get("/api/app-settings")
def get_app_settings() -> dict[str, Any]:
    return app_settings.get_settings()


@app.get("/api/app/update-check")
def update_check() -> dict[str, Any]:
    try:
        return update_checker.check_for_updates()
    except Exception as exc:
        return {
            "current_version": update_checker.CURRENT_VERSION,
            "latest_version": None,
            "update_available": False,
            "release_url": None,
            "download_url": "https://github.com/gosplunk/minehost-helper/releases/latest/download/MineHostHelperSetup.exe",
            "error": str(exc),
        }


@app.put("/api/app-settings")
def update_app_settings(data: AppSettingsUpdateRequest) -> dict[str, Any]:
    try:
        return app_settings.update_settings(data.model_dump(exclude_none=True))
    except Exception as exc:
        raise _api_error(exc)


@app.get("/api/discord/settings")
def get_discord_settings() -> dict[str, Any]:
    return discord_webhook.get_settings()


@app.put("/api/discord/settings")
def update_discord_settings(data: DiscordSettingsUpdateRequest) -> dict[str, Any]:
    try:
        return discord_webhook.update_settings(data.model_dump(exclude_none=True))
    except Exception as exc:
        raise _api_error(exc)


@app.post("/api/discord/test")
def test_discord_webhook() -> dict[str, Any]:
    try:
        return discord_webhook.test_message()
    except Exception as exc:
        raise _api_error(exc)


@app.get("/api/servers")
def list_servers() -> list[dict[str, Any]]:
    return server_manager.list_servers()


@app.post("/api/servers")
def create_server(data: ServerCreateRequest) -> dict[str, Any]:
    try:
        return server_manager.create_server(data)
    except Exception as exc:
        raise _api_error(exc)


@app.get("/api/servers/discovery")
def discover_servers() -> list[dict[str, Any]]:
    try:
        existing_paths = {str(Path(server["path"]).resolve()).lower() for server in server_manager.list_servers()}
        return [
            {**candidate, "already_added": candidate["path"].lower() in existing_paths}
            for candidate in scan_existing_servers()
        ]
    except Exception as exc:
        raise _api_error(exc)


@app.post("/api/servers/adopt")
def adopt_server(data: ServerAdoptRequest) -> dict[str, Any]:
    try:
        return server_manager.adopt_server(data)
    except Exception as exc:
        raise _api_error(exc)


@app.get("/api/servers/{server_id}")
def get_server(server_id: str) -> dict[str, Any]:
    try:
        return server_manager.get_server(server_id)
    except Exception as exc:
        raise _api_error(exc)


@app.get("/api/dashboard")
def dashboard(server_id: str | None = None) -> dict[str, Any]:
    servers = server_manager.list_servers()
    selected = _selected_server(server_id, servers)
    props = server_manager.read_properties(selected["id"]) if selected else {}
    port = _to_int(props.get("server-port", selected["port"] if selected else 25565), 25565)
    local_ip = networking.get_local_ip()
    public_ip = networking.get_public_ip()
    return {
        "servers": servers,
        "selected": selected,
        "properties": props,
        "process": server_manager.process_info(selected["id"]) if selected else {"running": False},
        "port_check": server_manager.check_port(selected["id"]) if selected else {"port": port, "available": True},
        "local_ip": local_ip,
        "public_ip": public_ip,
        "server_address": f"{public_ip or 'PUBLIC_IP'}:{port}",
        "local_address": f"{local_ip or 'LOCAL_IP'}:{port}",
        "recent_console": server_manager.console_lines(selected["id"], 20) if selected else [],
    }


@app.post("/api/servers/{server_id}/start")
def start_server(server_id: str) -> dict[str, Any]:
    try:
        server = server_manager.start(server_id)
        discord_webhook.notify_event(f"Starting Minecraft server: {server.get('name', server_id)}")
        return server
    except Exception as exc:
        raise _api_error(exc)


@app.post("/api/servers/{server_id}/stop")
def stop_server(server_id: str) -> dict[str, Any]:
    try:
        server = server_manager.stop(server_id)
        discord_webhook.notify_event(f"Stopping Minecraft server: {server.get('name', server_id)}")
        return server
    except Exception as exc:
        raise _api_error(exc)


@app.post("/api/servers/{server_id}/restart")
def restart_server(server_id: str) -> dict[str, Any]:
    try:
        server = server_manager.restart(server_id)
        discord_webhook.notify_event(f"Restarting Minecraft server: {server.get('name', server_id)}")
        return server
    except Exception as exc:
        raise _api_error(exc)


@app.post("/api/servers/{server_id}/kill")
def kill_server(server_id: str) -> dict[str, Any]:
    try:
        return server_manager.kill(server_id)
    except Exception as exc:
        raise _api_error(exc)


@app.get("/api/servers/{server_id}/port-check")
def server_port_check(server_id: str) -> dict[str, Any]:
    try:
        return server_manager.check_port(server_id)
    except Exception as exc:
        raise _api_error(exc)


@app.post("/api/servers/{server_id}/port-conflict/stop-owner")
def stop_port_owner(server_id: str) -> dict[str, Any]:
    try:
        return server_manager.stop_port_owner(server_id)
    except Exception as exc:
        raise _api_error(exc)


@app.post("/api/servers/{server_id}/port-conflict/use-next-port")
def use_next_available_port(server_id: str) -> dict[str, Any]:
    try:
        return server_manager.use_next_available_port(server_id)
    except Exception as exc:
        raise _api_error(exc)


@app.get("/api/servers/{server_id}/console")
def console(server_id: str, limit: int = Query(200, ge=1, le=1000)) -> dict[str, Any]:
    try:
        return {"lines": server_manager.console_lines(server_id, limit)}
    except Exception as exc:
        raise _api_error(exc)


@app.post("/api/servers/{server_id}/command")
def send_command(server_id: str, data: CommandRequest) -> dict[str, bool]:
    try:
        server_manager.send_command(server_id, data.command)
        return {"ok": True}
    except Exception as exc:
        raise _api_error(exc)


@app.get("/api/servers/{server_id}/command-center")
def command_center(server_id: str) -> dict[str, Any]:
    try:
        return {
            "server": server_manager.get_server(server_id),
            "players": server_manager.player_lists(server_id),
            "resources": server_manager.resource_snapshot(server_id),
            "recent_console": server_manager.console_lines(server_id, 12),
        }
    except Exception as exc:
        raise _api_error(exc)


@app.post("/api/servers/{server_id}/admin-command")
def admin_command(server_id: str, data: AdminCommandRequest) -> dict[str, Any]:
    try:
        return server_manager.admin_command(server_id, data.model_dump(exclude_none=True))
    except Exception as exc:
        raise _api_error(exc)


@app.get("/api/servers/{server_id}/players")
def players(server_id: str) -> dict[str, Any]:
    try:
        return server_manager.player_lists(server_id)
    except Exception as exc:
        raise _api_error(exc)


@app.post("/api/servers/{server_id}/players/{action}")
def player_action(server_id: str, action: str, data: PlayerActionRequest) -> dict[str, bool]:
    try:
        server_manager.player_action(server_id, action, data.player, data.reason)
        return {"ok": True}
    except Exception as exc:
        raise _api_error(exc)


@app.get("/api/servers/{server_id}/diagnostics")
def diagnostics(server_id: str) -> dict[str, Any]:
    try:
        return {"findings": server_manager.diagnose(server_id), "disk": server_manager.server_disk_usage(server_id)}
    except Exception as exc:
        raise _api_error(exc)


@app.get("/api/servers/{server_id}/files")
def list_files(server_id: str, path: str = "") -> dict[str, Any]:
    try:
        return server_manager.list_files(server_id, path)
    except Exception as exc:
        raise _api_error(exc)


@app.get("/api/servers/{server_id}/world-map")
def world_map(server_id: str, dimension: str = Query("overworld")) -> dict[str, Any]:
    try:
        return server_manager.world_map(server_id, dimension)
    except Exception as exc:
        raise _api_error(exc)


@app.get("/api/servers/{server_id}/files/read")
def read_file(server_id: str, path: str) -> dict[str, Any]:
    try:
        return server_manager.read_file(server_id, path)
    except Exception as exc:
        raise _api_error(exc)


@app.put("/api/servers/{server_id}/files/write")
def write_file(server_id: str, path: str, data: FileWriteRequest) -> dict[str, Any]:
    try:
        return server_manager.write_file(server_id, path, data.content)
    except Exception as exc:
        raise _api_error(exc)


@app.get("/api/servers/{server_id}/log")
def download_log(server_id: str) -> FileResponse:
    path = server_manager.log_file(server_id)
    if not path:
        raise HTTPException(status_code=404, detail="No log file exists yet")
    return FileResponse(path, filename=Path(path).name)


@app.get("/api/servers/{server_id}/properties")
def read_server_properties(server_id: str) -> dict[str, Any]:
    try:
        return server_manager.read_properties(server_id)
    except Exception as exc:
        raise _api_error(exc)


@app.put("/api/servers/{server_id}/properties")
def update_server_properties(server_id: str, data: PropertiesUpdateRequest) -> dict[str, Any]:
    try:
        return server_manager.write_properties(server_id, data.properties)
    except Exception as exc:
        raise _api_error(exc)


@app.post("/api/servers/{server_id}/properties/save-and-restart")
def save_and_restart(server_id: str, data: PropertiesUpdateRequest) -> dict[str, Any]:
    try:
        server_manager.write_properties(server_id, data.properties)
        return server_manager.restart(server_id)
    except Exception as exc:
        raise _api_error(exc)


@app.post("/api/servers/{server_id}/version")
def change_server_version(server_id: str, data: VersionChangeRequest) -> dict[str, Any]:
    try:
        return server_manager.change_version(server_id, data.version)
    except Exception as exc:
        raise _api_error(exc)


@app.get("/api/servers/{server_id}/backups")
def list_backups(server_id: str) -> list[dict[str, Any]]:
    try:
        return server_manager.list_backups(server_id)
    except Exception as exc:
        raise _api_error(exc)


@app.get("/api/servers/{server_id}/backup-schedule")
def get_backup_schedule(server_id: str) -> dict[str, Any]:
    return backup_scheduler.get_schedule(server_id)


@app.put("/api/servers/{server_id}/backup-schedule")
def update_backup_schedule(server_id: str, data: BackupScheduleUpdateRequest) -> dict[str, Any]:
    try:
        return backup_scheduler.update_schedule(server_id, data.model_dump())
    except Exception as exc:
        raise _api_error(exc)


@app.post("/api/servers/{server_id}/backups")
def create_backup(server_id: str) -> dict[str, Any]:
    try:
        backup = server_manager.create_backup(server_id)
        discord_webhook.notify_event(f"Created Minecraft server backup: {backup.get('name', server_id)}")
        return backup
    except Exception as exc:
        raise _api_error(exc)


@app.post("/api/servers/{server_id}/backups/{backup_name}/restore")
def restore_backup(server_id: str, backup_name: str) -> dict[str, Any]:
    try:
        return server_manager.restore_backup(server_id, backup_name)
    except Exception as exc:
        raise _api_error(exc)


@app.delete("/api/servers/{server_id}/backups/{backup_name}")
def delete_backup(server_id: str, backup_name: str) -> dict[str, bool]:
    try:
        server_manager.delete_backup(server_id, backup_name)
        return {"ok": True}
    except Exception as exc:
        raise _api_error(exc)


@app.get("/api/networking/status")
def networking_status(server_id: str | None = None) -> dict[str, Any]:
    servers = server_manager.list_servers()
    selected = _selected_server(server_id, servers)
    props = server_manager.read_properties(selected["id"]) if selected else {"server-port": 25565}
    port = int(props.get("server-port", 25565))
    local_ip = networking.get_local_ip()
    public_ip = networking.get_public_ip()
    local_open = networking.is_local_port_open(port)
    return {
        "port": port,
        "local_ip": local_ip,
        "public_ip": public_ip,
        "local_open": local_open,
        "firewall": firewall.check_firewall_rule(port),
        "public": networking.public_port_status(port, public_ip, local_open),
        "router_instructions": networking.router_instructions(port, local_ip),
    }


@app.post("/api/networking/firewall/fix")
def fix_firewall(data: FirewallFixRequest) -> dict[str, Any]:
    try:
        return firewall.create_firewall_rule(data.port)
    except Exception as exc:
        raise _api_error(exc)


@app.get("/api/networking/local-port-test")
def local_port_test(port: int = Query(25565, ge=1, le=65535)) -> dict[str, Any]:
    return {"port": port, "open": networking.is_local_port_open(port)}


@app.get("/api/networking/public-port-test")
def public_port_test(port: int = Query(25565, ge=1, le=65535)) -> dict[str, Any]:
    local_open = networking.is_local_port_open(port)
    public_ip = networking.get_public_ip()
    return networking.public_port_status(port, public_ip, local_open, check_external=True)


@app.post("/api/networking/router/upnp")
def upnp_attempt() -> dict[str, Any]:
    return {
        "success": False,
        "message": "Automatic router setup is not enabled in this MVP. Use the router instructions for a reliable setup.",
    }


@app.get("/")
def root() -> FileResponse:
    index = STATIC_DIR / "index.html"
    if index.exists():
        return FileResponse(index)
    raise HTTPException(status_code=404, detail="Frontend static files are missing")


if STATIC_DIR.exists():
    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
