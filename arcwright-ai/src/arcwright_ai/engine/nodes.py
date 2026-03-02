"""Engine nodes — Individual graph node implementations for orchestration pipeline."""

from __future__ import annotations

import logging
from decimal import Decimal

from arcwright_ai.core.lifecycle import TaskState
from arcwright_ai.engine.state import StoryState  # noqa: TC001

__all__: list[str] = [
    "agent_dispatch_node",
    "budget_check_node",
    "commit_node",
    "preflight_node",
    "route_budget_check",
    "route_validation",
    "validate_node",
]

logger = logging.getLogger(__name__)


async def preflight_node(state: StoryState) -> StoryState:
    """Placeholder preflight node — transitions QUEUED → RUNNING.

    Args:
        state: Current story execution state.

    Returns:
        Updated state with status set to RUNNING.
    """
    logger.info("engine.node.enter", extra={"data": {"node": "preflight", "story": str(state.story_id)}})
    # Transition: QUEUED → PREFLIGHT → RUNNING
    intermediate = state.model_copy(update={"status": TaskState.PREFLIGHT})
    updated = intermediate.model_copy(update={"status": TaskState.RUNNING})
    logger.info(
        "engine.node.exit",
        extra={"data": {"node": "preflight", "story": str(state.story_id), "status": str(updated.status)}},
    )
    return updated


async def budget_check_node(state: StoryState) -> StoryState:
    """Placeholder budget check node — handles budget/execution status transitions.

    If the budget is already exceeded, transitions to ESCALATED so the graph
    can terminate in an explicit escalated state. If the incoming state is
    RETRY (e.g., from a validation retry cycle), transitions back to RUNNING
    so the agent can be re-invoked. Otherwise passes state through unchanged.
    The routing decision (ok vs exceeded) is made by ``route_budget_check``.

    Args:
        state: Current story execution state.

    Returns:
        Updated state with status adjusted if coming from RETRY.
    """
    logger.info("engine.node.enter", extra={"data": {"node": "budget_check", "story": str(state.story_id)}})
    if route_budget_check(state) == "exceeded":
        updated = state.model_copy(update={"status": TaskState.ESCALATED})
        logger.info(
            "engine.node.exit",
            extra={"data": {"node": "budget_check", "story": str(state.story_id), "status": str(updated.status)}},
        )
        return updated
    if state.status == TaskState.RETRY:
        updated = state.model_copy(update={"status": TaskState.RUNNING})
        logger.info(
            "engine.node.exit",
            extra={"data": {"node": "budget_check", "story": str(state.story_id), "status": str(updated.status)}},
        )
        return updated
    logger.info(
        "engine.node.exit",
        extra={"data": {"node": "budget_check", "story": str(state.story_id), "status": str(state.status)}},
    )
    return state


async def agent_dispatch_node(state: StoryState) -> StoryState:
    """Placeholder agent dispatch node — transitions RUNNING → VALIDATING.

    Args:
        state: Current story execution state.

    Returns:
        Updated state with status set to VALIDATING.
    """
    logger.info("engine.node.enter", extra={"data": {"node": "agent_dispatch", "story": str(state.story_id)}})
    updated = state.model_copy(update={"status": TaskState.VALIDATING})
    logger.info(
        "engine.node.exit",
        extra={"data": {"node": "agent_dispatch", "story": str(state.story_id), "status": str(updated.status)}},
    )
    return updated


async def validate_node(state: StoryState) -> StoryState:
    """Placeholder validate node — transitions VALIDATING → SUCCESS.

    Placeholder implementation always succeeds (no real validation logic).
    Real validation is implemented in Epic 3.

    Args:
        state: Current story execution state.

    Returns:
        Updated state with status set to SUCCESS.
    """
    logger.info("engine.node.enter", extra={"data": {"node": "validate", "story": str(state.story_id)}})
    updated = state.model_copy(update={"status": TaskState.SUCCESS})
    logger.info(
        "engine.node.exit",
        extra={"data": {"node": "validate", "story": str(state.story_id), "status": str(updated.status)}},
    )
    return updated


async def commit_node(state: StoryState) -> StoryState:
    """Placeholder commit node — passes SUCCESS state through unchanged.

    Args:
        state: Current story execution state (expected SUCCESS).

    Returns:
        State unchanged.
    """
    logger.info("engine.node.enter", extra={"data": {"node": "commit", "story": str(state.story_id)}})
    logger.info(
        "engine.node.exit",
        extra={"data": {"node": "commit", "story": str(state.story_id), "status": str(state.status)}},
    )
    return state


def route_budget_check(state: StoryState) -> str:
    """Route after budget_check node — returns 'exceeded' or 'ok'.

    Returns 'exceeded' if:
    - max_invocations > 0 AND invocation_count >= max_invocations
    - OR max_cost > Decimal(0) AND estimated_cost >= max_cost

    Returns 'ok' otherwise (max values of 0 mean unlimited).

    Args:
        state: Current story execution state.

    Returns:
        'exceeded' if budget limits are breached, 'ok' otherwise.
    """
    budget = state.budget
    if budget.max_invocations > 0 and budget.invocation_count >= budget.max_invocations:
        return "exceeded"
    if budget.max_cost > Decimal(0) and budget.estimated_cost >= budget.max_cost:
        return "exceeded"
    return "ok"


def route_validation(state: StoryState) -> str:
    """Route after validate node — returns 'success', 'retry', or 'escalated'.

    Args:
        state: Current story execution state.

    Returns:
        'success' if status is SUCCESS, 'retry' if RETRY, 'escalated' otherwise.
    """
    if state.status == TaskState.SUCCESS:
        return "success"
    if state.status == TaskState.RETRY:
        return "retry"
    return "escalated"
