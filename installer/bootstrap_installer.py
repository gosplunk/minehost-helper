from __future__ import annotations

import argparse
import base64
from dataclasses import dataclass
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import time
import tkinter as tk
import winreg
from pathlib import Path
from tkinter import filedialog, messagebox

APP_NAME = "MineHost Helper"
APP_VERSION = "0.1.17"
PUBLISHER = "MineHost Helper"
EXE_NAME = "MineHostHelper.exe"
UNINSTALL_EXE_NAME = "Uninstall MineHost Helper.exe"
UNINSTALL_KEY = r"Software\Microsoft\Windows\CurrentVersion\Uninstall\MineHostHelper"
RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
RUN_VALUE_NAME = "MineHost Helper"
JAVA_FEATURE_VERSION = 25
PBKDF2_ITERATIONS = 260_000


@dataclass
class InstallResult:
    app_path: Path
    java_ready: bool
    java_message: str


def bundle_dir() -> Path:
    return Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent))


def payload_exe() -> Path:
    return bundle_dir() / "payload" / EXE_NAME


def payload_uninstaller() -> Path:
    return bundle_dir() / "payload" / UNINSTALL_EXE_NAME


def default_install_dir() -> Path:
    return Path(os.environ["LOCALAPPDATA"]) / "MineHostHelper"


def start_menu_shortcut_path() -> Path:
    return Path(os.environ["APPDATA"]) / "Microsoft" / "Windows" / "Start Menu" / "Programs" / "MineHost Helper.lnk"


def start_menu_uninstall_shortcut_path() -> Path:
    return Path(os.environ["APPDATA"]) / "Microsoft" / "Windows" / "Start Menu" / "Programs" / "Uninstall MineHost Helper.lnk"


def desktop_shortcut_path() -> Path:
    return Path(os.environ["USERPROFILE"]) / "Desktop" / "MineHost Helper.lnk"


def powershell_quote(value: Path | str) -> str:
    return str(value).replace("'", "''")


def create_shortcut(shortcut_path: Path, target: Path, description: str = APP_NAME) -> None:
    shortcut_path.parent.mkdir(parents=True, exist_ok=True)
    script = f"""
$WshShell = New-Object -ComObject WScript.Shell
$Shortcut = $WshShell.CreateShortcut('{powershell_quote(shortcut_path)}')
$Shortcut.TargetPath = '{powershell_quote(target)}'
$Shortcut.WorkingDirectory = '{powershell_quote(target.parent)}'
$Shortcut.IconLocation = '{powershell_quote(target)}'
$Shortcut.Description = '{powershell_quote(description)}'
$Shortcut.Save()
"""
    subprocess.run(
        ["powershell", "-NoLogo", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", script],
        check=False,
        creationflags=subprocess.CREATE_NO_WINDOW,
    )


def remove_shortcuts() -> None:
    for shortcut in (start_menu_shortcut_path(), start_menu_uninstall_shortcut_path(), desktop_shortcut_path()):
        shortcut.unlink(missing_ok=True)


def register_uninstaller(target_dir: Path) -> None:
    app_exe = target_dir / EXE_NAME
    uninstaller = target_dir / UNINSTALL_EXE_NAME
    with winreg.CreateKey(winreg.HKEY_CURRENT_USER, UNINSTALL_KEY) as key:
        winreg.SetValueEx(key, "DisplayName", 0, winreg.REG_SZ, APP_NAME)
        winreg.SetValueEx(key, "DisplayVersion", 0, winreg.REG_SZ, APP_VERSION)
        winreg.SetValueEx(key, "Publisher", 0, winreg.REG_SZ, PUBLISHER)
        winreg.SetValueEx(key, "InstallLocation", 0, winreg.REG_SZ, str(target_dir))
        winreg.SetValueEx(key, "DisplayIcon", 0, winreg.REG_SZ, str(app_exe))
        winreg.SetValueEx(key, "UninstallString", 0, winreg.REG_SZ, f'"{uninstaller}"')
        winreg.SetValueEx(key, "QuietUninstallString", 0, winreg.REG_SZ, f'"{uninstaller}" --silent')
        winreg.SetValueEx(key, "NoModify", 0, winreg.REG_DWORD, 1)
        winreg.SetValueEx(key, "NoRepair", 0, winreg.REG_DWORD, 1)


def unregister_uninstaller() -> None:
    try:
        winreg.DeleteKey(winreg.HKEY_CURRENT_USER, UNINSTALL_KEY)
    except FileNotFoundError:
        pass


def remove_startup_entry() -> None:
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY, 0, winreg.KEY_SET_VALUE) as key:
            winreg.DeleteValue(key, RUN_VALUE_NAME)
    except FileNotFoundError:
        pass


def stop_running_app() -> None:
    subprocess.run(
        ["taskkill", "/IM", EXE_NAME, "/T", "/F"],
        capture_output=True,
        text=True,
        check=False,
        creationflags=subprocess.CREATE_NO_WINDOW,
    )
    wait_for_processes_to_exit([EXE_NAME], timeout_seconds=12)


def wait_for_processes_to_exit(process_names: list[str], timeout_seconds: int = 10) -> bool:
    names = {name.lower() for name in process_names}
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        result = subprocess.run(
            ["tasklist", "/FO", "CSV", "/NH"],
            capture_output=True,
            text=True,
            check=False,
            creationflags=subprocess.CREATE_NO_WINDOW,
        )
        running = False
        for line in result.stdout.splitlines():
            image = line.split(",", 1)[0].strip().strip('"').lower()
            if image in names:
                running = True
                break
        if not running:
            return True
        time.sleep(0.5)
    return False


def parse_java_feature_version(version_text: str) -> int | None:
    match = re.search(r'version "([^"]+)"', version_text)
    if not match:
        return None
    raw = match.group(1)
    if raw.startswith("1."):
        parts = raw.split(".")
        return int(parts[1]) if len(parts) > 1 and parts[1].isdigit() else None
    feature = raw.split(".", 1)[0]
    return int(feature) if feature.isdigit() else None


def java_feature_version(java_path: Path) -> int | None:
    try:
        result = subprocess.run(
            [str(java_path), "-version"],
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
            creationflags=subprocess.CREATE_NO_WINDOW,
        )
    except Exception:
        return None
    return parse_java_feature_version(result.stderr or result.stdout or "")


def java_readiness(target_dir: Path, include_target_runtimes: bool = True) -> tuple[bool, str]:
    target_dir = target_dir.expanduser()
    candidates: list[tuple[str, Path]] = []
    if include_target_runtimes:
        candidates.extend(("bundled", path) for path in sorted((target_dir / "runtimes" / "java").glob("**/bin/java.exe")))
    system_java = shutil.which("java")
    if system_java:
        candidates.append(("system", Path(system_java)))

    checked: list[str] = []
    for source, java_path in candidates:
        feature = java_feature_version(java_path)
        if feature is None:
            checked.append(f"{source} Java at {java_path} could not be read")
            continue
        if feature >= JAVA_FEATURE_VERSION:
            label = "Bundled" if source == "bundled" else "System"
            return True, f"{label} Java {feature} is already available. Setup will skip Java download."
        checked.append(f"{source} Java {feature} is too old")

    if checked:
        return False, f"Java {JAVA_FEATURE_VERSION}+ was not found ({'; '.join(checked)}). Setup will prepare Temurin Java."
    return False, f"Java {JAVA_FEATURE_VERSION}+ was not found. Setup will prepare Temurin Java."


def _b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode("ascii").rstrip("=")


def _hash_password(password: str) -> dict[str, object]:
    salt = os.urandom(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, PBKDF2_ITERATIONS)
    return {
        "algorithm": "pbkdf2_sha256",
        "iterations": PBKDF2_ITERATIONS,
        "salt": _b64(salt),
        "hash": _b64(digest),
    }


def auth_file(target_dir: Path) -> Path:
    return target_dir / "app_data" / "auth.json"


def read_existing_auth_username(target_dir: Path) -> str | None:
    try:
        data = json.loads(auth_file(target_dir).read_text(encoding="utf-8"))
        username = str(data.get("username") or "").strip()
        return username or None
    except Exception:
        return None


def validate_auth_inputs(username: str, password: str, confirm: str) -> tuple[str, str]:
    cleaned = username.strip()
    if not 3 <= len(cleaned) <= 32:
        raise ValueError("Web login username must be 3 to 32 characters.")
    if not all(char.isalnum() or char in "._-" for char in cleaned):
        raise ValueError("Web login username can use letters, numbers, dots, dashes, and underscores.")
    if len(password) < 8:
        raise ValueError("Web login password must be at least 8 characters.")
    if password != confirm:
        raise ValueError("Web login passwords do not match.")
    return cleaned, password


def write_auth_file(target_dir: Path, username: str, password: str) -> None:
    path = auth_file(target_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {
                "username": username,
                "password": _hash_password(password),
                "sessions": {},
                "updated_at": time.time(),
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )


def prepare_java_runtime(app_exe: Path) -> tuple[bool, str]:
    error_file = app_exe.parent / "java-setup-error.txt"
    error_file.unlink(missing_ok=True)
    result = subprocess.run(
        [str(app_exe), "--prepare-java", "--java-version", str(JAVA_FEATURE_VERSION)],
        cwd=app_exe.parent,
        capture_output=True,
        text=True,
        timeout=420,
        check=False,
        creationflags=subprocess.CREATE_NO_WINDOW,
    )
    output = (result.stderr or result.stdout or "").strip()
    if result.returncode == 0:
        return True, f"Temurin Java {JAVA_FEATURE_VERSION} is ready."
    if error_file.exists():
        output = error_file.read_text(encoding="utf-8", errors="replace").strip()
    if not output:
        output = f"Java setup exited with code {result.returncode}."
    return False, output


def schedule_delete_file(path: Path) -> None:
    script = f"Start-Sleep -Seconds 3; Remove-Item -LiteralPath '{powershell_quote(path)}' -Force -ErrorAction SilentlyContinue"
    subprocess.Popen(
        ["powershell", "-NoLogo", "-NoProfile", "-WindowStyle", "Hidden", "-Command", script],
        creationflags=subprocess.CREATE_NO_WINDOW,
    )


def schedule_remove_dir(path: Path) -> None:
    script = f"Start-Sleep -Seconds 3; Remove-Item -LiteralPath '{powershell_quote(path)}' -Recurse -Force -ErrorAction SilentlyContinue"
    subprocess.Popen(
        ["powershell", "-NoLogo", "-NoProfile", "-WindowStyle", "Hidden", "-Command", script],
        creationflags=subprocess.CREATE_NO_WINDOW,
    )


def read_installed_dir() -> Path | None:
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, UNINSTALL_KEY) as key:
            value, _ = winreg.QueryValueEx(key, "InstallLocation")
            return Path(value)
    except FileNotFoundError:
        return None


def read_installed_version() -> str | None:
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, UNINSTALL_KEY) as key:
            value, _ = winreg.QueryValueEx(key, "DisplayVersion")
            return str(value)
    except FileNotFoundError:
        return None


def validate_install_dir(target_dir: Path) -> Path:
    target_dir = target_dir.expanduser().resolve()
    if target_dir.anchor == str(target_dir):
        raise ValueError("Choose a normal folder, not a drive root.")
    return target_dir


def is_safe_install_folder(target_dir: Path) -> bool:
    if target_dir.name.lower() in {"minehosthelper", "minehost helper"}:
        return True
    app_exe = target_dir / EXE_NAME
    uninstaller_exe = target_dir / UNINSTALL_EXE_NAME
    if app_exe.exists() or uninstaller_exe.exists():
        return True
    return False


def remove_install_folder_for_clean_install(target_dir: Path) -> None:
    target_dir = validate_install_dir(target_dir)
    if not target_dir.exists():
        return
    if not is_safe_install_folder(target_dir):
        raise ValueError(f"Refusing to clean an unrecognized install folder: {target_dir}")
    if target_dir in Path(sys.executable).resolve().parents:
        raise RuntimeError(
            "Clean Install cannot run while the setup app is inside the MineHost Helper install folder. "
            "Move MineHostHelperSetup.exe to Downloads or Desktop, then run it again."
        )

    parent = target_dir.parent
    timestamp = time.strftime("%Y%m%d-%H%M%S")
    archived_dir = parent / f"{target_dir.name}.old-{timestamp}"
    suffix = 1
    while archived_dir.exists():
        suffix += 1
        archived_dir = parent / f"{target_dir.name}.old-{timestamp}-{suffix}"

    last_error: Exception | None = None
    for attempt in range(1, 7):
        try:
            target_dir.rename(archived_dir)
            schedule_remove_dir(archived_dir)
            return
        except OSError as exc:
            last_error = exc
            time.sleep(0.75 * attempt)

    try:
        shutil.rmtree(target_dir)
        return
    except OSError as exc:
        last_error = exc

    raise RuntimeError(
        "Clean Install could not remove the old MineHost Helper folder because Windows still has a file open. "
        "Close MineHost Helper from the tray, close any Minecraft server windows, wait a few seconds, then try again. "
        f"Locked folder: {target_dir}. Windows error: {last_error}"
    ) from last_error


def install(
    target_dir: Path,
    create_desktop_shortcut: bool = True,
    launch_after: bool = True,
    clean_existing: bool = False,
    prepare_java: bool = True,
    auth_username: str | None = None,
    auth_password: str | None = None,
    keep_existing_auth: bool = True,
) -> InstallResult:
    source = payload_exe()
    uninstaller_source = payload_uninstaller()
    if not source.exists():
        raise FileNotFoundError(f"Installer payload is missing: {source}")
    if not uninstaller_source.exists():
        raise FileNotFoundError(f"Uninstaller payload is missing: {uninstaller_source}")

    target_dir = validate_install_dir(target_dir)

    stop_running_app()
    if clean_existing:
        remove_shortcuts()
        unregister_uninstaller()
        remove_startup_entry()
        remove_install_folder_for_clean_install(target_dir)

    target_dir.mkdir(parents=True, exist_ok=True)

    app_target = target_dir / EXE_NAME
    uninstall_target = target_dir / UNINSTALL_EXE_NAME
    shutil.copy2(source, app_target)
    shutil.copy2(uninstaller_source, uninstall_target)

    create_shortcut(start_menu_shortcut_path(), app_target, APP_NAME)
    create_shortcut(start_menu_uninstall_shortcut_path(), uninstall_target, f"Uninstall {APP_NAME}")

    if create_desktop_shortcut:
        create_shortcut(desktop_shortcut_path(), app_target, APP_NAME)
    else:
        desktop_shortcut_path().unlink(missing_ok=True)

    register_uninstaller(target_dir)

    if auth_username and auth_password:
        write_auth_file(target_dir, auth_username, auth_password)
    elif not keep_existing_auth or not auth_file(target_dir).exists():
        raise ValueError("Create a web login username and password before installing.")

    java_ready = False
    java_message = "Java setup was skipped."
    if prepare_java:
        try:
            java_ready, java_message = prepare_java_runtime(app_target)
        except subprocess.TimeoutExpired:
            java_message = (
                "Java setup took too long and was skipped. Open MineHost Helper and click "
                "Download Temurin Java Now before starting a server."
            )
        except Exception as exc:
            java_message = f"Java setup could not finish: {exc}"
        if not java_ready:
            (target_dir / "java-setup-warning.txt").write_text(java_message, encoding="utf-8")

    if launch_after:
        subprocess.Popen([str(app_target)], cwd=target_dir)
    return InstallResult(app_target, java_ready, java_message)


def uninstall(target_dir: Path | None = None, keep_data: bool = False, silent: bool = False) -> None:
    target_dir = (target_dir or read_installed_dir() or default_install_dir()).expanduser().resolve()
    if not silent:
        message = (
            f"Uninstall {APP_NAME} from:\n\n{target_dir}\n\n"
            "Minecraft servers, backups, and downloaded runtimes will be removed unless you choose to keep data."
        )
        if not messagebox.askyesno(f"Uninstall {APP_NAME}", message):
            return

    stop_running_app()
    remove_shortcuts()
    unregister_uninstaller()
    remove_startup_entry()

    app_exe = target_dir / EXE_NAME
    uninstaller_exe = target_dir / UNINSTALL_EXE_NAME

    if keep_data:
        app_exe.unlink(missing_ok=True)
        if Path(sys.executable).resolve() == uninstaller_exe.resolve():
            schedule_delete_file(uninstaller_exe)
        else:
            uninstaller_exe.unlink(missing_ok=True)
        return

    if target_dir.exists():
        # Avoid deleting broad accidental targets.
        if target_dir.name.lower() not in {"minehosthelper", "minehost helper"}:
            marker_files = {app_exe.name, uninstaller_exe.name}
            existing = {path.name for path in target_dir.iterdir() if path.is_file()}
            if not marker_files & existing:
                raise ValueError(f"Refusing to remove unrecognized install folder: {target_dir}")
        if target_dir in Path(sys.executable).resolve().parents:
            schedule_remove_dir(target_dir)
        else:
            shutil.rmtree(target_dir, ignore_errors=True)


class InstallerUi:
    def __init__(self) -> None:
        self.root = tk.Tk()
        self.root.title(f"{APP_NAME} Setup")
        self.root.geometry("760x760")
        self.root.minsize(700, 640)
        self.root.resizable(True, True)
        self.root.configure(bg="#fffdf6")
        self.desktop_var = tk.BooleanVar(value=True)
        self.launch_var = tk.BooleanVar(value=True)
        self.prepare_java_var = tk.BooleanVar(value=True)
        self.status_var = tk.StringVar(value="")
        self.java_status_var = tk.StringVar(value="")
        self.installed_dir = read_installed_dir()
        self.installed_version = read_installed_version()
        self.install_dir_var = tk.StringVar(value=str(self.installed_dir or default_install_dir()))
        self.existing_auth_username = read_existing_auth_username(self.installed_dir) if self.installed_dir else None
        self.keep_existing_auth_var = tk.BooleanVar(value=bool(self.existing_auth_username))
        self.auth_username_var = tk.StringVar(value=self.existing_auth_username or os.environ.get("USERNAME", "host"))
        self.auth_password_var = tk.StringVar(value="")
        self.auth_confirm_var = tk.StringVar(value="")
        self.install_buttons: list[tk.Button] = []
        self.prepare_java_checkbox: tk.Checkbutton | None = None
        self.auth_entries: list[tk.Entry] = []
        self._build()
        self._refresh_java_prepare_state()
        self._refresh_auth_state()
        self._fit_window_to_content()

    def _fit_window_to_content(self) -> None:
        self.root.update_idletasks()
        width = min(max(720, self.root.winfo_reqwidth() + 24), self.root.winfo_screenwidth() - 80)
        height = min(max(700, self.root.winfo_reqheight() + 24), self.root.winfo_screenheight() - 80)
        self.root.geometry(f"{width}x{height}")

    def _build(self) -> None:
        frame = tk.Frame(self.root, padx=28, pady=24, bg="#fffdf6")
        frame.pack(fill="both", expand=True)

        tk.Label(
            frame,
            text=f"{APP_NAME} Setup",
            font=("Segoe UI", 22, "bold"),
            bg="#fffdf6",
            fg="#243023",
        ).pack(anchor="w")

        if self.installed_dir:
            status_text = (
                f"{APP_NAME} is already installed.\n\n"
                f"Installed version: {self.installed_version or 'unknown'}\n"
                f"Installer version: {APP_VERSION}\n"
                f"Location: {self.installed_dir}\n\n"
                "Update / Repair keeps your Minecraft worlds, backups, Java, logs, and settings. "
                "Clean Install starts over and only runs after a clear warning."
            )
            status_bg = "#eef7e8"
            status_fg = "#1f6d36"
        else:
            status_text = (
                f"Choose where {APP_NAME} should live. Server files, backups, Java, and logs are stored "
                "inside the selected folder so everything stays together."
            )
            status_bg = "#fffdf6"
            status_fg = "#687466"

        tk.Label(
            frame,
            text=status_text,
            font=("Segoe UI", 10),
            bg=status_bg,
            fg=status_fg,
            padx=12 if self.installed_dir else 0,
            pady=10 if self.installed_dir else 0,
            wraplength=640,
            justify="left",
        ).pack(fill="x", pady=(8, 18))

        path_frame = tk.Frame(frame, bg="#fffdf6")
        path_frame.pack(fill="x", pady=(0, 12))
        tk.Label(path_frame, text="Install location", bg="#fffdf6", fg="#243023", font=("Segoe UI", 10, "bold")).pack(anchor="w")
        path_row = tk.Frame(path_frame, bg="#fffdf6")
        path_row.pack(fill="x", pady=(6, 0))
        install_dir_entry = tk.Entry(path_row, textvariable=self.install_dir_var, font=("Segoe UI", 10))
        install_dir_entry.pack(side="left", fill="x", expand=True)
        install_dir_entry.bind("<FocusOut>", lambda _event: self._refresh_java_prepare_state())
        install_dir_entry.bind("<Return>", lambda _event: self._refresh_java_prepare_state())
        tk.Button(
            path_row,
            text="Browse...",
            command=self._browse,
            bg="#e6ecd9",
            fg="#243023",
            relief="flat",
            padx=14,
            pady=6,
            font=("Segoe UI", 10, "bold"),
        ).pack(side="left", padx=(10, 0))

        tk.Checkbutton(
            frame,
            text="Create Desktop shortcut",
            variable=self.desktop_var,
            bg="#fffdf6",
            fg="#243023",
            activebackground="#fffdf6",
            font=("Segoe UI", 10),
        ).pack(anchor="w")

        tk.Checkbutton(
            frame,
            text="Launch after install",
            variable=self.launch_var,
            bg="#fffdf6",
            fg="#243023",
            activebackground="#fffdf6",
            font=("Segoe UI", 10),
        ).pack(anchor="w", pady=(4, 16))

        self.prepare_java_checkbox = tk.Checkbutton(
            frame,
            text=f"Prepare bundled Temurin Java {JAVA_FEATURE_VERSION} now (recommended)",
            variable=self.prepare_java_var,
            bg="#fffdf6",
            fg="#243023",
            activebackground="#fffdf6",
            font=("Segoe UI", 10),
        )
        self.prepare_java_checkbox.pack(anchor="w", pady=(0, 6))

        tk.Label(
            frame,
            textvariable=self.java_status_var,
            font=("Segoe UI", 9),
            bg="#fffdf6",
            fg="#687466",
            wraplength=620,
            justify="left",
        ).pack(fill="x", pady=(0, 16))

        auth_frame = tk.Frame(frame, bg="#fffdf6")
        auth_frame.pack(fill="x", pady=(0, 16))
        tk.Label(
            auth_frame,
            text="Web login",
            bg="#fffdf6",
            fg="#243023",
            font=("Segoe UI", 11, "bold"),
        ).pack(anchor="w")
        tk.Label(
            auth_frame,
            text=(
                "This protects the local browser control panel. Friends should never need this password. "
                "If you update MineHost Helper, setup can keep the existing login."
            ),
            bg="#fffdf6",
            fg="#687466",
            font=("Segoe UI", 9),
            wraplength=620,
            justify="left",
        ).pack(fill="x", pady=(3, 8))

        if self.existing_auth_username:
            tk.Checkbutton(
                auth_frame,
                text=f"Keep existing login for '{self.existing_auth_username}'",
                variable=self.keep_existing_auth_var,
                command=self._refresh_auth_state,
                bg="#fffdf6",
                fg="#243023",
                activebackground="#fffdf6",
                font=("Segoe UI", 10),
            ).pack(anchor="w", pady=(0, 8))

        credentials_grid = tk.Frame(auth_frame, bg="#fffdf6")
        credentials_grid.pack(fill="x")
        tk.Label(credentials_grid, text="Username", bg="#fffdf6", fg="#243023", font=("Segoe UI", 9, "bold")).grid(row=0, column=0, sticky="w")
        username_entry = tk.Entry(credentials_grid, textvariable=self.auth_username_var, font=("Segoe UI", 10))
        username_entry.grid(row=1, column=0, sticky="ew", padx=(0, 10), pady=(4, 8))
        tk.Label(credentials_grid, text="Password", bg="#fffdf6", fg="#243023", font=("Segoe UI", 9, "bold")).grid(row=0, column=1, sticky="w")
        password_entry = tk.Entry(credentials_grid, textvariable=self.auth_password_var, show="*", font=("Segoe UI", 10))
        password_entry.grid(row=1, column=1, sticky="ew", padx=(0, 10), pady=(4, 8))
        tk.Label(credentials_grid, text="Confirm password", bg="#fffdf6", fg="#243023", font=("Segoe UI", 9, "bold")).grid(row=0, column=2, sticky="w")
        confirm_entry = tk.Entry(credentials_grid, textvariable=self.auth_confirm_var, show="*", font=("Segoe UI", 10))
        confirm_entry.grid(row=1, column=2, sticky="ew", pady=(4, 8))
        credentials_grid.columnconfigure(0, weight=1)
        credentials_grid.columnconfigure(1, weight=1)
        credentials_grid.columnconfigure(2, weight=1)
        self.auth_entries = [username_entry, password_entry, confirm_entry]

        tk.Label(
            frame,
            text=(
                "An uninstaller will be added to Windows Apps & Features and the Start Menu. "
                "Preparing Java may take a few minutes on first install."
            ),
            font=("Segoe UI", 9),
            bg="#eef7e8",
            fg="#1f6d36",
            padx=12,
            pady=10,
            wraplength=620,
            justify="left",
        ).pack(fill="x", pady=(0, 18))

        tk.Label(
            frame,
            textvariable=self.status_var,
            font=("Segoe UI", 9, "bold"),
            bg="#fffdf6",
            fg="#687466",
            wraplength=620,
            justify="left",
        ).pack(fill="x", pady=(0, 12))

        button_row = tk.Frame(frame, bg="#fffdf6")
        button_row.pack(fill="x")

        primary_text = "Update / Repair" if self.installed_dir else "Install"
        primary_button = tk.Button(
            button_row,
            text=primary_text,
            command=lambda: self._install_clicked(clean_existing=False),
            bg="#2f8f46",
            fg="#ffffff",
            activebackground="#1f6d36",
            activeforeground="#ffffff",
            relief="flat",
            padx=22,
            pady=10,
            font=("Segoe UI", 10, "bold"),
        )
        primary_button.pack(side="left")
        self.install_buttons.append(primary_button)

        if self.installed_dir:
            clean_button = tk.Button(
                button_row,
                text="Clean Install",
                command=lambda: self._install_clicked(clean_existing=True),
                bg="#bb3b33",
                fg="#ffffff",
                activebackground="#9d2d26",
                activeforeground="#ffffff",
                relief="flat",
                padx=22,
                pady=10,
                font=("Segoe UI", 10, "bold"),
            )
            clean_button.pack(side="left", padx=(10, 0))
            self.install_buttons.append(clean_button)

        tk.Button(
            button_row,
            text="Cancel",
            command=self.root.destroy,
            bg="#e6ecd9",
            fg="#243023",
            relief="flat",
            padx=22,
            pady=10,
            font=("Segoe UI", 10, "bold"),
        ).pack(side="left", padx=(10, 0))

    def _browse(self) -> None:
        selected = filedialog.askdirectory(initialdir=str(Path(self.install_dir_var.get()).parent))
        if selected:
            path = Path(selected)
            if path.name.lower() not in {"minehosthelper", "minehost helper"}:
                path = path / "MineHostHelper"
            self.install_dir_var.set(str(path))
            self._refresh_java_prepare_state()

    def _refresh_java_prepare_state(self) -> None:
        try:
            ready, message = java_readiness(Path(self.install_dir_var.get()))
        except Exception as exc:
            ready = False
            message = f"Java check could not run yet: {exc}"
        self.java_status_var.set(message)
        if ready:
            self.prepare_java_var.set(False)
            if self.prepare_java_checkbox:
                self.prepare_java_checkbox.configure(state="disabled")
        else:
            self.prepare_java_var.set(True)
            if self.prepare_java_checkbox:
                self.prepare_java_checkbox.configure(state="normal")

    def _refresh_auth_state(self) -> None:
        state = "disabled" if self.existing_auth_username and self.keep_existing_auth_var.get() else "normal"
        for entry in self.auth_entries:
            entry.configure(state=state)

    def _install_clicked(self, clean_existing: bool) -> None:
        try:
            for button in self.install_buttons:
                button.configure(state="disabled")
            if clean_existing:
                message = (
                    "Clean Install will remove the existing MineHost Helper install folder before reinstalling.\n\n"
                    "This deletes local MineHost Helper servers, backups, downloaded Java, logs, and app settings "
                    "inside the selected folder.\n\n"
                    "Use Update / Repair instead if you want to keep existing Minecraft worlds."
                )
                if not messagebox.askyesno("Clean Install", message, icon="warning"):
                    for button in self.install_buttons:
                        button.configure(state="normal")
                    return
            self.status_var.set(
                "Installing MineHost Helper. Dependencies will be skipped when they are already ready."
            )
            self.root.update_idletasks()
            target_dir = Path(self.install_dir_var.get())
            java_ready, _java_message = java_readiness(target_dir, include_target_runtimes=not clean_existing)
            prepare_java_requested = self.prepare_java_var.get() and not java_ready
            if clean_existing and not java_ready:
                prepare_java_requested = True
            target_auth_username = read_existing_auth_username(target_dir)
            if self.keep_existing_auth_var.get() and not target_auth_username:
                self.existing_auth_username = None
                self.keep_existing_auth_var.set(False)
                self._refresh_auth_state()
                raise ValueError("No existing web login was found in the selected install location. Enter a new username and password.")
            if clean_existing and self.existing_auth_username and self.keep_existing_auth_var.get():
                self.keep_existing_auth_var.set(False)
                self._refresh_auth_state()
                raise ValueError("Clean Install deletes the old login. Enter a new web login password, then click Clean Install again.")
            keep_existing_auth = bool(target_auth_username and self.keep_existing_auth_var.get() and not clean_existing)
            auth_username = None
            auth_password = None
            if not keep_existing_auth:
                auth_username, auth_password = validate_auth_inputs(
                    self.auth_username_var.get(),
                    self.auth_password_var.get(),
                    self.auth_confirm_var.get(),
                )
            result = install(
                target_dir=target_dir,
                create_desktop_shortcut=self.desktop_var.get(),
                launch_after=self.launch_var.get(),
                clean_existing=clean_existing,
                prepare_java=prepare_java_requested,
                auth_username=auth_username,
                auth_password=auth_password,
                keep_existing_auth=keep_existing_auth,
            )
            action = "clean installed" if clean_existing else "updated" if self.installed_dir else "installed"
            if result.java_ready or not prepare_java_requested:
                messagebox.showinfo(APP_NAME, f"{APP_NAME} was {action}:\n\n{result.app_path}\n\n{result.java_message}")
            else:
                messagebox.showwarning(
                    APP_NAME,
                    f"{APP_NAME} was {action}:\n\n{result.app_path}\n\n"
                    f"Java still needs attention:\n{result.java_message}\n\n"
                    "MineHost Helper can retry from the Setup Wizard.",
                )
            self.root.destroy()
        except Exception as exc:
            messagebox.showerror(APP_NAME, f"Install failed:\n\n{exc}")
            for button in self.install_buttons:
                button.configure(state="normal")

    def run(self) -> None:
        self.root.mainloop()


class UninstallerUi:
    def __init__(self) -> None:
        self.root = tk.Tk()
        self.root.title(f"Uninstall {APP_NAME}")
        self.root.geometry("540x280")
        self.root.resizable(False, False)
        self.root.configure(bg="#fffdf6")
        self.keep_data_var = tk.BooleanVar(value=True)
        self.install_dir = read_installed_dir() or default_install_dir()
        self._build()

    def _build(self) -> None:
        frame = tk.Frame(self.root, padx=28, pady=24, bg="#fffdf6")
        frame.pack(fill="both", expand=True)
        tk.Label(
            frame,
            text=f"Uninstall {APP_NAME}",
            font=("Segoe UI", 22, "bold"),
            bg="#fffdf6",
            fg="#243023",
        ).pack(anchor="w")
        tk.Label(
            frame,
            text=f"Installed at:\n{self.install_dir}",
            font=("Segoe UI", 10),
            bg="#eef7e8",
            fg="#1f6d36",
            padx=12,
            pady=10,
            wraplength=470,
            justify="left",
        ).pack(fill="x", pady=(14, 14))
        tk.Checkbutton(
            frame,
            text="Keep server data, backups, downloaded Java, and logs",
            variable=self.keep_data_var,
            bg="#fffdf6",
            fg="#243023",
            activebackground="#fffdf6",
            font=("Segoe UI", 10),
        ).pack(anchor="w", pady=(0, 18))
        row = tk.Frame(frame, bg="#fffdf6")
        row.pack(fill="x")
        tk.Button(
            row,
            text="Uninstall",
            command=self._uninstall_clicked,
            bg="#bb3b33",
            fg="#ffffff",
            activebackground="#9d2d26",
            activeforeground="#ffffff",
            relief="flat",
            padx=22,
            pady=10,
            font=("Segoe UI", 10, "bold"),
        ).pack(side="left")
        tk.Button(
            row,
            text="Cancel",
            command=self.root.destroy,
            bg="#e6ecd9",
            fg="#243023",
            relief="flat",
            padx=22,
            pady=10,
            font=("Segoe UI", 10, "bold"),
        ).pack(side="left", padx=(10, 0))

    def _uninstall_clicked(self) -> None:
        try:
            uninstall(self.install_dir, keep_data=self.keep_data_var.get(), silent=True)
            messagebox.showinfo(APP_NAME, f"{APP_NAME} was uninstalled.")
            self.root.destroy()
        except Exception as exc:
            messagebox.showerror(APP_NAME, f"Uninstall failed:\n\n{exc}")

    def run(self) -> None:
        self.root.mainloop()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--uninstall", action="store_true")
    parser.add_argument("--silent", action="store_true")
    parser.add_argument("--no-desktop", action="store_true")
    parser.add_argument("--no-launch", action="store_true")
    parser.add_argument("--keep-data", action="store_true")
    parser.add_argument("--remove-data", action="store_true")
    parser.add_argument("--target-dir")
    parser.add_argument("--auth-username")
    parser.add_argument("--auth-password")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if args.uninstall:
        if args.silent:
            uninstall(
                Path(args.target_dir) if args.target_dir else None,
                keep_data=not args.remove_data if not args.keep_data else True,
                silent=True,
            )
            return
        UninstallerUi().run()
        return
    if args.silent:
        target_dir = Path(args.target_dir) if args.target_dir else default_install_dir()
        auth_username = args.auth_username
        auth_password = args.auth_password
        keep_existing_auth = bool(read_existing_auth_username(target_dir) and not args.remove_data and not auth_password)
        if auth_username and auth_password:
            auth_username, auth_password = validate_auth_inputs(auth_username, auth_password, auth_password)
        install(
            target_dir=target_dir,
            create_desktop_shortcut=not args.no_desktop,
            launch_after=not args.no_launch,
            clean_existing=args.remove_data,
            prepare_java=True,
            auth_username=auth_username,
            auth_password=auth_password,
            keep_existing_auth=keep_existing_auth,
        )
        return
    InstallerUi().run()


if __name__ == "__main__":
    main()
