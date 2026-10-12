"""Service adapters used by the Ace application controller."""

from .ace_client import AceAPIError, AceClient, AudioReply
from .audio import AudioRecorder, RecordingError
from .history import SessionHistory
from .hotkeys import HotkeyError, HotkeyListener

__all__ = [
    "AceAPIError",
    "AceClient",
    "AudioRecorder",
    "AudioReply",
    "SessionHistory",
    "HotkeyError",
    "HotkeyListener",
    "RecordingError",
]
