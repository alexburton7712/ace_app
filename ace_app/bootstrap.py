from __future__ import annotations

import sys
import threading
from pathlib import Path
from typing import Any

from .config import AppConfig, ConfigError
from .controller import ApplicationController
from .services import AceClient, AudioRecorder, HotkeyError, HotkeyListener, SessionHistory
from .widgets import WidgetStore
from .widgets.local_server import LoopbackWidgetServer


class ApplicationRuntime:
    """Construct dependencies in startup order and tear them down once."""

    def __init__(self, config: AppConfig) -> None:
        self.config = config
        self._closed = False
        self._close_lock = threading.Lock()
        self.widgets = WidgetStore()
        self.widget_server = LoopbackWidgetServer(
            self.widgets,
            max_body_bytes=config.widget_max_body_bytes,
            renderer_available=lambda: not self._closed,
        )
        self.history = SessionHistory(config.history_path)
        self.recorder = AudioRecorder()
        self.clients = {
            "local": AceClient(
                config.local_ace_url,
                config.local_ace_token,
                config.request_timeout,
                target="local",
                widget_callback_url=self.widget_server.callback_url,
                widget_callback_token=self.widget_server.token,
            ),
            "server": AceClient(
                config.server_ace_url,
                config.server_ace_token,
                config.request_timeout,
                target="server",
            ),
        }
        self.controller = ApplicationController(
            clients=self.clients,
            recorder=self.recorder,
            history=self.history,
            widget_store=self.widgets,
            active_target=config.active_target,
            assumed_context_turns=config.assumed_context_turns,
            connections={
                "local_widget_listener": "connected",
                "server_widget_stream": (
                    "unavailable" if config.server_widget_stream_url else "not_configured"
                ),
                "hotkeys": "disabled",
            },
        )
        self.hotkeys: HotkeyListener | None = None
        self.widget_server.start()

    def start_hotkeys(self) -> None:
        if not self.config.hotkeys_enabled or self.hotkeys is not None:
            return
        self.hotkeys = HotkeyListener(
            lambda: self.controller.start_recording(),
            lambda: self.controller.stop_and_send(),
            self._toggle_target,
        )
        try:
            self.hotkeys.start()
        except HotkeyError as exc:
            self.hotkeys = None
            self.controller.set_connection("hotkeys", "unavailable")
            self.controller.add_notice("hotkeys_unavailable", str(exc))
        else:
            self.controller.set_connection("hotkeys", "connected")

    def _toggle_target(self) -> None:
        snapshot = self.controller.get_snapshot()
        target = "server" if snapshot["active_target"] == "local" else "local"
        self.controller.select_target(target)

    def close(self) -> None:
        with self._close_lock:
            if self._closed:
                return
            self._closed = True
        self.controller.set_connection("local_widget_listener", "disconnected")
        self.widget_server.stop()
        if self.hotkeys is not None:
            self.hotkeys.stop()
            self.hotkeys = None
        self.controller.shutdown()
        self.history.clear_all()


def _frontend_assets() -> Path:
    root = Path(__file__).resolve().parent / "ui" / "dist"
    if not (root / "index.html").is_file():
        raise RuntimeError(
            "Ace UI assets have not been built. Run `npm install` and `npm run build` "
            "in ace_app/ui before launching."
        )
    return root


def run(config: AppConfig | None = None) -> int:
    from .desktop.window import AceWindow, QT_AVAILABLE

    if not QT_AVAILABLE:
        raise RuntimeError(
            "Ace App requires PySide6 with Qt WebEngine. Run "
            "`python -m pip install -r requirements.txt` first."
        )
    from PySide6.QtWidgets import QApplication

    resolved = config or AppConfig.from_env()
    app = QApplication.instance() or QApplication(sys.argv)
    app.setApplicationName("Ace App")
    app.setOrganizationName("Ace")
    runtime: ApplicationRuntime | None = None
    try:
        runtime = ApplicationRuntime(resolved)
        window = AceWindow(runtime.controller, dev_asset_root=_frontend_assets())
        app.aboutToQuit.connect(runtime.close)
        window.show()
        runtime.start_hotkeys()
        return int(app.exec())
    finally:
        if runtime is not None:
            runtime.close()


def main() -> int:
    try:
        return run()
    except (ConfigError, RuntimeError) as exc:
        print(f"Ace App: {exc}", file=sys.stderr)
        return 2


__all__ = ["ApplicationRuntime", "main", "run"]
