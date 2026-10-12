import importlib
import sys
import types
import unittest


fake_evdev = types.ModuleType("evdev")
fake_evdev.InputDevice = object
fake_evdev.ecodes = types.SimpleNamespace(EV_KEY=1, KEY_F9=67, KEY_F10=68)
fake_evdev.list_devices = lambda: []
sys.modules["evdev"] = fake_evdev
hotkeys = importlib.import_module("hotkeys")


class HotkeyListenerTests(unittest.TestCase):
    def test_f9_is_push_to_talk_and_ignores_key_repeat(self):
        calls = []
        listener = hotkeys.HotkeyListener(
            lambda: calls.append("start"),
            lambda: calls.append("stop"),
            lambda: calls.append("toggle"),
        )

        listener._handle_key(hotkeys.ecodes.KEY_F9, 1)
        listener._handle_key(hotkeys.ecodes.KEY_F9, 2)
        listener._handle_key(hotkeys.ecodes.KEY_F9, 0)

        self.assertEqual(calls, ["start", "stop"])

    def test_f10_toggles_only_on_key_down(self):
        calls = []
        listener = hotkeys.HotkeyListener(lambda: None, lambda: None, lambda: calls.append("toggle"))

        listener._handle_key(hotkeys.ecodes.KEY_F10, 1)
        listener._handle_key(hotkeys.ecodes.KEY_F10, 2)
        listener._handle_key(hotkeys.ecodes.KEY_F10, 0)

        self.assertEqual(calls, ["toggle"])


if __name__ == "__main__":
    unittest.main()
