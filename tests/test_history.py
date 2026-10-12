import json
import tempfile
import unittest
from pathlib import Path

from history import HistoryStore


class HistoryStoreTests(unittest.TestCase):
    def test_history_persists_separately_for_each_target(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "history.json"
            store = HistoryStore(path)
            store.append("local", "Local question", "Local answer")
            store.append("server", "Server question", "Server answer")

            reloaded = HistoryStore(path)

            self.assertEqual(reloaded.turns("local")[0].assistant_text, "Local answer")
            self.assertEqual(reloaded.turns("server")[0].assistant_text, "Server answer")
            self.assertEqual(len(json.loads(path.read_text())["local"]), 1)

    def test_clear_removes_only_selected_target(self):
        with tempfile.TemporaryDirectory() as directory:
            store = HistoryStore(Path(directory) / "history.json")
            store.append("local", "Question", "Answer")
            store.append("server", "Question", "Answer")

            store.clear("local")

            self.assertEqual(store.turns("local"), [])
            self.assertEqual(len(store.turns("server")), 1)


if __name__ == "__main__":
    unittest.main()
