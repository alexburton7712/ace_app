from __future__ import annotations

import dataclasses
import threading
import uuid
from collections.abc import Callable, Mapping
from concurrent.futures import Executor, ThreadPoolExecutor
from datetime import datetime, timezone
from typing import Any, Protocol


class Recorder(Protocol):
    @property
    def recording(self) -> bool: ...

    def start(self) -> None: ...

    def stop(self) -> bytes: ...

    def discard(self) -> None: ...


class AgentClient(Protocol):
    def send_audio(self, wav_data: bytes) -> Any: ...

    def clear_conversation(self) -> None: ...


class History(Protocol):
    def turns(self, target: str) -> list[Any]: ...

    def append(self, target: str, user_text: str, assistant_text: str) -> Any: ...

    def clear(self, target: str) -> None: ...


SnapshotCallback = Callable[[dict[str, Any]], None]


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _json_value(value: Any) -> Any:
    if hasattr(value, "to_dict"):
        return value.to_dict()
    if dataclasses.is_dataclass(value):
        return dataclasses.asdict(value)
    if isinstance(value, Mapping):
        return dict(value)
    return value


class ApplicationController:
    """Single authority for commands and externally visible application state."""

    TARGETS = ("local", "server")

    def __init__(
        self,
        *,
        clients: Mapping[str, AgentClient],
        recorder: Recorder,
        history: History,
        widget_store: Any,
        active_target: str = "local",
        assumed_context_turns: int = 10,
        connections: Mapping[str, str] | None = None,
        executor: Executor | None = None,
    ) -> None:
        if active_target not in self.TARGETS:
            raise ValueError(f"Unknown target: {active_target}")
        missing = set(self.TARGETS).difference(clients)
        if missing:
            raise ValueError(f"Missing clients for: {', '.join(sorted(missing))}")

        self._clients = dict(clients)
        self._recorder = recorder
        self._history = history
        self._widgets = widget_store
        self._active_target = active_target
        self._assumed_context_turns = assumed_context_turns
        self._connections = {
            "local_widget_listener": "disconnected",
            "server_widget_stream": "not_configured",
            "hotkeys": "disabled",
            **dict(connections or {}),
        }
        self._operation: dict[str, Any] = {"state": "idle"}
        self._notices: list[dict[str, Any]] = []
        self._revision = 0
        self._subscribers: list[SnapshotCallback] = []
        self._lock = threading.RLock()
        self._executor = executor or ThreadPoolExecutor(max_workers=2, thread_name_prefix="ace-work")
        self._owns_executor = executor is None
        self._shutting_down = False
        subscribe_widgets = getattr(self._widgets, "subscribe", None)
        self._widget_unsubscribe = (
            subscribe_widgets(self.widget_changed) if callable(subscribe_widgets) else None
        )

    def subscribe(self, callback: SnapshotCallback) -> Callable[[], None]:
        with self._lock:
            self._subscribers.append(callback)

        def unsubscribe() -> None:
            with self._lock:
                if callback in self._subscribers:
                    self._subscribers.remove(callback)

        return unsubscribe

    def get_snapshot(self) -> dict[str, Any]:
        with self._lock:
            target = self._active_target
            return {
                "schema_version": 1,
                "revision": self._revision,
                "active_target": target,
                "operation": dict(self._operation),
                "history": {
                    "turns": [_json_value(turn) for turn in self._history.turns(target)],
                    "assumed_context_turns": self._assumed_context_turns,
                },
                "widgets": self._widget_snapshot(),
                "connections": dict(self._connections),
                "notices": [dict(notice) for notice in self._notices],
            }

    def select_target(self, target: str) -> dict[str, Any]:
        if target not in self.TARGETS:
            return self._error("invalid_target", "Target must be 'local' or 'server'")
        with self._lock:
            busy = self._require_idle_locked()
            if busy:
                return busy
            if target != self._active_target:
                self._active_target = target
                self._changed_locked()
        return self._success(self.get_snapshot())

    def start_recording(self) -> dict[str, Any]:
        with self._lock:
            busy = self._require_idle_locked()
            if busy:
                return busy
            target = self._active_target
            operation = self._new_operation("recording", "audio", target)
            self._operation = operation
        try:
            self._recorder.start()
        except Exception as exc:
            with self._lock:
                self._operation = {"state": "idle"}
                self._add_notice_locked("recording_failed", self._safe_message(exc))
                self._changed_locked()
            return self._error("recording_failed", self._safe_message(exc))
        with self._lock:
            self._changed_locked()
        return self._success({"operation_id": operation["operation_id"]})

    def stop_and_send(self) -> dict[str, Any]:
        with self._lock:
            if self._operation.get("state") != "recording":
                return self._error("not_recording", "No recording is active")
            operation_id = self._operation["operation_id"]
            target = self._operation["target"]
        try:
            wav_data = self._recorder.stop()
        except Exception as exc:
            with self._lock:
                if self._operation.get("operation_id") == operation_id:
                    self._operation = {"state": "idle"}
                    self._add_notice_locked("recording_failed", self._safe_message(exc))
                    self._changed_locked()
            return self._error("recording_failed", self._safe_message(exc))

        with self._lock:
            if self._operation.get("operation_id") != operation_id:
                return self._error("stale_operation", "Recording operation is no longer active")
            self._operation["state"] = "sending"
            self._changed_locked()
        self._executor.submit(self._send_audio, operation_id, target, wav_data)
        return self._success({"operation_id": operation_id})

    def clear_conversation(self, target: str) -> dict[str, Any]:
        if target not in self.TARGETS:
            return self._error("invalid_target", "Target must be 'local' or 'server'")
        with self._lock:
            busy = self._require_idle_locked()
            if busy:
                return busy
            if not self._history.turns(target):
                return self._success({"cleared": False})
            operation = self._new_operation("clearing", "conversation", target)
            self._operation = operation
            self._changed_locked()
        self._executor.submit(self._clear, operation["operation_id"], target)
        return self._success({"operation_id": operation["operation_id"]})

    def dismiss_widget(self, widget_id: str) -> dict[str, Any]:
        if not isinstance(widget_id, str) or not widget_id:
            return self._error("invalid_widget_id", "A widget ID is required")
        try:
            removed = self._remove_widget(widget_id)
        except Exception as exc:
            return self._error("widget_remove_failed", self._safe_message(exc))
        if not removed:
            return self._error("widget_not_found", "Widget was not found")
        if self._widget_unsubscribe is None:
            with self._lock:
                self._changed_locked()
        return self._success({"id": widget_id})

    def widget_changed(self, *_: Any) -> None:
        """Callback for successful transport-driven widget mutations."""
        with self._lock:
            if not self._shutting_down:
                self._changed_locked()

    def set_connection(self, name: str, state: str) -> None:
        with self._lock:
            if self._connections.get(name) != state:
                self._connections[name] = state
                self._changed_locked()

    def add_notice(self, code: str, message: str) -> None:
        with self._lock:
            self._add_notice_locked(code, message)
            self._changed_locked()

    def shutdown(self) -> None:
        with self._lock:
            if self._shutting_down:
                return
            self._shutting_down = True
            self._operation = {"state": "shutting_down"}
            self._changed_locked()
        try:
            self._recorder.discard()
        finally:
            if callable(self._widget_unsubscribe):
                self._widget_unsubscribe()
                self._widget_unsubscribe = None
            if self._owns_executor:
                self._executor.shutdown(wait=False, cancel_futures=True)
            clear = getattr(self._widgets, "clear", None)
            if clear:
                clear()

    def _send_audio(self, operation_id: str, target: str, wav_data: bytes) -> None:
        try:
            reply = self._clients[target].send_audio(wav_data)
            answer = getattr(reply, "response", None)
            transcription = getattr(reply, "transcription", None)
            if answer is None and isinstance(reply, Mapping):
                answer = reply.get("response")
                transcription = reply.get("transcription")
            user_text = transcription or "Voice message (transcript unavailable)"
            self._history.append(target, user_text, str(answer))
        except Exception as exc:
            self._finish_failed(operation_id, "send_failed", exc)
            return
        self._finish(operation_id)

    def _clear(self, operation_id: str, target: str) -> None:
        try:
            self._history.clear(target)
        except Exception as exc:
            self._finish_failed(operation_id, "clear_failed", exc)
            return
        with self._lock:
            if self._shutting_down or self._operation.get("operation_id") != operation_id:
                return
            # Publish the empty local transcript immediately. A slow or
            # unavailable agent must not prevent the user from clearing the UI.
            self._changed_locked()
        try:
            self._clients[target].clear_conversation()
        except Exception as exc:
            with self._lock:
                if self._shutting_down or self._operation.get("operation_id") != operation_id:
                    return
                self._operation = {"state": "idle"}
                self._add_notice_locked(
                    "agent_context_clear_failed",
                    "Transcript cleared. Ace's active context could not be reset: "
                    f"{self._safe_message(exc)}",
                )
                self._changed_locked()
            return
        self._finish(operation_id)

    def _finish(self, operation_id: str) -> None:
        with self._lock:
            if self._shutting_down or self._operation.get("operation_id") != operation_id:
                return
            self._operation = {"state": "idle"}
            self._changed_locked()

    def _finish_failed(self, operation_id: str, code: str, error: Exception) -> None:
        with self._lock:
            if self._shutting_down or self._operation.get("operation_id") != operation_id:
                return
            self._operation = {"state": "idle"}
            self._add_notice_locked(code, self._safe_message(error))
            self._changed_locked()

    def _changed_locked(self) -> None:
        self._revision += 1
        snapshot = self.get_snapshot()
        subscribers = list(self._subscribers)
        for callback in subscribers:
            try:
                callback(snapshot)
            except Exception:
                # Presentation failures must not break authoritative state updates.
                continue

    def _require_idle_locked(self) -> dict[str, Any] | None:
        if self._shutting_down:
            return self._error("shutting_down", "Ace App is shutting down")
        if self._operation.get("state") != "idle":
            return self._error("busy", "Ace App is already processing a request")
        return None

    @staticmethod
    def _new_operation(state: str, kind: str, target: str) -> dict[str, Any]:
        return {
            "state": state,
            "operation_id": uuid.uuid4().hex,
            "kind": kind,
            "target": target,
            "started_at": _utc_now(),
        }

    def _widget_snapshot(self) -> list[Any]:
        for method_name in ("snapshot", "list", "all"):
            method = getattr(self._widgets, method_name, None)
            if method:
                return [_json_value(item) for item in method()]
        try:
            return [_json_value(item) for item in self._widgets]
        except TypeError:
            return []

    def _remove_widget(self, widget_id: str) -> bool:
        for method_name in ("remove", "dismiss"):
            method = getattr(self._widgets, method_name, None)
            if method:
                result = method(widget_id)
                return bool(result) if result is not None else True
        raise RuntimeError("Widget store does not support removal")

    def _add_notice_locked(self, code: str, message: str) -> None:
        self._notices.append(
            {"id": uuid.uuid4().hex, "code": code, "message": message, "created_at": _utc_now()}
        )
        self._notices = self._notices[-50:]

    @staticmethod
    def _safe_message(error: Exception) -> str:
        message = str(error).strip()
        return message[:500] if message else "The operation failed"

    @staticmethod
    def _success(value: Any) -> dict[str, Any]:
        return {"ok": True, "value": value}

    @staticmethod
    def _error(code: str, message: str) -> dict[str, Any]:
        return {"ok": False, "error": {"code": code, "message": message}}
