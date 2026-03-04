"""Tests for engine/nodes.py — graph node implementations and routing logic."""

from __future__ import annotations

import logging
from decimal import Decimal
from pathlib import Path

import pytest

from arcwright_ai.agent.invoker import InvocationResult
from arcwright_ai.core.config import ApiConfig, LimitsConfig, RunConfig
from arcwright_ai.core.constants import (
    AGENT_OUTPUT_FILENAME,
    CONTEXT_BUNDLE_FILENAME,
    DIR_ARCWRIGHT,
    DIR_RUNS,
    DIR_STORIES,
    HALT_REPORT_FILENAME,
    VALIDATION_FILENAME,
)
from arcwright_ai.core.exceptions import AgentError, ContextError, ValidationError
from arcwright_ai.core.lifecycle import TaskState
from arcwright_ai.core.types import BudgetState, ContextBundle, EpicId, RunId, StoryId
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
from arcwright_ai.validation.pipeline import PipelineOutcome, PipelineResult
from arcwright_ai.validation.v3_reflexion import (
    ACResult,
    ReflexionFeedback,
    V3ReflexionResult,
    ValidationResult,
)
from arcwright_ai.validation.v6_invariant import V6CheckResult, V6ValidationResult


def make_run_config(retry_budget: int = 3) -> RunConfig:
    """Build a minimal RunConfig suitable for tests."""
    return RunConfig(
        api=ApiConfig(claude_api_key="test-key-not-real"),
        limits=LimitsConfig(retry_budget=retry_budget),
    )


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


@pytest.fixture
def story_state_with_project(tmp_path: Path) -> StoryState:
    """Create a StoryState backed by a real project directory with BMAD artifacts."""
    spec_dir = tmp_path / "_spec" / "planning-artifacts"
    spec_dir.mkdir(parents=True)
    (spec_dir / "prd.md").write_text("# PRD\n\n## FR1\nTest requirement", encoding="utf-8")
    (spec_dir / "architecture.md").write_text("# Architecture\n\n### Decision 1\nTest decision", encoding="utf-8")

    story_path = tmp_path / "_spec" / "implementation-artifacts" / "2-6-preflight.md"
    story_path.parent.mkdir(parents=True, exist_ok=True)
    story_path.write_text(
        "# Story 2.6\n\n## Acceptance Criteria\n\n1. Test AC\n\n## Dev Notes\n\nFR1, Decision 1\n",
        encoding="utf-8",
    )

    return StoryState(
        story_id=StoryId("2-6-preflight-node"),
        epic_id=EpicId("epic-2"),
        run_id=RunId("20260302-143052-a7f3"),
        story_path=story_path,
        project_root=tmp_path,
        config=make_run_config(),
    )


@pytest.fixture
def validate_ready_state(tmp_path: Path) -> StoryState:
    """StoryState ready for validate_node — VALIDATING status with tmp_path project_root."""
    return StoryState(
        story_id=StoryId("3-4-validate-node"),
        epic_id=EpicId("epic-3"),
        run_id=RunId("20260302-143052-a7f3"),
        story_path=tmp_path / "_spec" / "3-4.md",
        project_root=tmp_path,
        status=TaskState.VALIDATING,
        agent_output="Mock implementation output",
        config=make_run_config(),
    )


def _make_pass_result() -> PipelineResult:
    """Create a PASS PipelineResult for test fixtures."""
    v6 = V6ValidationResult(
        passed=True,
        results=[V6CheckResult(check_name="file_existence", passed=True)],
    )
    return PipelineResult(
        passed=True,
        outcome=PipelineOutcome.PASS,
        v6_result=v6,
        tokens_used=300,
        cost=Decimal("0.005"),
    )


def _make_fail_v3_result() -> PipelineResult:
    """Create a FAIL_V3 PipelineResult with feedback for test fixtures."""
    v6 = V6ValidationResult(
        passed=True,
        results=[V6CheckResult(check_name="file_existence", passed=True)],
    )
    feedback = ReflexionFeedback(
        passed=False,
        unmet_criteria=["2", "3"],
        feedback_per_criterion={
            "2": "Missing X implementation",
            "3": "Test not passing",
        },
        attempt_number=1,
    )
    v3 = V3ReflexionResult(
        validation_result=ValidationResult(
            passed=False,
            ac_results=[
                ACResult(ac_id="2", passed=False, rationale="Missing X"),
                ACResult(ac_id="3", passed=False, rationale="Test failure"),
            ],
        ),
        feedback=feedback,
        tokens_used=500,
        cost=Decimal("0.01"),
    )
    return PipelineResult(
        passed=False,
        outcome=PipelineOutcome.FAIL_V3,
        v6_result=v6,
        v3_result=v3,
        feedback=feedback,
        tokens_used=500,
        cost=Decimal("0.01"),
    )


def _make_fail_v6_result() -> PipelineResult:
    """Create a FAIL_V6 PipelineResult for test fixtures."""
    v6 = V6ValidationResult(
        passed=False,
        results=[
            V6CheckResult(
                check_name="file_existence",
                passed=False,
                failure_detail="Required file src/module.py missing",
            )
        ],
    )
    return PipelineResult(
        passed=False,
        outcome=PipelineOutcome.FAIL_V6,
        v6_result=v6,
        tokens_used=0,
        cost=Decimal("0"),
    )


@pytest.fixture
def mock_pipeline_pass(monkeypatch: pytest.MonkeyPatch) -> PipelineResult:
    """Monkeypatch run_validation_pipeline to return PASS result."""
    result = _make_pass_result()

    async def _mock(*args: object, **kwargs: object) -> PipelineResult:
        return result

    monkeypatch.setattr("arcwright_ai.engine.nodes.run_validation_pipeline", _mock)
    return result


@pytest.fixture
def mock_pipeline_fail_v3(monkeypatch: pytest.MonkeyPatch) -> PipelineResult:
    """Monkeypatch run_validation_pipeline to return FAIL_V3 result."""
    result = _make_fail_v3_result()

    async def _mock(*args: object, **kwargs: object) -> PipelineResult:
        return result

    monkeypatch.setattr("arcwright_ai.engine.nodes.run_validation_pipeline", _mock)
    return result


@pytest.fixture
def mock_pipeline_fail_v6(monkeypatch: pytest.MonkeyPatch) -> PipelineResult:
    """Monkeypatch run_validation_pipeline to return FAIL_V6 result."""
    result = _make_fail_v6_result()

    async def _mock(*args: object, **kwargs: object) -> PipelineResult:
        return result

    monkeypatch.setattr("arcwright_ai.engine.nodes.run_validation_pipeline", _mock)
    return result


# ---------------------------------------------------------------------------
# Node transition tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_preflight_node_transitions_to_running(story_state_with_project: StoryState) -> None:
    result = await preflight_node(story_state_with_project)
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
async def test_budget_check_node_transitions_to_escalated_when_budget_exceeded(make_story_state: StoryState) -> None:
    state = make_story_state.model_copy(update={"budget": BudgetState(invocation_count=1, max_invocations=1)})
    result = await budget_check_node(state)
    assert result.status == TaskState.ESCALATED


@pytest.mark.asyncio
async def test_agent_dispatch_node_raises_context_error_when_bundle_missing(make_story_state: StoryState) -> None:
    """agent_dispatch_node raises ContextError if context_bundle is None."""
    state = make_story_state.model_copy(update={"status": TaskState.RUNNING, "context_bundle": None})
    with pytest.raises(ContextError, match="context_bundle"):
        await agent_dispatch_node(state)


@pytest.mark.asyncio
async def test_validate_node_transitions_to_success(
    validate_ready_state: StoryState,
    mock_pipeline_pass: PipelineResult,
) -> None:
    result = await validate_node(validate_ready_state)
    assert result.status == TaskState.SUCCESS
    assert result.validation_result is not None
    assert result.validation_result.passed is True


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


# ---------------------------------------------------------------------------
# validate_node — real implementation unit tests (Task 5)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_validate_node_v3_fail_within_retry_budget_transitions_to_retry(
    validate_ready_state: StoryState,
    mock_pipeline_fail_v3: PipelineResult,
) -> None:
    """FAIL_V3 with retry_count=0 and retry_budget=3 → RETRY, retry_count becomes 1."""
    state = validate_ready_state.model_copy(update={"retry_count": 0})
    result = await validate_node(state)
    assert result.status == TaskState.RETRY
    assert result.retry_count == 1


@pytest.mark.asyncio
async def test_validate_node_v3_fail_at_retry_limit_transitions_to_escalated(
    validate_ready_state: StoryState,
    mock_pipeline_fail_v3: PipelineResult,
) -> None:
    """FAIL_V3 with retry_count=3 and retry_budget=3 → ESCALATED, halt report written."""
    state = validate_ready_state.model_copy(
        update={
            "retry_count": 3,
            "config": make_run_config(retry_budget=3),
        }
    )
    result = await validate_node(state)
    assert result.status == TaskState.ESCALATED
    assert result.retry_count == 4

    halt_path = (
        validate_ready_state.project_root
        / DIR_ARCWRIGHT
        / DIR_RUNS
        / str(validate_ready_state.run_id)
        / DIR_STORIES
        / str(validate_ready_state.story_id)
        / HALT_REPORT_FILENAME
    )
    assert halt_path.exists()


@pytest.mark.asyncio
async def test_validate_node_v6_fail_transitions_to_escalated_immediately(
    validate_ready_state: StoryState,
    mock_pipeline_fail_v6: PipelineResult,
) -> None:
    """FAIL_V6 → ESCALATED immediately regardless of retry_count, halt report written."""
    state = validate_ready_state.model_copy(update={"retry_count": 0})
    result = await validate_node(state)
    assert result.status == TaskState.ESCALATED
    # retry_count NOT incremented on V6 failure
    assert result.retry_count == 0

    halt_path = (
        validate_ready_state.project_root
        / DIR_ARCWRIGHT
        / DIR_RUNS
        / str(validate_ready_state.run_id)
        / DIR_STORIES
        / str(validate_ready_state.story_id)
        / HALT_REPORT_FILENAME
    )
    assert halt_path.exists()


@pytest.mark.asyncio
async def test_validate_node_updates_budget_with_pipeline_costs(
    validate_ready_state: StoryState,
    mock_pipeline_pass: PipelineResult,
) -> None:
    """budget.total_tokens and budget.estimated_cost include pipeline costs."""
    result = await validate_node(validate_ready_state)
    assert result.budget.total_tokens == mock_pipeline_pass.tokens_used
    assert result.budget.estimated_cost == mock_pipeline_pass.cost


@pytest.mark.asyncio
async def test_validate_node_accumulates_retry_history(
    validate_ready_state: StoryState,
    mock_pipeline_pass: PipelineResult,
) -> None:
    """After validate_node runs, retry_history grows by one entry."""
    result = await validate_node(validate_ready_state)
    assert len(result.retry_history) == 1
    assert result.retry_history[0] is mock_pipeline_pass


@pytest.mark.asyncio
async def test_validate_node_writes_validation_checkpoint(
    validate_ready_state: StoryState,
    mock_pipeline_pass: PipelineResult,
) -> None:
    """validation.md is written at expected path after validate_node runs."""
    await validate_node(validate_ready_state)

    checkpoint_path = (
        validate_ready_state.project_root
        / DIR_ARCWRIGHT
        / DIR_RUNS
        / str(validate_ready_state.run_id)
        / DIR_STORIES
        / str(validate_ready_state.story_id)
        / VALIDATION_FILENAME
    )
    assert checkpoint_path.exists()
    content = checkpoint_path.read_text(encoding="utf-8")
    assert "# Validation Result" in content
    assert "Outcome" in content


@pytest.mark.asyncio
async def test_validate_node_writes_halt_report_on_v3_escalation(
    validate_ready_state: StoryState,
    mock_pipeline_fail_v3: PipelineResult,
) -> None:
    """halt-report.md is written with expected content on V3 MAX_RETRIES escalation."""
    state = validate_ready_state.model_copy(
        update={
            "retry_count": 3,
            "config": make_run_config(retry_budget=3),
        }
    )
    await validate_node(state)

    halt_path = (
        validate_ready_state.project_root
        / DIR_ARCWRIGHT
        / DIR_RUNS
        / str(validate_ready_state.run_id)
        / DIR_STORIES
        / str(validate_ready_state.story_id)
        / HALT_REPORT_FILENAME
    )
    assert halt_path.exists()
    content = halt_path.read_text(encoding="utf-8")
    assert "# Halt Report" in content
    assert "max_retries_exhausted" in content
    assert "Retry History" in content
    assert "**Retry Count**: 4" in content


@pytest.mark.asyncio
async def test_validate_node_writes_halt_report_on_v6_failure(
    validate_ready_state: StoryState,
    mock_pipeline_fail_v6: PipelineResult,
) -> None:
    """halt-report.md is written with V6 failure content on FAIL_V6 escalation."""
    await validate_node(validate_ready_state)

    halt_path = (
        validate_ready_state.project_root
        / DIR_ARCWRIGHT
        / DIR_RUNS
        / str(validate_ready_state.run_id)
        / DIR_STORIES
        / str(validate_ready_state.story_id)
        / HALT_REPORT_FILENAME
    )
    assert halt_path.exists()
    content = halt_path.read_text(encoding="utf-8")
    assert "# Halt Report" in content
    assert "v6_invariant_failure" in content
    assert "V6 Invariant Failures" in content


@pytest.mark.asyncio
async def test_validate_node_raises_validation_error_when_agent_output_missing(
    validate_ready_state: StoryState,
    mock_pipeline_pass: PipelineResult,
) -> None:
    """ValidationError raised immediately when agent_output is None."""
    state = validate_ready_state.model_copy(update={"agent_output": None})
    with pytest.raises(ValidationError, match="validate_node requires agent_output"):
        await validate_node(state)


@pytest.mark.asyncio
async def test_validate_node_emits_validation_pass_log_event(
    validate_ready_state: StoryState,
    mock_pipeline_pass: PipelineResult,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """validation.pass log event is emitted with expected data on success."""
    with caplog.at_level(logging.INFO):
        await validate_node(validate_ready_state)

    pass_records = [r for r in caplog.records if r.message == "validation.pass"]
    assert len(pass_records) == 1
    assert pass_records[0].data["story"] == str(validate_ready_state.story_id)  # type: ignore[attr-defined]
    assert pass_records[0].data["attempt"] == 1  # type: ignore[attr-defined]


@pytest.mark.asyncio
async def test_validate_node_emits_validation_fail_and_halt_log_events(
    validate_ready_state: StoryState,
    mock_pipeline_fail_v3: PipelineResult,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """validation.fail + run.halt are emitted on V3 exhausted escalation."""
    state = validate_ready_state.model_copy(
        update={
            "retry_count": 3,
            "config": make_run_config(retry_budget=3),
        }
    )
    with caplog.at_level(logging.INFO):
        await validate_node(state)

    fail_records = [r for r in caplog.records if r.message == "validation.fail"]
    halt_records = [r for r in caplog.records if r.message == "run.halt"]
    assert len(fail_records) == 1
    assert fail_records[0].data["outcome"] == "escalated"  # type: ignore[attr-defined]
    assert len(halt_records) == 1
    assert halt_records[0].data["reason"] == "max_retries_exhausted"  # type: ignore[attr-defined]


@pytest.mark.asyncio
async def test_validate_node_retry_includes_feedback_in_validation_result(
    validate_ready_state: StoryState,
    mock_pipeline_fail_v3: PipelineResult,
) -> None:
    """After RETRY, state.validation_result.feedback is populated with unmet_criteria."""
    result = await validate_node(validate_ready_state)
    assert result.status == TaskState.RETRY
    assert result.validation_result is not None
    assert result.validation_result.feedback is not None
    assert len(result.validation_result.feedback.unmet_criteria) > 0


# ---------------------------------------------------------------------------
# Preflight node — real implementation tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_preflight_node_resolves_context_and_transitions_to_running(
    story_state_with_project: StoryState,
) -> None:
    """Successful preflight populates context_bundle and transitions to RUNNING."""
    result = await preflight_node(story_state_with_project)

    assert result.status == TaskState.RUNNING
    assert result.context_bundle is not None
    assert result.context_bundle.story_content != ""


@pytest.mark.asyncio
async def test_preflight_node_writes_checkpoint_file(
    story_state_with_project: StoryState,
) -> None:
    """Checkpoint file is written at the expected path after successful preflight."""
    await preflight_node(story_state_with_project)

    checkpoint_file = (
        story_state_with_project.project_root
        / DIR_ARCWRIGHT
        / DIR_RUNS
        / str(story_state_with_project.run_id)
        / DIR_STORIES
        / str(story_state_with_project.story_id)
        / CONTEXT_BUNDLE_FILENAME
    )
    assert checkpoint_file.exists()
    assert "# Context Bundle" in checkpoint_file.read_text(encoding="utf-8")


@pytest.mark.asyncio
async def test_preflight_node_raises_context_error_on_missing_story(
    tmp_path: Path,
) -> None:
    """ContextError is raised when the story file does not exist."""
    state = StoryState(
        story_id=StoryId("2-6-preflight-node"),
        epic_id=EpicId("epic-2"),
        run_id=RunId("20260302-000000-xxxx"),
        story_path=tmp_path / "nonexistent-story.md",
        project_root=tmp_path,
        config=make_run_config(),
    )

    with pytest.raises(ContextError):
        await preflight_node(state)


@pytest.mark.asyncio
async def test_preflight_node_transitions_queued_to_preflight_before_running(
    monkeypatch: pytest.MonkeyPatch,
    story_state_with_project: StoryState,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Failure path emits terminal logs and retains PREFLIGHT status."""

    async def _raise_context_error(story_path: object, project_root: object, **kwargs: object) -> ContextBundle:
        raise ContextError("forced failure")

    monkeypatch.setattr("arcwright_ai.engine.nodes.build_context_bundle", _raise_context_error)

    with caplog.at_level(logging.INFO), pytest.raises(ContextError):
        await preflight_node(story_state_with_project)

    messages = [r.message for r in caplog.records]
    assert "engine.node.enter" in messages
    assert "context.error" in messages
    assert "engine.node.exit" in messages
    assert "context.resolve" not in messages

    # The context.error/exit logs are emitted inside the except block after the PREFLIGHT transition
    error_records = [r for r in caplog.records if r.message == "context.error"]
    exit_records = [r for r in caplog.records if r.message == "engine.node.exit"]
    assert len(error_records) == 1
    assert len(exit_records) == 1
    assert error_records[0].data["status"] == str(TaskState.PREFLIGHT)  # type: ignore[attr-defined]
    assert exit_records[0].data["status"] == str(TaskState.PREFLIGHT)  # type: ignore[attr-defined]


@pytest.mark.asyncio
async def test_preflight_node_context_error_never_transitions_to_running(
    monkeypatch: pytest.MonkeyPatch,
    story_state_with_project: StoryState,
) -> None:
    """On ContextError, preflight applies PREFLIGHT and never applies RUNNING."""
    transitions: list[TaskState] = []
    original_model_copy = StoryState.model_copy

    def _tracking_model_copy(self: StoryState, *args: object, **kwargs: object) -> StoryState:
        update = kwargs.get("update")
        if isinstance(update, dict):
            status = update.get("status")
            if isinstance(status, TaskState):
                transitions.append(status)
        return original_model_copy(self, *args, **kwargs)

    async def _raise_context_error(story_path: object, project_root: object, **kwargs: object) -> ContextBundle:
        raise ContextError("forced failure")

    monkeypatch.setattr(StoryState, "model_copy", _tracking_model_copy)
    monkeypatch.setattr("arcwright_ai.engine.nodes.build_context_bundle", _raise_context_error)

    with pytest.raises(ContextError):
        await preflight_node(story_state_with_project)

    assert transitions.count(TaskState.PREFLIGHT) == 1
    assert TaskState.RUNNING not in transitions


@pytest.mark.asyncio
async def test_preflight_node_creates_checkpoint_directory(
    story_state_with_project: StoryState,
) -> None:
    """Run directory structure is created even when it does not pre-exist."""
    run_dir = (
        story_state_with_project.project_root
        / DIR_ARCWRIGHT
        / DIR_RUNS
        / str(story_state_with_project.run_id)
        / DIR_STORIES
        / str(story_state_with_project.story_id)
    )
    assert not run_dir.exists(), "precondition: directory must not exist before preflight"

    await preflight_node(story_state_with_project)

    assert run_dir.is_dir()


@pytest.mark.asyncio
async def test_preflight_node_emits_structured_log_events(
    story_state_with_project: StoryState,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """engine.node.enter, context.resolve, and engine.node.exit log events are emitted."""
    with caplog.at_level(logging.INFO):
        await preflight_node(story_state_with_project)

    messages = {r.message for r in caplog.records}
    assert "engine.node.enter" in messages
    assert "context.resolve" in messages
    assert "engine.node.exit" in messages


# ---------------------------------------------------------------------------
# agent_dispatch_node — real SDK invocation tests (Task 6)
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_invoke_result() -> InvocationResult:
    """Minimal InvocationResult for mocking invoke_agent in dispatch tests."""
    return InvocationResult(
        output_text="# Mock Implementation\nDone.",
        tokens_input=500,
        tokens_output=200,
        total_cost=Decimal("0.05"),
        duration_ms=1000,
        session_id="test-session-001",
        num_turns=3,
        is_error=False,
    )


@pytest.fixture
async def dispatch_ready_state(
    story_state_with_project: StoryState,
    monkeypatch: pytest.MonkeyPatch,
    mock_invoke_result: InvocationResult,
) -> StoryState:
    """StoryState after preflight with invoke_agent monkeypatched.

    Runs preflight_node on story_state_with_project to populate context_bundle,
    then patches invoke_agent so agent_dispatch_node avoids real SDK calls.
    """
    state = await preflight_node(story_state_with_project)

    async def _mock_invoke(*args: object, **kwargs: object) -> InvocationResult:
        return mock_invoke_result

    monkeypatch.setattr("arcwright_ai.engine.nodes.invoke_agent", _mock_invoke)
    return state


@pytest.mark.asyncio
async def test_agent_dispatch_node_invokes_sdk_and_transitions_to_validating(
    dispatch_ready_state: StoryState,
    mock_invoke_result: InvocationResult,
) -> None:
    """Successful agent_dispatch_node transitions to VALIDATING with agent output."""
    result = await agent_dispatch_node(dispatch_ready_state)
    assert result.status == TaskState.VALIDATING
    assert result.agent_output == mock_invoke_result.output_text


@pytest.mark.asyncio
async def test_agent_dispatch_node_updates_budget(
    dispatch_ready_state: StoryState,
    mock_invoke_result: InvocationResult,
) -> None:
    """agent_dispatch_node increments invocation_count, total_tokens, and estimated_cost."""
    result = await agent_dispatch_node(dispatch_ready_state)
    assert result.budget.invocation_count == 1
    expected_tokens = mock_invoke_result.tokens_input + mock_invoke_result.tokens_output
    assert result.budget.total_tokens == expected_tokens
    assert result.budget.estimated_cost == mock_invoke_result.total_cost


@pytest.mark.asyncio
async def test_agent_dispatch_node_writes_agent_output_checkpoint(
    dispatch_ready_state: StoryState,
    mock_invoke_result: InvocationResult,
) -> None:
    """agent_dispatch_node writes agent-output.md checkpoint at the expected path."""
    await agent_dispatch_node(dispatch_ready_state)

    checkpoint_file = (
        dispatch_ready_state.project_root
        / DIR_ARCWRIGHT
        / DIR_RUNS
        / str(dispatch_ready_state.run_id)
        / DIR_STORIES
        / str(dispatch_ready_state.story_id)
        / AGENT_OUTPUT_FILENAME
    )
    assert checkpoint_file.exists()
    assert checkpoint_file.read_text(encoding="utf-8") == mock_invoke_result.output_text


@pytest.mark.asyncio
async def test_agent_dispatch_node_raises_agent_error_on_sdk_failure(
    dispatch_ready_state: StoryState,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """agent_dispatch_node propagates AgentError when invoke_agent raises it."""

    async def _raise_agent_error(*args: object, **kwargs: object) -> InvocationResult:
        raise AgentError("SDK connection failed")

    monkeypatch.setattr("arcwright_ai.engine.nodes.invoke_agent", _raise_agent_error)
    with pytest.raises(AgentError, match="SDK connection failed"):
        await agent_dispatch_node(dispatch_ready_state)


@pytest.mark.asyncio
async def test_agent_dispatch_node_emits_structured_log_events(
    dispatch_ready_state: StoryState,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """engine.node.enter, agent.dispatch, and engine.node.exit log events are emitted."""
    with caplog.at_level(logging.INFO):
        await agent_dispatch_node(dispatch_ready_state)

    messages = {r.message for r in caplog.records}
    assert "engine.node.enter" in messages
    assert "agent.dispatch" in messages
    assert "engine.node.exit" in messages
