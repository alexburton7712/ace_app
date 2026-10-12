"""Conversation-history stores for the Ace desktop application."""

from __future__ import annotations

import json
import os
import tempfile
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal

from ace_app.models import Target, Turn


class SessionHistory:
    """Keep conversation transcripts in memory for one application run.

    ``legacy_path`` is accepted solely so the new session-only app can remove
    history written by earlier versions. No conversation content is read from
    or written to that path.
    """

    TARGETS: tuple[Target, ...] = ("local", "server")

    def __init__(self, legacy_path: Path | str | None = None) -> None:
        data_root = Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share"))
        self.legacy_path = (
            Path(legacy_path)
            if legacy_path is not None
            else data_root / "ace-app" / "history.json"
        )
        self._lock = threading.RLock()
        self.histories: dict[Target, list[Turn]] = {"local": [], "server": []}
        self._discard_legacy_history()

    @staticmethod
    def _target(target: str) -> Target:
        if target not in {"local", "server"}:
            raise ValueError("target must be 'local' or 'server'")
        return target  # type: ignore[return-value]

    def turns(self, target: str) -> list[Turn]:
        key = self._target(target)
        with self._lock:
            return list(self.histories[key])

    def append(self, target: str, user_text: str, assistant_text: str) -> Turn:
        key = self._target(target)
        if not isinstance(user_text, str) or not isinstance(assistant_text, str):
            raise TypeError("history text must be strings")
        turn = Turn(
            timestamp=datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            user_text=user_text,
            assistant_text=assistant_text,
        )
        with self._lock:
            self.histories[key].append(turn)
        return turn

    def clear(self, target: str) -> None:
        key = self._target(target)
        with self._lock:
            self.histories[key] = []

    def clear_all(self) -> None:
        with self._lock:
            self.histories = {"local": [], "server": []}
        self._discard_legacy_history()

    def _discard_legacy_history(self) -> None:
        try:
            self.legacy_path.unlink(missing_ok=True)
        except OSError:
            # A stale unwritable file is never loaded, so it cannot repopulate
            # the current session.
            pass


class HistoryRepository:
    TARGETS: tuple[Target, ...] = ("local", "server")

    def __init__(self, path: Path | str | None = None) -> None:
        data_root = Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share"))
        self.path = Path(path) if path is not None else data_root / "ace-app" / "history.json"
        self._lock = threading.RLock()
        self.histories = self._load()

    @staticmethod
    def _target(target: str) -> Target:
        if target not in {"local", "server"}:
            raise ValueError("target must be 'local' or 'server'")
        return target  # type: ignore[return-value]

    def turns(self, target: str) -> list[Turn]:
        key = self._target(target)
        with self._lock:
            return list(self.histories[key])

    def append(self, target: str, user_text: str, assistant_text: str) -> Turn:
        key = self._target(target)
        if not isinstance(user_text, str) or not isinstance(assistant_text, str):
            raise TypeError("history text must be strings")
        turn = Turn(
            timestamp=datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            user_text=user_text,
            assistant_text=assistant_text,
        )
        with self._lock:
            updated = {name: list(turns) for name, turns in self.histories.items()}
            updated[key].append(turn)
            self._save(updated)
            self.histories = updated
        return turn

    def clear(self, target: str) -> None:
        key = self._target(target)
        with self._lock:
            updated = {name: list(turns) for name, turns in self.histories.items()}
            updated[key] = []
            self._save(updated)
            self.histories = updated

    def _load(self) -> dict[Target, list[Turn]]:
        result: dict[Target, list[Turn]] = {"local": [], "server": []}
        if not self.path.exists():
            return result
        try:
            value = json.loads(self.path.read_text(encoding="utf-8"))
            if not isinstance(value, dict):
                return result
            for target in self.TARGETS:
                items = value.get(target, [])
                if isinstance(items, list):
                    for item in items:
                        if isinstance(item, dict):
                            result[target].append(Turn.from_dict(item))
        except (OSError, UnicodeError, ValueError, TypeError):
            return {"local": [], "server": []}
        return result

    def _save(self, histories: dict[Target, list[Turn]]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        payload = json.dumps(
            {target: [turn.to_dict() for turn in histories[target]] for target in self.TARGETS},
            indent=2,
            ensure_ascii=False,
        ) + "\n"
        descriptor, raw_temp = tempfile.mkstemp(
            prefix=f".{self.path.name}.", suffix=".tmp", dir=self.path.parent
        )
        temporary = Path(raw_temp)
        try:
            os.fchmod(descriptor, 0o600)
            with os.fdopen(descriptor, "w", encoding="utf-8") as file:
                file.write(payload)
                file.flush()
                os.fsync(file.fileno())
            os.replace(temporary, self.path)
            os.chmod(self.path, 0o600)
        except BaseException:
            try:
                os.close(descriptor)
            except OSError:
                pass
            temporary.unlink(missing_ok=True)
            raise


# Retain the legacy name for existing imports and user scripts.
HistoryStore = HistoryRepository

__all__ = ["HistoryRepository", "HistoryStore", "SessionHistory", "Turn"]
