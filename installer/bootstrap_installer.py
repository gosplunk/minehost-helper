from __future__ import annotations

import argparse
from dataclasses import dataclass
import os
import shutil
import subprocess
import sys
import tkinter as tk
import winreg
from pathlib import Path
from tkinter import filedialog, messagebox

APP_NAME = "MineHost Helper"
APP_VERSION = "0.1.10"
PUBLISHER = "MineHost Helper"
EXE_NAME = "MineHostHelper.exe"
UNINSTALL_EXE_NAME = "Uninstall MineHost Helper.exe"
UNINSTALL_KEY = r"Software\Microsoft\Windows\CurrentVersion\Uninstall\MineHostHelper"
RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
RUN_VALUE_NAME = "MineHost Helper"
JAVA_FEATURE_VERSION = 25


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
        ["taskkill", "/IM", EXE_NAME, "/F"],
        capture_output=True,
        text=True,
        check=False,
        creationflags=subprocess.CREATE_NO_WINDOW,
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
        schedule_remove_dir(target_dir)
    else:
        shutil.rmtree(target_dir, ignore_errors=True)


def install(
    target_dir: Path,
    create_desktop_shortcut: bool = True,
    launch_after: bool = True,
    clean_existing: bool = False,
    prepare_java: bool = True,
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
        self.root.geometry("720x620")
        self.root.minsize(680, 540)
        self.root.resizable(True, True)
        self.root.configure(bg="#fffdf6")
        self.desktop_var = tk.BooleanVar(value=True)
        self.launch_var = tk.BooleanVar(value=True)
        self.prepare_java_var = tk.BooleanVar(value=True)
        self.status_var = tk.StringVar(value="")
        self.installed_dir = read_installed_dir()
        self.installed_version = read_installed_version()
        self.install_dir_var = tk.StringVar(value=str(self.installed_dir or default_install_dir()))
        self.install_buttons: list[tk.Button] = []
        self._build()
        self._fit_window_to_content()

    def _fit_window_to_content(self) -> None:
        self.root.update_idletasks()
        width = min(max(720, self.root.winfo_reqwidth() + 24), self.root.winfo_screenwidth() - 80)
        height = min(max(600, self.root.winfo_reqheight() + 24), self.root.winfo_screenheight() - 80)
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
        tk.Entry(path_row, textvariable=self.install_dir_var, font=("Segoe UI", 10)).pack(side="left", fill="x", expand=True)
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

        tk.Checkbutton(
            frame,
            text=f"Prepare bundled Temurin Java {JAVA_FEATURE_VERSION} now (recommended)",
            variable=self.prepare_java_var,
            bg="#fffdf6",
            fg="#243023",
            activebackground="#fffdf6",
            font=("Segoe UI", 10),
        ).pack(anchor="w", pady=(0, 16))

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
                "Installing MineHost Helper. If this is the first install, Java will be checked and downloaded now."
            )
            self.root.update_idletasks()
            result = install(
                target_dir=Path(self.install_dir_var.get()),
                create_desktop_shortcut=self.desktop_var.get(),
                launch_after=self.launch_var.get(),
                clean_existing=clean_existing,
                prepare_java=self.prepare_java_var.get(),
            )
            action = "clean installed" if clean_existing else "updated" if self.installed_dir else "installed"
            if result.java_ready or not self.prepare_java_var.get():
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
        install(
            target_dir=Path(args.target_dir) if args.target_dir else default_install_dir(),
            create_desktop_shortcut=not args.no_desktop,
            launch_after=not args.no_launch,
            clean_existing=args.remove_data,
            prepare_java=True,
        )
        return
    InstallerUi().run()


if __name__ == "__main__":
    main()
