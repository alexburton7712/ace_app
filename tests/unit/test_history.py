import tempfile
import unittest
from pathlib import Path

from ace_app.services.history import SessionHistory


class SessionHistoryTests(unittest.TestCase):
    def test_keeps_targets_separate_and_clears_only_selected_target(self):
        with tempfile.TemporaryDirectory() as directory:
            history = SessionHistory(Path(directory) / "history.json")
            history.append("local", "Local question", "Local answer")
            history.append("server", "Server question", "Server answer")

            history.clear("local")

            self.assertEqual(history.turns("local"), [])
            self.assertEqual(history.turns("server")[0].assistant_text, "Server answer")

    def test_rejects_unknown_target(self):
        with tempfile.TemporaryDirectory() as directory:
            history = SessionHistory(Path(directory) / "history.json")
            with self.assertRaises(ValueError):
                history.append("other", "Question", "Answer")
            with self.assertRaises(ValueError):
                history.clear("other")
            with self.assertRaises(ValueError):
                history.turns("other")

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
