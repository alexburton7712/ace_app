"""Transport-independent widget data models."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Literal

SourceTarget = Literal["local", "server"]
WidgetEventKind = Literal["upsert", "remove", "clear"]


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _timestamp(value: datetime) -> str:
    """Return a stable JSON timestamp, treating naive inputs as UTC."""
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


@dataclass(frozen=True, slots=True)
class Widget:
    id: str
    html: str
    source_target: SourceTarget
    created_at: datetime
    updated_at: datetime
    revision: int

    def to_dict(self) -> dict[str, object]:
        return {
            "id": self.id,
            "html": self.html,
            "source_target": self.source_target,
            "created_at": _timestamp(self.created_at),
            "updated_at": _timestamp(self.updated_at),
            "revision": self.revision,
        }

    # A named serialization method is convenient at controller boundaries.
    serialize = to_dict


@dataclass(frozen=True, slots=True)
class WidgetEvent:
    kind: WidgetEventKind
    revision: int
    widget: Widget | None = None
    widget_id: str | None = None

    def to_dict(self) -> dict[str, object]:
        result: dict[str, object] = {"kind": self.kind, "revision": self.revision}
        if self.widget is not None:
            result["widget"] = self.widget.to_dict()
        if self.widget_id is not None:
            result["widget_id"] = self.widget_id
        return result


@dataclass(frozen=True, slots=True)
class IngestResult:
    widget: Widget
    status: Literal["created", "replaced"]

    @property
    def created(self) -> bool:
        return self.status == "created"

    def to_dict(self) -> dict[str, object]:
        return {
            "id": self.widget.id,
            "status": self.status,
            "revision": self.widget.revision,
        }
