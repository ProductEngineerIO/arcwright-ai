"""Core lifecycle — Task lifecycle state machine and transition validation."""

from __future__ import annotations

from enum import StrEnum

__all__: list[str] = [
    "VALID_TRANSITIONS",
    "TaskState",
    "validate_transition",
]


class TaskState(StrEnum):
    """Lifecycle states for a story execution task.

    States flow through:
    ``queued → preflight → running → validating → success / retry / escalated``.
    Retry cycles back to running.  Escalated is terminal (halt).
    """

    QUEUED = "queued"
    PREFLIGHT = "preflight"
    RUNNING = "running"
    VALIDATING = "validating"
    SUCCESS = "success"
    RETRY = "retry"
    ESCALATED = "escalated"


#: Complete state-transition graph.  Terminal states map to empty frozensets.
VALID_TRANSITIONS: dict[TaskState, frozenset[TaskState]] = {
    TaskState.QUEUED: frozenset({TaskState.PREFLIGHT}),
    TaskState.PREFLIGHT: frozenset({TaskState.RUNNING, TaskState.ESCALATED}),
    TaskState.RUNNING: frozenset({TaskState.VALIDATING, TaskState.ESCALATED}),
    TaskState.VALIDATING: frozenset({TaskState.SUCCESS, TaskState.RETRY, TaskState.ESCALATED}),
    TaskState.RETRY: frozenset({TaskState.RUNNING, TaskState.ESCALATED}),
    TaskState.SUCCESS: frozenset(),  # terminal
    TaskState.ESCALATED: frozenset(),  # terminal
}


def validate_transition(from_state: TaskState, to_state: TaskState) -> None:
    """Validate a task lifecycle state transition.

    Args:
        from_state: Current state.
        to_state: Proposed next state.

    Raises:
        ValueError: If the transition from *from_state* to *to_state* is not
            permitted by the state machine.
    """
    allowed = VALID_TRANSITIONS.get(from_state, frozenset())
    if to_state not in allowed:
        sorted_allowed = sorted(str(s) for s in allowed) or ["none (terminal state)"]
        raise ValueError(
            f"Invalid state transition: {from_state!r} \u2192 {to_state!r}. "
            f"Allowed from {from_state!r}: {sorted_allowed}"
        )
