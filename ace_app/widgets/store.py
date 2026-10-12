"""Thread-safe, insertion-ordered, in-memory widget storage."""

from __future__ import annotations

import logging
from collections import OrderedDict
from collections.abc import Callable
from datetime import datetime
from threading import RLock

from .models import IngestResult, SourceTarget, Widget, WidgetEvent, utc_now
from .validation import DEFAULT_MAX_BODY_BYTES, WidgetValidationError, validate_widget_payload

WidgetCallback = Callable[[WidgetEvent], None]
_LOG = logging.getLogger(__name__)


class WidgetStore:
    """Authoritative session state. No method performs filesystem I/O."""

    def __init__(self) -> None:
        self._lock = RLock()
        self._widgets: OrderedDict[str, Widget] = OrderedDict()
        self._revision = 0
        self._callbacks: list[WidgetCallback] = []

    @property
    def revision(self) -> int:
        with self._lock:
            return self._revision

    def subscribe(self, callback: WidgetCallback) -> Callable[[], None]:
        """Register a framework-neutral change callback and return an unsubscribe function."""
        if not callable(callback):
            raise TypeError("callback must be callable")
        with self._lock:
            self._callbacks.append(callback)

        def unsubscribe() -> None:
            with self._lock:
                try:
                    self._callbacks.remove(callback)
                except ValueError:
                    pass

        return unsubscribe

    def upsert(
        self,
        widget_id: str,
        html: str,
        source_target: SourceTarget,
        *,
        now: datetime | None = None,
    ) -> IngestResult:
        if source_target not in ("local", "server"):
            raise ValueError("source_target must be local or server")
        timestamp = now or utc_now()
        with self._lock:
            previous = self._widgets.get(widget_id)
            self._revision += 1
            revision = self._revision
            widget = Widget(
                id=widget_id,
                html=html,
                source_target=source_target,
                created_at=previous.created_at if previous else timestamp,
                updated_at=timestamp,
                revision=revision,
            )
            self._widgets[widget_id] = widget
            callbacks = tuple(self._callbacks)
        self._notify(callbacks, WidgetEvent("upsert", revision, widget=widget))
        return IngestResult(widget, "replaced" if previous else "created")

    def get(self, widget_id: str) -> Widget | None:
        with self._lock:
            return self._widgets.get(widget_id)

    def list(self) -> list[Widget]:
        with self._lock:
            return list(self._widgets.values())

    snapshot = list

    def remove(self, widget_id: str) -> Widget | None:
        with self._lock:
            removed = self._widgets.pop(widget_id, None)
            if removed is None:
                return None
            self._revision += 1
            revision = self._revision
            callbacks = tuple(self._callbacks)
        self._notify(callbacks, WidgetEvent("remove", revision, widget_id=widget_id))
        return removed

    dismiss = remove

    def clear(self) -> None:
        with self._lock:
            if not self._widgets:
                return
            self._widgets.clear()
            self._revision += 1
            revision = self._revision
            callbacks = tuple(self._callbacks)
        self._notify(callbacks, WidgetEvent("clear", revision))

    def __len__(self) -> int:
        with self._lock:
            return len(self._widgets)

    @staticmethod
    def _notify(callbacks: tuple[WidgetCallback, ...], event: WidgetEvent) -> None:
        for callback in callbacks:
            try:
                callback(event)
            except Exception:
                # State has already committed. A presentation listener cannot roll it back.
                _LOG.exception("widget change callback failed")


def ingest_widget(
    source_target: SourceTarget,
    untrusted_payload: object,
    store: WidgetStore,
    *,
    max_widget_bytes: int = DEFAULT_MAX_BODY_BYTES,
) -> IngestResult:
    """The single validation-and-mutation path used by every transport."""
    if source_target not in ("local", "server"):
        raise WidgetValidationError("invalid_source", "invalid widget source")
    validated = validate_widget_payload(untrusted_payload, max_widget_bytes=max_widget_bytes)
    return store.upsert(validated.id, validated.html, source_target)
