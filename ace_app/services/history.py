"""Conversation-history stores for the Ace desktop application."""

from __future__ import annotations

import os
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


__all__ = ["SessionHistory", "Turn"]
