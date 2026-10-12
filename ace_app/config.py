"""Validated environment configuration with secret-safe diagnostics."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Mapping
from urllib.parse import urlsplit

from .models import Target

DEFAULT_LOCAL_URL = "http://127.0.0.1:8001"
DEFAULT_MAX_WIDGET_BODY_BYTES = 256 * 1024
HARD_MAX_WIDGET_BODY_BYTES = 4 * 1024 * 1024


class ConfigError(ValueError):
    """Raised when application configuration is unsafe or invalid."""


def _bool(name: str, value: str | None, default: bool) -> bool:
    if value is None or not value.strip():
        return default
    normalized = value.strip().lower()
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off"}:
        return False
    raise ConfigError(f"{name} must be true or false")


def _int(name: str, value: str | None, default: int, minimum: int, maximum: int) -> int:
    if value is None or not value.strip():
        return default
    try:
        parsed = int(value)
    except ValueError as exc:
        raise ConfigError(f"{name} must be an integer") from exc
    if not minimum <= parsed <= maximum:
        raise ConfigError(f"{name} must be between {minimum} and {maximum}")
    return parsed


def _float(name: str, value: str | None, default: float) -> float:
    if value is None or not value.strip():
        return default
    try:
        parsed = float(value)
    except ValueError as exc:
        raise ConfigError(f"{name} must be a number") from exc
    if not 0 < parsed <= 600:
        raise ConfigError(f"{name} must be greater than 0 and at most 600")
    return parsed


def _url(name: str, value: str) -> str:
    candidate = value.strip().rstrip("/")
    parsed = urlsplit(candidate)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ConfigError(f"{name} must be an http or https URL")
    if parsed.username or parsed.password:
        raise ConfigError(f"{name} must not contain credentials")
    if parsed.query or parsed.fragment:
        raise ConfigError(f"{name} must not contain a query or fragment")
    return candidate


@dataclass(frozen=True, slots=True, repr=False)
class AppConfig:
    local_ace_url: str = DEFAULT_LOCAL_URL
    server_ace_url: str = DEFAULT_LOCAL_URL
    local_ace_token: str | None = field(default=None, repr=False)
    server_ace_token: str | None = field(default=None, repr=False)
    active_target: Target = "local"
    request_timeout: float = 120.0
    assumed_context_turns: int = 10
    history_path: Path | None = None
    widget_bind_address: str = "127.0.0.1"
    widget_port: int = 0
    widget_max_body_bytes: int = DEFAULT_MAX_WIDGET_BODY_BYTES
    hotkeys_enabled: bool = False
    diagnostics_enabled: bool = False
    server_widget_stream_url: str | None = None
    server_widget_stream_token: str | None = field(default=None, repr=False)

    @property
    def default_target(self) -> Target:
        return self.active_target

    @property
    def local_url(self) -> str:
        return self.local_ace_url

    @property
    def server_url(self) -> str:
        return self.server_ace_url

    @property
    def local_token(self) -> str | None:
        return self.local_ace_token

    @property
    def server_token(self) -> str | None:
        return self.server_ace_token

    @property
    def max_widget_payload_bytes(self) -> int:
        return self.widget_max_body_bytes

    @property
    def max_widget_body_bytes(self) -> int:
        return self.widget_max_body_bytes

    @property
    def local_widget_bind_address(self) -> str:
        return self.widget_bind_address

    @property
    def local_widget_port(self) -> int:
        return self.widget_port

    @property
    def timeout(self) -> float:
        return self.request_timeout

    def __repr__(self) -> str:
        def present(secret: str | None) -> str:
            return "<redacted>" if secret else "None"

        return (
            "AppConfig("
            f"local_ace_url={self.local_ace_url!r}, server_ace_url={self.server_ace_url!r}, "
            f"local_ace_token={present(self.local_ace_token)}, "
            f"server_ace_token={present(self.server_ace_token)}, "
            f"active_target={self.active_target!r}, request_timeout={self.request_timeout!r}, "
            f"assumed_context_turns={self.assumed_context_turns!r}, history_path={self.history_path!r}, "
            f"widget_bind_address={self.widget_bind_address!r}, widget_port={self.widget_port!r}, "
            f"widget_max_body_bytes={self.widget_max_body_bytes!r}, "
            f"hotkeys_enabled={self.hotkeys_enabled!r}, diagnostics_enabled={self.diagnostics_enabled!r}, "
            f"server_widget_stream_url={self.server_widget_stream_url!r}, "
            f"server_widget_stream_token={present(self.server_widget_stream_token)})"
        )

    @classmethod
    def from_env(cls, env: Mapping[str, str] | None = None) -> "AppConfig":
        values = os.environ if env is None else env
        local_url = _url("LOCAL_ACE_URL", values.get("LOCAL_ACE_URL", DEFAULT_LOCAL_URL))
        server_url = _url("SERVER_ACE_URL", values.get("SERVER_ACE_URL", local_url))
        shared_token = values.get("ACE_TOKEN") or None
        target = (values.get("ACE_TARGET") or values.get("ACE_ACTIVE_TARGET") or "local").strip().lower()
        if target not in {"local", "server"}:
            raise ConfigError("ACE_TARGET must be 'local' or 'server'")

        bind = values.get(
            "ACE_WIDGET_BIND",
            values.get("LOCAL_WIDGET_BIND_ADDRESS", values.get("WIDGET_BIND_ADDRESS", "127.0.0.1")),
        ).strip()
        if bind not in {"127.0.0.1", "localhost", "::1"}:
            raise ConfigError("ACE_WIDGET_BIND must be a loopback address")

        stream_url_value = values.get("SERVER_WIDGET_STREAM_URL") or None
        stream_url = _url("SERVER_WIDGET_STREAM_URL", stream_url_value) if stream_url_value else None
        path_value = values.get("ACE_HISTORY_PATH")
        return cls(
            local_ace_url=local_url,
            server_ace_url=server_url,
            local_ace_token=values.get("LOCAL_ACE_TOKEN") or shared_token,
            server_ace_token=values.get("SERVER_ACE_TOKEN") or shared_token,
            active_target=target,  # type: ignore[arg-type]
            request_timeout=_float("ACE_REQUEST_TIMEOUT", values.get("ACE_REQUEST_TIMEOUT"), 120.0),
            assumed_context_turns=_int(
                "ACE_ASSUMED_CONTEXT_TURNS", values.get("ACE_ASSUMED_CONTEXT_TURNS"), 10, 1, 10_000
            ),
            history_path=Path(path_value).expanduser() if path_value else None,
            widget_bind_address=bind,
            widget_port=_int(
                "ACE_WIDGET_PORT",
                values.get("ACE_WIDGET_PORT") or values.get("LOCAL_WIDGET_PORT"),
                0,
                0,
                65_535,
            ),
            widget_max_body_bytes=_int(
                "ACE_WIDGET_MAX_BODY_BYTES",
                values.get("ACE_WIDGET_MAX_BODY_BYTES")
                or values.get("MAX_WIDGET_PAYLOAD_BYTES")
                or values.get("WIDGET_MAX_BODY_BYTES"),
                DEFAULT_MAX_WIDGET_BODY_BYTES,
                1,
                HARD_MAX_WIDGET_BODY_BYTES,
            ),
            hotkeys_enabled=_bool("ACE_HOTKEYS_ENABLED", values.get("ACE_HOTKEYS_ENABLED"), False),
            diagnostics_enabled=_bool("ACE_DIAGNOSTICS", values.get("ACE_DIAGNOSTICS"), False),
            server_widget_stream_url=stream_url,
            server_widget_stream_token=values.get("SERVER_WIDGET_STREAM_TOKEN")
            or values.get("SERVER_ACE_TOKEN")
            or shared_token,
        )


load_config = AppConfig.from_env
