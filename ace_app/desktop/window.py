"""Qt WebEngine application window and trusted-frame event dispatch."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Callable

from .bridge import AppBridge, DesktopController
from .request_policy import TrustedRequestPolicy, deny_permission, harden_profile

try:
    from PySide6.QtCore import QFile, QObject, QUrl, Signal, Slot
    from PySide6.QtWebChannel import QWebChannel
    from PySide6.QtWebEngineCore import QWebEnginePage, QWebEngineProfile
    from PySide6.QtWebEngineWidgets import QWebEngineView
    from PySide6.QtWidgets import QMainWindow

    QT_AVAILABLE = True
except ImportError:  # pragma: no cover - depends on desktop packages
    QT_AVAILABLE = False

    class QMainWindow:  # type: ignore[no-redef]
        pass

    def Slot(*_args: object, **_kwargs: object):  # type: ignore[misc,no-redef]
        """Import-safe stand-in used only until launch reports missing Qt."""

        return lambda function: function


if QT_AVAILABLE:

    class SecurePage(QWebEnginePage):
        def __init__(self, profile: QWebEngineProfile, app_url: QUrl, parent: Any = None) -> None:
            super().__init__(profile, parent)
            self._app_url = app_url

        def acceptNavigationRequest(self, url: QUrl, nav_type: Any, is_main_frame: bool) -> bool:
            if not is_main_frame:
                return True  # Request interceptor and iframe sandbox still apply.
            return url == self._app_url or url.scheme().lower() == "about" and url.path() == "blank"

        def createWindow(self, _window_type: Any) -> None:
            return None


    class SnapshotDispatcher(QObject):
        snapshot_ready = Signal(str)


class AceWindow(QMainWindow):
    """Desktop host that loads only the bundled (or explicit dev) application."""

    def __init__(
        self,
        controller: DesktopController,
        *,
        dev_asset_root: Path | None = None,
        qrc_url: str = "qrc:/ace-ui/index.html",
    ) -> None:
        if not QT_AVAILABLE:  # pragma: no cover
            raise RuntimeError(
                "Ace's desktop UI requires PySide6 with Qt WebEngine. "
                "Run `python -m pip install -r requirements.txt` first."
            )
        super().__init__()
        self.setWindowTitle("Ace")
        self.resize(1240, 800)
        self._controller = controller
        self._capability = AppBridge.new_capability()
        self._bridge = AppBridge(controller, self._capability)
        self._unsubscribe: Callable[[], None] | None = None

        dev_root = dev_asset_root.resolve() if dev_asset_root else None
        if dev_root is not None:
            index_path = dev_root / "index.html"
            if not index_path.is_file():
                raise RuntimeError(f"Frontend development asset is missing: {index_path}")
            app_url = QUrl.fromLocalFile(str(index_path))
        else:
            try:
                from . import resources_rc  # type: ignore[import-not-found]  # noqa: F401
            except ImportError:
                # A packager may register the qrc directly instead of generating
                # the Python module, so test the resource before failing.
                if not QFile.exists(":/ace-ui/index.html"):
                    raise RuntimeError(
                        "Bundled Ace UI resources are unavailable. Build the frontend and "
                        "compile desktop/resources.qrc, or pass dev_asset_root."
                    )
            app_url = QUrl(qrc_url)

        self._profile = QWebEngineProfile(self)
        self._policy = TrustedRequestPolicy(dev_root=dev_root)
        harden_profile(self._profile, self._policy)
        self._page = SecurePage(self._profile, app_url, self)
        self._view = QWebEngineView(self)
        self._view.setPage(self._page)
        self.setCentralWidget(self._view)

        self._channel = QWebChannel(self._page)
        self._channel.registerObject("AppBridge", self._bridge)
        self._page.setWebChannel(self._channel)

        self._page.settings().setAttribute(
            self._page.settings().WebAttribute.LocalContentCanAccessRemoteUrls, False
        )
        self._page.settings().setAttribute(
            # The source-tree launcher loads the built JS/CSS beside index.html.
            # The interceptor still denies every file request whose first party
            # is an opaque widget frame, and packaged qrc builds keep this off.
            self._page.settings().WebAttribute.LocalContentCanAccessFileUrls,
            dev_root is not None,
        )
        self._page.settings().setAttribute(
            self._page.settings().WebAttribute.FullScreenSupportEnabled, False
        )

        self._dispatcher = SnapshotDispatcher(self)
        self._dispatcher.snapshot_ready.connect(self._send_snapshot_json)
        self._connect_denials()
        self._page.loadFinished.connect(self._on_load_finished)
        self._view.load(app_url)
        self._subscribe()

    def _connect_denials(self) -> None:
        if hasattr(self._page, "permissionRequested"):
            self._page.permissionRequested.connect(deny_permission)
        if hasattr(self._page, "featurePermissionRequested"):
            self._page.featurePermissionRequested.connect(
                lambda origin, feature: self._page.setFeaturePermission(
                    origin, feature, QWebEnginePage.PermissionPolicy.PermissionDeniedByUser
                )
            )
        if hasattr(self._profile, "downloadRequested"):
            self._profile.downloadRequested.connect(lambda item: item.cancel())

    def _subscribe(self) -> None:
        subscribe = getattr(self._controller, "subscribe", None)
        if callable(subscribe):
            unsubscribe = subscribe(self.publish_snapshot)
            if callable(unsubscribe):
                self._unsubscribe = unsubscribe

    @Slot(bool)
    def _on_load_finished(self, loaded: bool) -> None:
        if not loaded:
            return
        # The secret exists only as a lexical binding in the trusted main frame.
        capability = json.dumps(self._capability)
        script = (
            "(() => { const capability = " + capability + ";"
            "if (typeof window.__ACE_NATIVE_CONNECT__ !== 'function' || "
            "typeof QWebChannel !== 'function' || !window.qt?.webChannelTransport) return;"
            "new QWebChannel(window.qt.webChannelTransport, channel => "
            "window.__ACE_NATIVE_CONNECT__(channel.objects.AppBridge, capability)); })();"
        )
        self._page.runJavaScript(script)

    def publish_snapshot(self, snapshot: dict[str, Any]) -> None:
        """Thread-safe entry point for controller subscription callbacks."""

        try:
            encoded = json.dumps(snapshot, separators=(",", ":"))
        except (TypeError, ValueError):
            return
        self._dispatcher.snapshot_ready.emit(encoded)

    @Slot(str)
    def _send_snapshot_json(self, encoded: str) -> None:
        argument = json.dumps(encoded)
        self._page.runJavaScript(
            "window.__ACE_DESKTOP__?.receiveSnapshot(JSON.parse(" + argument + "));"
        )

    def closeEvent(self, event: Any) -> None:
        if self._unsubscribe is not None:
            self._unsubscribe()
            self._unsubscribe = None
        self._bridge.revoke()
        self._page.setWebChannel(None)
        super().closeEvent(event)


__all__ = ["AceWindow", "QT_AVAILABLE"]
