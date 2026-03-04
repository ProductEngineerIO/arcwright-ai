"""Tests for engine/graph.py — LangGraph StateGraph construction and invocation."""

from __future__ import annotations

from decimal import Decimal
from pathlib import Path

import pytest
from langgraph.graph.state import CompiledStateGraph

from arcwright_ai.agent.invoker import InvocationResult
from arcwright_ai.core.config import ApiConfig, LimitsConfig, RunConfig
from arcwright_ai.core.lifecycle import TaskState
from arcwright_ai.core.types import BudgetState, EpicId, RunId, StoryId
from arcwright_ai.engine.graph import build_story_graph
from arcwright_ai.engine.state import StoryState
from arcwright_ai.validation.pipeline import PipelineOutcome, PipelineResult
from arcwright_ai.validation.v3_reflexion import (
    ACResult,
    ReflexionFeedback,
    V3ReflexionResult,
    ValidationResult,
)
from arcwright_ai.validation.v6_invariant import V6CheckResult, V6ValidationResult


def make_run_config() -> RunConfig:
    """Build a minimal RunConfig suitable for tests."""
    return RunConfig(api=ApiConfig(claude_api_key="test-key-not-real"))


def make_initial_state() -> StoryState:
    """Build a minimal initial StoryState with QUEUED status."""
    return StoryState(
        story_id=StoryId("2-1-state-models"),
        epic_id=EpicId("epic-2"),
        run_id=RunId("20260302-143052-a7f3"),
        story_path=Path("_spec/2-1.md"),
        project_root=Path("/project"),
        config=make_run_config(),
    )


@pytest.fixture
def graph_project_state(tmp_path: Path) -> StoryState:
    """Provide a StoryState with a real project directory for full-graph invocation tests."""
    spec_dir = tmp_path / "_spec" / "planning-artifacts"
    spec_dir.mkdir(parents=True)
    (spec_dir / "prd.md").write_text("# PRD\n\n## FR1\nTest requirement", encoding="utf-8")
    (spec_dir / "architecture.md").write_text("# Architecture\n\n### Decision 1\nTest decision", encoding="utf-8")

    story_path = tmp_path / "_spec" / "implementation-artifacts" / "2-1-state-models.md"
    story_path.parent.mkdir(parents=True, exist_ok=True)
    story_path.write_text(
        "# Story 2.1\n\n## Acceptance Criteria\n\n1. Test AC\n\n## Dev Notes\n\nFR1, Decision 1\n",
        encoding="utf-8",
    )

    return StoryState(
        story_id=StoryId("2-1-state-models"),
        epic_id=EpicId("epic-2"),
        run_id=RunId("20260302-143052-a7f3"),
        story_path=story_path,
        project_root=tmp_path,
        config=make_run_config(),
    )


@pytest.fixture
def mock_agent(monkeypatch: pytest.MonkeyPatch) -> None:
    """Monkeypatch invoke_agent for graph integration tests that traverse agent_dispatch."""

    async def _mock(*args: object, **kwargs: object) -> InvocationResult:
        return InvocationResult(
            output_text="Mock agent output",
            tokens_input=100,
            tokens_output=50,
            total_cost=Decimal("0.01"),
            duration_ms=100,
            session_id="mock-session",
            num_turns=1,
            is_error=False,
        )

    monkeypatch.setattr("arcwright_ai.engine.nodes.invoke_agent", _mock)


@pytest.fixture
def mock_pipeline(monkeypatch: pytest.MonkeyPatch) -> None:
    """Monkeypatch run_validation_pipeline for graph integration tests."""
    v6 = V6ValidationResult(
        passed=True,
        results=[V6CheckResult(check_name="file_existence", passed=True)],
    )
    result = PipelineResult(
        passed=True,
        outcome=PipelineOutcome.PASS,
        v6_result=v6,
    )

    async def _mock(*args: object, **kwargs: object) -> PipelineResult:
        return result

    monkeypatch.setattr("arcwright_ai.engine.nodes.run_validation_pipeline", _mock)


# ---------------------------------------------------------------------------
# Graph construction tests
# ---------------------------------------------------------------------------


def test_build_story_graph_returns_compiled_graph() -> None:
    graph = build_story_graph()
    assert isinstance(graph, CompiledStateGraph)


def test_graph_contains_all_expected_nodes() -> None:
    graph = build_story_graph()
    node_names = set(graph.nodes.keys())
    expected = {"preflight", "budget_check", "agent_dispatch", "validate", "commit"}
    assert expected.issubset(node_names)


def test_graph_contains_expected_conditional_routing() -> None:
    graph = build_story_graph()
    branches = graph.builder.branches

    budget_branch = branches["budget_check"]["route_budget_check"].ends
    assert budget_branch["ok"] == "agent_dispatch"
    assert budget_branch["exceeded"] == "__end__"

    validate_branch = branches["validate"]["route_validation"].ends
    assert validate_branch["success"] == "commit"
    assert validate_branch["retry"] == "budget_check"
    assert validate_branch["escalated"] == "__end__"


# ---------------------------------------------------------------------------
# Graph invocation tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_graph_success_path_end_to_end(
    graph_project_state: StoryState,
    mock_agent: None,
    mock_pipeline: None,
) -> None:
    graph = build_story_graph()
    result = await graph.ainvoke(graph_project_state)
    # LangGraph may return a dict or a state object depending on config
    final_status = result.get("status") if isinstance(result, dict) else result.status
    assert final_status == TaskState.SUCCESS


@pytest.mark.asyncio
async def test_graph_invocation_no_errors(
    graph_project_state: StoryState,
    mock_agent: None,
    mock_pipeline: None,
) -> None:
    graph = build_story_graph()
    # Should not raise
    await graph.ainvoke(graph_project_state)


@pytest.mark.asyncio
async def test_graph_budget_exceeded_path_escalates_and_exits(
    graph_project_state: StoryState,
    mock_agent: None,
) -> None:
    graph = build_story_graph()
    initial_state = graph_project_state.model_copy(
        update={
            "budget": BudgetState(
                invocation_count=1,
                max_invocations=1,
                estimated_cost=Decimal("0"),
                max_cost=Decimal("0"),
            )
        }
    )

    result = await graph.ainvoke(initial_state)
    final_status = result.get("status") if isinstance(result, dict) else result.status
    assert final_status == TaskState.ESCALATED


@pytest.mark.asyncio
async def test_graph_retry_path_v3_fail_then_pass(
    graph_project_state: StoryState,
    mock_agent: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """First pipeline call FAIL_V3, second PASS: final status SUCCESS, retry_count=1."""
    v6_pass = V6ValidationResult(
        passed=True,
        results=[V6CheckResult(check_name="file_existence", passed=True)],
    )
    feedback = ReflexionFeedback(
        passed=False,
        unmet_criteria=["1"],
        feedback_per_criterion={"1": "Fix required"},
        attempt_number=1,
    )
    fail_v3 = PipelineResult(
        passed=False,
        outcome=PipelineOutcome.FAIL_V3,
        v6_result=v6_pass,
        v3_result=V3ReflexionResult(
            validation_result=ValidationResult(
                passed=False,
                ac_results=[ACResult(ac_id="1", passed=False, rationale="Missing impl")],
            ),
            feedback=feedback,
            tokens_used=400,
            cost=Decimal("0.008"),
        ),
        feedback=feedback,
        tokens_used=400,
        cost=Decimal("0.008"),
    )
    pass_result = PipelineResult(
        passed=True,
        outcome=PipelineOutcome.PASS,
        v6_result=v6_pass,
    )

    call_count = 0

    async def _mock_retry(*args: object, **kwargs: object) -> PipelineResult:
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            return fail_v3
        return pass_result

    monkeypatch.setattr("arcwright_ai.engine.nodes.run_validation_pipeline", _mock_retry)

    graph = build_story_graph()
    result = await graph.ainvoke(graph_project_state)
    final_status = result.get("status") if isinstance(result, dict) else result.status
    final_retry_count = result.get("retry_count") if isinstance(result, dict) else result.retry_count

    assert final_status == TaskState.SUCCESS
    assert final_retry_count == 1


@pytest.mark.asyncio
async def test_graph_max_retry_escalated_path(
    graph_project_state: StoryState,
    mock_agent: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Pipeline always returns FAIL_V3 with retry_budget=2: escalates after 3 attempts."""
    v6_pass = V6ValidationResult(
        passed=True,
        results=[V6CheckResult(check_name="file_existence", passed=True)],
    )
    feedback = ReflexionFeedback(
        passed=False,
        unmet_criteria=["1"],
        feedback_per_criterion={"1": "Fix required"},
        attempt_number=1,
    )
    fail_v3 = PipelineResult(
        passed=False,
        outcome=PipelineOutcome.FAIL_V3,
        v6_result=v6_pass,
        v3_result=V3ReflexionResult(
            validation_result=ValidationResult(
                passed=False,
                ac_results=[ACResult(ac_id="1", passed=False, rationale="Still failing")],
            ),
            feedback=feedback,
            tokens_used=400,
            cost=Decimal("0.008"),
        ),
        feedback=feedback,
        tokens_used=400,
        cost=Decimal("0.008"),
    )

    async def _mock_always_fail(*args: object, **kwargs: object) -> PipelineResult:
        return fail_v3

    monkeypatch.setattr("arcwright_ai.engine.nodes.run_validation_pipeline", _mock_always_fail)

    # retry_budget=2 → after 3 attempts (0<2 → retry, 1<2 → retry, 2>=2 → escalated)
    initial_state = graph_project_state.model_copy(
        update={
            "config": RunConfig(
                api=ApiConfig(claude_api_key="test-key-not-real"),
                limits=LimitsConfig(retry_budget=2),
            )
        }
    )

    graph = build_story_graph()
    result = await graph.ainvoke(initial_state)
    final_status = result.get("status") if isinstance(result, dict) else result.status

    assert final_status == TaskState.ESCALATED
