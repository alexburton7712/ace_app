"""Defense-in-depth WebEngine navigation, request, and permission policy."""

from __future__ import annotations

from pathlib import Path
from typing import Any

try:
    from PySide6.QtCore import QUrl
    from PySide6.QtWebEngineCore import (
        QWebEnginePage,
        QWebEngineProfile,
        QWebEngineUrlRequestInfo,
        QWebEngineUrlRequestInterceptor,
    )

    QT_AVAILABLE = True
except ImportError:  # pragma: no cover - depends on desktop packages
    QT_AVAILABLE = False
    QUrl = Any  # type: ignore[misc,assignment]
    QWebEnginePage = Any  # type: ignore[misc,assignment]
    QWebEngineProfile = Any  # type: ignore[misc,assignment]

    class QWebEngineUrlRequestInterceptor:  # type: ignore[no-redef]
        pass


NETWORK_SCHEMES = frozenset({"http", "https", "ws", "wss", "ftp"})


class TrustedRequestPolicy(QWebEngineUrlRequestInterceptor):
    """Allow app assets and inert iframe resources, denying all web egress.

    A qrc/file resource is accepted only when both it and its first-party URL
    belong to the trusted app.  Consequently an opaque ``about:srcdoc`` widget
    cannot load qrc assets (including qwebchannel.js) or development files.
    """

    def __init__(self, *, qrc_prefix: str = "/ace-ui/", dev_root: Path | None = None) -> None:
        if QT_AVAILABLE:
            super().__init__()
        self.qrc_prefix = qrc_prefix.rstrip("/") + "/"
        self.dev_root = dev_root.resolve() if dev_root else None

    def _trusted_qrc(self, url: Any) -> bool:
        return url.scheme().lower() == "qrc" and url.path().startswith(self.qrc_prefix)

    @staticmethod
    def _webchannel_script(url: Any) -> bool:
        return url.scheme().lower() == "qrc" and url.path() == "/qtwebchannel/qwebchannel.js"

    def _trusted_file(self, url: Any) -> bool:
        if url.scheme().lower() != "file" or self.dev_root is None:
            return False
        try:
            candidate = Path(url.toLocalFile()).resolve()
            candidate.relative_to(self.dev_root)
            return True
        except (OSError, ValueError):
            return False

    def is_allowed(self, url: Any, first_party: Any) -> bool:
        scheme = url.scheme().lower()
        if scheme in NETWORK_SCHEMES or scheme in {"filesystem", "content"}:
            return False
        if scheme == "qrc":
            app_origin = self._trusted_qrc(first_party) or self._trusted_file(first_party)
            initial_app_load = self._trusted_qrc(url) and not first_party.scheme()
            return (self._trusted_qrc(url) or self._webchannel_script(url)) and (app_origin or initial_app_load)
        if scheme == "file":
            initial_app_load = self._trusted_file(url) and not first_party.scheme()
            return self._trusted_file(url) and (self._trusted_file(first_party) or initial_app_load)
        if scheme in {"about", "data", "blob"}:
            # Widgets need srcdoc plus data/blob images. CSP further limits type.
            return True
        return False

    def interceptRequest(self, info: Any) -> None:  # Qt callback name
        if not self.is_allowed(info.requestUrl(), info.firstPartyUrl()):
            info.block(True)


def harden_profile(profile: Any, policy: TrustedRequestPolicy) -> None:
    """Configure a profile with no persistent browser state or downloads."""

    if not QT_AVAILABLE:  # pragma: no cover
        raise RuntimeError("PySide6 with Qt WebEngine is required")
    profile.setUrlRequestInterceptor(policy)
    profile.setHttpCacheType(QWebEngineProfile.HttpCacheType.MemoryHttpCache)
    profile.setPersistentCookiesPolicy(
        QWebEngineProfile.PersistentCookiesPolicy.NoPersistentCookies
    )
    # An unnamed QWebEngineProfile is off-the-record.  These paths remain empty.
    if hasattr(profile, "setPersistentPermissionsPolicy"):
        profile.setPersistentPermissionsPolicy(
            QWebEngineProfile.PersistentPermissionsPolicy.AskEveryTime
        )


def deny_permission(permission: Any) -> None:
    """Deny either Qt 6.8 QWebEnginePermission or older request forms."""

    if hasattr(permission, "deny"):
        permission.deny()


__all__ = ["NETWORK_SCHEMES", "TrustedRequestPolicy", "deny_permission", "harden_profile"]
