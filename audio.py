from __future__ import annotations

import os
import signal
import subprocess
import tempfile
from pathlib import Path


class RecordingError(RuntimeError):
    pass


class AudioRecorder:
    def __init__(self, executable: str = "pw-record", sample_rate: int = 16000) -> None:
        self.executable = executable
        self.sample_rate = sample_rate
        self.process: subprocess.Popen[bytes] | None = None
        self.path: Path | None = None

    @property
    def recording(self) -> bool:
        return self.process is not None

    def start(self) -> None:
        if self.recording:
            return
        fd, path = tempfile.mkstemp(prefix="ace-app-", suffix=".wav")
        os.close(fd)
        self.path = Path(path)
        try:
            self.process = subprocess.Popen(
                [self.executable, "--rate", str(self.sample_rate), "--channels", "1", "--format", "s16", path],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.PIPE,
            )
        except OSError as exc:
            self.path.unlink(missing_ok=True)
            self.path = None
            raise RecordingError(f"Could not start {self.executable}: {exc}") from exc

    def stop(self) -> bytes:
        if not self.process or not self.path:
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
        finally:
            path.unlink(missing_ok=True)
        if len(data) <= 44 or not (data.startswith(b"RIFF") and data[8:12] == b"WAVE"):
            raise RecordingError(f"Recording did not produce valid WAV audio: {stderr.decode(errors='replace')[:300]}")
        return data

    def discard(self) -> None:
        if self.process and self.process.poll() is None:
            self.process.kill()
            self.process.communicate()
        if self.path:
            self.path.unlink(missing_ok=True)
        self.process = None
        self.path = None
