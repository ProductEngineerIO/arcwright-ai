"""Tests for engine/nodes.py — graph node implementations and routing logic."""

from __future__ import annotations

import logging
from decimal import Decimal
from pathlib import Path
from unittest.mock import AsyncMock

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
from arcwright_ai.core.exceptions import AgentError, BranchError, ContextError, ScmError, ValidationError, WorktreeError
from arcwright_ai.core.lifecycle import TaskState
from arcwright_ai.core.types import BudgetState, ContextBundle, EpicId, RunId, StoryId
from arcwright_ai.engine.nodes import (
    _build_validation_history_dicts,
    _derive_halt_reason,
    _derive_story_title,
    agent_dispatch_node,
    budget_check_node,
    commit_node,
    finalize_node,
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


@pytest.fixture(autouse=True)
def _mock_output_functions(monkeypatch: pytest.MonkeyPatch) -> None:
    """Patch output functions called by engine nodes to prevent real I/O."""
    monkeypatch.setattr("arcwright_ai.engine.nodes.append_entry", AsyncMock())
    monkeypatch.setattr("arcwright_ai.engine.nodes.update_story_status", AsyncMock())
    monkeypatch.setattr("arcwright_ai.engine.nodes.update_run_status", AsyncMock())
    monkeypatch.setattr("arcwright_ai.engine.nodes.write_success_summary", AsyncMock())
    monkeypatch.setattr("arcwright_ai.engine.nodes.write_halt_report", AsyncMock())
    # Default SCM mocks — prevent real git calls in unit tests
    monkeypatch.setattr(
        "arcwright_ai.engine.nodes.create_worktree",
        AsyncMock(return_value=Path("/project/.arcwright-ai/worktrees/2-1-state-models")),
    )
    monkeypatch.setattr("arcwright_ai.engine.nodes.remove_worktree", AsyncMock())
    monkeypatch.setattr("arcwright_ai.engine.nodes.commit_story", AsyncMock(return_value="abc1234"))


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


@pytest.mark.asyncio
async def test_validate_node_sdk_crash_transitions_to_escalated(
    validate_ready_state: StoryState,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """SDK crash during run_validation_pipeline escalates instead of propagating.

    Guards against regression where a CommandError / AgentError from the
    reflexion invocation bubbled out of validate_node uncaught, bypassing
    finalize_node and leaving the worktree behind.
    """
    from arcwright_ai.engine.nodes import run_validation_pipeline  # noqa: PLC0415

    async def _crash(*args: object, **kwargs: object) -> PipelineResult:
        raise AgentError("Command failed with exit code 1 (exit code: 1)")

    monkeypatch.setattr("arcwright_ai.engine.nodes.run_validation_pipeline", _crash)

    result = await validate_node(validate_ready_state)

    assert result.status == TaskState.ESCALATED, f"Expected ESCALATED on SDK crash, got {result.status}"


@pytest.mark.asyncio
async def test_validate_node_sdk_crash_writes_halt_report(
    validate_ready_state: StoryState,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """SDK crash during validation writes a halt report to the checkpoint dir."""

    async def _crash(*args: object, **kwargs: object) -> PipelineResult:
        raise AgentError("Command failed with exit code 1 (exit code: 1)")

    monkeypatch.setattr("arcwright_ai.engine.nodes.run_validation_pipeline", _crash)

    await validate_node(validate_ready_state)

    halt_reports = list(
        validate_ready_state.project_root.glob(f".arcwright-ai/runs/*/stories/*/{HALT_REPORT_FILENAME}")
    )
    assert len(halt_reports) == 1, "Expected halt report to be written on SDK crash"
    content = halt_reports[0].read_text(encoding="utf-8")
    assert "validation_sdk_error" in content, "Halt report should identify SDK error source"


# ---------------------------------------------------------------------------
# Preflight node — real implementation tests
# ---------------------------------------------------------------------------
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
async def test_agent_dispatch_node_escalates_cleanly_on_sdk_failure(
    dispatch_ready_state: StoryState,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """SDK crash in agent_dispatch_node escalates to ESCALATED instead of propagating.

    Previously raised AgentError uncaught, bypassing finalize_node and leaking
    the worktree.  Now the node catches the exception, writes a halt report,
    and returns ESCALATED so finalize_node can clean up.
    """

    async def _raise_agent_error(*args: object, **kwargs: object) -> InvocationResult:
        raise AgentError("SDK connection failed")

    monkeypatch.setattr("arcwright_ai.engine.nodes.invoke_agent", _raise_agent_error)
    result = await agent_dispatch_node(dispatch_ready_state)

    assert result.status == TaskState.ESCALATED, f"Expected ESCALATED on SDK crash, got {result.status}"
    halt_reports = list(
        dispatch_ready_state.project_root.glob(f".arcwright-ai/runs/*/stories/*/{HALT_REPORT_FILENAME}")
    )
    assert len(halt_reports) == 1, "Expected halt report written on agent SDK crash"
    content = halt_reports[0].read_text(encoding="utf-8")
    assert "agent_sdk_error" in content


@pytest.mark.asyncio
async def test_agent_dispatch_node_sdk_failure_passthrough_in_validate_node(
    dispatch_ready_state: StoryState,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """validate_node passes through immediately when state arrives as ESCALATED.

    Ensures agent SDK crash → validate passthrough → finalize works end-to-end
    without a second exception raised inside validate_node.
    """

    async def _raise_agent_error(*args: object, **kwargs: object) -> InvocationResult:
        raise AgentError("SDK connection failed")

    monkeypatch.setattr("arcwright_ai.engine.nodes.invoke_agent", _raise_agent_error)
    escalated_state = await agent_dispatch_node(dispatch_ready_state)

    # validate_node must pass through without crashing
    result = await validate_node(escalated_state)
    assert result.status == TaskState.ESCALATED


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


# ---------------------------------------------------------------------------
# Task 10: agent_dispatch_node provenance wiring tests (AC: #10a-d)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_agent_dispatch_node_calls_append_entry_with_provenance_entry(
    dispatch_ready_state: StoryState,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """agent_dispatch_node calls append_entry with a ProvenanceEntry after successful invocation."""
    mock_append = AsyncMock()
    monkeypatch.setattr("arcwright_ai.engine.nodes.append_entry", mock_append)

    await agent_dispatch_node(dispatch_ready_state)

    assert mock_append.call_count == 1
    call_args = mock_append.call_args
    # Second positional arg is the ProvenanceEntry
    entry = call_args[0][1]
    assert str(dispatch_ready_state.story_id) in entry.decision
    assert dispatch_ready_state.config.model.version in entry.alternatives
    assert "Prompt length:" in entry.rationale
    assert "retry_count:" in entry.rationale
    assert entry.timestamp != ""


@pytest.mark.asyncio
async def test_agent_dispatch_node_provenance_failure_does_not_raise(
    dispatch_ready_state: StoryState,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """agent_dispatch_node completes successfully when append_entry raises OSError."""
    monkeypatch.setattr(
        "arcwright_ai.engine.nodes.append_entry",
        AsyncMock(side_effect=OSError("disk full")),
    )

    result = await agent_dispatch_node(dispatch_ready_state)
    assert result.status == TaskState.VALIDATING


@pytest.mark.asyncio
async def test_validate_node_calls_append_entry_with_provenance_entry(
    validate_ready_state: StoryState,
    mock_pipeline_pass: PipelineResult,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """validate_node calls append_entry with correct ProvenanceEntry after validation."""
    mock_append = AsyncMock()
    monkeypatch.setattr("arcwright_ai.engine.nodes.append_entry", mock_append)

    await validate_node(validate_ready_state)

    assert mock_append.call_count == 1
    call_args = mock_append.call_args
    entry = call_args[0][1]
    assert "Validation attempt 1" in entry.decision
    assert PipelineOutcome.PASS.value in entry.decision
    assert entry.timestamp != ""


@pytest.mark.asyncio
async def test_validate_node_provenance_entry_includes_failed_acs_for_fail_v3(
    validate_ready_state: StoryState,
    mock_pipeline_fail_v3: PipelineResult,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """validate_node provenance entry ac_references contains unmet_criteria for FAIL_V3."""
    mock_append = AsyncMock()
    monkeypatch.setattr("arcwright_ai.engine.nodes.append_entry", mock_append)

    await validate_node(validate_ready_state)

    call_args = mock_append.call_args
    entry = call_args[0][1]
    assert "2" in entry.ac_references
    assert "3" in entry.ac_references


@pytest.mark.asyncio
async def test_validate_node_provenance_failure_does_not_raise(
    validate_ready_state: StoryState,
    mock_pipeline_pass: PipelineResult,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """validate_node completes successfully when append_entry raises OSError."""
    monkeypatch.setattr(
        "arcwright_ai.engine.nodes.append_entry",
        AsyncMock(side_effect=OSError("disk full")),
    )

    result = await validate_node(validate_ready_state)
    assert result.status == TaskState.SUCCESS


# ---------------------------------------------------------------------------
# Task 11: commit_node run_manager wiring tests (AC: #10e-g)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_commit_node_calls_update_story_status_with_success(
    make_story_state: StoryState,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """commit_node calls update_story_status with status='success' and non-None completed_at."""
    mock_update_story = AsyncMock()
    monkeypatch.setattr("arcwright_ai.engine.nodes.update_story_status", mock_update_story)
    monkeypatch.setattr("arcwright_ai.engine.nodes.update_run_status", AsyncMock())

    state = make_story_state.model_copy(update={"status": TaskState.SUCCESS})
    await commit_node(state)

    assert mock_update_story.call_count == 1
    call_kwargs = mock_update_story.call_args[1]
    assert call_kwargs["status"] == "success"
    assert call_kwargs["completed_at"] is not None


@pytest.mark.asyncio
async def test_commit_node_calls_update_run_status_with_last_completed_story_and_budget(
    make_story_state: StoryState,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """commit_node calls update_run_status with last_completed_story and budget from state."""
    mock_update_run = AsyncMock()
    monkeypatch.setattr("arcwright_ai.engine.nodes.update_story_status", AsyncMock())
    monkeypatch.setattr("arcwright_ai.engine.nodes.update_run_status", mock_update_run)

    state = make_story_state.model_copy(update={"status": TaskState.SUCCESS})
    await commit_node(state)

    assert mock_update_run.call_count == 1
    call_kwargs = mock_update_run.call_args[1]
    assert call_kwargs["last_completed_story"] == str(state.story_id)
    assert call_kwargs["budget"] == state.budget


@pytest.mark.asyncio
async def test_commit_node_continues_when_update_story_status_raises(
    make_story_state: StoryState,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """commit_node logs warning but does not raise when update_story_status raises RunError."""
    from arcwright_ai.core.exceptions import RunError

    monkeypatch.setattr(
        "arcwright_ai.engine.nodes.update_story_status",
        AsyncMock(side_effect=RunError("run not found")),
    )
    monkeypatch.setattr("arcwright_ai.engine.nodes.update_run_status", AsyncMock())

    state = make_story_state.model_copy(update={"status": TaskState.SUCCESS})
    result = await commit_node(state)
    assert result.status == TaskState.SUCCESS


# ---------------------------------------------------------------------------
# Task 12: finalize_node tests (AC: #10h-m)
# ---------------------------------------------------------------------------


@pytest.fixture
def finalize_state_success(make_story_state: StoryState) -> StoryState:
    """StoryState in SUCCESS terminal status for finalize_node tests."""
    return make_story_state.model_copy(update={"status": TaskState.SUCCESS})


@pytest.fixture
def finalize_state_escalated(make_story_state: StoryState) -> StoryState:
    """StoryState in ESCALATED terminal status with retry history for finalize_node tests."""
    fail_v3_result = _make_fail_v3_result()
    return make_story_state.model_copy(
        update={
            "status": TaskState.ESCALATED,
            "retry_history": [fail_v3_result],
            "retry_count": 3,
            "agent_output": "Agent output text",
        }
    )


@pytest.mark.asyncio
async def test_finalize_node_calls_write_success_summary_on_success(
    finalize_state_success: StoryState,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """finalize_node calls write_success_summary when state.status is SUCCESS."""
    mock_success = AsyncMock()
    monkeypatch.setattr("arcwright_ai.engine.nodes.write_success_summary", mock_success)

    await finalize_node(finalize_state_success)

    assert mock_success.call_count == 1
    args = mock_success.call_args[0]
    assert args[0] == finalize_state_success.project_root
    assert args[1] == str(finalize_state_success.run_id)


@pytest.mark.asyncio
async def test_finalize_node_calls_write_halt_report_on_escalated(
    finalize_state_escalated: StoryState,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """finalize_node calls write_halt_report when state.status is ESCALATED."""
    mock_halt = AsyncMock()
    monkeypatch.setattr("arcwright_ai.engine.nodes.write_halt_report", mock_halt)

    await finalize_node(finalize_state_escalated)

    assert mock_halt.call_count == 1
    call_kwargs = mock_halt.call_args[1]
    assert call_kwargs["halted_story"] == str(finalize_state_escalated.story_id)
    assert call_kwargs["halt_reason"] == "max_retries_exhausted"
    assert isinstance(call_kwargs["validation_history"], list)
    assert call_kwargs["last_agent_output"] == "Agent output text"
    assert isinstance(call_kwargs["suggested_fix"], str)


@pytest.mark.asyncio
async def test_finalize_node_returns_state_unchanged(
    finalize_state_success: StoryState,
) -> None:
    """finalize_node returns state unchanged regardless of summary write outcome."""
    result = await finalize_node(finalize_state_success)
    assert result.status == finalize_state_success.status
    assert result.story_id == finalize_state_success.story_id


@pytest.mark.asyncio
async def test_finalize_node_continues_when_write_success_summary_raises(
    finalize_state_success: StoryState,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """finalize_node completes successfully when write_success_summary raises."""
    monkeypatch.setattr(
        "arcwright_ai.engine.nodes.write_success_summary",
        AsyncMock(side_effect=OSError("disk full")),
    )

    result = await finalize_node(finalize_state_success)
    assert result.status == TaskState.SUCCESS


@pytest.mark.asyncio
async def test_finalize_node_escalated_with_empty_retry_history_uses_budget_exceeded(
    make_story_state: StoryState,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """finalize_node with ESCALATED + empty retry_history → halt_reason='budget_exceeded', history=[]."""
    mock_halt = AsyncMock()
    monkeypatch.setattr("arcwright_ai.engine.nodes.write_halt_report", mock_halt)

    state = make_story_state.model_copy(update={"status": TaskState.ESCALATED, "retry_history": [], "retry_count": 0})
    await finalize_node(state)

    assert mock_halt.call_count == 1
    call_kwargs = mock_halt.call_args[1]
    assert call_kwargs["halt_reason"] == "budget_exceeded"
    assert call_kwargs["validation_history"] == []


def test_derive_halt_reason_returns_v6_invariant_failure_for_fail_v6(
    make_story_state: StoryState,
) -> None:
    """_derive_halt_reason returns 'v6_invariant_failure' when last result is FAIL_V6."""
    fail_v6 = _make_fail_v6_result()
    state = make_story_state.model_copy(
        update={"status": TaskState.ESCALATED, "retry_history": [fail_v6], "retry_count": 1}
    )
    assert _derive_halt_reason(state) == "v6_invariant_failure"


def test_derive_halt_reason_returns_max_retries_when_budget_exhausted(
    make_story_state: StoryState,
) -> None:
    """_derive_halt_reason returns 'max_retries_exhausted' when retry_count >= retry_budget."""
    fail_v3 = _make_fail_v3_result()
    state = make_story_state.model_copy(
        update={
            "status": TaskState.ESCALATED,
            "retry_history": [fail_v3],
            "retry_count": 3,  # >= retry_budget=3
            "config": make_run_config(retry_budget=3),
        }
    )
    assert _derive_halt_reason(state) == "max_retries_exhausted"


def test_build_validation_history_dicts_converts_pipeline_results(
    make_story_state: StoryState,
) -> None:
    """_build_validation_history_dicts returns correct dict format for each PipelineResult."""
    fail_v3 = _make_fail_v3_result()
    pass_result = _make_pass_result()
    state = make_story_state.model_copy(update={"retry_history": [fail_v3, pass_result]})
    history = _build_validation_history_dicts(state)

    assert len(history) == 2
    assert history[0]["attempt"] == 1
    assert history[0]["outcome"] == PipelineOutcome.FAIL_V3.value
    assert "V3" in history[0]["failures"]
    assert history[1]["attempt"] == 2
    assert history[1]["outcome"] == PipelineOutcome.PASS.value
    assert history[1]["failures"] == ""


# ---------------------------------------------------------------------------
# Story 6.6: SCM integration — _derive_story_title helper (AC: #4.5)
# ---------------------------------------------------------------------------


def test_derive_story_title_strips_prefix_and_title_cases() -> None:
    """_derive_story_title converts '6-6-scm-integration' → 'Scm Integration'."""
    assert _derive_story_title("6-6-scm-integration") == "Scm Integration"


def test_derive_story_title_handles_three_part_slug() -> None:
    """_derive_story_title handles multi-word name after prefix."""
    assert _derive_story_title("2-1-state-models") == "State Models"


def test_derive_story_title_no_prefix_returns_slug_title_cased() -> None:
    """_derive_story_title returns title-cased slug when no numeric prefix."""
    assert _derive_story_title("my-story") == "My Story"


# ---------------------------------------------------------------------------
# Story 6.6: SCM integration — preflight_node (AC: #1, #7, #8)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_preflight_node_creates_worktree(
    story_state_with_project: StoryState,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """preflight_node calls create_worktree and sets worktree_path in state."""
    expected_path = Path("/project/.arcwright-ai/worktrees/2-6-preflight-node")
    mock_create = AsyncMock(return_value=expected_path)
    monkeypatch.setattr("arcwright_ai.engine.nodes.create_worktree", mock_create)

    result = await preflight_node(story_state_with_project)

    mock_create.assert_called_once_with(
        str(story_state_with_project.story_id),
        project_root=story_state_with_project.project_root,
    )
    assert result.worktree_path == expected_path
    assert result.status == TaskState.RUNNING


@pytest.mark.asyncio
async def test_preflight_node_scm_error_escalates(
    story_state_with_project: StoryState,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """preflight_node transitions to ESCALATED and writes halt report when create_worktree fails."""
    scm_exc = ScmError("git worktree add failed", details={"code": 128})

    async def _raise(*args: object, **kwargs: object) -> Path:
        raise scm_exc

    monkeypatch.setattr("arcwright_ai.engine.nodes.create_worktree", _raise)

    result = await preflight_node(story_state_with_project)

    assert result.status == TaskState.ESCALATED
    assert result.worktree_path is None

    halt_path = (
        story_state_with_project.project_root
        / DIR_ARCWRIGHT
        / DIR_RUNS
        / str(story_state_with_project.run_id)
        / DIR_STORIES
        / str(story_state_with_project.story_id)
        / HALT_REPORT_FILENAME
    )
    assert halt_path.exists()
    content = halt_path.read_text(encoding="utf-8")
    assert "preflight_worktree_creation_failed" in content
    assert "git worktree add failed" in content


def test_route_budget_check_returns_exceeded_when_state_already_escalated(make_story_state: StoryState) -> None:
    """Escalated states must route directly to finalize via exceeded edge."""
    state = make_story_state.model_copy(update={"status": TaskState.ESCALATED})
    assert route_budget_check(state) == "exceeded"


# ---------------------------------------------------------------------------
# Story 6.6: SCM integration — agent_dispatch_node (AC: #2, #5, #6)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_agent_dispatch_uses_worktree_cwd(
    story_state_with_project: StoryState,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """agent_dispatch_node passes worktree_path as cwd when worktree_path is set."""
    worktree = Path("/project/.arcwright-ai/worktrees/2-6-preflight-node")
    monkeypatch.setattr("arcwright_ai.engine.nodes.create_worktree", AsyncMock(return_value=worktree))
    preflight_result = await preflight_node(story_state_with_project)
    assert preflight_result.worktree_path == worktree

    captured_cwd: list[Path] = []

    async def _mock_invoke(prompt: str, *, model: str, cwd: Path, sandbox: object) -> object:
        captured_cwd.append(cwd)
        from decimal import Decimal

        from arcwright_ai.agent.invoker import InvocationResult

        return InvocationResult(
            output_text="done",
            tokens_input=10,
            tokens_output=10,
            total_cost=Decimal("0.001"),
            duration_ms=100,
            session_id="s1",
            num_turns=1,
            is_error=False,
        )

    monkeypatch.setattr("arcwright_ai.engine.nodes.invoke_agent", _mock_invoke)
    await agent_dispatch_node(preflight_result)

    assert len(captured_cwd) == 1
    assert captured_cwd[0] == worktree


@pytest.mark.asyncio
async def test_agent_dispatch_falls_back_to_project_root(
    story_state_with_project: StoryState,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """agent_dispatch_node uses project_root as cwd when worktree_path is None."""
    monkeypatch.setattr("arcwright_ai.engine.nodes.create_worktree", AsyncMock(return_value=None))
    # Build state with worktree_path=None directly
    from arcwright_ai.context.injector import build_context_bundle

    bundle = await build_context_bundle(
        story_state_with_project.story_path,
        story_state_with_project.project_root,
        artifacts_path=story_state_with_project.config.methodology.artifacts_path,
    )
    state = story_state_with_project.model_copy(
        update={
            "status": TaskState.RUNNING,
            "context_bundle": bundle,
            "worktree_path": None,
        }
    )

    captured_cwd: list[Path] = []

    async def _mock_invoke(prompt: str, *, model: str, cwd: Path, sandbox: object) -> object:
        captured_cwd.append(cwd)
        from decimal import Decimal

        from arcwright_ai.agent.invoker import InvocationResult

        return InvocationResult(
            output_text="done",
            tokens_input=10,
            tokens_output=10,
            total_cost=Decimal("0.001"),
            duration_ms=100,
            session_id="s1",
            num_turns=1,
            is_error=False,
        )

    monkeypatch.setattr("arcwright_ai.engine.nodes.invoke_agent", _mock_invoke)
    await agent_dispatch_node(state)

    assert captured_cwd[0] == story_state_with_project.project_root


# ---------------------------------------------------------------------------
# Story 6.6: SCM integration — commit_node (AC: #3, #6, #13)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_commit_node_commits_and_removes_worktree(
    make_story_state: StoryState,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """commit_node calls commit_story and remove_worktree with correct args when worktree_path set."""
    worktree_path = Path("/project/.arcwright-ai/worktrees/2-1-state-models")
    state = make_story_state.model_copy(update={"status": TaskState.SUCCESS, "worktree_path": worktree_path})

    mock_commit = AsyncMock(return_value="deadbeef")
    mock_remove = AsyncMock()
    monkeypatch.setattr("arcwright_ai.engine.nodes.commit_story", mock_commit)
    monkeypatch.setattr("arcwright_ai.engine.nodes.remove_worktree", mock_remove)

    result = await commit_node(state)

    assert result.status == TaskState.SUCCESS
    mock_commit.assert_called_once()
    call_kwargs = mock_commit.call_args[1]
    assert call_kwargs["story_slug"] == str(state.story_id)
    assert call_kwargs["worktree_path"] == worktree_path

    mock_remove.assert_called_once_with(str(state.story_id), project_root=state.project_root)


@pytest.mark.asyncio
async def test_commit_node_skips_scm_when_no_worktree(
    make_story_state: StoryState,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """commit_node skips SCM operations when worktree_path is None."""
    state = make_story_state.model_copy(update={"status": TaskState.SUCCESS, "worktree_path": None})

    mock_commit = AsyncMock(return_value="deadbeef")
    mock_remove = AsyncMock()
    monkeypatch.setattr("arcwright_ai.engine.nodes.commit_story", mock_commit)
    monkeypatch.setattr("arcwright_ai.engine.nodes.remove_worktree", mock_remove)

    result = await commit_node(state)

    assert result.status == TaskState.SUCCESS
    mock_commit.assert_not_called()
    mock_remove.assert_not_called()


@pytest.mark.asyncio
async def test_commit_node_handles_branch_error_gracefully(
    make_story_state: StoryState,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """commit_node logs warning on BranchError but still calls remove_worktree (non-fatal)."""
    worktree_path = Path("/project/.arcwright-ai/worktrees/2-1-state-models")
    state = make_story_state.model_copy(update={"status": TaskState.SUCCESS, "worktree_path": worktree_path})

    async def _raise_branch_error(*args: object, **kwargs: object) -> str:
        raise BranchError("nothing to commit", details={})

    mock_remove = AsyncMock()
    monkeypatch.setattr("arcwright_ai.engine.nodes.commit_story", _raise_branch_error)
    monkeypatch.setattr("arcwright_ai.engine.nodes.remove_worktree", mock_remove)

    with caplog.at_level(logging.WARNING):
        result = await commit_node(state)

    assert result.status == TaskState.SUCCESS
    assert any("scm.commit.error" in r.message for r in caplog.records)
    mock_remove.assert_called_once()


@pytest.mark.asyncio
async def test_commit_node_handles_worktree_error_gracefully(
    make_story_state: StoryState,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """commit_node logs warning on WorktreeError from remove_worktree but does not crash."""
    worktree_path = Path("/project/.arcwright-ai/worktrees/2-1-state-models")
    state = make_story_state.model_copy(update={"status": TaskState.SUCCESS, "worktree_path": worktree_path})

    async def _raise_worktree_error(*args: object, **kwargs: object) -> None:
        raise WorktreeError("worktree not found", details={})

    monkeypatch.setattr("arcwright_ai.engine.nodes.commit_story", AsyncMock(return_value="abc123"))
    monkeypatch.setattr("arcwright_ai.engine.nodes.remove_worktree", _raise_worktree_error)

    with caplog.at_level(logging.WARNING):
        result = await commit_node(state)

    assert result.status == TaskState.SUCCESS
    assert any("scm.worktree.remove.error" in r.message for r in caplog.records)


# ---------------------------------------------------------------------------
# Story 6.6: SCM integration — finalize_node (AC: #4)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_finalize_preserves_worktree_on_escalated(
    make_story_state: StoryState,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """finalize_node logs scm.worktree.preserved on ESCALATED and does NOT call remove_worktree."""
    worktree_path = Path("/project/.arcwright-ai/worktrees/2-1-state-models")
    state = make_story_state.model_copy(update={"status": TaskState.ESCALATED, "worktree_path": worktree_path})

    mock_remove = AsyncMock()
    monkeypatch.setattr("arcwright_ai.engine.nodes.remove_worktree", mock_remove)

    with caplog.at_level(logging.INFO):
        result = await finalize_node(state)

    assert result.status == TaskState.ESCALATED
    mock_remove.assert_not_called()
    assert any("scm.worktree.preserved" in r.message for r in caplog.records)


@pytest.mark.asyncio
async def test_finalize_no_worktree_preserved_log_when_no_worktree_path(
    make_story_state: StoryState,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """finalize_node does not log scm.worktree.preserved when worktree_path is None."""
    state = make_story_state.model_copy(update={"status": TaskState.ESCALATED, "worktree_path": None})

    with caplog.at_level(logging.INFO):
        result = await finalize_node(state)

    assert result.status == TaskState.ESCALATED
    assert not any("scm.worktree.preserved" in r.message for r in caplog.records)
