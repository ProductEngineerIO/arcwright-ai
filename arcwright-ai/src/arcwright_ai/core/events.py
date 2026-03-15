"""Core events — EventEmitter protocol and NoOpEmitter for observe-mode hooks."""

from __future__ import annotations

from typing import Any, Protocol

__all__: list[str] = [
    "EventEmitter",
    "NoOpEmitter",
]


class EventEmitter(Protocol):
    """Protocol for observe-mode event emission.

    Every subsystem calls ``emit()`` at key lifecycle moments.  The default
    :class:`NoOpEmitter` silently discards events.  The Growth phase replaces it
    with a streaming emitter hooked to the CLI's ``--observe`` flag.
    """

    def emit(self, event: str, data: dict[str, Any]) -> None:
        """Emit a named event with structured data.

        Args:
            event: Dot-separated event name, e.g. ``"engine.node.enter"``.
            data: Structured payload for this event.
        """
        ...


class NoOpEmitter:
    """Default EventEmitter that discards all events.

    Used throughout MVP where observe mode is not active.
    """

    def emit(self, event: str, data: dict[str, Any]) -> None:
        """Accept and discard the event silently.

        Args:
            event: Dot-separated event name (ignored).
            data: Structured payload (ignored).
        """
