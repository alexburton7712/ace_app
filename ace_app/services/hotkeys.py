"""Optional Linux global-hotkey adapter with lazy evdev loading."""

from __future__ import annotations

import importlib
import select
import threading
from collections.abc import Callable
from typing import Any


class HotkeyError(RuntimeError):
    pass


class HotkeyListener:
    """Listen for F9 push-to-talk and F10 target switching when enabled."""

    KEY_F9 = 67
    KEY_F10 = 68
    EV_KEY = 1

    def __init__(
        self,
        on_record_start: Callable[[], None],
        on_record_stop: Callable[[], None],
        on_toggle_target: Callable[[], None],
    ) -> None:
        self.on_record_start = on_record_start
        self.on_record_stop = on_record_stop
        self.on_toggle_target = on_toggle_target
        self.devices: list[Any] = []
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._f9_down = False
        self._evdev: Any | None = None

    @staticmethod
    def available() -> bool:
        try:
            importlib.import_module("evdev")
        except (ImportError, OSError):
            return False
        return True

    def _load_evdev(self) -> Any:
        try:
            return importlib.import_module("evdev")
        except (ImportError, OSError) as exc:
            raise HotkeyError(
                "Global hotkeys are unavailable because the optional evdev dependency is not installed."
            ) from exc

    def start(self) -> None:
        if self._thread is not None:
            return
        self._stop.clear()
        self._evdev = self._load_evdev()
        ecodes = self._evdev.ecodes
        self.KEY_F9 = ecodes.KEY_F9
        self.KEY_F10 = ecodes.KEY_F10
        self.EV_KEY = ecodes.EV_KEY
        self.devices = self._find_keyboards()
        self._thread = threading.Thread(target=self._run, daemon=True, name="ace-hotkeys")
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        thread = self._thread
        if thread is not None and thread is not threading.current_thread():
            thread.join(timeout=1)
        for device in self.devices:
            try:
                device.close()
            except OSError:
                pass
        self.devices.clear()
        self._thread = None
        self._f9_down = False

    def _find_keyboards(self) -> list[Any]:
        if self._evdev is None:
            self._evdev = self._load_evdev()
        keyboards: list[Any] = []
        permission_denied = False
        for path in self._evdev.list_devices():
            try:
                device = self._evdev.InputDevice(path)
                keys = device.capabilities().get(self.EV_KEY, [])
            except PermissionError:
                permission_denied = True
                continue
            except OSError:
                continue
            if self.KEY_F9 in keys or self.KEY_F10 in keys:
                keyboards.append(device)
            else:
                device.close()
        if keyboards:
            return keyboards
        if permission_denied:
            raise HotkeyError("Global hotkeys cannot read keyboard devices; check input-device permissions.")
        raise HotkeyError("No keyboard device exposing F9 or F10 was found.")

    def _run(self) -> None:
        while not self._stop.is_set():
            try:
                ready, _, _ = select.select(self.devices, [], [], 0.25)
                for device in ready:
                    for event in device.read():
                        if event.type == self.EV_KEY:
                            self._handle_key(event.code, event.value)
            except OSError:
                if not self._stop.is_set():
                    self._stop.set()

    def _handle_key(self, code: int, value: int) -> None:
        if code == self.KEY_F9:
            if value == 1 and not self._f9_down:
                self._f9_down = True
                self.on_record_start()
            elif value == 0 and self._f9_down:
                self._f9_down = False
                self.on_record_stop()
        elif code == self.KEY_F10 and value == 1:
            self.on_toggle_target()


__all__ = ["HotkeyError", "HotkeyListener"]
