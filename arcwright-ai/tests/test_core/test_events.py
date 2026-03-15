"""Tests for core/events.py — EventEmitter protocol and NoOpEmitter."""

from __future__ import annotations

from arcwright_ai.core.events import EventEmitter, NoOpEmitter

# ---------------------------------------------------------------------------
# NoOpEmitter behaviour
# ---------------------------------------------------------------------------


def test_no_op_emitter_emit_returns_none() -> None:
    emitter = NoOpEmitter()
    result = emitter.emit("test.event", {"key": "value"})
    assert result is None


def test_no_op_emitter_emit_accepts_empty_data() -> None:
    emitter = NoOpEmitter()
    emitter.emit("engine.start", {})  # must not raise


def test_no_op_emitter_emit_accepts_nested_data() -> None:
    emitter = NoOpEmitter()
    emitter.emit("agent.invoke", {"story_id": "1-2", "tokens": 1000, "nested": {"k": "v"}})


def test_no_op_emitter_does_not_store_events() -> None:
    emitter = NoOpEmitter()
    emitter.emit("event.one", {"a": 1})
    emitter.emit("event.two", {"b": 2})
    # No state should be retained
    assert not hasattr(emitter, "_events")
    assert not hasattr(emitter, "events")


# ---------------------------------------------------------------------------
# EventEmitter Protocol duck-typing
# ---------------------------------------------------------------------------


def test_no_op_emitter_satisfies_event_emitter_protocol() -> None:
    """NoOpEmitter must structurally conform to EventEmitter Protocol."""
    emitter: EventEmitter = NoOpEmitter()
    # Protocol is satisfied — calling emit must work
    emitter.emit("test", {})


def test_custom_class_satisfies_event_emitter_protocol() -> None:
    """Any class with the right emit() signature satisfies the Protocol."""
    from typing import Any

    class _CustomEmitter:
        def __init__(self) -> None:
            self.calls: list[tuple[str, dict[str, Any]]] = []

        def emit(self, event: str, data: dict[str, Any]) -> None:
            self.calls.append((event, data))

    emitter: EventEmitter = _CustomEmitter()
    emitter.emit("custom.event", {"val": 42})
    assert emitter.calls == [("custom.event", {"val": 42})]  # type: ignore[union-attr]


# ---------------------------------------------------------------------------
# __all__ completeness
# ---------------------------------------------------------------------------


def test_all_symbols_exported() -> None:
    import arcwright_ai.core.events as mod

    expected = {"EventEmitter", "NoOpEmitter"}
    assert set(mod.__all__) == expected
