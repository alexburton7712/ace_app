from __future__ import annotations

import select
import threading
from collections.abc import Callable

from evdev import InputDevice, ecodes, list_devices


class HotkeyError(RuntimeError):
    pass


class HotkeyListener:
    """Listen for global F9 push-to-talk and F10 target switching."""

    def __init__(
        self,
        on_record_start: Callable[[], None],
        on_record_stop: Callable[[], None],
        on_toggle_target: Callable[[], None],
    ) -> None:
        self.on_record_start = on_record_start
        self.on_record_stop = on_record_stop
        self.on_toggle_target = on_toggle_target
        self.devices: list[InputDevice] = []
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._f9_down = False

    def start(self) -> None:
        if self._thread:
            return
        self.devices = self._find_keyboards()
        self._thread = threading.Thread(target=self._run, daemon=True, name="ace-hotkeys")
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=1)
        for device in self.devices:
            device.close()
        self.devices.clear()
        self._thread = None

    @staticmethod
    def _find_keyboards() -> list[InputDevice]:
        keyboards: list[InputDevice] = []
        permission_denied = False
        for path in list_devices():
            try:
                device = InputDevice(path)
                keys = device.capabilities().get(ecodes.EV_KEY, [])
            except PermissionError:
                permission_denied = True
                continue
            except OSError:
                continue
            if ecodes.KEY_F9 in keys or ecodes.KEY_F10 in keys:
                keyboards.append(device)
            else:
                device.close()

        if keyboards:
            return keyboards
        if permission_denied:
            raise HotkeyError(
                "Cannot read keyboard events. Add your user to the input group with "
                "'sudo usermod -aG input $USER', then log out and back in."
            )
        raise HotkeyError("No keyboard device exposing F9 or F10 was found.")

    def _run(self) -> None:
        while not self._stop.is_set():
            try:
                ready, _, _ = select.select(self.devices, [], [], 0.25)
                for device in ready:
                    for event in device.read():
                        if event.type == ecodes.EV_KEY:
                            self._handle_key(event.code, event.value)
            except OSError:
                if not self._stop.is_set():
                    self._stop.set()

    def _handle_key(self, code: int, value: int) -> None:
        if code == ecodes.KEY_F9:
            if value == 1 and not self._f9_down:
                self._f9_down = True
                self.on_record_start()
            elif value == 0 and self._f9_down:
                self._f9_down = False
                self.on_record_stop()
        elif code == ecodes.KEY_F10 and value == 1:
            self.on_toggle_target()
