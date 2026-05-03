from __future__ import annotations

import argparse
import os
import sys
import threading
import time
import tkinter as tk
import traceback
import webbrowser
from tkinter import messagebox

import uvicorn

from backend import app_settings, java_manager
from backend.config import APP_NAME, DEFAULT_MANAGER_PORT, ROOT_DIR
from backend.server_manager import server_manager
from backend.utils import find_free_port

try:
    import pystray
    from PIL import Image, ImageDraw
except Exception:  # pragma: no cover - tray support is optional in dev environments.
    pystray = None
    Image = None
    ImageDraw = None


class LauncherApp:
    def __init__(self, start_minimized: bool = False) -> None:
        self.start_minimized = start_minimized
        self.host = "127.0.0.1"
        self.port = find_free_port(DEFAULT_MANAGER_PORT, self.host)
        self.url = f"http://{self.host}:{self.port}"
        self.server: uvicorn.Server | None = None
        self.thread: threading.Thread | None = None
        self.tray_icon = None
        self._closing = False
        self._has_shown_tray_tip = False

        self.root = tk.Tk()
        self.root.title(APP_NAME)
        self.root.geometry("540x320")
        self.root.resizable(False, False)
        self.root.protocol("WM_DELETE_WINDOW", self.close_window)

        self.status = tk.StringVar(value="Starting local web manager...")
        self.tray_status = tk.StringVar(value="Tray agent is starting...")
        self._build_ui()
        self._start_tray()

        if self.start_minimized:
            self.root.withdraw()

    def _build_ui(self) -> None:
        frame = tk.Frame(self.root, padx=28, pady=24, bg="#fffdf6")
        frame.pack(fill="both", expand=True)
        self.root.configure(bg="#fffdf6")

        tk.Label(
            frame,
            text="MineHost Helper",
            font=("Segoe UI", 22, "bold"),
            bg="#fffdf6",
            fg="#243023",
        ).pack(anchor="w")

        tk.Label(
            frame,
            text="The web manager and tray agent are running locally on this PC.",
            font=("Segoe UI", 10),
            bg="#fffdf6",
            fg="#687466",
            wraplength=480,
            justify="left",
        ).pack(anchor="w", pady=(6, 14))

        tk.Label(
            frame,
            textvariable=self.status,
            font=("Segoe UI", 10, "bold"),
            bg="#eef7e8",
            fg="#1f6d36",
            padx=14,
            pady=12,
            wraplength=450,
            justify="left",
        ).pack(fill="x", pady=(0, 12))

        tk.Label(
            frame,
            textvariable=self.tray_status,
            font=("Segoe UI", 9),
            bg="#fff0c9",
            fg="#5d4b24",
            padx=12,
            pady=10,
            wraplength=450,
            justify="left",
        ).pack(fill="x", pady=(0, 16))

        button_row = tk.Frame(frame, bg="#fffdf6")
        button_row.pack(fill="x")

        self._button(button_row, "Open Web Manager", lambda: webbrowser.open(self.url), "#2f8f46", "#ffffff").pack(side="left")
        self._button(button_row, "Hide to Tray", self.hide_to_tray, "#e6ecd9", "#243023").pack(side="left", padx=(10, 0))
        self._button(button_row, "Exit Agent", self.stop_and_exit, "#bb3b33", "#ffffff").pack(side="left", padx=(10, 0))

        tk.Label(
            frame,
            text="Close hides this agent to the tray when enabled in Server Settings. Friends connect to Minecraft, not this manager.",
            font=("Segoe UI", 9),
            bg="#fffdf6",
            fg="#687466",
            wraplength=460,
            justify="left",
        ).pack(anchor="w", pady=(18, 0))

    def _button(self, parent: tk.Widget, text: str, command, bg: str, fg: str) -> tk.Button:
        return tk.Button(
            parent,
            text=text,
            command=command,
            bg=bg,
            fg=fg,
            activebackground=bg,
            activeforeground=fg,
            relief="flat",
            padx=15,
            pady=10,
            font=("Segoe UI", 10, "bold"),
        )

    def _tray_image(self):
        assert Image is not None and ImageDraw is not None
        image = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
        draw = ImageDraw.Draw(image)
        draw.rounded_rectangle((6, 6, 58, 58), radius=12, fill=(91, 56, 34, 255))
        draw.rectangle((6, 6, 58, 31), fill=(73, 163, 67, 255))
        draw.rectangle((6, 28, 58, 36), fill=(37, 117, 56, 255))
        draw.rectangle((17, 42, 25, 50), fill=(139, 90, 53, 255))
        draw.rectangle((31, 38, 39, 46), fill=(139, 90, 53, 255))
        draw.rectangle((45, 44, 53, 52), fill=(139, 90, 53, 255))
        return image

    def _start_tray(self) -> None:
        if pystray is None or Image is None:
            self.tray_status.set("Tray icon is unavailable in this build. The agent window will stay visible.")
            return
        menu = pystray.Menu(
            pystray.MenuItem("Open MineHost Helper", lambda: self.root.after(0, lambda: webbrowser.open(self.url))),
            pystray.MenuItem("Show Agent Window", lambda: self.root.after(0, self.show_window)),
            pystray.MenuItem("Hide to Tray", lambda: self.root.after(0, self.hide_to_tray)),
            pystray.MenuItem("Start Auto-Start Servers", lambda: self.root.after(0, self.start_auto_servers)),
            pystray.MenuItem("Exit Agent", lambda: self.root.after(0, self.stop_and_exit)),
        )
        self.tray_icon = pystray.Icon("MineHostHelper", self._tray_image(), APP_NAME, menu)
        self.tray_icon.run_detached()
        self.tray_status.set("Tray agent is running. Use the MineHost grass block icon near the clock to reopen or exit.")

    def start_backend(self) -> None:
        os.environ["MINEHOST_HOST"] = self.host
        os.environ["MINEHOST_PORT"] = str(self.port)
        config = uvicorn.Config(
            "backend.main:app",
            host=self.host,
            port=self.port,
            log_level="warning",
            access_log=False,
            log_config=None,
        )
        self.server = uvicorn.Server(config)
        self.thread = threading.Thread(target=self._run_server_safe, daemon=True)
        self.thread.start()
        threading.Thread(target=self._after_backend_start, daemon=True).start()

    def _run_server_safe(self) -> None:
        try:
            assert self.server is not None
            self.server.run()
        except Exception:
            log_path = ROOT_DIR / "launcher-error.log"
            log_path.write_text(traceback.format_exc(), encoding="utf-8")
            self.status.set(f"Backend failed to start. Details were written to {log_path}")

    def _after_backend_start(self) -> None:
        time.sleep(1.5)
        self.status.set(f"Running at {self.url}")
        settings = app_settings.get_settings()
        if settings.get("auto_start_server_ids"):
            self.start_auto_servers()
        should_open = (
            os.environ.get("MINEHOST_NO_BROWSER") != "1"
            and not self.start_minimized
            and settings.get("auto_open_browser", True)
        )
        if should_open:
            webbrowser.open(self.url)

    def start_auto_servers(self) -> None:
        settings = app_settings.get_settings()
        server_ids = settings.get("auto_start_server_ids", [])
        if not server_ids:
            self.status.set("No Minecraft servers are selected for auto-start.")
            return
        for server_id in server_ids:
            try:
                server_manager.start(server_id)
            except Exception as exc:
                self.status.set(f"Auto-start needs attention: {exc}")
                return
        self.status.set(f"Auto-start requested for {len(server_ids)} Minecraft server(s).")

    def show_window(self) -> None:
        self.root.deiconify()
        self.root.lift()
        self.root.focus_force()

    def hide_to_tray(self) -> None:
        if self.tray_icon is None:
            self.root.iconify()
            return
        self.root.withdraw()
        if not self._has_shown_tray_tip:
            self._has_shown_tray_tip = True
            self.tray_status.set("MineHost Helper is still running in the tray. Use the tray icon to reopen it.")

    def close_window(self) -> None:
        if app_settings.get_settings().get("close_to_tray", True):
            self.hide_to_tray()
            return
        self.stop_and_exit()

    def stop_and_exit(self) -> None:
        if self._closing:
            return
        self._closing = True
        self.status.set("Stopping MineHost Helper...")
        try:
            server_manager.stop_all(timeout=8)
        except Exception:
            pass
        if self.server:
            self.server.should_exit = True
        if self.tray_icon:
            try:
                self.tray_icon.stop()
            except Exception:
                pass
        self.root.after(250, self.root.destroy)

    def run(self) -> None:
        try:
            self.start_backend()
            self.root.mainloop()
        except Exception as exc:
            messagebox.showerror(APP_NAME, f"MineHost Helper could not start:\n\n{exc}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--minimized", action="store_true")
    parser.add_argument("--prepare-java", action="store_true", help="Download or verify the bundled Java runtime, then exit.")
    parser.add_argument("--java-version", type=int, default=java_manager.DEFAULT_JAVA_FEATURE_VERSION)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if args.prepare_java:
        try:
            java_manager.install_temurin_jre(args.java_version)
            (ROOT_DIR / "java-setup-error.txt").unlink(missing_ok=True)
        except Exception as exc:
            message = str(exc)
            (ROOT_DIR / "java-setup-error.txt").write_text(message, encoding="utf-8")
            raise SystemExit(1)
        return
    LauncherApp(start_minimized=args.minimized).run()


if __name__ == "__main__":
    main()
