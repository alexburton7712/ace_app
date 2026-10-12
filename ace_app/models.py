"""Typed, JSON-compatible application state models."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Literal, TypeAlias

JSONScalar: TypeAlias = str | int | float | bool | None
JSONValue: TypeAlias = JSONScalar | list["JSONValue"] | dict[str, "JSONValue"]
Target: TypeAlias = Literal["local", "server"]


class OperationState(str, Enum):
    IDLE = "idle"
    RECORDING = "recording"
    SENDING = "sending"
    CLEARING = "clearing"
    SHUTTING_DOWN = "shutting_down"


def _iso(value: datetime | str) -> str:
    if isinstance(value, datetime):
        return value.isoformat().replace("+00:00", "Z")
    return value


@dataclass(frozen=True, slots=True)
class Turn:
    timestamp: str
    user_text: str
    assistant_text: str

    def to_dict(self) -> dict[str, str]:
        return {
            "timestamp": self.timestamp,
            "user_text": self.user_text,
            "assistant_text": self.assistant_text,
        }

    @classmethod
    def from_dict(cls, value: object) -> "Turn":
        if not isinstance(value, dict):
            raise ValueError("history turn must be an object")
        timestamp = value.get("timestamp", "")
        user_text = value.get("user_text", "Voice message")
        assistant_text = value.get("assistant_text", "")
        return cls(str(timestamp), str(user_text), str(assistant_text))

    from_json = from_dict


@dataclass(frozen=True, slots=True)
class Operation:
    state: OperationState = OperationState.IDLE
    operation_id: str | None = None
    kind: str | None = None
    target: Target | None = None
    started_at: datetime | str | None = None

    def to_dict(self) -> dict[str, JSONValue]:
        result: dict[str, JSONValue] = {"state": self.state.value}
        if self.operation_id is not None:
            result["operation_id"] = self.operation_id
        if self.kind is not None:
            result["kind"] = self.kind
        if self.target is not None:
            result["target"] = self.target
        if self.started_at is not None:
            result["started_at"] = _iso(self.started_at)
        return result


@dataclass(frozen=True, slots=True)
class Notice:
    code: str
    message: str
    level: Literal["info", "warning", "error"] = "info"
    notice_id: str | None = None

    def to_dict(self) -> dict[str, JSONValue]:
        result: dict[str, JSONValue] = {
            "code": self.code,
            "message": self.message,
            "level": self.level,
        }
        if self.notice_id is not None:
            result["id"] = self.notice_id
        return result


@dataclass(frozen=True, slots=True)
class HistorySnapshot:
    turns: tuple[Turn, ...] = ()
    assumed_context_turns: int = 10

    def to_dict(self) -> dict[str, JSONValue]:
        return {
            "turns": [turn.to_dict() for turn in self.turns],
            "assumed_context_turns": self.assumed_context_turns,
        }


@dataclass(frozen=True, slots=True)
class AppSnapshot:
    revision: int
    active_target: Target
    operation: Operation | dict[str, JSONValue] = field(default_factory=Operation)
    history: HistorySnapshot | dict[str, JSONValue] = field(default_factory=HistorySnapshot)
    widgets: tuple[object, ...] | list[object] = ()
    connections: dict[str, str] = field(default_factory=dict)
    notices: tuple[Notice | dict[str, JSONValue], ...] | list[Notice | dict[str, JSONValue]] = ()
    schema_version: int = 1

    @staticmethod
    def _serialize(value: object) -> JSONValue:
        if hasattr(value, "to_dict"):
            return AppSnapshot._serialize(value.to_dict())  # type: ignore[union-attr]
        if isinstance(value, datetime):
            return _iso(value)
        if isinstance(value, Enum) and isinstance(value.value, str):
            return value.value
        if value is None or isinstance(value, (str, int, float, bool)):
            return value
        if isinstance(value, dict):
            return {str(key): AppSnapshot._serialize(item) for key, item in value.items()}
        if isinstance(value, (list, tuple)):
            return [AppSnapshot._serialize(item) for item in value]
        raise TypeError(f"{type(value).__name__} is not JSON compatible")

    def to_dict(self) -> dict[str, JSONValue]:
        return {
            "schema_version": self.schema_version,
            "revision": self.revision,
            "active_target": self.active_target,
            "operation": self._serialize(self.operation),
            "history": self._serialize(self.history),
            "widgets": self._serialize(self.widgets),
            "connections": self._serialize(self.connections),
            "notices": self._serialize(self.notices),
        }

    as_dict = to_dict
