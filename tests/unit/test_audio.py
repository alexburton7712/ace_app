import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock

from ace_app.services.audio import AudioRecorder, RecordingError


class AudioRecorderTests(unittest.TestCase):
    def test_stop_returns_valid_wav_and_removes_file(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "clip.wav"
            path.write_bytes(b"RIFF" + b"\0" * 4 + b"WAVE" + b"\0" * 40)
            process = Mock()
            process.poll.return_value = None
            process.communicate.return_value = (b"", b"")
            recorder = AudioRecorder()
            recorder.path = path
            recorder.process = process

            data = recorder.stop()

            self.assertTrue(data.startswith(b"RIFF"))
            self.assertFalse(path.exists())
            process.send_signal.assert_called_once()

    def test_stop_rejects_invalid_wav(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "clip.wav"
            path.write_bytes(b"not wave data")
            process = Mock()
            process.poll.return_value = 0
            process.communicate.return_value = (b"", b"capture failed")
            recorder = AudioRecorder()
            recorder.path = path
            recorder.process = process

            with self.assertRaises(RecordingError):
                recorder.stop()


if __name__ == "__main__":
    unittest.main()
