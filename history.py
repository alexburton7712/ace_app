from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


@dataclass(slots=True)
class Turn:
    timestamp: str
    user_text: str
    assistant_text: str

    @classmethod
    def from_json(cls, value: dict[str, Any]) -> "Turn":
        return cls(
            timestamp=str(value.get("timestamp", "")),
            user_text=str(value.get("user_text", "Voice message")),
            assistant_text=str(value.get("assistant_text", "")),
        )


class HistoryStore:
    """Persist the complete locally observed history for each Ace target."""

    TARGETS = ("local", "server")

    def __init__(self, path: Path | None = None) -> None:
        data_root = Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share"))
        self.path = path or data_root / "ace-app" / "history.json"
        self.histories = self._load()

    def turns(self, target: str) -> list[Turn]:
        return list(self.histories.get(target, []))

    def append(self, target: str, user_text: str, assistant_text: str) -> Turn:
        turn = Turn(
            timestamp=datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            user_text=user_text,
            assistant_text=assistant_text,
        )
        updated = {name: list(turns) for name, turns in self.histories.items()}
        updated.setdefault(target, []).append(turn)
        self._save(updated)
        self.histories = updated
        return turn

    def clear(self, target: str) -> None:
        updated = {name: list(turns) for name, turns in self.histories.items()}
        updated[target] = []
        self._save(updated)
        self.histories = updated

    def _load(self) -> dict[str, list[Turn]]:
        empty = {target: [] for target in self.TARGETS}
        if not self.path.exists():
            return empty
        try:
            value = json.loads(self.path.read_text(encoding="utf-8"))
            for target in self.TARGETS:
                items = value.get(target, [])
                if isinstance(items, list):
                    empty[target] = [Turn.from_json(item) for item in items if isinstance(item, dict)]
        except (OSError, ValueError, TypeError):
            pass
        return empty

    def _save(self, histories: dict[str, list[Turn]]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_suffix(".tmp")
        temporary.write_text(
            json.dumps(
                {target: [asdict(turn) for turn in turns] for target, turns in histories.items()},
                indent=2,
                ensure_ascii=False,
            )
            + "\n",
            encoding="utf-8",
        )
        os.chmod(temporary, 0o600)
        temporary.replace(self.path)
