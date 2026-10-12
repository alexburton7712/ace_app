import importlib
import unittest
from unittest.mock import patch

from ace_app.services.hotkeys import HotkeyError, HotkeyListener


class HotkeyListenerTests(unittest.TestCase):
    def test_package_import_does_not_require_evdev(self):
        with patch.object(importlib, "import_module", side_effect=ModuleNotFoundError("evdev")):
            listener = HotkeyListener(lambda: None, lambda: None, lambda: None)
            with self.assertRaises(HotkeyError):
                listener.start()

    def test_f9_push_to_talk_ignores_repeat_and_f10_uses_key_down(self):
        calls: list[str] = []
        listener = HotkeyListener(
            lambda: calls.append("start"),
            lambda: calls.append("stop"),
            lambda: calls.append("toggle"),
        )
        listener._handle_key(listener.KEY_F9, 1)
        listener._handle_key(listener.KEY_F9, 2)
        listener._handle_key(listener.KEY_F9, 0)
        listener._handle_key(listener.KEY_F10, 2)
        listener._handle_key(listener.KEY_F10, 1)
        self.assertEqual(calls, ["start", "stop", "toggle"])


if __name__ == "__main__":
    unittest.main()
