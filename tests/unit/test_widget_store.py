import threading
import unittest
from datetime import datetime, timezone

from ace_app.widgets.store import WidgetStore, ingest_widget


class WidgetStoreTests(unittest.TestCase):
    def test_replace_retains_position_and_creation_time(self):
        store = WidgetStore()
        first = datetime(2026, 1, 1, tzinfo=timezone.utc)
        second = datetime(2026, 1, 2, tzinfo=timezone.utc)
        created = store.upsert("a", "one", "local", now=first)
        store.upsert("b", "two", "server", now=first)
        replaced = store.upsert("a", "new", "server", now=second)
        self.assertEqual([widget.id for widget in store.list()], ["a", "b"])
        self.assertEqual(replaced.status, "replaced")
        self.assertEqual(replaced.widget.created_at, created.widget.created_at)
        self.assertEqual(replaced.widget.updated_at, second)
        self.assertEqual(replaced.widget.source_target, "server")
        self.assertEqual(replaced.widget.revision, 3)

    def test_callbacks_are_outside_lock_and_removable(self):
        store = WidgetStore()
        events = []

        def callback(event):
            events.append(event)
            store.list()

        unsubscribe = store.subscribe(callback)
        ingest_widget("local", {"id": "one", "widget": "<p>one</p>"}, store)
        store.remove("one")
        unsubscribe()
        store.upsert("two", "x", "local")
        self.assertEqual([event.kind for event in events], ["upsert", "remove"])

    def test_parallel_insertions_do_not_corrupt_store(self):
        store = WidgetStore()
        threads = [
            threading.Thread(target=store.upsert, args=(f"w{i}", str(i), "local"))
            for i in range(30)
        ]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()
        self.assertEqual(len(store), 30)
        self.assertEqual(sorted(widget.revision for widget in store.list()), list(range(1, 31)))

    def test_serialization_is_json_compatible(self):
        widget = WidgetStore().upsert("a", "<p>x</p>", "local").widget
        data = widget.to_dict()
        self.assertTrue(data["created_at"].endswith("Z"))
        self.assertEqual(data["html"], "<p>x</p>")


if __name__ == "__main__":
    unittest.main()
