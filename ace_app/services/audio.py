"""PipeWire WAV recording lifecycle."""

from __future__ import annotations

import os
import signal
import subprocess
import tempfile
import threading
from pathlib import Path


class RecordingError(RuntimeError):
    pass


class AudioRecorder:
    def __init__(self, executable: str = "pw-record", sample_rate: int = 16_000) -> None:
        self.executable = executable
        self.sample_rate = sample_rate
        self.process: subprocess.Popen[bytes] | None = None
        self.path: Path | None = None
        self._lock = threading.RLock()

    @property
    def recording(self) -> bool:
        with self._lock:
            return self.process is not None

    def start(self) -> None:
        with self._lock:
            if self.process is not None:
                return
            descriptor, raw_path = tempfile.mkstemp(prefix="ace-app-", suffix=".wav")
            os.close(descriptor)
            path = Path(raw_path)
            try:
                process = subprocess.Popen(
                    [
                        self.executable,
                        "--rate",
                        str(self.sample_rate),
                        "--channels",
                        "1",
                        "--format",
                        "s16",
                        raw_path,
                    ],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.PIPE,
                )
            except OSError as exc:
                path.unlink(missing_ok=True)
                raise RecordingError(f"Could not start {self.executable}: {exc}") from exc
            self.path = path
            self.process = process

    def stop(self) -> bytes:
        with self._lock:
            if self.process is None or self.path is None:
                raise RecordingError("No recording is active")
            process, path = self.process, self.path
            self.process = None
            self.path = None

        if process.poll() is None:
            process.send_signal(signal.SIGINT)
        try:
            _, stderr = process.communicate(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
            _, stderr = process.communicate()
        try:
            data = path.read_bytes()
        except OSError as exc:
            raise RecordingError(f"Could not read recorded audio: {exc}") from exc
        finally:
            path.unlink(missing_ok=True)
        if len(data) <= 44 or not (data.startswith(b"RIFF") and data[8:12] == b"WAVE"):
            detail = (stderr or b"").decode(errors="replace")[:300]
            message = "Recording did not produce valid WAV audio"
            raise RecordingError(f"{message}: {detail}" if detail else message)
        return data

    def discard(self) -> None:
        with self._lock:
            process, path = self.process, self.path
            self.process = None
            self.path = None
        if process is not None and process.poll() is None:
            process.kill()
            try:
                process.communicate(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.communicate()
        if path is not None:
            path.unlink(missing_ok=True)

    close = discard
