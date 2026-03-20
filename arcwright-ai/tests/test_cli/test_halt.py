"""Tests for HaltController — graceful halt coordination.

Tests cover:
    - Exit code mapping for all exception types (AC#6, #7, #8, D6 taxonomy).
    - handle_halt() structured output, artifact writes, best-effort behaviour.
    - handle_graph_halt() ESCALATED exit codes and halt report content.
    - Provenance flush, NFR2 completed-story protection, NFR3 SDK wrapping.
    - Best-effort behaviour when write_halt_report / update_run_status raise.

All filesystem tests use tmp_path for isolation.
All tests run in asyncio auto mode (no @pytest.mark.asyncio required).
"""

from __future__ import annotations

from decimal import Decimal
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

from arcwright_ai.cli.halt import HaltController
from arcwright_ai.core.exceptions import (
    AgentBudgetError,
    AgentError,
    AgentTimeoutError,
    ArcwrightError,
    BranchError,
    ConfigError,
    ContextError,
    ProjectError,
    SandboxViolation,
    ScmError,
    ValidationError,
    WorktreeError,
)
from arcwright_ai.core.lifecycle import TaskState
from arcwright_ai.core.types import BudgetState, StoryId

# ---------------------------------------------------------------------------
# Constants (D6 exit codes)
# ---------------------------------------------------------------------------

EXIT_SUCCESS = 0
EXIT_VALIDATION = 1
EXIT_AGENT = 2
EXIT_CONFIG = 3
EXIT_SCM = 4
EXIT_INTERNAL = 5


# ---------------------------------------------------------------------------
# Shared test fixtures / factory helpers
# ---------------------------------------------------------------------------


def _make_budget(
    invocations: int = 0,
    tokens: int = 0,
    cost: str = "0",
    *,
    max_invocations: int = 0,
    max_cost: str = "0",
) -> BudgetState:
    """Return a BudgetState with the given values."""
    return BudgetState(
        invocation_count=invocations,
        total_tokens=tokens,
        estimated_cost=Decimal(cost),
        max_invocations=max_invocations,
        max_cost=Decimal(max_cost),
    )


def _make_halt_controller(tmp_path: Path, run_id: str = "20260306-120000-abc123") -> HaltController:
    """Return a HaltController pointing at tmp_path."""
    return HaltController(
        project_root=tmp_path,
        run_id=run_id,
        epic_spec="5",
    )


def _make_story_state(
    *,
    status: TaskState = TaskState.ESCALATED,
    retry_history: list[object] | None = None,
    retry_count: int = 0,
    agent_output: str | None = None,
    retry_budget: int = 3,
    story_id: str = "5-2-halt-controller",
    tmp_path: Path | None = None,
) -> MagicMock:
    """Return a StoryState-like mock configurable for halt tests.

    Uses MagicMock to avoid requiring a full StoryState (which needs RunConfig,
    story_path, project_root, etc.). All fields accessed by HaltController are
    explicitly configured.
    """
    state = MagicMock()
    state.story_id = StoryId(story_id)
    state.status = status
    state.retry_history = retry_history or []
    state.retry_count = retry_count
    state.agent_output = agent_output
    state.config = MagicMock()
    state.config.limits.retry_budget = retry_budget
    return state


def _make_fail_v3_result(unmet_criteria: list[str] | None = None) -> MagicMock:
    """Return a PipelineResult-like mock with FAIL_V3 outcome."""
    result = MagicMock()
    result.outcome = "fail_v3"
    result.v6_result = None
    result.feedback = MagicMock()
    result.feedback.unmet_criteria = unmet_criteria or ["AC1", "AC2"]
    result.feedback.feedback_per_criterion = {"AC1": "was not implemented", "AC2": "missing test"}
    return result


def _make_fail_v6_result(failure_count: int = 2) -> MagicMock:
    """Return a PipelineResult-like mock with FAIL_V6 outcome."""
    result = MagicMock()
    result.outcome = "fail_v6"
    failures = [MagicMock() for _ in range(failure_count)]
    result.v6_result = MagicMock()
    result.v6_result.failures = failures
    result.feedback = None
    return result


# ---------------------------------------------------------------------------
# Task 8.1 — _determine_exit_code_for_exception: D6 taxonomy mapping
# ---------------------------------------------------------------------------


class TestDetermineExitCodeForException:
    """Covers all exception types from D6 taxonomy (AC#8.1)."""

    def test_agent_budget_error(self) -> None:
        assert HaltController._determine_exit_code_for_exception(AgentBudgetError("budget")) == EXIT_AGENT

    def test_agent_timeout_error(self) -> None:
        assert HaltController._determine_exit_code_for_exception(AgentTimeoutError("timeout")) == EXIT_AGENT

    def test_sandbox_violation(self) -> None:
        assert HaltController._determine_exit_code_for_exception(SandboxViolation("sandbox")) == EXIT_AGENT

    def test_agent_error_base(self) -> None:
        assert HaltController._determine_exit_code_for_exception(AgentError("crash")) == EXIT_AGENT

    def test_scm_error(self) -> None:
        assert HaltController._determine_exit_code_for_exception(ScmError("git failed")) == EXIT_SCM

    def test_worktree_error(self) -> None:
        assert HaltController._determine_exit_code_for_exception(WorktreeError("worktree")) == EXIT_SCM

    def test_branch_error(self) -> None:
        assert HaltController._determine_exit_code_for_exception(BranchError("branch")) == EXIT_SCM

    def test_config_error(self) -> None:
        assert HaltController._determine_exit_code_for_exception(ConfigError("config")) == EXIT_CONFIG

    def test_project_error(self) -> None:
        assert HaltController._determine_exit_code_for_exception(ProjectError("project")) == EXIT_CONFIG

    def test_context_error(self) -> None:
        assert HaltController._determine_exit_code_for_exception(ContextError("context")) == EXIT_CONFIG

    def test_validation_error(self) -> None:
        assert HaltController._determine_exit_code_for_exception(ValidationError("validation")) == EXIT_VALIDATION

    def test_arcwright_error_base(self) -> None:
        assert HaltController._determine_exit_code_for_exception(ArcwrightError("base")) == EXIT_INTERNAL

    def test_generic_exception(self) -> None:
        assert HaltController._determine_exit_code_for_exception(RuntimeError("unexpected")) == EXIT_INTERNAL


# ---------------------------------------------------------------------------
# Task 8.2 — handle_halt(): structured output contains all required fields
# ---------------------------------------------------------------------------


async def test_handle_halt_output_contains_required_fields(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """handle_halt() halt summary contains completed stories, halted story, halt reason,
    budget, and the resume command (AC#5)."""
    # Arrange
    controller = _make_halt_controller(tmp_path)
    budget = _make_budget(invocations=3, tokens=1500, cost="0.15")
    completed = ["5-1-epic-dispatch"]

    monkeypatch.setattr("arcwright_ai.cli.halt.write_halt_report", AsyncMock(return_value=tmp_path / "s.md"))
    monkeypatch.setattr("arcwright_ai.cli.halt.update_run_status", AsyncMock())
    monkeypatch.setattr("arcwright_ai.cli.halt.append_entry", AsyncMock())

    # Act
    exit_code = await controller.handle_halt(
        story_id=StoryId("5-2-halt-controller"),
        exception=AgentError("agent crashed while applying edits"),
        accumulated_budget=budget,
        completed_stories=completed,
        last_completed="5-1-epic-dispatch",
    )

    # Assert exit code
    assert exit_code == EXIT_AGENT

    # Assert output contains required fields (AC#5)
    captured = capsys.readouterr()
    output = captured.err  # typer.echo writes to stderr in tests
    assert "5-2-halt-controller" in output, "Halted story must appear in output"
    assert "5-1-epic-dispatch" in output, "Completed stories must appear in output"
    assert "agent error" in output, "Halt reason must appear in output"
    assert "0.15" in output, "Budget cost must appear in output"
    assert "1500" in output, "Budget tokens must appear in output"
    assert "EPIC-5" in output, "Resume command must reference the epic"
    assert "--resume" in output, "Resume command flag must appear in output"


# ---------------------------------------------------------------------------
# Task 8.3 — handle_graph_halt(): ESCALATED + validation exhaustion → exit 1
# ---------------------------------------------------------------------------


async def test_handle_graph_halt_validation_exhaustion_exit_code(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """ESCALATED state from validation exhaustion maps to exit code 1 (AC#7)."""
    controller = _make_halt_controller(tmp_path)
    budget = _make_budget(tokens=5000, cost="0.50")

    # retry_count >= retry_budget  → max_retries_exhausted
    story_state = _make_story_state(
        status=TaskState.ESCALATED,
        retry_history=[_make_fail_v3_result()],
        retry_count=3,
        retry_budget=3,
    )

    write_halt_mock = AsyncMock(return_value=tmp_path / "s.md")
    monkeypatch.setattr("arcwright_ai.cli.halt.write_halt_report", write_halt_mock)
    monkeypatch.setattr("arcwright_ai.cli.halt.update_run_status", AsyncMock())
    monkeypatch.setattr("arcwright_ai.cli.halt.append_entry", AsyncMock())

    exit_code = await controller.handle_graph_halt(
        story_state=story_state,
        accumulated_budget=budget,
        completed_stories=[],
        last_completed=None,
    )

    assert exit_code == EXIT_VALIDATION, f"Validation exhaustion must map to exit 1, got {exit_code}"

    # halt report must have been written with non-empty validation_history
    assert write_halt_mock.called
    call_kwargs = write_halt_mock.call_args.kwargs
    assert call_kwargs["validation_history"], "Validation history must be non-empty for exhaustion halt"


# ---------------------------------------------------------------------------
# Task 8.4 — handle_graph_halt(): ESCALATED + budget exceeded → exit 2
# ---------------------------------------------------------------------------


async def test_handle_graph_halt_budget_exceeded_exit_code(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """ESCALATED state with no retry history (budget check triggered) → exit code 2 (AC#12)."""
    controller = _make_halt_controller(tmp_path)
    budget = _make_budget(tokens=10000, cost="2.00", max_cost="1.00")

    # No retry_history → budget-check escalation
    story_state = _make_story_state(
        status=TaskState.ESCALATED,
        retry_history=[],
        retry_count=0,
    )

    write_halt_mock = AsyncMock(return_value=tmp_path / "s.md")
    monkeypatch.setattr("arcwright_ai.cli.halt.write_halt_report", write_halt_mock)
    monkeypatch.setattr("arcwright_ai.cli.halt.update_run_status", AsyncMock())
    monkeypatch.setattr("arcwright_ai.cli.halt.append_entry", AsyncMock())

    exit_code = await controller.handle_graph_halt(
        story_state=story_state,
        accumulated_budget=budget,
        completed_stories=[],
        last_completed=None,
    )

    assert exit_code == EXIT_AGENT, f"Budget exceeded must map to exit 2, got {exit_code}"
    assert write_halt_mock.called, "write_halt_report must be called for budget-exceeded halt"


# ---------------------------------------------------------------------------
# Task 8.5 — Provenance flush: append_entry called with halt reason and budget
# ---------------------------------------------------------------------------


async def test_handle_halt_flushes_provenance(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """handle_halt() calls append_entry with a halt ProvenanceEntry (AC#3)."""
    controller = _make_halt_controller(tmp_path)
    budget = _make_budget(invocations=2, tokens=800, cost="0.08")

    append_mock = AsyncMock()
    monkeypatch.setattr("arcwright_ai.cli.halt.write_halt_report", AsyncMock(return_value=tmp_path / "s.md"))
    monkeypatch.setattr("arcwright_ai.cli.halt.update_run_status", AsyncMock())
    monkeypatch.setattr("arcwright_ai.cli.halt.append_entry", append_mock)

    await controller.handle_halt(
        story_id=StoryId("5-2-halt-controller"),
        exception=ScmError("git push failed"),
        accumulated_budget=budget,
        completed_stories=[],
        last_completed=None,
    )

    assert append_mock.called, "append_entry must be called to flush provenance"
    _, entry = append_mock.call_args.args
    # ProvenanceEntry decision must contain halt reason
    assert "SCM error" in entry.decision or "halt" in entry.decision.lower()
    # Rationale must reference budget state
    assert "invocations=2" in entry.rationale
    assert "tokens=800" in entry.rationale
    assert "0.08" in entry.rationale


# ---------------------------------------------------------------------------
# Task 8.6 — write_halt_report called for exception-based halts (AC#2)
# ---------------------------------------------------------------------------


async def test_handle_halt_calls_write_halt_report(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """handle_halt() calls write_halt_report with the failing story slug (AC#2)."""
    controller = _make_halt_controller(tmp_path)
    budget = _make_budget()

    write_halt_mock = AsyncMock(return_value=tmp_path / "summary.md")
    monkeypatch.setattr("arcwright_ai.cli.halt.write_halt_report", write_halt_mock)
    monkeypatch.setattr("arcwright_ai.cli.halt.update_run_status", AsyncMock())
    monkeypatch.setattr("arcwright_ai.cli.halt.append_entry", AsyncMock())

    await controller.handle_halt(
        story_id=StoryId("5-2-halt-controller"),
        exception=AgentBudgetError("tokens exceeded"),
        accumulated_budget=budget,
        completed_stories=[],
        last_completed=None,
    )

    assert write_halt_mock.called, "write_halt_report must be called for exception-based halts"
    call_kwargs = write_halt_mock.call_args.kwargs
    assert call_kwargs["halted_story"] == "5-2-halt-controller"
    assert "budget" in call_kwargs["halt_reason"]


# ---------------------------------------------------------------------------
# Task 8.7 — NFR3: asyncio.TimeoutError caught and wrapped in dispatch loop
# ---------------------------------------------------------------------------


def test_nfr3_timeout_error_wrapped_as_agent_error(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """asyncio.TimeoutError is caught in the dispatch loop and wrapped as AgentError
    before reaching halt controller, so the exit code is 2 (EXIT_AGENT) (AC#9)."""
    from typer.testing import CliRunner

    from arcwright_ai.cli.app import app
    from arcwright_ai.core.config import ApiConfig, RunConfig

    runner = CliRunner()
    impl = tmp_path / "_spec" / "implementation-artifacts"
    impl.mkdir(parents=True)
    (impl / "5-1-some-story.md").write_text("# Story 5.1\n")

    test_config = RunConfig(api=ApiConfig(claude_api_key="test-key"))
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr("arcwright_ai.cli.dispatch.load_config", lambda *a, **k: test_config)

    async def _create_run(project_root: Path, run_id: object, config: object, story_slugs: list[str]) -> Path:
        run_dir = project_root / ".arcwright-ai" / "runs" / str(run_id)
        run_dir.mkdir(parents=True, exist_ok=True)
        return run_dir

    async def _noop(*a: object, **k: object) -> None:
        pass

    monkeypatch.setattr("arcwright_ai.cli.dispatch.create_run", _create_run)
    monkeypatch.setattr("arcwright_ai.cli.dispatch.update_run_status", _noop)
    monkeypatch.setattr("arcwright_ai.cli.dispatch.update_story_status", _noop)
    monkeypatch.setattr("arcwright_ai.cli.halt.write_halt_report", AsyncMock(return_value=tmp_path / "s.md"))
    monkeypatch.setattr("arcwright_ai.cli.halt.update_run_status", _noop)
    monkeypatch.setattr("arcwright_ai.cli.halt.append_entry", AsyncMock())
    monkeypatch.setattr("arcwright_ai.cli.dispatch.typer.confirm", lambda *a, **k: None)

    def _make_timeout_graph() -> object:
        g = MagicMock()

        async def _ainvoke(state: object) -> object:
            raise TimeoutError("connection timed out")

        g.ainvoke = _ainvoke
        return g

    monkeypatch.setattr("arcwright_ai.cli.dispatch.build_story_graph", _make_timeout_graph)

    result = runner.invoke(app, ["dispatch", "--epic", "5", "--yes"])
    # TimeoutError is wrapped as AgentError → exit code 2
    assert (
        result.exit_code == EXIT_AGENT
    ), f"asyncio.TimeoutError must produce exit code 2 (EXIT_AGENT), got {result.exit_code}"


# ---------------------------------------------------------------------------
# Task 8.8 — NFR3: ConnectionError caught and wrapped in dispatch loop
# ---------------------------------------------------------------------------


def test_nfr3_connection_error_wrapped_as_agent_error(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """ConnectionError is caught in the dispatch loop and wrapped as AgentError
    before reaching halt controller, so the exit code is 2 (EXIT_AGENT) (AC#9)."""
    from typer.testing import CliRunner

    from arcwright_ai.cli.app import app
    from arcwright_ai.core.config import ApiConfig, RunConfig

    runner = CliRunner()
    impl = tmp_path / "_spec" / "implementation-artifacts"
    impl.mkdir(parents=True)
    (impl / "5-1-some-story.md").write_text("# Story 5.1\n")

    test_config = RunConfig(api=ApiConfig(claude_api_key="test-key"))
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr("arcwright_ai.cli.dispatch.load_config", lambda *a, **k: test_config)

    async def _create_run(project_root: Path, run_id: object, config: object, story_slugs: list[str]) -> Path:
        run_dir = project_root / ".arcwright-ai" / "runs" / str(run_id)
        run_dir.mkdir(parents=True, exist_ok=True)
        return run_dir

    async def _noop(*a: object, **k: object) -> None:
        pass

    monkeypatch.setattr("arcwright_ai.cli.dispatch.create_run", _create_run)
    monkeypatch.setattr("arcwright_ai.cli.dispatch.update_run_status", _noop)
    monkeypatch.setattr("arcwright_ai.cli.dispatch.update_story_status", _noop)
    monkeypatch.setattr("arcwright_ai.cli.halt.write_halt_report", AsyncMock(return_value=tmp_path / "s.md"))
    monkeypatch.setattr("arcwright_ai.cli.halt.update_run_status", _noop)
    monkeypatch.setattr("arcwright_ai.cli.halt.append_entry", AsyncMock())
    monkeypatch.setattr("arcwright_ai.cli.dispatch.typer.confirm", lambda *a, **k: None)

    def _make_connection_error_graph() -> object:
        g = MagicMock()

        async def _ainvoke(state: object) -> object:
            raise ConnectionError("API server unreachable")

        g.ainvoke = _ainvoke
        return g

    monkeypatch.setattr("arcwright_ai.cli.dispatch.build_story_graph", _make_connection_error_graph)

    result = runner.invoke(app, ["dispatch", "--epic", "5", "--yes"])
    assert (
        result.exit_code == EXIT_AGENT
    ), f"ConnectionError must produce exit code 2 (EXIT_AGENT), got {result.exit_code}"


def test_nfr3_http_status_error_wrapped_as_agent_error(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """HTTPStatusError is caught in the dispatch loop and wrapped as AgentError
    before reaching halt controller, producing exit code 2 (EXIT_AGENT)."""
    httpx = pytest.importorskip("httpx")
    from typer.testing import CliRunner

    from arcwright_ai.cli.app import app
    from arcwright_ai.core.config import ApiConfig, RunConfig

    runner = CliRunner()
    impl = tmp_path / "_spec" / "implementation-artifacts"
    impl.mkdir(parents=True)
    (impl / "5-1-some-story.md").write_text("# Story 5.1\n")

    test_config = RunConfig(api=ApiConfig(claude_api_key="test-key"))
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr("arcwright_ai.cli.dispatch.load_config", lambda *a, **k: test_config)

    async def _create_run(project_root: Path, run_id: object, config: object, story_slugs: list[str]) -> Path:
        run_dir = project_root / ".arcwright-ai" / "runs" / str(run_id)
        run_dir.mkdir(parents=True, exist_ok=True)
        return run_dir

    async def _noop(*a: object, **k: object) -> None:
        pass

    monkeypatch.setattr("arcwright_ai.cli.dispatch.create_run", _create_run)
    monkeypatch.setattr("arcwright_ai.cli.dispatch.update_run_status", _noop)
    monkeypatch.setattr("arcwright_ai.cli.dispatch.update_story_status", _noop)
    monkeypatch.setattr("arcwright_ai.cli.halt.write_halt_report", AsyncMock(return_value=tmp_path / "s.md"))
    monkeypatch.setattr("arcwright_ai.cli.halt.update_run_status", _noop)
    monkeypatch.setattr("arcwright_ai.cli.halt.append_entry", AsyncMock())
    monkeypatch.setattr("arcwright_ai.cli.dispatch.typer.confirm", lambda *a, **k: None)

    request = httpx.Request("GET", "https://example.com")
    response = httpx.Response(500, request=request)

    def _make_http_status_graph() -> object:
        g = MagicMock()

        async def _ainvoke(state: object) -> object:
            raise httpx.HTTPStatusError("Server Error", request=request, response=response)

        g.ainvoke = _ainvoke
        return g

    monkeypatch.setattr("arcwright_ai.cli.dispatch.build_story_graph", _make_http_status_graph)

    result = runner.invoke(app, ["dispatch", "--epic", "5", "--yes"])
    assert (
        result.exit_code == EXIT_AGENT
    ), f"HTTPStatusError must produce exit code 2 (EXIT_AGENT), got {result.exit_code}"


# ---------------------------------------------------------------------------
# Task 8.9 — NFR2: completed story directories are not modified after halt
# ---------------------------------------------------------------------------


async def test_nfr2_completed_story_dirs_not_modified(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Completed story directories are not touched when halt occurs on a later story (AC#10)."""
    run_id = "20260306-120000-abc123"

    # Create synthetic completed story directory with known content
    completed_story_dir = tmp_path / ".arcwright-ai" / "runs" / run_id / "stories" / "5-1-done-story"
    completed_story_dir.mkdir(parents=True)
    completed_file = completed_story_dir / "validation.md"
    sentinel_content = "# Completed story — do not modify\n"
    completed_file.write_text(sentinel_content)

    controller = HaltController(
        project_root=tmp_path,
        run_id=run_id,
        epic_spec="5",
    )
    budget = _make_budget()

    write_halt_mock = AsyncMock(return_value=tmp_path / "summary.md")
    monkeypatch.setattr("arcwright_ai.cli.halt.write_halt_report", write_halt_mock)
    monkeypatch.setattr("arcwright_ai.cli.halt.update_run_status", AsyncMock())
    # We do NOT mock append_entry — but the failing story directory doesn't exist,
    # so append_entry will call write_entries() which creates the directory.

    # Trigger halt on a DIFFERENT story
    await controller.handle_halt(
        story_id=StoryId("5-2-halt-controller"),  # <- failing story
        exception=AgentError("crash"),
        accumulated_budget=budget,
        completed_stories=["5-1-done-story"],  # <- completed story
        last_completed="5-1-done-story",
    )

    # Completed story's validation.md must be byte-identical
    assert completed_file.read_text() == sentinel_content, "HaltController must not modify completed story directories"


async def test_handle_halt_nfr2_guard_raises_for_completed_story(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """handle_halt() raises AssertionError when called for a story in completed_stories (AC#10)."""
    controller = _make_halt_controller(tmp_path)
    budget = _make_budget()

    monkeypatch.setattr("arcwright_ai.cli.halt.write_halt_report", AsyncMock(return_value=tmp_path / "s.md"))
    monkeypatch.setattr("arcwright_ai.cli.halt.update_run_status", AsyncMock())
    monkeypatch.setattr("arcwright_ai.cli.halt.append_entry", AsyncMock())

    with pytest.raises(AssertionError, match="already-completed"):
        await controller.handle_halt(
            story_id=StoryId("5-1-done-story"),  # in completed_stories!
            exception=AgentError("oops"),
            accumulated_budget=budget,
            completed_stories=["5-1-done-story"],
            last_completed="5-1-done-story",
        )


async def test_handle_graph_halt_nfr2_guard_raises_for_completed_story(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """handle_graph_halt() raises AssertionError when called for completed story."""
    controller = _make_halt_controller(tmp_path)
    budget = _make_budget()
    story_state = _make_story_state(story_id="5-1-done-story", status=TaskState.ESCALATED, retry_history=[])

    monkeypatch.setattr("arcwright_ai.cli.halt.write_halt_report", AsyncMock(return_value=tmp_path / "s.md"))
    monkeypatch.setattr("arcwright_ai.cli.halt.update_run_status", AsyncMock())
    monkeypatch.setattr("arcwright_ai.cli.halt.append_entry", AsyncMock())

    with pytest.raises(AssertionError, match="already-completed"):
        await controller.handle_graph_halt(
            story_state=story_state,
            accumulated_budget=budget,
            completed_stories=["5-1-done-story"],
            last_completed="5-1-done-story",
        )


# ---------------------------------------------------------------------------
# Task 8.10 — Best-effort: write_halt_report raises, controller returns exit code
# ---------------------------------------------------------------------------


async def test_best_effort_write_halt_report_failure_does_not_suppress_exit(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """write_halt_report raising must not prevent halt controller returning exit code (AC#2 Note)."""
    controller = _make_halt_controller(tmp_path)
    budget = _make_budget()

    monkeypatch.setattr(
        "arcwright_ai.cli.halt.write_halt_report",
        AsyncMock(side_effect=OSError("disk full")),
    )
    monkeypatch.setattr("arcwright_ai.cli.halt.update_run_status", AsyncMock())
    monkeypatch.setattr("arcwright_ai.cli.halt.append_entry", AsyncMock())

    exit_code = await controller.handle_halt(
        story_id=StoryId("5-2-halt-controller"),
        exception=AgentError("crash"),
        accumulated_budget=budget,
        completed_stories=[],
        last_completed=None,
    )

    assert (
        exit_code == EXIT_AGENT
    ), "write_halt_report failure must not prevent halt controller returning correct exit code"


async def test_best_effort_write_halt_report_failure_graph_halt(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """write_halt_report raising during graph halt must not suppress the exit code."""
    controller = _make_halt_controller(tmp_path)
    budget = _make_budget()
    story_state = _make_story_state(status=TaskState.ESCALATED, retry_history=[])

    monkeypatch.setattr(
        "arcwright_ai.cli.halt.write_halt_report",
        AsyncMock(side_effect=OSError("disk full")),
    )
    monkeypatch.setattr("arcwright_ai.cli.halt.update_run_status", AsyncMock())
    monkeypatch.setattr("arcwright_ai.cli.halt.append_entry", AsyncMock())

    exit_code = await controller.handle_graph_halt(
        story_state=story_state,
        accumulated_budget=budget,
        completed_stories=[],
        last_completed=None,
    )

    assert exit_code == EXIT_AGENT, "write_halt_report failure must not prevent halt controller returning exit code"


# ---------------------------------------------------------------------------
# Task 8.11 — Best-effort: update_run_status raises, controller returns exit code
# ---------------------------------------------------------------------------


async def test_best_effort_update_run_status_failure_does_not_suppress_exit(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """update_run_status raising must not prevent halt controller returning exit code (AC#4 Note)."""
    controller = _make_halt_controller(tmp_path)
    budget = _make_budget()

    monkeypatch.setattr("arcwright_ai.cli.halt.write_halt_report", AsyncMock(return_value=tmp_path / "s.md"))
    monkeypatch.setattr(
        "arcwright_ai.cli.halt.update_run_status",
        AsyncMock(side_effect=OSError("run.yaml locked")),
    )
    monkeypatch.setattr("arcwright_ai.cli.halt.append_entry", AsyncMock())

    exit_code = await controller.handle_halt(
        story_id=StoryId("5-2-halt-controller"),
        exception=ScmError("git failed"),
        accumulated_budget=budget,
        completed_stories=[],
        last_completed=None,
    )

    assert (
        exit_code == EXIT_SCM
    ), "update_run_status failure must not prevent halt controller returning correct exit code"


async def test_best_effort_update_run_status_failure_graph_halt(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """update_run_status raising during graph halt must not suppress the exit code."""
    controller = _make_halt_controller(tmp_path)
    budget = _make_budget()
    story_state = _make_story_state(
        status=TaskState.ESCALATED,
        retry_history=[_make_fail_v3_result()],
        retry_count=3,
        retry_budget=3,
    )

    monkeypatch.setattr("arcwright_ai.cli.halt.write_halt_report", AsyncMock(return_value=tmp_path / "s.md"))
    monkeypatch.setattr(
        "arcwright_ai.cli.halt.update_run_status",
        AsyncMock(side_effect=OSError("disk full")),
    )
    monkeypatch.setattr("arcwright_ai.cli.halt.append_entry", AsyncMock())

    exit_code = await controller.handle_graph_halt(
        story_state=story_state,
        accumulated_budget=budget,
        completed_stories=[],
        last_completed=None,
    )

    assert exit_code == EXIT_VALIDATION, "update_run_status failure must not suppress the exit code"


# ---------------------------------------------------------------------------
# Task 8.11 continued — exit code mapping AC#8.11 full taxonomy
# ---------------------------------------------------------------------------


class TestExitCodeMappingComplete:
    """Full exit code mapping: one case each for validation, config, SCM, agent, internal."""

    def test_agent_budget_error_exit_2(self) -> None:
        assert HaltController._determine_exit_code_for_exception(AgentBudgetError("x")) == 2

    def test_validation_exhaustion_exit_1(self) -> None:
        assert HaltController._determine_exit_code_for_exception(ValidationError("x")) == 1

    def test_scm_error_exit_4(self) -> None:
        assert HaltController._determine_exit_code_for_exception(ScmError("x")) == 4

    def test_config_error_exit_3(self) -> None:
        assert HaltController._determine_exit_code_for_exception(ConfigError("x")) == 3

    def test_unhandled_exception_exit_5(self) -> None:
        assert HaltController._determine_exit_code_for_exception(Exception("raw")) == 5

    def test_arcwright_error_exit_5(self) -> None:
        assert HaltController._determine_exit_code_for_exception(ArcwrightError("base")) == 5


# ---------------------------------------------------------------------------
# Additional: _halt_reason_for_exception and _halt_reason_for_graph_state
# ---------------------------------------------------------------------------


class TestHaltReasonStrings:
    """Verify halt reason strings conform to AC#5 vocabulary."""

    def test_agent_budget_error_reason(self) -> None:
        assert HaltController._halt_reason_for_exception(AgentBudgetError("x")) == "budget exceeded"

    def test_sandbox_violation_reason(self) -> None:
        assert HaltController._halt_reason_for_exception(SandboxViolation("x")) == "sandbox violation"

    def test_agent_error_reason(self) -> None:
        assert HaltController._halt_reason_for_exception(AgentError("x")) == "agent error"

    def test_agent_error_sdk_reason_from_details(self) -> None:
        assert (
            HaltController._halt_reason_for_exception(
                AgentError(
                    "SDK communication failure",
                    details={"error_category": "sdk", "original_error": "HTTPStatusError"},
                )
            )
            == "SDK error"
        )

    def test_scm_error_reason(self) -> None:
        assert HaltController._halt_reason_for_exception(ScmError("x")) == "SCM error"

    def test_validation_error_reason(self) -> None:
        assert HaltController._halt_reason_for_exception(ValidationError("x")) == "validation exhaustion"

    def test_config_error_reason(self) -> None:
        assert HaltController._halt_reason_for_exception(ConfigError("x")) == "config/context error"

    def test_context_error_reason(self) -> None:
        assert HaltController._halt_reason_for_exception(ContextError("x")) == "config/context error"

    def test_unhandled_exception_reason(self) -> None:
        assert HaltController._halt_reason_for_exception(Exception("raw")) == "internal error"

    def test_graph_state_budget_exceeded_reason(self) -> None:
        state = _make_story_state(status=TaskState.ESCALATED, retry_history=[])
        budget = _make_budget(cost="1.00", max_cost="1.00")
        assert HaltController._halt_reason_for_graph_state(state, budget) == "budget exceeded"

    def test_graph_state_escalated_no_retry_no_budget_reason(self) -> None:
        state = _make_story_state(status=TaskState.ESCALATED, retry_history=[])
        budget = _make_budget(cost="0.10", max_cost="10.00")
        assert HaltController._halt_reason_for_graph_state(state, budget) == "SDK error"

    def test_graph_state_sdk_failure_reason(self) -> None:
        failure = MagicMock()
        failure.check_name = "validation_sdk_error"
        fail_v6 = _make_fail_v6_result(failure_count=1)
        fail_v6.v6_result.failures = [failure]
        state = _make_story_state(status=TaskState.ESCALATED, retry_history=[fail_v6])
        budget = _make_budget(cost="0.10", max_cost="10.00")
        assert HaltController._halt_reason_for_graph_state(state, budget) == "SDK error"

    def test_graph_state_validation_exhaustion_reason(self) -> None:
        state = _make_story_state(
            status=TaskState.ESCALATED,
            retry_history=[_make_fail_v3_result()],
            retry_count=3,
            retry_budget=3,
        )
        budget = _make_budget(cost="0.10", max_cost="10.00")
        assert HaltController._halt_reason_for_graph_state(state, budget) == "validation exhaustion"

    def test_graph_state_v6_failure_reason(self) -> None:
        state = _make_story_state(
            status=TaskState.ESCALATED,
            retry_history=[_make_fail_v6_result()],
            retry_count=1,
            retry_budget=3,
        )
        budget = _make_budget(cost="0.10", max_cost="10.00")
        assert HaltController._halt_reason_for_graph_state(state, budget) == "validation exhaustion"


# ---------------------------------------------------------------------------
# Additional: _build_validation_history
# ---------------------------------------------------------------------------


def test_build_validation_history_empty_retry_history() -> None:
    """Empty retry_history produces empty validation history list."""
    state = _make_story_state(retry_history=[])
    result = HaltController._build_validation_history(state)
    assert result == []


def test_build_validation_history_with_fail_v3() -> None:
    """FAIL_V3 result produces history entry with attempt number and failures string."""
    state = _make_story_state(
        retry_history=[_make_fail_v3_result(unmet_criteria=["AC1"])],
    )
    history = HaltController._build_validation_history(state)
    assert len(history) == 1
    assert history[0]["attempt"] == 1
    assert history[0]["outcome"] == "fail_v3"
    assert "AC1" in history[0]["failures"]


def test_build_validation_history_with_fail_v6() -> None:
    """FAIL_V6 result produces history entry with V6 failure count."""
    state = _make_story_state(
        retry_history=[_make_fail_v6_result(failure_count=3)],
    )
    history = HaltController._build_validation_history(state)
    assert len(history) == 1
    assert history[0]["outcome"] == "fail_v6"
    assert "3" in history[0]["failures"], "V6 failure count must appear in failures string"


# ---------------------------------------------------------------------------
# Additional: resume command format
# ---------------------------------------------------------------------------


class TestResumeCommand:
    """HaltController._build_resume_command produces correct format for various epic_spec inputs."""

    def test_plain_number_epic_spec(self) -> None:
        c = HaltController(project_root=Path("/tmp"), run_id="x", epic_spec="5")
        assert c._build_resume_command() == "arcwright-ai dispatch --epic EPIC-5 --resume"

    def test_epic_prefix_epic_spec(self) -> None:
        c = HaltController(project_root=Path("/tmp"), run_id="x", epic_spec="epic-5")
        assert c._build_resume_command() == "arcwright-ai dispatch --epic EPIC-5 --resume"

    def test_uppercase_epic_prefix(self) -> None:
        c = HaltController(project_root=Path("/tmp"), run_id="x", epic_spec="EPIC-5")
        cmd = c._build_resume_command()
        assert "EPIC-5" in cmd
        assert "--resume" in cmd


# ---------------------------------------------------------------------------
# Additional: _suggested_fix_for_graph_state budget/sdk branching
# ---------------------------------------------------------------------------


class TestSuggestedFixForGraphState:
    """Verify budget-aware suggested fix routing for graph halts."""

    def test_budget_exceeded_fix_message(self) -> None:
        state = _make_story_state(status=TaskState.ESCALATED, retry_history=[])
        budget = _make_budget(cost="2.00", max_cost="1.00")

        fix = HaltController._suggested_fix_for_graph_state(state, budget)

        assert "Budget ceiling was exceeded" in fix
        assert "limits.cost_per_run" in fix

    def test_no_retry_no_budget_fix_message(self) -> None:
        state = _make_story_state(status=TaskState.ESCALATED, retry_history=[])
        budget = _make_budget(cost="0.10", max_cost="10.00")

        fix = HaltController._suggested_fix_for_graph_state(state, budget)

        assert "Agent invocation failed before validation completed" in fix
        assert "SDK stderr logs" in fix

    def test_sdk_failure_fix_message(self) -> None:
        failure = MagicMock()
        failure.check_name = "validation_sdk_error"
        fail_v6 = _make_fail_v6_result(failure_count=1)
        fail_v6.v6_result.failures = [failure]
        state = _make_story_state(status=TaskState.ESCALATED, retry_history=[fail_v6])
        budget = _make_budget(cost="0.10", max_cost="10.00")

        fix = HaltController._suggested_fix_for_graph_state(state, budget)

        assert "Agent invocation failed before validation completed" in fix
        assert "model access" in fix


# ---------------------------------------------------------------------------
# Task 7.1-7.4 / AC#15 — HaltController previous_run_id threading (Story 5.4)
# ---------------------------------------------------------------------------


async def test_halt_controller_previous_run_id_passed_to_write_halt_report(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """(7.1 / AC#15a) HaltController with previous_run_id passes it to write_halt_report()."""
    captured_kwargs: dict[str, object] = {}

    async def _mock_write_halt_report(*args: object, **kwargs: object) -> Path:
        captured_kwargs.update(kwargs)
        return tmp_path / "summary.md"

    monkeypatch.setattr("arcwright_ai.cli.halt.write_halt_report", _mock_write_halt_report)
    monkeypatch.setattr("arcwright_ai.cli.halt.update_run_status", AsyncMock())
    monkeypatch.setattr("arcwright_ai.cli.halt.append_entry", AsyncMock())

    controller = HaltController(
        project_root=tmp_path,
        run_id="20260306-120000-abc123",
        epic_spec="5",
        previous_run_id="20260301-100000-orig01",
    )
    budget = _make_budget()
    await controller.handle_halt(
        story_id=StoryId("5-4-halt-resume"),
        exception=AgentError("crash"),
        accumulated_budget=budget,
        completed_stories=[],
        last_completed=None,
    )

    assert captured_kwargs.get("previous_run_id") == "20260301-100000-orig01"


async def test_halt_controller_no_previous_run_id_passes_none(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """(7.2 / AC#15b) HaltController without previous_run_id passes None (backward compat)."""
    captured_kwargs: dict[str, object] = {}

    async def _mock_write_halt_report(*args: object, **kwargs: object) -> Path:
        captured_kwargs.update(kwargs)
        return tmp_path / "summary.md"

    monkeypatch.setattr("arcwright_ai.cli.halt.write_halt_report", _mock_write_halt_report)
    monkeypatch.setattr("arcwright_ai.cli.halt.update_run_status", AsyncMock())
    monkeypatch.setattr("arcwright_ai.cli.halt.append_entry", AsyncMock())

    controller = HaltController(
        project_root=tmp_path,
        run_id="20260306-120000-abc123",
        epic_spec="5",
    )
    budget = _make_budget()
    await controller.handle_halt(
        story_id=StoryId("5-4-halt-resume"),
        exception=AgentError("crash"),
        accumulated_budget=budget,
        completed_stories=[],
        last_completed=None,
    )

    assert captured_kwargs.get("previous_run_id") is None


async def test_handle_graph_halt_extracts_failing_ac_ids_from_v3(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """(7.3 / AC#15c) handle_graph_halt() extracts failing AC IDs from StoryState.retry_history."""
    captured_kwargs: dict[str, object] = {}

    async def _mock_write_halt_report(*args: object, **kwargs: object) -> Path:
        captured_kwargs.update(kwargs)
        return tmp_path / "summary.md"

    monkeypatch.setattr("arcwright_ai.cli.halt.write_halt_report", _mock_write_halt_report)
    monkeypatch.setattr("arcwright_ai.cli.halt.update_run_status", AsyncMock())
    monkeypatch.setattr("arcwright_ai.cli.halt.append_entry", AsyncMock())

    story_state = _make_story_state(
        retry_history=[_make_fail_v3_result(unmet_criteria=["AC1", "AC3"])],
    )

    controller = _make_halt_controller(tmp_path)
    budget = _make_budget()
    await controller.handle_graph_halt(
        story_state=story_state,
        accumulated_budget=budget,
        completed_stories=[],
        last_completed=None,
    )

    failing_ac_ids = captured_kwargs.get("failing_ac_ids")
    assert isinstance(failing_ac_ids, list)
    assert "1" in failing_ac_ids
    assert "3" in failing_ac_ids


async def test_handle_halt_exception_path_passes_empty_failing_ac_ids(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """(7.4 / AC#15d) handle_halt() exception path passes failing_ac_ids=[]."""
    captured_kwargs: dict[str, object] = {}

    async def _mock_write_halt_report(*args: object, **kwargs: object) -> Path:
        captured_kwargs.update(kwargs)
        return tmp_path / "summary.md"

    monkeypatch.setattr("arcwright_ai.cli.halt.write_halt_report", _mock_write_halt_report)
    monkeypatch.setattr("arcwright_ai.cli.halt.update_run_status", AsyncMock())
    monkeypatch.setattr("arcwright_ai.cli.halt.append_entry", AsyncMock())

    controller = _make_halt_controller(tmp_path)
    budget = _make_budget()
    await controller.handle_halt(
        story_id=StoryId("5-4-halt-resume"),
        exception=AgentError("crash"),
        accumulated_budget=budget,
        completed_stories=[],
        last_completed=None,
    )

    assert captured_kwargs.get("failing_ac_ids") == []


async def test_handle_graph_halt_passes_worktree_path(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Graph halt path forwards worktree_path to write_halt_report when available."""
    captured_kwargs: dict[str, object] = {}

    async def _mock_write_halt_report(*args: object, **kwargs: object) -> Path:
        captured_kwargs.update(kwargs)
        return tmp_path / "summary.md"

    monkeypatch.setattr("arcwright_ai.cli.halt.write_halt_report", _mock_write_halt_report)
    monkeypatch.setattr("arcwright_ai.cli.halt.update_run_status", AsyncMock())
    monkeypatch.setattr("arcwright_ai.cli.halt.append_entry", AsyncMock())

    story_state = _make_story_state(
        retry_history=[_make_fail_v6_result()],
    )
    story_state.worktree_path = tmp_path / ".arcwright-ai" / "worktrees" / "5-2-halt-controller"

    controller = _make_halt_controller(tmp_path)
    budget = _make_budget()
    await controller.handle_graph_halt(
        story_state=story_state,
        accumulated_budget=budget,
        completed_stories=[],
        last_completed=None,
    )

    assert captured_kwargs.get("worktree_path") == str(story_state.worktree_path)


# ---------------------------------------------------------------------------
# Task 7 — _extract_failing_ac_ids_from_state (AC: #8, #15)
# ---------------------------------------------------------------------------


def test_extract_failing_ac_ids_from_state_v3_feedback() -> None:
    """_extract_failing_ac_ids_from_state extracts ACs from V3 unmet_criteria."""
    state = _make_story_state(
        retry_history=[_make_fail_v3_result(unmet_criteria=["AC1", "AC3"])],
    )
    result = HaltController._extract_failing_ac_ids_from_state(state)
    assert "1" in result
    assert "3" in result


def test_extract_failing_ac_ids_from_state_empty_history() -> None:
    """_extract_failing_ac_ids_from_state returns [] for empty retry history."""
    state = _make_story_state(retry_history=[])
    result = HaltController._extract_failing_ac_ids_from_state(state)
    assert result == []


def test_extract_failing_ac_ids_from_state_v6_no_ac_id_attr() -> None:
    """_extract_failing_ac_ids_from_state handles V6 failures with no ac_id attribute."""
    state = _make_story_state(
        retry_history=[_make_fail_v6_result(failure_count=2)],
    )
    # V6 failures from _make_fail_v6_result don't have ac_id or rule_id → returns empty
    result = HaltController._extract_failing_ac_ids_from_state(state)
    assert isinstance(result, list)


async def test_handle_graph_halt_ignores_v6_rule_id_only_when_collecting_ac_ids(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """V6 rule-only failures are not reported as failing AC IDs in halt report args."""
    captured_kwargs: dict[str, object] = {}

    async def _mock_write_halt_report(*args: object, **kwargs: object) -> Path:
        captured_kwargs.update(kwargs)
        return tmp_path / "summary.md"

    monkeypatch.setattr("arcwright_ai.cli.halt.write_halt_report", _mock_write_halt_report)
    monkeypatch.setattr("arcwright_ai.cli.halt.update_run_status", AsyncMock())
    monkeypatch.setattr("arcwright_ai.cli.halt.append_entry", AsyncMock())

    failure = MagicMock()
    failure.ac_id = None
    failure.rule_id = "V6-001"
    v6_result = MagicMock()
    v6_result.failures = [failure]
    pipeline_result = MagicMock()
    pipeline_result.outcome = "fail_v6"
    pipeline_result.feedback = None
    pipeline_result.v6_result = v6_result

    state = _make_story_state(retry_history=[pipeline_result])
    controller = _make_halt_controller(tmp_path)
    await controller.handle_graph_halt(
        story_state=state,
        accumulated_budget=_make_budget(),
        completed_stories=[],
        last_completed=None,
    )

    assert captured_kwargs.get("failing_ac_ids") == []


# ---------------------------------------------------------------------------
# Story 13.2 — Platform-account failure guidance (AC: #1, #2, #3, #4)
# ---------------------------------------------------------------------------


def _make_agent_error_with_platform_classification(category_str: str) -> AgentError:
    """Return an AgentError whose details carry a classified platform-account failure."""
    from arcwright_ai.core.errors import CLAUDE_ERROR_REGISTRY, ClaudeErrorCategory

    category = ClaudeErrorCategory(category_str)
    cls = CLAUDE_ERROR_REGISTRY[category]
    return AgentError(
        cls.summary,
        details={"classification": cls, "failure_category": category_str},
    )


class TestPlatformAccountSuggestedFix:
    """_suggested_fix_for_exception returns platform-specific guidance for billing/auth/model_access.

    Each test verifies AC#1 (billing) and AC#2 (auth, model_access).
    """

    def test_billing_error_mentions_credits_and_platform(self) -> None:
        """billing_error suggested fix references Claude platform and credits/billing (AC#1)."""
        exc = _make_agent_error_with_platform_classification("billing_error")
        fix = HaltController._suggested_fix_for_exception(exc)
        assert (
            "Claude platform" in fix or "Claude Platform" in fix
        ), "Billing fix must state this is a Claude platform/account issue"
        assert "credit" in fix.lower() or "billing" in fix.lower(), "Billing fix must mention credits or billing"

    def test_auth_error_mentions_api_key_and_platform(self) -> None:
        """auth_error suggested fix references Claude platform and API key (AC#2)."""
        exc = _make_agent_error_with_platform_classification("auth_error")
        fix = HaltController._suggested_fix_for_exception(exc)
        assert (
            "Claude platform" in fix or "Claude Platform" in fix
        ), "Auth fix must state this is a Claude platform/account issue"
        assert "api key" in fix.lower() or "ANTHROPIC_API_KEY" in fix, "Auth fix must mention API key verification"

    def test_model_access_error_mentions_model_and_platform(self) -> None:
        """model_access_error suggested fix references Claude platform and model entitlement (AC#2)."""
        exc = _make_agent_error_with_platform_classification("model_access_error")
        fix = HaltController._suggested_fix_for_exception(exc)
        assert (
            "Claude platform" in fix or "Claude Platform" in fix
        ), "Model access fix must state this is a Claude platform/account issue"
        assert "model" in fix.lower(), "Model access fix must mention model"

    def test_non_platform_agent_error_uses_generic_fix(self) -> None:
        """AgentError without platform classification gets the existing generic message."""
        exc = AgentError("SDK crash", details={"error_category": "sdk"})
        fix = HaltController._suggested_fix_for_exception(exc)
        assert "Agent invocation failed" in fix
        assert "Claude Platform" not in fix

    def test_billing_fix_does_not_expose_secrets(self) -> None:
        """Platform guidance must never include raw API key values (AC#4 / scope boundary)."""
        from arcwright_ai.core.errors import CLAUDE_ERROR_REGISTRY, ClaudeErrorCategory

        cls = CLAUDE_ERROR_REGISTRY[ClaudeErrorCategory.AUTH_ERROR]
        exc = AgentError(
            cls.summary,
            details={
                "classification": cls,
                "failure_category": "auth_error",
                "captured_stderr": "Error: Invalid API key sk-ant-secret123abc",
            },
        )
        fix = HaltController._suggested_fix_for_exception(exc)
        assert "sk-ant-secret123abc" not in fix, "Raw API key must not appear in suggested fix"


class TestPlatformAccountTerminalOutput:
    """handle_halt() emits platform-account guidance in terminal output (AC#1, #2, #3)."""

    async def test_billing_terminal_output_says_claude_platform(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """billing_error halt output explicitly says Claude platform issue (AC#1)."""
        exc = _make_agent_error_with_platform_classification("billing_error")
        controller = _make_halt_controller(tmp_path)
        monkeypatch.setattr("arcwright_ai.cli.halt.write_halt_report", AsyncMock(return_value=tmp_path / "s.md"))
        monkeypatch.setattr("arcwright_ai.cli.halt.update_run_status", AsyncMock())
        monkeypatch.setattr("arcwright_ai.cli.halt.append_entry", AsyncMock())

        await controller.handle_halt(
            story_id=StoryId("13-2-billing-test"),
            exception=exc,
            accumulated_budget=_make_budget(),
            completed_stories=[],
            last_completed=None,
        )

        output = capsys.readouterr().err
        assert (
            "Claude platform" in output or "Claude Platform" in output
        ), "Terminal output must explicitly say this is a Claude platform/account issue"
        assert (
            "credit" in output.lower() or "billing" in output.lower()
        ), "Terminal output must mention credits or billing for billing failures"

    async def test_auth_terminal_output_says_claude_platform(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """auth_error halt output instructs operator to verify API key (AC#2)."""
        exc = _make_agent_error_with_platform_classification("auth_error")
        controller = _make_halt_controller(tmp_path)
        monkeypatch.setattr("arcwright_ai.cli.halt.write_halt_report", AsyncMock(return_value=tmp_path / "s.md"))
        monkeypatch.setattr("arcwright_ai.cli.halt.update_run_status", AsyncMock())
        monkeypatch.setattr("arcwright_ai.cli.halt.append_entry", AsyncMock())

        await controller.handle_halt(
            story_id=StoryId("13-2-auth-test"),
            exception=exc,
            accumulated_budget=_make_budget(),
            completed_stories=[],
            last_completed=None,
        )

        output = capsys.readouterr().err
        assert "Claude platform" in output or "Claude Platform" in output
        assert "api key" in output.lower() or "ANTHROPIC_API_KEY" in output

    async def test_model_access_terminal_output_says_claude_platform(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """model_access_error halt output instructs operator to verify model entitlement (AC#2)."""
        exc = _make_agent_error_with_platform_classification("model_access_error")
        controller = _make_halt_controller(tmp_path)
        monkeypatch.setattr("arcwright_ai.cli.halt.write_halt_report", AsyncMock(return_value=tmp_path / "s.md"))
        monkeypatch.setattr("arcwright_ai.cli.halt.update_run_status", AsyncMock())
        monkeypatch.setattr("arcwright_ai.cli.halt.append_entry", AsyncMock())

        await controller.handle_halt(
            story_id=StoryId("13-2-model-test"),
            exception=exc,
            accumulated_budget=_make_budget(),
            completed_stories=[],
            last_completed=None,
        )

        output = capsys.readouterr().err
        assert "Claude platform" in output or "Claude Platform" in output
        assert "model" in output.lower()

    async def test_non_platform_agent_error_no_platform_guidance_in_terminal(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """Non-platform AgentError must not emit platform guidance in terminal output."""
        exc = AgentError("SDK crash", details={"error_category": "sdk"})
        controller = _make_halt_controller(tmp_path)
        monkeypatch.setattr("arcwright_ai.cli.halt.write_halt_report", AsyncMock(return_value=tmp_path / "s.md"))
        monkeypatch.setattr("arcwright_ai.cli.halt.update_run_status", AsyncMock())
        monkeypatch.setattr("arcwright_ai.cli.halt.append_entry", AsyncMock())

        await controller.handle_halt(
            story_id=StoryId("13-2-sdk-test"),
            exception=exc,
            accumulated_budget=_make_budget(),
            completed_stories=[],
            last_completed=None,
        )

        output = capsys.readouterr().err
        assert "Claude Platform" not in output


class TestPlatformGuidanceConsistency:
    """Platform guidance is consistent across terminal output, halt report, and summary (AC#3)."""

    async def test_billing_platform_guidance_in_halt_report_suggested_fix(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """billing_error suggested_fix passed to write_halt_report contains platform guidance (AC#3)."""
        exc = _make_agent_error_with_platform_classification("billing_error")
        controller = _make_halt_controller(tmp_path)

        captured: dict[str, object] = {}

        async def _mock_write(*args: object, **kwargs: object) -> Path:
            captured.update(kwargs)
            return tmp_path / "s.md"

        monkeypatch.setattr("arcwright_ai.cli.halt.write_halt_report", _mock_write)
        monkeypatch.setattr("arcwright_ai.cli.halt.update_run_status", AsyncMock())
        monkeypatch.setattr("arcwright_ai.cli.halt.append_entry", AsyncMock())

        await controller.handle_halt(
            story_id=StoryId("13-2-billing-test"),
            exception=exc,
            accumulated_budget=_make_budget(),
            completed_stories=[],
            last_completed=None,
        )

        fix = str(captured.get("suggested_fix", ""))
        assert (
            "Claude platform" in fix or "Claude Platform" in fix
        ), "Halt report suggested_fix must contain platform guidance"
        assert "credit" in fix.lower() or "billing" in fix.lower()

    async def test_auth_platform_guidance_in_halt_report_suggested_fix(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """auth_error suggested_fix passed to write_halt_report contains platform guidance (AC#3)."""
        exc = _make_agent_error_with_platform_classification("auth_error")
        controller = _make_halt_controller(tmp_path)

        captured: dict[str, object] = {}

        async def _mock_write(*args: object, **kwargs: object) -> Path:
            captured.update(kwargs)
            return tmp_path / "s.md"

        monkeypatch.setattr("arcwright_ai.cli.halt.write_halt_report", _mock_write)
        monkeypatch.setattr("arcwright_ai.cli.halt.update_run_status", AsyncMock())
        monkeypatch.setattr("arcwright_ai.cli.halt.append_entry", AsyncMock())

        await controller.handle_halt(
            story_id=StoryId("13-2-auth-test"),
            exception=exc,
            accumulated_budget=_make_budget(),
            completed_stories=[],
            last_completed=None,
        )

        fix = str(captured.get("suggested_fix", ""))
        assert "Claude platform" in fix or "Claude Platform" in fix
        assert "api key" in fix.lower() or "ANTHROPIC_API_KEY" in fix
