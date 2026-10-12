"""Authenticated, loopback-only HTTP transport for Local Ace widgets."""

from __future__ import annotations

import hmac
import json
import re
import secrets
import socket
from collections.abc import Callable
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from threading import BoundedSemaphore, Event, Lock, Thread
from typing import Any

from .store import WidgetStore, ingest_widget
from .validation import (
    DEFAULT_MAX_BODY_BYTES,
    WidgetValidationError,
    validate_max_body_bytes,
)

_CONTENT_LENGTH = re.compile(r"^[0-9]+$", re.ASCII)


class _DuplicateKey(ValueError):
    pass


def _strict_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise _DuplicateKey("duplicate JSON key")
        result[key] = value
    return result


class _BoundedHTTPServer(ThreadingHTTPServer):
    allow_reuse_address = False
    daemon_threads = False
    block_on_close = True

    def __init__(self, *args: Any, max_workers: int, **kwargs: Any) -> None:
        if isinstance(max_workers, bool) or not isinstance(max_workers, int) or max_workers < 1:
            raise ValueError("max_workers must be a positive integer")
        self._worker_slots = BoundedSemaphore(max_workers)
        super().__init__(*args, **kwargs)

    def process_request(self, request: socket.socket, client_address: tuple[str, int]) -> None:
        # Applying backpressure here bounds live request-handler threads.
        self._worker_slots.acquire()
        try:
            super().process_request(request, client_address)
        except BaseException:
            self._worker_slots.release()
            raise

    def process_request_thread(
        self, request: socket.socket, client_address: tuple[str, int]
    ) -> None:
        try:
            super().process_request_thread(request, client_address)
        finally:
            self._worker_slots.release()


class _WidgetRequestHandler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def setup(self) -> None:
        super().setup()
        self.connection.settimeout(self.server.socket_timeout)  # type: ignore[attr-defined]

    def log_message(self, format: str, *args: object) -> None:
        # Requests may contain deliberately hostile input; the host can add safe metrics.
        return

    def send_response(self, code: int, message: str | None = None) -> None:
        """BaseHTTPRequestHandler normally discloses its Python server banner."""
        self.log_request(code)
        self.send_response_only(code, message)
        self.send_header("Date", self.date_time_string())

    def _json(self, status: int, value: object) -> None:
        encoded = json.dumps(value, separators=(",", ":"), ensure_ascii=True).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(encoded)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("Connection", "close")
        self.end_headers()
        try:
            self.wfile.write(encoded)
        except (BrokenPipeError, ConnectionResetError, socket.timeout):
            pass
        self.close_connection = True

    def _error(self, status: int, code: str, message: str) -> None:
        self._json(status, {"error": {"code": code, "message": message}})

    def _unknown(self) -> None:
        self._error(HTTPStatus.NOT_FOUND, "not_found", "endpoint not found")

    def do_POST(self) -> None:  # noqa: N802 - BaseHTTPRequestHandler API
        if self.path != "/api/widgets":
            self._unknown()
            return
        server = self.server
        if not server.accepting.is_set() or not server.renderer_available():  # type: ignore[attr-defined]
            self._error(HTTPStatus.SERVICE_UNAVAILABLE, "unavailable", "widget ingestion unavailable")
            return

        supplied = self.headers.get("Authorization", "")
        prefix = "Bearer "
        supplied_token = supplied[len(prefix) :] if supplied.startswith(prefix) else ""
        expected = server.widget_token  # type: ignore[attr-defined]
        if not hmac.compare_digest(supplied_token.encode("utf-8"), expected.encode("utf-8")):
            self._error(HTTPStatus.UNAUTHORIZED, "unauthorized", "authentication required")
            return

        if self.headers.get("Transfer-Encoding") is not None:
            self._error(HTTPStatus.BAD_REQUEST, "invalid_length", "invalid Content-Length")
            return
        raw_length = self.headers.get("Content-Length")
        if raw_length is None or _CONTENT_LENGTH.fullmatch(raw_length) is None:
            self._error(HTTPStatus.BAD_REQUEST, "invalid_length", "invalid Content-Length")
            return
        length = int(raw_length)
        if length > server.max_body_bytes:  # type: ignore[attr-defined]
            self._error(HTTPStatus.REQUEST_ENTITY_TOO_LARGE, "payload_too_large", "request body exceeds the size limit")
            return

        content_type = self.headers.get("Content-Type", "")
        media_type, separator, parameters = content_type.partition(";")
        if media_type.strip().lower() != "application/json":
            self._error(HTTPStatus.UNSUPPORTED_MEDIA_TYPE, "unsupported_media_type", "Content-Type must be application/json")
            return
        if separator:
            parts = [part.strip() for part in parameters.split(";") if part.strip()]
            if len(parts) != 1 or "=" not in parts[0]:
                self._error(HTTPStatus.UNSUPPORTED_MEDIA_TYPE, "unsupported_encoding", "JSON encoding must be UTF-8")
                return
            name, charset = (item.strip().lower() for item in parts[0].split("=", 1))
            charset = charset.strip('"')
            if name != "charset" or charset not in ("utf-8", "utf8"):
                self._error(HTTPStatus.UNSUPPORTED_MEDIA_TYPE, "unsupported_encoding", "JSON encoding must be UTF-8")
                return

        try:
            body = self.rfile.read(length)
        except (socket.timeout, OSError):
            self._error(HTTPStatus.BAD_REQUEST, "invalid_body", "request body could not be read")
            return
        if len(body) != length:
            self._error(HTTPStatus.BAD_REQUEST, "invalid_body", "incomplete request body")
            return
        try:
            text = body.decode("utf-8", errors="strict")
            payload = json.loads(text, object_pairs_hook=_strict_object)
        except (UnicodeDecodeError, json.JSONDecodeError, _DuplicateKey):
            self._error(HTTPStatus.BAD_REQUEST, "malformed_json", "request body must be valid UTF-8 JSON")
            return

        try:
            result = ingest_widget(
                "local", payload, server.widget_store, max_widget_bytes=server.max_body_bytes  # type: ignore[attr-defined]
            )
        except WidgetValidationError as error:
            self._error(error.status, error.code, error.message)
            return
        self._json(HTTPStatus.CREATED if result.created else HTTPStatus.OK, result.to_dict())

    def do_GET(self) -> None:  # noqa: N802
        self._unknown()

    def do_DELETE(self) -> None:  # noqa: N802
        self._unknown()

    def do_PUT(self) -> None:  # noqa: N802
        self._unknown()

    def do_PATCH(self) -> None:  # noqa: N802
        self._unknown()

    def do_OPTIONS(self) -> None:  # noqa: N802
        self._unknown()


class LoopbackWidgetServer:
    """Owns a bounded HTTP listener and its per-launch bearer credential."""

    def __init__(
        self,
        store: WidgetStore,
        *,
        max_body_bytes: int = DEFAULT_MAX_BODY_BYTES,
        max_concurrent_requests: int = 8,
        socket_timeout: float = 5.0,
        renderer_available: Callable[[], bool] | None = None,
        token: str | None = None,
    ) -> None:
        self.store = store
        self.max_body_bytes = validate_max_body_bytes(max_body_bytes)
        if socket_timeout <= 0:
            raise ValueError("socket_timeout must be positive")
        self.socket_timeout = float(socket_timeout)
        self.token = token or secrets.token_urlsafe(32)
        if not self.token:
            raise ValueError("token must not be empty")
        self._available = renderer_available or (lambda: True)
        self._lifecycle_lock = Lock()
        self._thread: Thread | None = None
        self._closed = False
        self._httpd = _BoundedHTTPServer(
            ("127.0.0.1", 0), _WidgetRequestHandler, max_workers=max_concurrent_requests
        )
        self._httpd.socket_timeout = self.socket_timeout
        self._httpd.widget_token = self.token
        self._httpd.widget_store = self.store
        self._httpd.max_body_bytes = self.max_body_bytes
        self._httpd.renderer_available = self._available
        self._httpd.accepting = Event()

    @property
    def host(self) -> str:
        return "127.0.0.1"

    @property
    def port(self) -> int:
        return int(self._httpd.server_address[1])

    @property
    def callback_url(self) -> str:
        return f"http://127.0.0.1:{self.port}/api/widgets"

    @property
    def callback_headers(self) -> dict[str, str]:
        return {
            "X-Ace-Widget-Callback": self.callback_url,
            "X-Ace-Widget-Token": self.token,
            "X-Ace-Widget-Protocol": "1",
        }

    @property
    def running(self) -> bool:
        thread = self._thread
        return bool(thread and thread.is_alive() and self._httpd.accepting.is_set())

    def start(self) -> "LoopbackWidgetServer":
        with self._lifecycle_lock:
            if self._closed:
                raise RuntimeError("widget server is closed")
            if self._thread is not None:
                return self
            self._httpd.accepting.set()
            self._thread = Thread(
                target=self._httpd.serve_forever,
                name="ace-widget-listener",
                kwargs={"poll_interval": 0.1},
                daemon=False,
            )
            self._thread.start()
        return self

    def stop(self) -> None:
        with self._lifecycle_lock:
            if self._closed:
                return
            self._httpd.accepting.clear()
            thread = self._thread
            if thread is not None:
                self._httpd.shutdown()
                thread.join(timeout=max(2.0, self.socket_timeout + 1.0))
            self._httpd.server_close()
            self._closed = True

    close = stop

    def __enter__(self) -> "LoopbackWidgetServer":
        return self.start()

    def __exit__(self, exc_type: object, exc: object, traceback: object) -> None:
        self.stop()


# Descriptive alias for callers that prefer the architecture document's name.
LocalWidgetServer = LoopbackWidgetServer

__all__ = ["LocalWidgetServer", "LoopbackWidgetServer"]
