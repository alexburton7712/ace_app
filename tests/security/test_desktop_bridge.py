from __future__ import annotations

import json
import unittest

from ace_app.desktop.bridge import AppBridge


class Controller:
    def __init__(self) -> None:
        self.calls: list[tuple[object, ...]] = []

    def get_snapshot(self):
        self.calls.append(("snapshot",))
        return {"revision": 1}

    def select_target(self, target):
        self.calls.append(("select", target))

    def start_recording(self):
        self.calls.append(("start",))

    def stop_and_send(self):
        self.calls.append(("stop",))

    def clear_conversation(self, target):
        self.calls.append(("clear", target))

    def dismiss_widget(self, widget_id):
        self.calls.append(("dismiss", widget_id))


class DesktopBridgeTests(unittest.TestCase):
    def test_every_command_requires_exact_capability(self):
        controller = Controller()
        bridge = AppBridge(controller, "correct-capability")
        attempts = [
            bridge.get_snapshot("wrong"),
            bridge.select_target("wrong", "server"),
            bridge.start_recording("wrong"),
            bridge.stop_and_send("wrong"),
            bridge.clear_conversation("wrong", "local"),
            bridge.dismiss_widget("wrong", "daily-news"),
        ]
        self.assertEqual(controller.calls, [])
        self.assertTrue(
            all(json.loads(value)["error"]["code"] == "unauthorized" for value in attempts)
        )

    def test_bridge_exposes_only_six_public_commands(self):
        commands = {
            name
            for name in dir(AppBridge)
            if not name.startswith("_") and callable(getattr(AppBridge, name))
        }
        expected = {
            "get_snapshot", "select_target", "start_recording", "stop_and_send",
            "clear_conversation", "dismiss_widget",
        }
        self.assertLessEqual(expected, commands)
        self.assertFalse({"execute", "evaluate", "fetch", "read_file"} & commands)

    def test_valid_call_is_serialized_and_revoke_is_final(self):
        controller = Controller()
        bridge = AppBridge(controller, "cap")
        result = json.loads(bridge.get_snapshot("cap"))
        self.assertEqual(result, {"ok": True, "value": {"revision": 1}})
        bridge.revoke()
        self.assertFalse(json.loads(bridge.start_recording("cap"))["ok"])
        self.assertEqual(controller.calls, [("snapshot",)])

    def test_internal_exception_does_not_cross_or_echo_details(self):
        controller = Controller()

        def explode():
            raise RuntimeError("secret path /home/alice/token")

        controller.start_recording = explode  # type: ignore[method-assign]
        result = AppBridge(controller, "cap").start_recording("cap")
        self.assertNotIn("secret path", result)
        self.assertEqual(json.loads(result)["error"]["code"], "command_failed")
