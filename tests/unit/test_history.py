import json
import stat
import tempfile
import unittest
from pathlib import Path

from ace_app.services.history import HistoryRepository, SessionHistory


class HistoryRepositoryTests(unittest.TestCase):
    def test_preserves_legacy_shape_and_private_permissions(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "history.json"
            repository = HistoryRepository(path)
            repository.append("local", "Question", "Answer")
            repository.append("server", "Remote", "Reply")

            self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o600)
            saved = json.loads(path.read_text(encoding="utf-8"))
            self.assertEqual(set(saved), {"local", "server"})
            self.assertEqual(saved["local"][0]["assistant_text"], "Answer")

    def test_invalid_target_cannot_create_a_new_history_partition(self):
        with tempfile.TemporaryDirectory() as directory:
            repository = HistoryRepository(Path(directory) / "history.json")
            with self.assertRaises(ValueError):
                repository.append("other", "Question", "Answer")
            with self.assertRaises(ValueError):
                repository.clear("other")
            with self.assertRaises(ValueError):
                repository.turns("other")

    def test_malformed_legacy_file_loads_as_empty(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "history.json"
            path.write_text("not-json", encoding="utf-8")
            repository = HistoryRepository(path)
            self.assertEqual(repository.turns("local"), [])
            self.assertEqual(repository.turns("server"), [])


class SessionHistoryTests(unittest.TestCase):
    def test_starts_empty_removes_legacy_file_and_never_writes(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "history.json"
            path.write_text('{"local": [{"assistant_text": "old"}]}', encoding="utf-8")

            history = SessionHistory(path)
            history.append("local", "Question", "Answer")

            self.assertEqual(len(history.turns("local")), 1)
            self.assertFalse(path.exists())

            restarted = SessionHistory(path)
            self.assertEqual(restarted.turns("local"), [])


if __name__ == "__main__":
    unittest.main()
