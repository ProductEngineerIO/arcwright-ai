"""Tests for engine/nodes.py — placeholder node functions and routing logic."""

from __future__ import annotations

from decimal import Decimal
from pathlib import Path

import pytest

from arcwright_ai.core.config import ApiConfig, RunConfig
from arcwright_ai.core.lifecycle import TaskState
from arcwright_ai.core.types import BudgetState, EpicId, RunId, StoryId
from arcwright_ai.engine.nodes import (
    agent_dispatch_node,
    budget_check_node,
    commit_node,
    preflight_node,
    route_budget_check,
    route_validation,
    validate_node,
)
from arcwright_ai.engine.state import StoryState


def make_run_config() -> RunConfig:
    """Build a minimal RunConfig suitable for tests."""
    return RunConfig(api=ApiConfig(claude_api_key="test-key-not-real"))


@pytest.fixture
def make_story_state() -> StoryState:
    """Return a minimal StoryState with QUEUED status."""
    return StoryState(
        story_id=StoryId("2-1-state-models"),
        epic_id=EpicId("epic-2"),
        run_id=RunId("20260302-143052-a7f3"),
        story_path=Path("_spec/2-1.md"),
        project_root=Path("/project"),
        config=make_run_config(),
    )


# ---------------------------------------------------------------------------
# Node transition tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_preflight_node_transitions_to_running(make_story_state: StoryState) -> None:
    result = await preflight_node(make_story_state)
    assert result.status == TaskState.RUNNING


@pytest.mark.asyncio
async def test_budget_check_node_passes_through_when_running(make_story_state: StoryState) -> None:
    state = make_story_state.model_copy(update={"status": TaskState.RUNNING})
    result = await budget_check_node(state)
    assert result.status == TaskState.RUNNING


@pytest.mark.asyncio
async def test_budget_check_node_transitions_retry_to_running(make_story_state: StoryState) -> None:
    state = make_story_state.model_copy(update={"status": TaskState.RETRY})
    result = await budget_check_node(state)
    assert result.status == TaskState.RUNNING


@pytest.mark.asyncio
async def test_agent_dispatch_node_transitions_to_validating(make_story_state: StoryState) -> None:
    state = make_story_state.model_copy(update={"status": TaskState.RUNNING})
    result = await agent_dispatch_node(state)
    assert result.status == TaskState.VALIDATING


@pytest.mark.asyncio
async def test_validate_node_transitions_to_success(make_story_state: StoryState) -> None:
    state = make_story_state.model_copy(update={"status": TaskState.VALIDATING})
    result = await validate_node(state)
    assert result.status == TaskState.SUCCESS


@pytest.mark.asyncio
async def test_commit_node_preserves_success(make_story_state: StoryState) -> None:
    state = make_story_state.model_copy(update={"status": TaskState.SUCCESS})
    result = await commit_node(state)
    assert result.status == TaskState.SUCCESS


# ---------------------------------------------------------------------------
# route_budget_check tests
# ---------------------------------------------------------------------------


def test_route_budget_check_returns_ok_when_within_limits(make_story_state: StoryState) -> None:
    # Default budget: max_invocations=0, max_cost=Decimal("0") — unlimited
    assert route_budget_check(make_story_state) == "ok"


def test_route_budget_check_returns_exceeded_on_invocation_limit(make_story_state: StoryState) -> None:
    budget = BudgetState(invocation_count=5, max_invocations=5)
    state = make_story_state.model_copy(update={"budget": budget})
    assert route_budget_check(state) == "exceeded"


def test_route_budget_check_returns_exceeded_on_invocation_limit_less_than(make_story_state: StoryState) -> None:
    budget = BudgetState(invocation_count=6, max_invocations=5)
    state = make_story_state.model_copy(update={"budget": budget})
    assert route_budget_check(state) == "exceeded"


def test_route_budget_check_returns_ok_when_below_invocation_limit(make_story_state: StoryState) -> None:
    budget = BudgetState(invocation_count=4, max_invocations=5)
    state = make_story_state.model_copy(update={"budget": budget})
    assert route_budget_check(state) == "ok"


def test_route_budget_check_returns_exceeded_on_cost_limit(make_story_state: StoryState) -> None:
    budget = BudgetState(estimated_cost=Decimal("1.00"), max_cost=Decimal("1.00"))
    state = make_story_state.model_copy(update={"budget": budget})
    assert route_budget_check(state) == "exceeded"


def test_route_budget_check_returns_ok_when_cost_below_limit(make_story_state: StoryState) -> None:
    budget = BudgetState(estimated_cost=Decimal("0.50"), max_cost=Decimal("1.00"))
    state = make_story_state.model_copy(update={"budget": budget})
    assert route_budget_check(state) == "ok"


def test_route_budget_check_returns_ok_when_max_cost_is_zero_unlimited(make_story_state: StoryState) -> None:
    budget = BudgetState(estimated_cost=Decimal("999.99"), max_cost=Decimal("0"))
    state = make_story_state.model_copy(update={"budget": budget})
    assert route_budget_check(state) == "ok"


# ---------------------------------------------------------------------------
# route_validation tests
# ---------------------------------------------------------------------------


def test_route_validation_returns_success(make_story_state: StoryState) -> None:
    state = make_story_state.model_copy(update={"status": TaskState.SUCCESS})
    assert route_validation(state) == "success"


def test_route_validation_returns_retry(make_story_state: StoryState) -> None:
    state = make_story_state.model_copy(update={"status": TaskState.RETRY})
    assert route_validation(state) == "retry"


def test_route_validation_returns_escalated(make_story_state: StoryState) -> None:
    state = make_story_state.model_copy(update={"status": TaskState.ESCALATED})
    assert route_validation(state) == "escalated"
