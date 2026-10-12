from __future__ import annotations

import tempfile
import threading
import unittest
from concurrent.futures import Executor, Future
from pathlib import Path
from types import SimpleNamespace

from ace_app.controller import ApplicationController


class ImmediateExecutor(Executor):
    def submit(self, fn, /, *args, **kwargs):
        future = Future()
        try:
            future.set_result(fn(*args, **kwargs))
        except BaseException as exc:
            future.set_exception(exc)
        return future


class FakeRecorder:
    recording = False

    def start(self):
        self.recording = True

    def stop(self):
        self.recording = False
        return b"RIFF----WAVEaudio"

    def discard(self):
        self.recording = False


class FakeHistory:
    def __init__(self):
        self.values = {"local": [], "server": []}

    def turns(self, target):
        return list(self.values[target])

    def append(self, target, user_text, assistant_text):
        self.values[target].append(
            {"timestamp": "now", "user_text": user_text, "assistant_text": assistant_text}
        )

    def clear(self, target):
        self.values[target] = []


class FakeClient:
    def __init__(self, response="answer", clear_error=None):
        self.response = response
        self.clear_error = clear_error
        self.clears = 0

    def send_audio(self, data):
        return SimpleNamespace(response=self.response, transcription="question")

    def clear_conversation(self):
        self.clears += 1
        if self.clear_error is not None:
            raise self.clear_error


class FakeWidgets:
    def __init__(self):
        self.values = []

    def snapshot(self):
        return list(self.values)

    def remove(self, widget_id):
        before = len(self.values)
        self.values = [value for value in self.values if value["id"] != widget_id]
        return before != len(self.values)

    def clear(self):
        self.values.clear()


class ControllerTests(unittest.TestCase):
    def make_controller(self):
        self.history = FakeHistory()
        self.widgets = FakeWidgets()
        self.clients = {"local": FakeClient(), "server": FakeClient()}
        return ApplicationController(
            clients=self.clients,
            recorder=FakeRecorder(),
            history=self.history,
            widget_store=self.widgets,
            executor=ImmediateExecutor(),
        )

    def test_audio_operation_captures_target_and_appends_history(self):
        controller = self.make_controller()
        self.assertTrue(controller.start_recording()["ok"])
        self.assertFalse(controller.select_target("server")["ok"])
        self.assertTrue(controller.stop_and_send()["ok"])

        self.assertEqual(controller.get_snapshot()["operation"], {"state": "idle"})
        self.assertEqual(self.history.values["local"][0]["assistant_text"], "answer")
        self.assertEqual(self.history.values["server"], [])

    def test_clear_only_captured_target_and_keeps_widgets(self):
        controller = self.make_controller()
        self.history.values["local"].append({"assistant_text": "local"})
        self.history.values["server"].append({"assistant_text": "server"})
        self.widgets.values.append({"id": "daily-news", "html": "<h1>News</h1>"})

        self.assertTrue(controller.clear_conversation("local")["ok"])

        self.assertEqual(self.history.values["local"], [])
        self.assertEqual(len(self.history.values["server"]), 1)
        self.assertEqual(len(controller.get_snapshot()["widgets"]), 1)

    def test_clear_with_empty_transcript_is_a_no_op(self):
        controller = self.make_controller()
        self.clients["local"].clear_error = RuntimeError("Could not clear conversation")

        result = controller.clear_conversation("local")

        self.assertTrue(result["ok"])
        self.assertEqual(result["value"], {"cleared": False})
        self.assertEqual(self.clients["local"].clears, 0)
        self.assertEqual(controller.get_snapshot()["notices"], [])

    def test_clear_removes_transcript_when_agent_context_reset_fails(self):
        controller = self.make_controller()
        self.history.values["local"].append({"assistant_text": "local"})
        self.clients["local"].clear_error = RuntimeError("Could not clear conversation")

        self.assertTrue(controller.clear_conversation("local")["ok"])

        snapshot = controller.get_snapshot()
        self.assertEqual(snapshot["history"]["turns"], [])
        self.assertEqual(snapshot["operation"], {"state": "idle"})
        self.assertEqual(snapshot["notices"][-1]["code"], "agent_context_clear_failed")
        self.assertIn("Transcript cleared", snapshot["notices"][-1]["message"])

    def test_revisions_increase_and_dismissal_is_independent(self):
        controller = self.make_controller()
        revisions = []
        controller.subscribe(lambda snapshot: revisions.append(snapshot["revision"]))
        self.widgets.values.append({"id": "one"})
        controller.widget_changed()
        result = controller.dismiss_widget("one")

        self.assertTrue(result["ok"])
        self.assertEqual(revisions, sorted(set(revisions)))
        self.assertGreaterEqual(len(revisions), 2)


if __name__ == "__main__":
    unittest.main()
