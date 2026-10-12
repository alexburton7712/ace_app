"""The deliberately small, capability-protected JavaScript command surface."""

from __future__ import annotations

import json
import secrets
from collections.abc import Callable, Mapping
from typing import Any, Protocol, runtime_checkable

try:  # Core tests and headless tools must be able to import this module.
    from PySide6.QtCore import QObject, Slot

    QT_AVAILABLE = True
except ImportError:  # pragma: no cover - exercised when PySide is unavailable
    QT_AVAILABLE = False

    class QObject:  # type: ignore[no-redef]
        def __init__(self, *_args: object, **_kwargs: object) -> None:
            super().__init__()

    def Slot(*_args: object, **_kwargs: object) -> Callable[[Callable[..., Any]], Callable[..., Any]]:  # type: ignore[misc]
        return lambda function: function


Envelope = dict[str, Any]
SnapshotCallback = Callable[[dict[str, Any]], None]


@runtime_checkable
class DesktopController(Protocol):
    """Controller contract consumed by the desktop layer.

    Implementations may return a raw JSON-compatible value or an existing
    ``{"ok": ...}`` envelope.  Commands are expected to reject invalid state
    themselves; the bridge is only an authorization and serialization layer.
    """

    def get_snapshot(self) -> Any: ...

    def select_target(self, target: str) -> Any: ...

    def start_recording(self) -> Any: ...

    def stop_and_send(self) -> Any: ...

    def clear_conversation(self, target: str) -> Any: ...

    def dismiss_widget(self, widget_id: str) -> Any: ...

    # Optional at runtime: subscribe(callback) -> unsubscribe callable.


def _json_default(value: object) -> object:
    if hasattr(value, "to_dict"):
        return value.to_dict()  # type: ignore[no-any-return,attr-defined]
    if hasattr(value, "value"):
        return value.value  # type: ignore[attr-defined]
    raise TypeError(f"{type(value).__name__} is not JSON serializable")


class AppBridge(QObject):
    """Exactly six commands, each guarded by one per-process capability."""

    def __init__(self, controller: DesktopController, capability: str) -> None:
        super().__init__()
        self._controller = controller
        self._capability = capability

    @staticmethod
    def new_capability() -> str:
        """Return a 256-bit URL-safe capability suitable for one app process."""

        return secrets.token_urlsafe(32)

    def revoke(self) -> None:
        self._capability = ""

    def _authorized(self, supplied: str) -> bool:
        expected = self._capability
        return bool(expected) and secrets.compare_digest(expected, supplied)

    @staticmethod
    def _encode(envelope: Envelope) -> str:
        try:
            return json.dumps(envelope, default=_json_default, separators=(",", ":"))
        except (TypeError, ValueError):
            return json.dumps(
                {
                    "ok": False,
                    "error": {
                        "code": "serialization_error",
                        "message": "The native result could not be serialized",
                    },
                },
                separators=(",", ":"),
            )

    def _invoke(self, capability: str, command: Callable[..., Any], *args: Any) -> str:
        if not self._authorized(capability):
            return self._encode(
                {
                    "ok": False,
                    "error": {"code": "unauthorized", "message": "Invalid bridge capability"},
                }
            )
        try:
            result = command(*args)
            if isinstance(result, Mapping) and isinstance(result.get("ok"), bool):
                envelope = dict(result)
            else:
                envelope = {"ok": True, "value": result}
            return self._encode(envelope)
        except Exception as exc:  # The Qt boundary must never leak an exception.
            code = getattr(exc, "code", "command_failed")
            public_message = getattr(exc, "public_message", None)
            if not isinstance(public_message, str) or not public_message:
                public_message = "The command could not be completed"
            return self._encode(
                {"ok": False, "error": {"code": str(code), "message": public_message}}
            )

    @Slot(str, result=str)
    def get_snapshot(self, capability: str) -> str:
        return self._invoke(capability, self._controller.get_snapshot)

    @Slot(str, str, result=str)
    def select_target(self, capability: str, target: str) -> str:
        return self._invoke(capability, self._controller.select_target, target)

    @Slot(str, result=str)
    def start_recording(self, capability: str) -> str:
        return self._invoke(capability, self._controller.start_recording)

    @Slot(str, result=str)
    def stop_and_send(self, capability: str) -> str:
        return self._invoke(capability, self._controller.stop_and_send)

    @Slot(str, str, result=str)
    def clear_conversation(self, capability: str, target: str) -> str:
        return self._invoke(capability, self._controller.clear_conversation, target)

    @Slot(str, str, result=str)
    def dismiss_widget(self, capability: str, widget_id: str) -> str:
        return self._invoke(capability, self._controller.dismiss_widget, widget_id)


__all__ = ["AppBridge", "DesktopController", "QT_AVAILABLE"]
