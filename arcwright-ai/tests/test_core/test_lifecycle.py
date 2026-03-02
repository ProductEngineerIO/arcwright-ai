"""Tests for core/lifecycle.py — TaskState enum and transition validation."""

from __future__ import annotations

import pytest

from arcwright_ai.core.lifecycle import VALID_TRANSITIONS, TaskState, validate_transition

# ---------------------------------------------------------------------------
# TaskState enum values
# ---------------------------------------------------------------------------


def test_task_state_values() -> None:
    assert str(TaskState.QUEUED) == "queued"
    assert str(TaskState.PREFLIGHT) == "preflight"
    assert str(TaskState.RUNNING) == "running"
    assert str(TaskState.VALIDATING) == "validating"
    assert str(TaskState.SUCCESS) == "success"
    assert str(TaskState.RETRY) == "retry"
    assert str(TaskState.ESCALATED) == "escalated"


def test_task_state_count() -> None:
    assert len(TaskState) == 7


def test_task_state_is_str() -> None:
    for state in TaskState:
        assert isinstance(state, str)


# ---------------------------------------------------------------------------
# Valid transitions — must not raise
# ---------------------------------------------------------------------------


def test_valid_transition_queued_to_preflight() -> None:
    validate_transition(TaskState.QUEUED, TaskState.PREFLIGHT)


def test_valid_transition_preflight_to_running() -> None:
    validate_transition(TaskState.PREFLIGHT, TaskState.RUNNING)


def test_valid_transition_preflight_to_escalated() -> None:
    validate_transition(TaskState.PREFLIGHT, TaskState.ESCALATED)


def test_valid_transition_running_to_validating() -> None:
    validate_transition(TaskState.RUNNING, TaskState.VALIDATING)


def test_valid_transition_running_to_escalated() -> None:
    validate_transition(TaskState.RUNNING, TaskState.ESCALATED)


def test_valid_transition_validating_to_success() -> None:
    validate_transition(TaskState.VALIDATING, TaskState.SUCCESS)


def test_valid_transition_validating_to_retry() -> None:
    validate_transition(TaskState.VALIDATING, TaskState.RETRY)


def test_valid_transition_validating_to_escalated() -> None:
    validate_transition(TaskState.VALIDATING, TaskState.ESCALATED)


def test_valid_transition_retry_to_running() -> None:
    validate_transition(TaskState.RETRY, TaskState.RUNNING)


def test_valid_transition_retry_to_escalated() -> None:
    validate_transition(TaskState.RETRY, TaskState.ESCALATED)


# ---------------------------------------------------------------------------
# All entries in VALID_TRANSITIONS must pass validation
# ---------------------------------------------------------------------------


def test_all_valid_transitions_in_table_pass() -> None:
    for from_state, destinations in VALID_TRANSITIONS.items():
        for to_state in destinations:
            validate_transition(from_state, to_state)  # must not raise


# ---------------------------------------------------------------------------
# Invalid transitions — must raise ValueError with descriptive message
# ---------------------------------------------------------------------------


def test_invalid_transition_queued_to_running() -> None:
    with pytest.raises(ValueError, match="queued"):
        validate_transition(TaskState.QUEUED, TaskState.RUNNING)


def test_invalid_transition_queued_to_success() -> None:
    with pytest.raises(ValueError, match="success"):
        validate_transition(TaskState.QUEUED, TaskState.SUCCESS)


def test_invalid_transition_running_to_queued() -> None:
    with pytest.raises(ValueError, match="running"):
        validate_transition(TaskState.RUNNING, TaskState.QUEUED)


def test_invalid_transition_running_to_preflight() -> None:
    with pytest.raises(ValueError, match="preflight"):
        validate_transition(TaskState.RUNNING, TaskState.PREFLIGHT)


def test_invalid_transition_validating_to_queued() -> None:
    with pytest.raises(ValueError, match="queued"):
        validate_transition(TaskState.VALIDATING, TaskState.QUEUED)


# ---------------------------------------------------------------------------
# Terminal states — any outgoing transition must raise
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("to_state", list(TaskState))
def test_success_is_terminal(to_state: TaskState) -> None:
    with pytest.raises(ValueError, match="terminal"):
        validate_transition(TaskState.SUCCESS, to_state)


@pytest.mark.parametrize("to_state", list(TaskState))
def test_escalated_is_terminal(to_state: TaskState) -> None:
    with pytest.raises(ValueError, match="terminal"):
        validate_transition(TaskState.ESCALATED, to_state)


# ---------------------------------------------------------------------------
# Error message format — contains both state names
# ---------------------------------------------------------------------------


def test_error_message_contains_from_state() -> None:
    with pytest.raises(ValueError, match="queued"):
        validate_transition(TaskState.QUEUED, TaskState.RUNNING)


def test_error_message_contains_to_state() -> None:
    with pytest.raises(ValueError, match="running"):
        validate_transition(TaskState.QUEUED, TaskState.RUNNING)


# ---------------------------------------------------------------------------
# __all__ completeness
# ---------------------------------------------------------------------------


def test_all_symbols_exported() -> None:
    import arcwright_ai.core.lifecycle as mod

    expected = {"TaskState", "VALID_TRANSITIONS", "validate_transition"}
    assert set(mod.__all__) == expected
