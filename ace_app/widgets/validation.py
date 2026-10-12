"""Strict validation shared by all widget transports."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Mapping

DEFAULT_MAX_BODY_BYTES = 256 * 1024
HARD_MAX_BODY_BYTES = 4 * 1024 * 1024
WIDGET_ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$", re.ASCII)


@dataclass(frozen=True, slots=True)
class ValidatedWidgetPayload:
    id: str
    html: str


class WidgetValidationError(ValueError):
    """A client-safe validation failure."""

    def __init__(self, code: str, message: str, *, status: int = 400) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.status = status


def validate_max_body_bytes(value: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError("maximum widget body size must be an integer")
    if value < 1 or value > HARD_MAX_BODY_BYTES:
        raise ValueError(
            f"maximum widget body size must be between 1 and {HARD_MAX_BODY_BYTES} bytes"
        )
    return value


def validate_widget_payload(
    payload: object, *, max_widget_bytes: int = DEFAULT_MAX_BODY_BYTES
) -> ValidatedWidgetPayload:
    """Validate a decoded protocol-v1 payload without altering its HTML."""
    limit = validate_max_body_bytes(max_widget_bytes)
    if not isinstance(payload, Mapping):
        raise WidgetValidationError("invalid_shape", "request body must be a JSON object")
    if set(payload.keys()) != {"id", "widget"}:
        raise WidgetValidationError(
            "invalid_shape", "request body must contain only id and widget"
        )

    widget_id = payload["id"]
    if not isinstance(widget_id, str) or WIDGET_ID_PATTERN.fullmatch(widget_id) is None:
        raise WidgetValidationError(
            "invalid_id", "id must use 1-64 letters, digits, dots, underscores, or hyphens"
        )

    html = payload["widget"]
    if not isinstance(html, str) or not html:
        raise WidgetValidationError("invalid_widget", "widget must be a non-empty string")
    if "\x00" in html:
        raise WidgetValidationError("invalid_widget", "widget must not contain NUL characters")
    if len(html.encode("utf-8")) > limit:
        raise WidgetValidationError("payload_too_large", "widget exceeds the size limit", status=413)
    return ValidatedWidgetPayload(widget_id, html)
