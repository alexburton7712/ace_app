from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import requests


class AceAPIError(RuntimeError):
    pass


@dataclass(slots=True)
class AudioReply:
    response: str
    transcription: str | None = None


class AceClient:
    """Send recorded audio to Ace and return its text response."""

    def __init__(
        self,
        base_url: str,
        token: str | None = None,
        timeout: float = 120,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.token = token
        self.timeout = timeout

    @property
    def audio_url(self) -> str:
        return f"{self.base_url}/api/audio"

    @property
    def conversation_url(self) -> str:
        return f"{self.base_url}/api/conversation"

    @property
    def headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self.token}"} if self.token else {}

    def send_audio(self, wav_data: bytes) -> AudioReply:
        try:
            response = requests.post(
                self.audio_url,
                headers=self.headers,
                files={"file": ("clip.wav", wav_data, "audio/wav")},
                timeout=self.timeout,
            )
            response.raise_for_status()
            body: Any = response.json()
        except requests.RequestException as exc:
            detail = ""
            if exc.response is not None:
                try:
                    error_body = exc.response.json()
                    detail = f": {error_body.get('message', error_body.get('detail', error_body))}"
                except (ValueError, AttributeError):
                    detail = f": {exc.response.text[:300]}"
            raise AceAPIError(f"Could not send audio ({exc}){detail}") from exc
        except ValueError as exc:
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
                        transcription.strip() if isinstance(transcription, str) and transcription.strip() else None,
                    )
        raise AceAPIError("Agent response did not contain a non-empty 'response' field")

    def clear_conversation(self) -> None:
        try:
            response = requests.delete(
                self.conversation_url,
                headers=self.headers,
                timeout=self.timeout,
            )
            response.raise_for_status()
        except requests.RequestException as exc:
            detail = ""
            if exc.response is not None:
                try:
                    error_body = exc.response.json()
                    detail = f": {error_body.get('message', error_body.get('detail', error_body))}"
                except (ValueError, AttributeError):
                    detail = f": {exc.response.text[:300]}"
            raise AceAPIError(f"Could not clear conversation ({exc}){detail}") from exc
