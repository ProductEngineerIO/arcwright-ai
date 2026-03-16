"""Tests for engine/nodes.py — graph node implementations and routing logic."""

from __future__ import annotations

import logging
from decimal import Decimal
from pathlib import Path
from unittest.mock import AsyncMock

import pytest

from arcwright_ai.agent.invoker import InvocationResult
from arcwright_ai.core.config import ApiConfig, LimitsConfig, ModelRole, RunConfig, ScmConfig
from arcwright_ai.core.constants import (
    AGENT_OUTPUT_FILENAME,
    BRANCH_PREFIX,
    CONTEXT_BUNDLE_FILENAME,
    DIR_ARCWRIGHT,
    DIR_RUNS,
    DIR_STORIES,
    HALT_REPORT_FILENAME,
    STORY_COPY_FILENAME,
    VALIDATION_FILENAME,
)
from arcwright_ai.core.exceptions import (
    AgentBudgetError,
    AgentError,
    BranchError,
    ContextError,
    ScmError,
    ValidationError,
    WorktreeError,
)
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
from arcwright_ai.scm.git import GitResult
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
    monkeypatch.setattr("arcwright_ai.engine.nodes.delete_remote_branch", AsyncMock(return_value=True))
    monkeypatch.setattr("arcwright_ai.engine.nodes.commit_story", AsyncMock(return_value="abc1234"))
    # Story 6.7: push/PR mocks (non-fatal operations — default to success)
    monkeypatch.setattr("arcwright_ai.engine.nodes.push_branch", AsyncMock())
    monkeypatch.setattr(
        "arcwright_ai.engine.nodes.generate_pr_body",
        AsyncMock(return_value="## Story: 6-7-push-branch\n\n---\n"),
    )
    monkeypatch.setattr(
        "arcwright_ai.engine.nodes.open_pull_request",
        AsyncMock(return_value=None),
    )
    # Story 9.2: fetch_and_sync and _detect_default_branch mocks
    monkeypatch.setattr(
        "arcwright_ai.engine.nodes.fetch_and_sync",
        AsyncMock(return_value="abc1234567890abcdef1234567890abcdef123456"),
    )
    monkeypatch.setattr(
        "arcwright_ai.engine.nodes._detect_default_branch",
        AsyncMock(return_value="main"),
    )
    # Story 9.3: merge_pull_request mock — defaults False (auto_merge=False in RunConfig)
    monkeypatch.setattr(
        "arcwright_ai.engine.nodes.merge_pull_request",
        AsyncMock(return_value=False),
    )
    monkeypatch.setattr(
        "arcwright_ai.engine.nodes.get_pull_request_merge_sha",
        AsyncMock(return_value=None),
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
        tokens_input=200,
        tokens_output=100,
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
        tokens_input=320,
        tokens_output=180,
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
async def test_validate_node_populates_cost_by_role_review(
    validate_ready_state: StoryState,
    mock_pipeline_pass: PipelineResult,
) -> None:
    """validate_node records validation cost under cost_by_role['review'] in per_story."""
    result = await validate_node(validate_ready_state)
    story_slug = str(validate_ready_state.story_id)
    assert story_slug in result.budget.per_story
    sc = result.budget.per_story[story_slug]
    assert "review" in sc.cost_by_role
    assert sc.cost_by_role["review"] == mock_pipeline_pass.cost
    assert sc.invocations_by_role.get("review") == 1
    assert sc.tokens_input_by_role.get("review") == mock_pipeline_pass.tokens_input
    assert sc.tokens_output_by_role.get("review") == mock_pipeline_pass.tokens_output


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


@pytest.mark.asyncio
async def test_validate_node_uses_worktree_path_as_cwd(
    validate_ready_state: StoryState,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """validate_node passes worktree_path as cwd to run_validation_pipeline so
    the V3 reflexion agent reads files from the worktree, not the main repo root."""
    worktree = validate_ready_state.project_root / ".arcwright-ai" / "worktrees" / "3-4-validate-node"
    worktree.mkdir(parents=True, exist_ok=True)
    state = validate_ready_state.model_copy(update={"worktree_path": worktree})

    captured_cwd: list[Path] = []

    async def _capture(*args: object, **kwargs: object) -> PipelineResult:
        captured_cwd.append(kwargs["cwd"])
        return _make_pass_result()

    monkeypatch.setattr("arcwright_ai.engine.nodes.run_validation_pipeline", _capture)

    await validate_node(state)

    assert captured_cwd == [worktree], "cwd must be worktree_path, not project_root"


@pytest.mark.asyncio
async def test_validate_node_falls_back_to_project_root_when_no_worktree(
    validate_ready_state: StoryState,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """When worktree_path is None, cwd falls back to project_root."""
    captured_cwd: list[Path] = []

    async def _capture(*args: object, **kwargs: object) -> PipelineResult:
        captured_cwd.append(kwargs["cwd"])
        return _make_pass_result()

    monkeypatch.setattr("arcwright_ai.engine.nodes.run_validation_pipeline", _capture)

    await validate_node(validate_ready_state)  # worktree_path is None by default

    assert captured_cwd == [validate_ready_state.project_root]


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
async def test_preflight_node_copies_story_file(
    story_state_with_project: StoryState,
) -> None:
    """Story file is copied into the run checkpoint directory for provenance."""
    await preflight_node(story_state_with_project)

    story_copy = (
        story_state_with_project.project_root
        / DIR_ARCWRIGHT
        / DIR_RUNS
        / str(story_state_with_project.run_id)
        / DIR_STORIES
        / str(story_state_with_project.story_id)
        / STORY_COPY_FILENAME
    )
    assert story_copy.exists(), "story.md should be copied into checkpoint directory"
    original = story_state_with_project.story_path.read_text(encoding="utf-8")
    assert story_copy.read_text(encoding="utf-8") == original


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
    # estimated_cost now uses pricing-based calculation, not SDK-reported total_cost
    from arcwright_ai.core.types import calculate_invocation_cost

    expected_cost = calculate_invocation_cost(
        mock_invoke_result.tokens_input,
        mock_invoke_result.tokens_output,
        dispatch_ready_state.config.models.get(ModelRole.GENERATE).pricing,
    )
    assert result.budget.estimated_cost == expected_cost


@pytest.mark.asyncio
async def test_agent_dispatch_node_updates_per_story_and_token_breakdown(
    dispatch_ready_state: StoryState,
    mock_invoke_result: InvocationResult,
) -> None:
    """agent_dispatch_node populates per_story, total_tokens_input, total_tokens_output."""
    from arcwright_ai.core.types import StoryCost, calculate_invocation_cost

    result = await agent_dispatch_node(dispatch_ready_state)
    story_slug = str(dispatch_ready_state.story_id)

    # Per-story tracking
    assert story_slug in result.budget.per_story
    sc = result.budget.per_story[story_slug]
    assert isinstance(sc, StoryCost)
    assert sc.tokens_input == mock_invoke_result.tokens_input
    assert sc.tokens_output == mock_invoke_result.tokens_output
    assert sc.invocations == 1
    expected_cost = calculate_invocation_cost(
        mock_invoke_result.tokens_input,
        mock_invoke_result.tokens_output,
        dispatch_ready_state.config.models.get(ModelRole.GENERATE).pricing,
    )
    assert sc.cost == expected_cost

    # Token breakdown
    assert result.budget.total_tokens_input == mock_invoke_result.tokens_input
    assert result.budget.total_tokens_output == mock_invoke_result.tokens_output


@pytest.mark.asyncio
async def test_agent_dispatch_node_populates_cost_by_role_generate(
    dispatch_ready_state: StoryState,
    mock_invoke_result: InvocationResult,
) -> None:
    """agent_dispatch_node records invocation cost under cost_by_role['generate']."""
    from arcwright_ai.core.types import calculate_invocation_cost

    result = await agent_dispatch_node(dispatch_ready_state)
    story_slug = str(dispatch_ready_state.story_id)
    sc = result.budget.per_story[story_slug]
    expected_cost = calculate_invocation_cost(
        mock_invoke_result.tokens_input,
        mock_invoke_result.tokens_output,
        dispatch_ready_state.config.models.get(ModelRole.GENERATE).pricing,
    )
    assert "generate" in sc.cost_by_role
    assert sc.cost_by_role["generate"] == expected_cost
    assert sc.invocations_by_role.get("generate") == 1
    assert sc.tokens_input_by_role.get("generate") == mock_invoke_result.tokens_input
    assert sc.tokens_output_by_role.get("generate") == mock_invoke_result.tokens_output
    # Should not have a review cost
    assert "review" not in sc.cost_by_role


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
    assert dispatch_ready_state.config.models.get(ModelRole.GENERATE).version in entry.alternatives
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
# Story 8.2: Role-based model resolution tests (AC: #15a-f)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_agent_dispatch_node_resolves_generate_role(
    dispatch_ready_state: StoryState,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """agent_dispatch_node passes GENERATE role model version to invoke_agent (AC: #15a)."""
    from decimal import Decimal

    captured_kwargs: dict[str, object] = {}

    async def _capture_invoke(*args: object, **kwargs: object) -> InvocationResult:
        captured_kwargs.update(kwargs)
        return InvocationResult(
            output_text="output",
            tokens_input=100,
            tokens_output=50,
            total_cost=Decimal("0.001"),
            duration_ms=100,
            session_id="s-1",
            num_turns=1,
            is_error=False,
        )

    monkeypatch.setattr("arcwright_ai.engine.nodes.invoke_agent", _capture_invoke)
    await agent_dispatch_node(dispatch_ready_state)

    expected_version = dispatch_ready_state.config.models.get(ModelRole.GENERATE).version
    assert captured_kwargs.get("model") == expected_version


@pytest.mark.asyncio
async def test_validate_node_resolves_review_role(
    validate_ready_state: StoryState,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """validate_node passes REVIEW role model version to run_validation_pipeline (AC: #15b)."""
    captured_kwargs: dict[str, object] = {}

    async def _capture_pipeline(*args: object, **kwargs: object) -> PipelineResult:
        captured_kwargs.update(kwargs)
        return _make_pass_result()

    monkeypatch.setattr("arcwright_ai.engine.nodes.run_validation_pipeline", _capture_pipeline)
    await validate_node(validate_ready_state)

    expected_version = validate_ready_state.config.models.get(ModelRole.REVIEW).version
    assert captured_kwargs.get("model") == expected_version


@pytest.mark.asyncio
async def test_validate_node_falls_back_to_generate_when_no_review(
    validate_ready_state: StoryState,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """validate_node falls back to GENERATE model when REVIEW is not configured (AC: #15c, Boundary #1).

    make_run_config() creates a generate-only config, so ModelRegistry.get(REVIEW)
    falls back to the generate model version.
    """
    captured_kwargs: dict[str, object] = {}

    async def _capture_pipeline(*args: object, **kwargs: object) -> PipelineResult:
        captured_kwargs.update(kwargs)
        return _make_pass_result()

    monkeypatch.setattr("arcwright_ai.engine.nodes.run_validation_pipeline", _capture_pipeline)
    await validate_node(validate_ready_state)

    generate_version = validate_ready_state.config.models.get(ModelRole.GENERATE).version
    assert captured_kwargs.get("model") == generate_version


@pytest.mark.asyncio
async def test_agent_dispatch_cost_uses_generate_role_pricing(
    dispatch_ready_state: StoryState,
    mock_invoke_result: InvocationResult,
) -> None:
    """agent_dispatch_node uses GENERATE role pricing for cost calculation (AC: #15d)."""
    from arcwright_ai.core.types import calculate_invocation_cost

    result = await agent_dispatch_node(dispatch_ready_state)

    gen_pricing = dispatch_ready_state.config.models.get(ModelRole.GENERATE).pricing
    expected_cost = calculate_invocation_cost(
        mock_invoke_result.tokens_input,
        mock_invoke_result.tokens_output,
        gen_pricing,
    )
    assert result.budget.estimated_cost == expected_cost


@pytest.mark.asyncio
async def test_agent_dispatch_provenance_includes_role(
    dispatch_ready_state: StoryState,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """agent_dispatch_node provenance entry includes role info in rationale (AC: #15e)."""
    mock_append = AsyncMock()
    monkeypatch.setattr("arcwright_ai.engine.nodes.append_entry", mock_append)

    await agent_dispatch_node(dispatch_ready_state)

    assert mock_append.call_count == 1
    entry = mock_append.call_args[0][1]
    assert "generate" in entry.rationale
    gen_version = dispatch_ready_state.config.models.get(ModelRole.GENERATE).version
    assert gen_version in entry.alternatives


@pytest.mark.asyncio
async def test_validate_node_with_dual_model_config(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """validate_node uses REVIEW model version (not GENERATE) with dual-role config (AC: #15f).

    When both generate and review are configured with distinct versions,
    validate_node must pass the review model version to run_validation_pipeline.
    """
    from arcwright_ai.core.config import ModelRegistry, ModelSpec

    dual_config = RunConfig(
        api=ApiConfig(claude_api_key="test-key"),
        models=ModelRegistry(
            roles={
                "generate": ModelSpec(version="claude-sonnet-4-20250514"),
                "review": ModelSpec(version="claude-opus-4-5"),
            }
        ),
    )
    state = StoryState(
        story_id=StoryId("8-2-dual-model"),
        epic_id=EpicId("epic-8"),
        run_id=RunId("20260312-120000-abc1"),
        story_path=tmp_path / "_spec" / "8-2.md",
        project_root=tmp_path,
        status=TaskState.VALIDATING,
        agent_output="Mock output",
        config=dual_config,
    )

    captured_kwargs: dict[str, object] = {}

    async def _capture_pipeline(*args: object, **kwargs: object) -> PipelineResult:
        captured_kwargs.update(kwargs)
        return _make_pass_result()

    monkeypatch.setattr("arcwright_ai.engine.nodes.run_validation_pipeline", _capture_pipeline)
    await validate_node(state)

    assert captured_kwargs.get("model") == "claude-opus-4-5"
    assert captured_kwargs.get("model") != "claude-sonnet-4-20250514"


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
        "abc1234567890abcdef1234567890abcdef123456",
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


@pytest.mark.asyncio
async def test_preflight_node_removes_stale_worktree_and_retries(
    story_state_with_project: StoryState,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """When create_worktree raises 'already exists', preflight removes the stale
    worktree and retries rather than escalating.  This handles the common case
    where a prior escalated run preserved the worktree."""
    from arcwright_ai.core.exceptions import ScmError

    expected_path = Path("/project/.arcwright-ai/worktrees/2-6-preflight-node")
    stale_exc = ScmError(
        "Worktree already exists for '2-6-preflight-node'",
        details={"story_slug": "2-6-preflight-node"},
    )

    call_count = 0

    async def _create_worktree(slug: str, base_ref: str | None = None, *, project_root: Path) -> Path:
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            raise stale_exc
        return expected_path

    mock_remove = AsyncMock()
    mock_delete_remote = AsyncMock(return_value=True)
    monkeypatch.setattr("arcwright_ai.engine.nodes.create_worktree", _create_worktree)
    monkeypatch.setattr("arcwright_ai.engine.nodes.remove_worktree", mock_remove)
    monkeypatch.setattr("arcwright_ai.engine.nodes.delete_remote_branch", mock_delete_remote)

    result = await preflight_node(story_state_with_project)

    assert result.status == TaskState.RUNNING, "Should succeed after stale cleanup"
    assert result.worktree_path == expected_path
    assert call_count == 2, "create_worktree called twice (first stale, then fresh)"
    mock_remove.assert_awaited_once_with(
        str(story_state_with_project.story_id),
        project_root=story_state_with_project.project_root,
        delete_branch=True,
        force=True,
    )
    # Verify remote branch is also cleaned up to prevent non-fast-forward rejections
    mock_delete_remote.assert_awaited_once()


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
    """commit_node resolves base_ref and calls commit_story/remove_worktree when worktree_path is set."""
    worktree_path = Path("/project/.arcwright-ai/worktrees/2-1-state-models")
    state = make_story_state.model_copy(update={"status": TaskState.SUCCESS, "worktree_path": worktree_path})

    mock_commit = AsyncMock(return_value="deadbeef")
    mock_remove = AsyncMock()
    mock_detect_default_branch = AsyncMock(return_value="main")
    mock_git = AsyncMock(return_value=GitResult(stdout="base123\n", stderr="", returncode=0))
    monkeypatch.setattr("arcwright_ai.engine.nodes.commit_story", mock_commit)
    monkeypatch.setattr("arcwright_ai.engine.nodes.remove_worktree", mock_remove)
    monkeypatch.setattr("arcwright_ai.engine.nodes._detect_default_branch", mock_detect_default_branch)
    monkeypatch.setattr("arcwright_ai.engine.nodes.git", mock_git)

    result = await commit_node(state)

    assert result.status == TaskState.SUCCESS
    mock_commit.assert_called_once()
    call_kwargs = mock_commit.call_args[1]
    assert call_kwargs["story_slug"] == str(state.story_id)
    assert call_kwargs["worktree_path"] == worktree_path
    assert call_kwargs["base_ref"] == "base123"
    mock_detect_default_branch.assert_called_once_with(
        state.project_root,
        str(state.story_id),
        default_branch_override=state.config.scm.default_branch,
    )
    mock_git.assert_any_call("merge-base", "HEAD", "main", cwd=worktree_path)

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


# ---------------------------------------------------------------------------
# Story 6.7 — commit_node push + PR integration tests (Task 5.3)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_commit_node_calls_push_branch_after_successful_commit(
    make_story_state: StoryState,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """commit_node calls push_branch after a successful commit (AC: #8)."""
    worktree_path = Path("/project/.arcwright-ai/worktrees/2-1-state-models")
    state = make_story_state.model_copy(update={"status": TaskState.SUCCESS, "worktree_path": worktree_path})

    mock_push = AsyncMock(return_value=True)
    monkeypatch.setattr("arcwright_ai.engine.nodes.push_branch", mock_push)

    await commit_node(state)

    mock_push.assert_called_once()
    call_kwargs = mock_push.call_args
    # branch_name should be arcwright/<story_id>, project_root should be state.project_root
    assert BRANCH_PREFIX in call_kwargs.args[0]
    assert call_kwargs.kwargs["remote"] == "origin"
    assert call_kwargs.kwargs["worktree_path"] == worktree_path


@pytest.mark.asyncio
async def test_commit_node_calls_generate_pr_body_after_push(
    make_story_state: StoryState,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """commit_node calls generate_pr_body after push (AC: #3, #8)."""
    worktree_path = Path("/project/.arcwright-ai/worktrees/2-1-state-models")
    state = make_story_state.model_copy(update={"status": TaskState.SUCCESS, "worktree_path": worktree_path})

    mock_gen = AsyncMock(return_value="PR body")
    monkeypatch.setattr("arcwright_ai.engine.nodes.generate_pr_body", mock_gen)
    monkeypatch.setattr("arcwright_ai.engine.nodes.push_branch", AsyncMock(return_value=True))

    await commit_node(state)

    mock_gen.assert_called_once()


@pytest.mark.asyncio
async def test_commit_node_calls_open_pull_request_after_generate_pr_body(
    make_story_state: StoryState,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """commit_node calls open_pull_request after generating PR body (AC: #4, #8)."""
    worktree_path = Path("/project/.arcwright-ai/worktrees/2-1-state-models")
    state = make_story_state.model_copy(update={"status": TaskState.SUCCESS, "worktree_path": worktree_path})

    mock_gen = AsyncMock(return_value="PR body")
    mock_open = AsyncMock(return_value="https://github.com/owner/repo/pull/1")
    monkeypatch.setattr("arcwright_ai.engine.nodes.push_branch", AsyncMock(return_value=True))
    monkeypatch.setattr("arcwright_ai.engine.nodes.generate_pr_body", mock_gen)
    monkeypatch.setattr("arcwright_ai.engine.nodes.open_pull_request", mock_open)

    result = await commit_node(state)

    mock_open.assert_called_once()
    assert result.pr_url == "https://github.com/owner/repo/pull/1"


@pytest.mark.asyncio
async def test_commit_node_stores_pr_url_in_state(
    make_story_state: StoryState,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """commit_node stores pr_url in state when open_pull_request succeeds (AC: #9)."""
    worktree_path = Path("/project/.arcwright-ai/worktrees/2-1-state-models")
    state = make_story_state.model_copy(update={"status": TaskState.SUCCESS, "worktree_path": worktree_path})

    expected_url = "https://github.com/owner/repo/pull/7"
    monkeypatch.setattr("arcwright_ai.engine.nodes.push_branch", AsyncMock(return_value=True))
    monkeypatch.setattr("arcwright_ai.engine.nodes.generate_pr_body", AsyncMock(return_value="body"))
    monkeypatch.setattr("arcwright_ai.engine.nodes.open_pull_request", AsyncMock(return_value=expected_url))

    result = await commit_node(state)

    assert result.pr_url == expected_url


@pytest.mark.asyncio
async def test_commit_node_pr_url_none_when_open_pull_request_returns_none(
    make_story_state: StoryState,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """commit_node pr_url is None when open_pull_request returns None (gh missing)."""
    worktree_path = Path("/project/.arcwright-ai/worktrees/2-1-state-models")
    state = make_story_state.model_copy(update={"status": TaskState.SUCCESS, "worktree_path": worktree_path})

    monkeypatch.setattr("arcwright_ai.engine.nodes.push_branch", AsyncMock(return_value=True))
    monkeypatch.setattr("arcwright_ai.engine.nodes.generate_pr_body", AsyncMock(return_value="body"))
    monkeypatch.setattr("arcwright_ai.engine.nodes.open_pull_request", AsyncMock(return_value=None))

    result = await commit_node(state)

    assert result.pr_url is None


@pytest.mark.asyncio
async def test_commit_node_remove_worktree_called_even_if_push_fails(
    make_story_state: StoryState,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """remove_worktree is called even when push_branch returns False (AC: #8 non-fatal)."""
    worktree_path = Path("/project/.arcwright-ai/worktrees/2-1-state-models")
    state = make_story_state.model_copy(update={"status": TaskState.SUCCESS, "worktree_path": worktree_path})

    monkeypatch.setattr("arcwright_ai.engine.nodes.push_branch", AsyncMock(return_value=False))
    mock_remove = AsyncMock()
    monkeypatch.setattr("arcwright_ai.engine.nodes.remove_worktree", mock_remove)
    mock_gen = AsyncMock(return_value="PR body")
    monkeypatch.setattr("arcwright_ai.engine.nodes.generate_pr_body", mock_gen)

    result = await commit_node(state)

    assert result.status == TaskState.SUCCESS
    mock_remove.assert_called_once()
    mock_gen.assert_not_called()


@pytest.mark.asyncio
async def test_commit_node_push_not_called_when_commit_fails(
    make_story_state: StoryState,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """push_branch is NOT called when commit_story raises (no commit = no push)."""
    worktree_path = Path("/project/.arcwright-ai/worktrees/2-1-state-models")
    state = make_story_state.model_copy(update={"status": TaskState.SUCCESS, "worktree_path": worktree_path})

    from arcwright_ai.core.exceptions import BranchError as _BranchError

    monkeypatch.setattr(
        "arcwright_ai.engine.nodes.commit_story",
        AsyncMock(side_effect=_BranchError("no changes", details={})),
    )
    mock_push = AsyncMock()
    monkeypatch.setattr("arcwright_ai.engine.nodes.push_branch", mock_push)

    await commit_node(state)

    mock_push.assert_not_called()


@pytest.mark.asyncio
async def test_commit_node_push_pr_do_not_change_story_status(
    make_story_state: StoryState,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Story status remains SUCCESS even when open_pull_request raises (AC: #5, #8)."""
    worktree_path = Path("/project/.arcwright-ai/worktrees/2-1-state-models")
    state = make_story_state.model_copy(update={"status": TaskState.SUCCESS, "worktree_path": worktree_path})

    monkeypatch.setattr("arcwright_ai.engine.nodes.push_branch", AsyncMock(return_value=True))
    monkeypatch.setattr("arcwright_ai.engine.nodes.generate_pr_body", AsyncMock(side_effect=Exception("boom")))

    result = await commit_node(state)

    assert result.status == TaskState.SUCCESS


# ---------------------------------------------------------------------------
# Story 6.7 — PR URL in run summary (Task 5.5)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_commit_node_updates_story_status_with_pr_url(
    make_story_state: StoryState,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """commit_node calls update_story_status with pr_url when PR is created (AC: #9)."""
    worktree_path = Path("/project/.arcwright-ai/worktrees/2-1-state-models")
    state = make_story_state.model_copy(update={"status": TaskState.SUCCESS, "worktree_path": worktree_path})

    expected_url = "https://github.com/owner/repo/pull/99"
    monkeypatch.setattr("arcwright_ai.engine.nodes.push_branch", AsyncMock(return_value=True))
    monkeypatch.setattr("arcwright_ai.engine.nodes.generate_pr_body", AsyncMock(return_value="body"))
    monkeypatch.setattr("arcwright_ai.engine.nodes.open_pull_request", AsyncMock(return_value=expected_url))
    mock_update = AsyncMock()
    monkeypatch.setattr("arcwright_ai.engine.nodes.update_story_status", mock_update)

    await commit_node(state)

    # One of the calls to update_story_status should include pr_url
    pr_url_calls = [call for call in mock_update.call_args_list if call.kwargs.get("pr_url") == expected_url]
    assert pr_url_calls, "update_story_status was not called with pr_url"


# ---------------------------------------------------------------------------
# Story 7.2: Budget check node — dual ceiling enforcement
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_budget_check_node_records_provenance_on_halt(
    make_story_state: StoryState,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """budget_check_node writes a ProvenanceEntry when budget exceeded (AC: #3, #11d)."""
    mock_append = AsyncMock()
    monkeypatch.setattr("arcwright_ai.engine.nodes.append_entry", mock_append)

    budget = BudgetState(
        invocation_count=5,
        max_invocations=5,
        total_tokens=50_000,
        estimated_cost=Decimal("1.50"),
        max_cost=Decimal("10.0"),
    )
    state = make_story_state.model_copy(update={"budget": budget})
    result = await budget_check_node(state)

    assert result.status == TaskState.ESCALATED
    assert mock_append.call_count == 1
    args = mock_append.call_args[0]
    entry = args[1]
    assert entry.decision == "Budget ceiling exceeded \u2014 halting execution"
    assert "FR25" in entry.ac_references
    assert "NFR10" in entry.ac_references
    assert "D2" in entry.ac_references
    assert "invocation_count=5/5" in entry.rationale
    assert "total_tokens=50000" in entry.rationale


@pytest.mark.asyncio
async def test_budget_check_node_returns_escalated_with_budget_details(
    make_story_state: StoryState,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """budget_check_node returns ESCALATED (not raises) — aligns with LangGraph pattern (AC: #3, #11e)."""
    mock_append = AsyncMock()
    monkeypatch.setattr("arcwright_ai.engine.nodes.append_entry", mock_append)

    budget = BudgetState(
        invocation_count=10,
        max_invocations=5,
        estimated_cost=Decimal("3.50"),
        max_cost=Decimal("10.0"),
        total_tokens=100_000,
    )
    state = make_story_state.model_copy(update={"budget": budget})
    result = await budget_check_node(state)

    # Returns ESCALATED (not raises) — finalize_node can still run
    assert result.status == TaskState.ESCALATED
    # Provenance was recorded with budget details
    entry = mock_append.call_args[0][1]
    assert "estimated_cost=$3.50" in entry.rationale


@pytest.mark.asyncio
async def test_budget_check_provenance_identifies_invocation_ceiling(
    make_story_state: StoryState,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Provenance rationale identifies invocation ceiling when invocation limit breached (AC: #11f)."""
    mock_append = AsyncMock()
    monkeypatch.setattr("arcwright_ai.engine.nodes.append_entry", mock_append)

    budget = BudgetState(
        invocation_count=5,
        max_invocations=5,
        estimated_cost=Decimal("0.50"),
        max_cost=Decimal("10.0"),
    )
    state = make_story_state.model_copy(update={"budget": budget})
    await budget_check_node(state)

    entry = mock_append.call_args[0][1]
    assert "invocation_ceiling" in entry.rationale
    assert "cost_ceiling" not in entry.rationale


@pytest.mark.asyncio
async def test_budget_check_provenance_identifies_cost_ceiling(
    make_story_state: StoryState,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Provenance rationale identifies cost ceiling when cost limit breached (AC: #11f)."""
    mock_append = AsyncMock()
    monkeypatch.setattr("arcwright_ai.engine.nodes.append_entry", mock_append)

    budget = BudgetState(
        invocation_count=2,
        max_invocations=5,
        estimated_cost=Decimal("10.00"),
        max_cost=Decimal("10.00"),
    )
    state = make_story_state.model_copy(update={"budget": budget})
    await budget_check_node(state)

    entry = mock_append.call_args[0][1]
    assert "cost_ceiling" in entry.rationale
    assert "invocation_ceiling" not in entry.rationale


def test_graph_edge_budget_before_dispatch() -> None:
    """Graph structure places budget_check between preflight and agent_dispatch (AC: #2, #11g)."""
    from arcwright_ai.engine.graph import build_story_graph

    graph = build_story_graph()
    # LangGraph compiled graph exposes .get_graph() with nodes and edges
    graph_structure = graph.get_graph()

    # Collect all edge tuples: (source, target)
    edges = [(edge.source, edge.target) for edge in graph_structure.edges]

    # Verify preflight → budget_check and budget_check → agent_dispatch edges exist
    assert ("preflight", "budget_check") in edges
    # budget_check routes to agent_dispatch ("ok") or finalize ("exceeded")
    # The conditional edge from budget_check should have agent_dispatch as a target
    budget_targets = [t for s, t in edges if s == "budget_check"]
    assert "agent_dispatch" in budget_targets, f"budget_check targets: {budget_targets}"
    assert "finalize" in budget_targets, f"budget_check targets: {budget_targets}"


def test_retry_accumulates_in_same_budget(make_story_state: StoryState) -> None:
    """Retry invocations share the same BudgetState — route_budget_check evaluates accumulated budget (AC: #5, #11h)."""
    # Simulate a state after 1 retry: invocation_count=2 (first pass + one retry),
    # RETRY status, and budget close to limit
    budget = BudgetState(
        invocation_count=4,
        max_invocations=5,
        estimated_cost=Decimal("8.00"),
        max_cost=Decimal("10.0"),
    )
    state = make_story_state.model_copy(update={"status": TaskState.RETRY, "retry_count": 1, "budget": budget})
    # Still within budget
    assert route_budget_check(state) == "ok"

    # After one more retry: invocation_count=5 — at ceiling
    budget_at_ceiling = budget.model_copy(update={"invocation_count": 5})
    state_at_ceiling = state.model_copy(update={"budget": budget_at_ceiling})
    assert route_budget_check(state_at_ceiling) == "exceeded"


@pytest.mark.asyncio
async def test_finalize_handles_budget_escalation(
    make_story_state: StoryState,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """finalize_node handles ESCALATED from budget halt with budget details in suggested_fix (AC: #6, #11i)."""
    mock_halt = AsyncMock()
    monkeypatch.setattr("arcwright_ai.engine.nodes.write_halt_report", mock_halt)

    budget = BudgetState(
        invocation_count=5,
        max_invocations=5,
        total_tokens=50_000,
        estimated_cost=Decimal("1.50"),
        max_cost=Decimal("10.0"),
    )
    state = make_story_state.model_copy(
        update={"status": TaskState.ESCALATED, "retry_history": [], "retry_count": 0, "budget": budget}
    )
    await finalize_node(state)

    assert mock_halt.call_count == 1
    call_kwargs = mock_halt.call_args[1]
    assert call_kwargs["halt_reason"] == "budget_exceeded"
    # Suggested fix should include budget consumption details
    suggested_fix = call_kwargs["suggested_fix"]
    assert "invocations=5/5" in suggested_fix
    assert "$1.50" in suggested_fix
    assert "total_tokens=50000" in suggested_fix
    assert "invocation_ceiling" in suggested_fix


@pytest.mark.asyncio
async def test_budget_check_provenance_failure_does_not_block_halt(
    make_story_state: StoryState,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Provenance write failure must not prevent budget halt (Boundary #6, AC: #11k)."""
    mock_append = AsyncMock(side_effect=OSError("disk full"))
    monkeypatch.setattr("arcwright_ai.engine.nodes.append_entry", mock_append)

    budget = BudgetState(invocation_count=5, max_invocations=5)
    state = make_story_state.model_copy(update={"budget": budget})
    result = await budget_check_node(state)

    # Node still returns ESCALATED despite provenance failure
    assert result.status == TaskState.ESCALATED
    assert mock_append.call_count == 1


def test_agent_budget_error_carries_details() -> None:
    """AgentBudgetError accepts a details dict with budget state (AC: #11k)."""
    details = {
        "invocation_count": 5,
        "max_invocations": 5,
        "estimated_cost": "1.50",
        "max_cost": "10.0",
        "total_tokens": 50_000,
        "breached_ceiling": "invocation_ceiling",
    }
    err = AgentBudgetError("Budget ceiling exceeded", details=details)
    assert err.message == "Budget ceiling exceeded"
    assert err.details is not None
    assert err.details["breached_ceiling"] == "invocation_ceiling"
    assert err.details["invocation_count"] == 5


# ---------------------------------------------------------------------------
# Story 7.4: Budget persistence unit tests (AC: #10a-#10f, #10k, #10l)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_agent_dispatch_node_persists_budget_to_run_yaml(
    dispatch_ready_state: StoryState,
    mock_invoke_result: InvocationResult,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """agent_dispatch_node calls update_run_status with updated budget after success (AC: #10a)."""
    from arcwright_ai.core.types import calculate_invocation_cost

    captured: list[BudgetState] = []

    async def _capture(project_root: object, run_id: object, **kwargs: object) -> None:
        if "budget" in kwargs:
            captured.append(kwargs["budget"])  # type: ignore[arg-type]

    monkeypatch.setattr("arcwright_ai.engine.nodes.update_run_status", _capture)
    result = await agent_dispatch_node(dispatch_ready_state)

    assert result.status == TaskState.VALIDATING
    assert len(captured) == 1, "update_run_status should be called once with budget"
    persisted = captured[0]
    assert persisted.invocation_count == 1
    expected_cost = calculate_invocation_cost(
        mock_invoke_result.tokens_input,
        mock_invoke_result.tokens_output,
        dispatch_ready_state.config.models.get(ModelRole.GENERATE).pricing,
    )
    assert persisted.estimated_cost == expected_cost
    assert persisted.total_tokens_input == mock_invoke_result.tokens_input
    assert persisted.total_tokens_output == mock_invoke_result.tokens_output


@pytest.mark.asyncio
async def test_agent_dispatch_node_persists_budget_on_sdk_error(
    dispatch_ready_state: StoryState,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """agent_dispatch_node calls update_run_status with estimated budget after SDK failure (AC: #10b)."""
    captured: list[BudgetState] = []

    async def _raise_agent_error(*args: object, **kwargs: object) -> InvocationResult:
        raise AgentError("SDK connection failed")

    async def _capture(project_root: object, run_id: object, **kwargs: object) -> None:
        if "budget" in kwargs:
            captured.append(kwargs["budget"])  # type: ignore[arg-type]

    monkeypatch.setattr("arcwright_ai.engine.nodes.invoke_agent", _raise_agent_error)
    monkeypatch.setattr("arcwright_ai.engine.nodes.update_run_status", _capture)

    result = await agent_dispatch_node(dispatch_ready_state)

    assert result.status == TaskState.ESCALATED
    assert len(captured) == 1, "update_run_status should be called once on SDK error path"
    persisted = captured[0]
    # Estimated: must have non-zero input tokens from prompt estimation
    assert persisted.invocation_count == 1
    assert persisted.total_tokens_input > 0  # estimated from prompt length
    assert persisted.total_tokens_output == 0  # no output on error


@pytest.mark.asyncio
async def test_agent_dispatch_node_sdk_error_estimates_tokens_from_prompt(
    dispatch_ready_state: StoryState,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """SDK error path estimates input tokens as len(prompt) // 4 (AC: #10c)."""
    from arcwright_ai.agent.prompt import build_prompt

    async def _raise(*args: object, **kwargs: object) -> InvocationResult:
        raise AgentError("SDK crashed")

    monkeypatch.setattr("arcwright_ai.engine.nodes.invoke_agent", _raise)

    # Compute the expected prompt length the same way agent_dispatch_node does
    assert dispatch_ready_state.context_bundle is not None
    prompt = build_prompt(dispatch_ready_state.context_bundle, feedback=None)
    expected_estimated_input = len(prompt) // 4

    result = await agent_dispatch_node(dispatch_ready_state)

    assert result.status == TaskState.ESCALATED
    assert result.budget.total_tokens_input == expected_estimated_input


@pytest.mark.asyncio
async def test_agent_dispatch_node_sdk_error_logs_estimation_warning(
    dispatch_ready_state: StoryState,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """SDK error path emits budget.estimated_from_prompt warning (AC: #10d)."""

    async def _raise(*args: object, **kwargs: object) -> InvocationResult:
        raise AgentError("SDK crashed")

    monkeypatch.setattr("arcwright_ai.engine.nodes.invoke_agent", _raise)

    with caplog.at_level(logging.WARNING):
        await agent_dispatch_node(dispatch_ready_state)

    estimation_records = [r for r in caplog.records if r.message == "budget.estimated_from_prompt"]
    assert estimation_records, "Expected budget.estimated_from_prompt warning"
    assert estimation_records[0].data["estimated"] is True


@pytest.mark.asyncio
async def test_agent_dispatch_node_sdk_error_prefers_partial_usage_over_estimate(
    dispatch_ready_state: StoryState,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """SDK error path uses partial SDK usage tokens when provided (Boundary #5)."""

    async def _raise_with_partial_usage(*args: object, **kwargs: object) -> InvocationResult:
        raise AgentError(
            "SDK crashed after partial usage",
            details={"usage": {"input_tokens": 123, "output_tokens": 0}},
        )

    monkeypatch.setattr("arcwright_ai.engine.nodes.invoke_agent", _raise_with_partial_usage)
    result = await agent_dispatch_node(dispatch_ready_state)

    assert result.status == TaskState.ESCALATED
    assert result.budget.total_tokens_input == 123
    assert result.budget.total_tokens_output == 0


@pytest.mark.asyncio
async def test_validate_node_persists_budget_to_run_yaml(
    validate_ready_state: StoryState,
    mock_pipeline_pass: PipelineResult,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """validate_node calls update_run_status with updated budget after validation (AC: #10e)."""
    captured: list[BudgetState] = []

    async def _capture(project_root: object, run_id: object, **kwargs: object) -> None:
        if "budget" in kwargs:
            captured.append(kwargs["budget"])  # type: ignore[arg-type]

    monkeypatch.setattr("arcwright_ai.engine.nodes.update_run_status", _capture)

    result = await validate_node(validate_ready_state)

    assert result.status == TaskState.SUCCESS
    assert len(captured) >= 1, "update_run_status should be called with budget"
    persisted = captured[0]
    assert persisted.total_tokens == mock_pipeline_pass.tokens_used
    assert persisted.estimated_cost == mock_pipeline_pass.cost


@pytest.mark.asyncio
async def test_finalize_node_persists_budget_on_escalated(
    make_story_state: StoryState,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """finalize_node calls update_run_status with budget on ESCALATED path (AC: #10f)."""
    from arcwright_ai.core.types import StoryCost

    captured_budgets: list[BudgetState] = []

    async def _capture(project_root: object, run_id: object, **kwargs: object) -> None:
        if "budget" in kwargs:
            captured_budgets.append(kwargs["budget"])  # type: ignore[arg-type]

    monkeypatch.setattr("arcwright_ai.engine.nodes.update_run_status", _capture)

    story_slug = str(make_story_state.story_id)
    expected_budget = BudgetState(
        invocation_count=2,
        total_tokens=1500,
        estimated_cost=Decimal("0.03"),
        per_story={story_slug: StoryCost(tokens_input=800, tokens_output=700, cost=Decimal("0.03"), invocations=2)},
    )
    escalated_state = make_story_state.model_copy(
        update={
            "status": TaskState.ESCALATED,
            "agent_output": "partial output",
            "budget": expected_budget,
        }
    )

    result = await finalize_node(escalated_state)

    assert result.status == TaskState.ESCALATED
    assert any(b.invocation_count == 2 for b in captured_budgets), (
        "update_run_status should be called with the escalated budget"
    )


@pytest.mark.asyncio
async def test_agent_dispatch_run_yaml_write_failure_does_not_halt(
    dispatch_ready_state: StoryState,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """run.yaml write failure in agent_dispatch_node does not halt execution (Boundary #1, AC: #10g)."""
    call_count = 0

    async def _raise_on_budget(*args: object, **kwargs: object) -> None:
        nonlocal call_count
        call_count += 1
        if "budget" in kwargs:
            raise OSError("disk full")

    monkeypatch.setattr("arcwright_ai.engine.nodes.update_run_status", _raise_on_budget)

    result = await agent_dispatch_node(dispatch_ready_state)

    # Node must complete normally despite persistence failure
    assert result.status == TaskState.VALIDATING
    assert call_count >= 1


@pytest.mark.asyncio
async def test_validate_node_run_yaml_write_failure_does_not_halt(
    validate_ready_state: StoryState,
    mock_pipeline_pass: PipelineResult,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """run.yaml write failure in validate_node does not halt execution (Boundary #1, AC: #10l)."""
    call_count = 0

    async def _raise_on_budget(*args: object, **kwargs: object) -> None:
        nonlocal call_count
        call_count += 1
        if "budget" in kwargs:
            raise OSError("disk full")

    monkeypatch.setattr("arcwright_ai.engine.nodes.update_run_status", _raise_on_budget)

    result = await validate_node(validate_ready_state)

    assert result.status == TaskState.SUCCESS
    assert call_count >= 1


# ---------------------------------------------------------------------------
# Story 7.4: Integration tests - multi-story cost accumulation (AC: #10g-#10j)
# ---------------------------------------------------------------------------


@pytest.fixture
async def run_with_yaml(
    story_state_with_project: StoryState,
    monkeypatch: pytest.MonkeyPatch,
) -> StoryState:
    """Set up a real run.yaml and restore the real update_run_status for integration tests."""
    from arcwright_ai.output.run_manager import create_run
    from arcwright_ai.output.run_manager import update_run_status as real_update_run_status

    story_slug = str(story_state_with_project.story_id)
    await create_run(
        story_state_with_project.project_root,
        story_state_with_project.run_id,
        story_state_with_project.config,
        [story_slug],
    )
    monkeypatch.setattr("arcwright_ai.engine.nodes.update_run_status", real_update_run_status)
    return story_state_with_project


def _state_from_graph_result(result: StoryState | dict[str, object], template: StoryState) -> StoryState:
    """Normalize LangGraph invoke results to StoryState for assertions."""
    if isinstance(result, StoryState):
        return result
    return template.model_copy(update=result)


@pytest.mark.asyncio
async def test_integration_three_story_run_accumulates_total_cost(
    run_with_yaml: StoryState,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """3 sequential stories through full graph accumulate correct totals (AC: #10g)."""
    from arcwright_ai.core.types import calculate_invocation_cost
    from arcwright_ai.engine.graph import build_story_graph

    graph = build_story_graph()

    per_story_tokens = [
        (100, 50),  # story 1: input=100, output=50
        (200, 80),  # story 2: input=200, output=80
        (150, 60),  # story 3: input=150, output=60
    ]

    # Keep validation cost neutral for this accumulation assertion.
    v6 = V6ValidationResult(passed=True, results=[V6CheckResult(check_name="file_existence", passed=True)])

    async def _mock_pipeline_pass(*args: object, **kwargs: object) -> PipelineResult:
        return PipelineResult(
            passed=True,
            outcome=PipelineOutcome.PASS,
            v6_result=v6,
            tokens_used=0,
            cost=Decimal("0"),
        )

    monkeypatch.setattr("arcwright_ai.engine.nodes.run_validation_pipeline", _mock_pipeline_pass)

    current_budget = run_with_yaml.budget
    for i, (inp, out) in enumerate(per_story_tokens):
        story_slug = f"story-{i + 1}"

        async def _mock_invoke(
            *args: object,
            _inp: int = inp,
            _out: int = out,
            _slug: str = story_slug,
            **kwargs: object,
        ) -> InvocationResult:
            return InvocationResult(
                output_text="done",
                tokens_input=_inp,
                tokens_output=_out,
                total_cost=Decimal("0.001"),
                duration_ms=100,
                session_id=f"s-{_slug}",
                num_turns=1,
                is_error=False,
            )

        monkeypatch.setattr("arcwright_ai.engine.nodes.invoke_agent", _mock_invoke)
        initial_state = run_with_yaml.model_copy(
            update={
                "story_id": story_slug,
                "budget": current_budget,
                "status": TaskState.QUEUED,
                "retry_count": 0,
                "validation_result": None,
                "retry_history": [],
                "agent_output": None,
                "worktree_path": None,
            }
        )
        graph_result = await graph.ainvoke(initial_state)
        completed_state = _state_from_graph_result(graph_result, initial_state)
        current_budget = completed_state.budget

    final_budget = current_budget
    assert final_budget.invocation_count == 3
    # Verify total tokens: sum of all inputs + outputs
    expected_total = sum(i + o for i, o in per_story_tokens)
    assert final_budget.total_tokens == expected_total

    # Verify total cost
    expected_cost = sum(
        calculate_invocation_cost(i, o, run_with_yaml.config.models.get(ModelRole.GENERATE).pricing)
        for i, o in per_story_tokens
    )
    assert final_budget.estimated_cost == expected_cost


@pytest.mark.asyncio
async def test_integration_retry_costs_in_per_story_and_run_totals(
    run_with_yaml: StoryState,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Retry invocations appear in per_story.invocations and run-level totals (AC: #10h)."""
    from arcwright_ai.engine.graph import build_story_graph

    graph = build_story_graph()
    story_slug = str(run_with_yaml.story_id)

    async def _mock_invoke(*args: object, **kwargs: object) -> InvocationResult:
        return InvocationResult(
            output_text="attempt",
            tokens_input=300,
            tokens_output=100,
            total_cost=Decimal("0.005"),
            duration_ms=200,
            session_id="s-1",
            num_turns=1,
            is_error=False,
        )

    v6 = V6ValidationResult(passed=True, results=[V6CheckResult(check_name="file_existence", passed=True)])
    feedback = ReflexionFeedback(
        passed=False,
        unmet_criteria=["1"],
        feedback_per_criterion={"1": "Fix required"},
        attempt_number=1,
    )
    fail_v3 = PipelineResult(
        passed=False,
        outcome=PipelineOutcome.FAIL_V3,
        v6_result=v6,
        v3_result=V3ReflexionResult(
            validation_result=ValidationResult(
                passed=False,
                ac_results=[ACResult(ac_id="1", passed=False, rationale="Missing impl")],
            ),
            feedback=feedback,
            tokens_used=0,
            cost=Decimal("0"),
        ),
        feedback=feedback,
        tokens_used=0,
        cost=Decimal("0"),
    )
    pass_result = PipelineResult(
        passed=True,
        outcome=PipelineOutcome.PASS,
        v6_result=v6,
        tokens_used=0,
        cost=Decimal("0"),
    )

    validation_call_count = 0

    async def _mock_pipeline_retry(*args: object, **kwargs: object) -> PipelineResult:
        nonlocal validation_call_count
        validation_call_count += 1
        if validation_call_count == 1:
            return fail_v3
        return pass_result

    monkeypatch.setattr("arcwright_ai.engine.nodes.invoke_agent", _mock_invoke)
    monkeypatch.setattr("arcwright_ai.engine.nodes.run_validation_pipeline", _mock_pipeline_retry)

    graph_result = await graph.ainvoke(run_with_yaml)
    final_state = _state_from_graph_result(graph_result, run_with_yaml)
    final_budget = final_state.budget

    # Total invocations = 3 (2 generate dispatches + 1 review validation)
    assert final_budget.invocation_count == 3
    # per_story shows aggregate invocations across roles
    assert story_slug in final_budget.per_story
    assert final_budget.per_story[story_slug].invocations == 3
    assert final_budget.per_story[story_slug].invocations_by_role.get("generate") == 2
    assert final_budget.per_story[story_slug].invocations_by_role.get("review") == 1
    # Tokens doubled
    assert final_budget.total_tokens_input == 600
    assert final_budget.total_tokens_output == 200


@pytest.mark.asyncio
async def test_integration_run_yaml_reflects_final_cost(
    run_with_yaml: StoryState,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """run.yaml budget matches in-memory state after full graph story execution (AC: #10i)."""
    import yaml

    from arcwright_ai.core.constants import DIR_ARCWRIGHT, DIR_RUNS, RUN_METADATA_FILENAME
    from arcwright_ai.engine.graph import build_story_graph

    graph = build_story_graph()

    v6 = V6ValidationResult(passed=True, results=[V6CheckResult(check_name="file_existence", passed=True)])

    async def _mock_pipeline_pass(*args: object, **kwargs: object) -> PipelineResult:
        return PipelineResult(
            passed=True,
            outcome=PipelineOutcome.PASS,
            v6_result=v6,
            tokens_used=0,
            cost=Decimal("0"),
        )

    async def _mock_invoke(*args: object, **kwargs: object) -> InvocationResult:
        return InvocationResult(
            output_text="done",
            tokens_input=400,
            tokens_output=150,
            total_cost=Decimal("0.007"),
            duration_ms=300,
            session_id="s-int",
            num_turns=2,
            is_error=False,
        )

    monkeypatch.setattr("arcwright_ai.engine.nodes.invoke_agent", _mock_invoke)
    monkeypatch.setattr("arcwright_ai.engine.nodes.run_validation_pipeline", _mock_pipeline_pass)
    graph_result = await graph.ainvoke(run_with_yaml)
    final_state = _state_from_graph_result(graph_result, run_with_yaml)

    # Read run.yaml from disk
    run_yaml_path = (
        run_with_yaml.project_root / DIR_ARCWRIGHT / DIR_RUNS / str(run_with_yaml.run_id) / RUN_METADATA_FILENAME
    )
    assert run_yaml_path.exists(), "run.yaml must exist after full graph execution"
    with run_yaml_path.open(encoding="utf-8") as fh:
        data = yaml.safe_load(fh)

    budget_section = data["budget"]
    assert budget_section["invocation_count"] == 1
    assert budget_section["total_tokens_input"] == 400
    assert budget_section["total_tokens_output"] == 150
    # estimated_cost stored as str
    assert Decimal(budget_section["estimated_cost"]) == final_state.budget.estimated_cost


@pytest.mark.asyncio
async def test_integration_zero_invocations_missed(
    run_with_yaml: StoryState,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Every SDK invocation increments invocation_count — zero are missed (AC: #10j)."""
    from arcwright_ai.engine.graph import build_story_graph

    n_stories = 4
    graph = build_story_graph()
    current_budget = run_with_yaml.budget

    v6 = V6ValidationResult(passed=True, results=[V6CheckResult(check_name="file_existence", passed=True)])

    async def _mock_pipeline_pass(*args: object, **kwargs: object) -> PipelineResult:
        return PipelineResult(
            passed=True,
            outcome=PipelineOutcome.PASS,
            v6_result=v6,
            tokens_used=0,
            cost=Decimal("0"),
        )

    monkeypatch.setattr("arcwright_ai.engine.nodes.run_validation_pipeline", _mock_pipeline_pass)

    for i in range(n_stories):
        story_slug = f"story-{i + 1}"

        async def _mock_invoke(*args: object, _i: int = i, **kwargs: object) -> InvocationResult:
            return InvocationResult(
                output_text="done",
                tokens_input=50,
                tokens_output=20,
                total_cost=Decimal("0.001"),
                duration_ms=50,
                session_id=f"s-{_i}",
                num_turns=1,
                is_error=False,
            )

        monkeypatch.setattr("arcwright_ai.engine.nodes.invoke_agent", _mock_invoke)
        initial_state = run_with_yaml.model_copy(
            update={
                "story_id": story_slug,
                "budget": current_budget,
                "status": TaskState.QUEUED,
                "retry_count": 0,
                "validation_result": None,
                "retry_history": [],
                "agent_output": None,
                "worktree_path": None,
            }
        )
        graph_result = await graph.ainvoke(initial_state)
        completed_state = _state_from_graph_result(graph_result, initial_state)
        current_budget = completed_state.budget

    assert current_budget.invocation_count == n_stories, (
        f"Expected {n_stories} invocations tracked, got {current_budget.invocation_count}"
    )
    assert len(current_budget.per_story) == n_stories, (
        f"Expected {n_stories} per-story entries, got {len(current_budget.per_story)}"
    )
    for i in range(n_stories):
        slug = f"story-{i + 1}"
        assert slug in current_budget.per_story
        assert current_budget.per_story[slug].invocations == 1


# ---------------------------------------------------------------------------
# Story 9.2 — preflight_node fetch_and_sync integration tests (AC: #5, #6)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_preflight_calls_fetch_and_sync(
    story_state_with_project: StoryState,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """preflight_node calls fetch_and_sync before create_worktree when base_ref is None."""
    call_order: list[str] = []

    async def _fetch_and_sync(*_args: object, **_kwargs: object) -> str:
        call_order.append("fetch")
        return "deadbeef1234567890deadbeef1234567890dead"

    async def _create_worktree(*_args: object, **_kwargs: object) -> Path:
        call_order.append("create_worktree")
        return Path("/project/.arcwright-ai/worktrees/2-6-preflight-node")

    mock_fetch = AsyncMock(side_effect=_fetch_and_sync)
    mock_create = AsyncMock(side_effect=_create_worktree)
    monkeypatch.setattr("arcwright_ai.engine.nodes.fetch_and_sync", mock_fetch)
    monkeypatch.setattr("arcwright_ai.engine.nodes.create_worktree", mock_create)
    monkeypatch.setattr(
        "arcwright_ai.engine.nodes._detect_default_branch",
        AsyncMock(return_value="main"),
    )

    await preflight_node(story_state_with_project)

    mock_fetch.assert_called_once()
    mock_create.assert_called_once()
    assert call_order == ["fetch", "create_worktree"]


@pytest.mark.asyncio
async def test_preflight_base_ref_bypasses_fetch(
    story_state_with_project: StoryState,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """preflight_node skips fetch_and_sync entirely when state.base_ref is already set."""
    mock_fetch = AsyncMock(return_value="shouldnotbecalled")
    monkeypatch.setattr("arcwright_ai.engine.nodes.fetch_and_sync", mock_fetch)

    state_with_base_ref = story_state_with_project.model_copy(update={"base_ref": "explicit-sha-abc123"})
    await preflight_node(state_with_base_ref)

    mock_fetch.assert_not_called()


@pytest.mark.asyncio
async def test_preflight_passes_fetch_sha_to_create_worktree(
    story_state_with_project: StoryState,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """preflight_node passes the SHA returned by fetch_and_sync as base_ref to create_worktree."""
    expected_sha = "cafebabe1234567890cafebabe1234567890cafe"
    monkeypatch.setattr(
        "arcwright_ai.engine.nodes.fetch_and_sync",
        AsyncMock(return_value=expected_sha),
    )
    monkeypatch.setattr(
        "arcwright_ai.engine.nodes._detect_default_branch",
        AsyncMock(return_value="main"),
    )
    mock_create = AsyncMock(return_value=Path("/project/.arcwright-ai/worktrees/2-6-preflight-node"))
    monkeypatch.setattr("arcwright_ai.engine.nodes.create_worktree", mock_create)

    await preflight_node(story_state_with_project)

    mock_create.assert_called_once()
    _args, _kwargs = mock_create.call_args
    # base_ref is the second positional arg
    assert _args[1] == expected_sha


# ---------------------------------------------------------------------------
# Story 9.3 — commit_node auto-merge integration tests (AC: #16)
# ---------------------------------------------------------------------------


def _make_run_config_with_auto_merge() -> RunConfig:
    """Build a RunConfig with auto_merge=True for Story 9.3 tests."""
    config = make_run_config()
    return config.model_copy(update={"scm": ScmConfig(auto_merge=True)})


@pytest.mark.asyncio
async def test_commit_node_calls_merge_when_auto_merge_enabled(
    make_story_state: StoryState,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """commit_node calls merge_pull_request when auto_merge=True and pr_url is set."""
    worktree_path = Path("/project/.arcwright-ai/worktrees/2-1-state-models")
    state = make_story_state.model_copy(
        update={
            "status": TaskState.SUCCESS,
            "worktree_path": worktree_path,
            "config": _make_run_config_with_auto_merge(),
        }
    )
    expected_url = "https://github.com/owner/repo/pull/42"
    monkeypatch.setattr("arcwright_ai.engine.nodes.push_branch", AsyncMock(return_value=True))
    monkeypatch.setattr("arcwright_ai.engine.nodes.generate_pr_body", AsyncMock(return_value="body"))
    monkeypatch.setattr("arcwright_ai.engine.nodes.open_pull_request", AsyncMock(return_value=expected_url))
    mock_merge = AsyncMock(return_value=True)
    monkeypatch.setattr("arcwright_ai.engine.nodes.merge_pull_request", mock_merge)

    await commit_node(state)

    mock_merge.assert_called_once()
    call_args = mock_merge.call_args
    assert call_args.args[0] == expected_url
    assert call_args.kwargs["strategy"] == "squash"
    assert call_args.kwargs["project_root"] == state.project_root


@pytest.mark.asyncio
async def test_commit_node_skips_merge_when_auto_merge_disabled(
    make_story_state: StoryState,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """commit_node does NOT call merge_pull_request when auto_merge=False."""
    worktree_path = Path("/project/.arcwright-ai/worktrees/2-1-state-models")
    state = make_story_state.model_copy(
        update={
            "status": TaskState.SUCCESS,
            "worktree_path": worktree_path,
            # default config has auto_merge=False
        }
    )
    expected_url = "https://github.com/owner/repo/pull/42"
    monkeypatch.setattr("arcwright_ai.engine.nodes.push_branch", AsyncMock(return_value=True))
    monkeypatch.setattr("arcwright_ai.engine.nodes.generate_pr_body", AsyncMock(return_value="body"))
    monkeypatch.setattr("arcwright_ai.engine.nodes.open_pull_request", AsyncMock(return_value=expected_url))
    mock_merge = AsyncMock(return_value=True)
    monkeypatch.setattr("arcwright_ai.engine.nodes.merge_pull_request", mock_merge)

    await commit_node(state)

    mock_merge.assert_not_called()


@pytest.mark.asyncio
async def test_commit_node_skips_merge_when_pr_url_none(
    make_story_state: StoryState,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """commit_node does NOT call merge_pull_request when pr_url is None even if auto_merge=True."""
    worktree_path = Path("/project/.arcwright-ai/worktrees/2-1-state-models")
    state = make_story_state.model_copy(
        update={
            "status": TaskState.SUCCESS,
            "worktree_path": worktree_path,
            "config": _make_run_config_with_auto_merge(),
        }
    )
    # push succeeds but PR creation returns None
    monkeypatch.setattr("arcwright_ai.engine.nodes.push_branch", AsyncMock(return_value=True))
    monkeypatch.setattr("arcwright_ai.engine.nodes.generate_pr_body", AsyncMock(return_value="body"))
    monkeypatch.setattr("arcwright_ai.engine.nodes.open_pull_request", AsyncMock(return_value=None))
    mock_merge = AsyncMock(return_value=True)
    monkeypatch.setattr("arcwright_ai.engine.nodes.merge_pull_request", mock_merge)

    await commit_node(state)

    mock_merge.assert_not_called()


@pytest.mark.asyncio
async def test_commit_node_records_merge_provenance(
    make_story_state: StoryState,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """commit_node calls append_entry with ProvenanceEntry containing 'Auto-merge' in decision."""
    worktree_path = Path("/project/.arcwright-ai/worktrees/2-1-state-models")
    state = make_story_state.model_copy(
        update={
            "status": TaskState.SUCCESS,
            "worktree_path": worktree_path,
            "config": _make_run_config_with_auto_merge(),
        }
    )
    expected_url = "https://github.com/owner/repo/pull/42"
    monkeypatch.setattr("arcwright_ai.engine.nodes.push_branch", AsyncMock(return_value=True))
    monkeypatch.setattr("arcwright_ai.engine.nodes.generate_pr_body", AsyncMock(return_value="body"))
    monkeypatch.setattr("arcwright_ai.engine.nodes.open_pull_request", AsyncMock(return_value=expected_url))
    monkeypatch.setattr("arcwright_ai.engine.nodes.merge_pull_request", AsyncMock(return_value=True))
    monkeypatch.setattr("arcwright_ai.engine.nodes.get_pull_request_merge_sha", AsyncMock(return_value="abc1234"))

    mock_append = AsyncMock()
    monkeypatch.setattr("arcwright_ai.engine.nodes.append_entry", mock_append)

    await commit_node(state)

    # At least one append_entry call should be for the merge provenance
    merge_entries = [
        call
        for call in mock_append.call_args_list
        if "Auto-merge" in (call.args[1].decision if len(call.args) > 1 else "")
    ]
    assert merge_entries, "Expected ProvenanceEntry with 'Auto-merge' in decision"
    entry = merge_entries[0].args[1]
    assert "FR39" in entry.ac_references
    assert "D7" in entry.ac_references
    assert "merge_attempted_at=" in entry.rationale
    assert "status=success" in entry.rationale
    assert "strategy=squash" in entry.rationale
    assert "merge_sha=abc1234" in entry.rationale


@pytest.mark.asyncio
async def test_commit_node_status_success_on_merge_failure(
    make_story_state: StoryState,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """commit_node status remains SUCCESS when merge_pull_request returns False (non-fatal)."""
    worktree_path = Path("/project/.arcwright-ai/worktrees/2-1-state-models")
    state = make_story_state.model_copy(
        update={
            "status": TaskState.SUCCESS,
            "worktree_path": worktree_path,
            "config": _make_run_config_with_auto_merge(),
        }
    )
    expected_url = "https://github.com/owner/repo/pull/42"
    monkeypatch.setattr("arcwright_ai.engine.nodes.push_branch", AsyncMock(return_value=True))
    monkeypatch.setattr("arcwright_ai.engine.nodes.generate_pr_body", AsyncMock(return_value="body"))
    monkeypatch.setattr("arcwright_ai.engine.nodes.open_pull_request", AsyncMock(return_value=expected_url))
    # merge fails
    monkeypatch.setattr("arcwright_ai.engine.nodes.merge_pull_request", AsyncMock(return_value=False))

    result = await commit_node(state)

    assert result.status == TaskState.SUCCESS
    assert result.pr_url == expected_url
