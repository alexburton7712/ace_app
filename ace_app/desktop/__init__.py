"""Qt WebEngine desktop shell for Ace App.

The modules in this package remain importable without PySide6 so core and unit
tests can run on machines that do not have the desktop runtime installed.
Calling :func:`require_qt` (or constructing a window) provides the actionable
runtime error.
"""

from __future__ import annotations


def require_qt() -> None:
    """Raise a useful error when the optional Qt desktop runtime is absent."""

    try:
        import PySide6.QtWebEngineWidgets  # noqa: F401
    except ImportError as exc:  # pragma: no cover - depends on host packages
        raise RuntimeError(
            "Ace's desktop UI requires PySide6 with Qt WebEngine. "
            "Run `python -m pip install -r requirements.txt` first."
        ) from exc


__all__ = ["require_qt"]
