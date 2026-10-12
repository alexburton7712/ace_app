"""HTTP client for the established Ace audio and conversation API."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

import requests


class AceAPIError(RuntimeError):
    """A safe, user-presentable Ace request failure."""


@dataclass(frozen=True, slots=True)
class AudioReply:
    response: str
    transcription: str | None = None


class AceClient:
    """Send audio and conversation commands to one captured Ace target."""

    def __init__(
        self,
        base_url: str,
        token: str | None = None,
        timeout: float = 120,
        *,
        target: Literal["local", "server"] = "local",
        widget_callback_url: str | None = None,
        widget_callback_token: str | None = None,
        widget_callback: str | None = None,
        widget_token: str | None = None,
        widget_protocol: str = "1",
        session: Any | None = None,
    ) -> None:
        if target not in {"local", "server"}:
            raise ValueError("target must be 'local' or 'server'")
        if timeout <= 0:
            raise ValueError("timeout must be greater than zero")
        if widget_callback_url and widget_callback and widget_callback_url != widget_callback:
            raise ValueError("conflicting widget callback URLs")
        if widget_callback_token and widget_token and widget_callback_token != widget_token:
            raise ValueError("conflicting widget callback tokens")
        widget_callback_url = widget_callback_url or widget_callback
        widget_callback_token = widget_callback_token or widget_token
        if bool(widget_callback_url) != bool(widget_callback_token):
            raise ValueError("widget callback URL and token must be configured together")
        self.base_url = base_url.rstrip("/")
        self.token = token
        self.timeout = timeout
        self.target = target
        self.widget_callback_url = widget_callback_url
        self.widget_callback_token = widget_callback_token
        self.widget_protocol = widget_protocol
        self._session = session or requests

    @classmethod
    def from_config(
        cls,
        config: Any,
        target: Literal["local", "server"],
        **kwargs: Any,
    ) -> "AceClient":
        """Construct one target client from :class:`AppConfig`-like settings."""
        prefix = "local" if target == "local" else "server"
        base_url = getattr(config, f"{prefix}_ace_url", None)
        if base_url is None:
            base_url = getattr(config, f"{prefix}_url")
        token = getattr(config, f"{prefix}_ace_token", None)
        if token is None:
            token = getattr(config, f"{prefix}_token", None)
        timeout = getattr(config, "request_timeout", None)
        if timeout is None:
            timeout = getattr(config, "timeout", 120)
        return cls(
            base_url,
            token,
            timeout,
            target=target,
            **kwargs,
        )

    @property
    def audio_url(self) -> str:
        return f"{self.base_url}/api/audio"

    @property
    def conversation_url(self) -> str:
        return f"{self.base_url}/api/conversation"

    @property
    def headers(self) -> dict[str, str]:
        headers: dict[str, str] = {}
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        # Even accidental server-client callback configuration must not cross
        # the local trust boundary.
        if self.target == "local" and self.widget_callback_url and self.widget_callback_token:
            headers.update(
                {
                    "X-Ace-Widget-Callback": self.widget_callback_url,
                    "X-Ace-Widget-Token": self.widget_callback_token,
                    "X-Ace-Widget-Protocol": self.widget_protocol,
                }
            )
        return headers

    @property
    def callback_headers(self) -> dict[str, str]:
        return {key: value for key, value in self.headers.items() if key.startswith("X-Ace-Widget-")}

    def _safe_error(self, action: str, exc: requests.RequestException) -> AceAPIError:
        status = getattr(exc.response, "status_code", None)
        suffix = f" (HTTP {status})" if status is not None else ""
        # Do not copy response bodies, URLs, or request headers into UI errors;
        # any of them may contain credentials supplied by another service.
        return AceAPIError(f"Could not {action}{suffix}")

    def send_audio(self, wav_data: bytes) -> AudioReply:
        try:
            response = self._session.post(
                self.audio_url,
                headers=self.headers,
                files={"file": ("clip.wav", wav_data, "audio/wav")},
                timeout=self.timeout,
            )
            response.raise_for_status()
            body: Any = response.json()
        except requests.RequestException as exc:
            raise self._safe_error("send audio", exc) from exc
        except (TypeError, ValueError) as exc:
            raise AceAPIError("Agent returned invalid JSON") from exc

        if isinstance(body, str) and body.strip():
            return AudioReply(body.strip())
        if isinstance(body, dict):
            for field in ("response", "text", "message"):
                value = body.get(field)
                if isinstance(value, str) and value.strip():
                    transcription = body.get("transcription", body.get("user_transcript"))
                    return AudioReply(
                        value.strip(),
                        transcription.strip()
                        if isinstance(transcription, str) and transcription.strip()
                        else None,
                    )
        raise AceAPIError("Agent response did not contain a non-empty 'response' field")

    def clear_conversation(self) -> None:
        try:
            response = self._session.delete(
                self.conversation_url,
                headers=self.headers,
                timeout=self.timeout,
            )
            response.raise_for_status()
        except requests.RequestException as exc:
            raise self._safe_error("clear conversation", exc) from exc
