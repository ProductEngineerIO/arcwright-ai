"""Tests for CLI dispatch command — story/epic finder, run ID, JSONL handler, integration.

Uses typer.testing.CliRunner for command invocation.
All filesystem tests use tmp_path for full isolation.
"""

from __future__ import annotations

import json
import logging
import re
from decimal import Decimal
from typing import TYPE_CHECKING

import pytest
import typer
from typer.testing import CliRunner

from arcwright_ai.agent.invoker import InvocationResult
from arcwright_ai.cli.app import app
from arcwright_ai.cli.dispatch import (
    _find_epic_stories,
    _find_latest_run_for_epic,
    _find_story_file,
    _JsonlFileHandler,
)
from arcwright_ai.core.config import ApiConfig, RunConfig
from arcwright_ai.core.types import EpicId, StoryId
from arcwright_ai.output.run_manager import generate_run_id

if TYPE_CHECKING:
    from pathlib import Path

runner = CliRunner()

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_RUN_ID_PATTERN = re.compile(r"^\d{8}-\d{6}-[0-9a-f]{6}$")


def _make_test_project(tmp_path: Path, epic_num: str = "2", story_num: str = "1") -> Path:
    """Scaffold a minimal project with BMAD artifacts and one story.

    Returns:
        Path to the created story file.
    """
    planning = tmp_path / "_spec" / "planning-artifacts"
    planning.mkdir(parents=True)
    (planning / "prd.md").write_text("# PRD\n\n## FR1\nTest requirement", encoding="utf-8")
    (planning / "architecture.md").write_text("# Architecture\n\n### Decision 1\nTest decision", encoding="utf-8")

    impl = tmp_path / "_spec" / "implementation-artifacts"
    impl.mkdir(parents=True)
    story_file = impl / f"{epic_num}-{story_num}-story-slug.md"
    story_file.write_text(
        f"# Story {epic_num}.{story_num}\n\n## Dev Notes\n\nFR1, Decision 1\n",
        encoding="utf-8",
    )
    return story_file


# ---------------------------------------------------------------------------
# Task 7.1 — _find_story_file parses story spec formats
# ---------------------------------------------------------------------------


def test_dispatch_story_parses_dot_format(tmp_path: Path) -> None:
    """_find_story_file resolves '2.7' → epic_num=2, story_num=7."""
    impl = tmp_path / "_spec" / "implementation-artifacts"
    impl.mkdir(parents=True)
    story_file = impl / "2-7-agent-dispatch-node.md"
    story_file.write_text("# Story 2.7\n", encoding="utf-8")

    found_path, story_id, epic_id = _find_story_file("2.7", impl)
    assert found_path == story_file
    assert story_id == StoryId("2-7-agent-dispatch-node")
    assert epic_id == EpicId("epic-2")


def test_dispatch_story_parses_hyphen_format(tmp_path: Path) -> None:
    """_find_story_file resolves '2-7' → same result as '2.7'."""
    impl = tmp_path / "_spec" / "implementation-artifacts"
    impl.mkdir(parents=True)
    story_file = impl / "2-7-agent-dispatch-node.md"
    story_file.write_text("# Story 2.7\n", encoding="utf-8")

    found_path, story_id, epic_id = _find_story_file("2-7", impl)
    assert found_path == story_file
    assert story_id == StoryId("2-7-agent-dispatch-node")
    assert epic_id == EpicId("epic-2")


# ---------------------------------------------------------------------------
# Task 7.2 — _find_story_file raises on missing story
# ---------------------------------------------------------------------------


def test_dispatch_story_raises_on_missing_story(tmp_path: Path) -> None:
    """_find_story_file raises ProjectError when no matching file exists."""
    from arcwright_ai.core.exceptions import ProjectError

    impl = tmp_path / "_spec" / "implementation-artifacts"
    impl.mkdir(parents=True)

    with pytest.raises(ProjectError, match="No story file found"):
        _find_story_file("9.9", impl)


# ---------------------------------------------------------------------------
# Task 7.3 — _find_epic_stories returns sorted list
# ---------------------------------------------------------------------------


def test_find_epic_stories_returns_sorted_list(tmp_path: Path) -> None:
    """_find_epic_stories returns stories sorted by story number, no retrospectives."""
    impl = tmp_path / "_spec" / "implementation-artifacts"
    impl.mkdir(parents=True)
    (impl / "2-3-context-answerer.md").write_text("# Story 2.3\n", encoding="utf-8")
    (impl / "2-1-state-models.md").write_text("# Story 2.1\n", encoding="utf-8")
    (impl / "2-5-agent-invoker.md").write_text("# Story 2.5\n", encoding="utf-8")
    (impl / "epic-2-retrospective.md").write_text("# Retro\n", encoding="utf-8")

    stories = _find_epic_stories("2", impl)

    assert len(stories) == 3
    story_ids = [str(sid) for _, sid, _ in stories]
    assert story_ids == [
        "2-1-state-models",
        "2-3-context-answerer",
        "2-5-agent-invoker",
    ]


def test_find_epic_stories_accepts_epic_prefix_format(tmp_path: Path) -> None:
    """_find_epic_stories handles 'epic-2' as well as '2'."""
    impl = tmp_path / "_spec" / "implementation-artifacts"
    impl.mkdir(parents=True)
    (impl / "2-1-state-models.md").write_text("# Story 2.1\n", encoding="utf-8")

    stories_plain = _find_epic_stories("2", impl)
    stories_prefix = _find_epic_stories("epic-2", impl)

    assert [str(sid) for _, sid, _ in stories_plain] == [str(sid) for _, sid, _ in stories_prefix]


def test_find_epic_stories_raises_on_empty_epic(tmp_path: Path) -> None:
    """_find_epic_stories raises ProjectError when epic has no stories."""
    from arcwright_ai.core.exceptions import ProjectError

    impl = tmp_path / "_spec" / "implementation-artifacts"
    impl.mkdir(parents=True)

    with pytest.raises(ProjectError, match="No story files found"):
        _find_epic_stories("99", impl)


# ---------------------------------------------------------------------------
# Task 7.4 — _generate_run_id format
# ---------------------------------------------------------------------------


def test_generate_run_id_format() -> None:
    """generate_run_id returns YYYYMMDD-HHMMSS-<6hex> format."""
    run_id = generate_run_id()
    assert _RUN_ID_PATTERN.match(str(run_id)), f"Unexpected format: {run_id!r}"


def test_generate_run_id_is_unique() -> None:
    """Consecutive run IDs are different."""
    assert generate_run_id() != generate_run_id()


# ---------------------------------------------------------------------------
# Task 7.5 — _JsonlFileHandler writes correct JSON Lines format
# ---------------------------------------------------------------------------


def test_jsonl_handler_writes_correct_format(tmp_path: Path) -> None:
    """_JsonlFileHandler emits valid JSON Lines with D8 envelope fields."""
    log_file = tmp_path / "test.jsonl"
    handler = _JsonlFileHandler(log_file)
    handler.setLevel(logging.INFO)

    test_logger = logging.getLogger("arcwright_ai.test_jsonl")
    test_logger.addHandler(handler)
    test_logger.setLevel(logging.INFO)
    try:
        test_logger.info("test.event", extra={"data": {"key": "value"}})
    finally:
        test_logger.removeHandler(handler)
        handler.close()

    lines = log_file.read_text(encoding="utf-8").strip().split("\n")
    assert len(lines) == 1

    entry = json.loads(lines[0])
    assert entry["event"] == "test.event"
    assert entry["level"] == "info"
    assert entry["data"] == {"key": "value"}
    assert "ts" in entry


def test_jsonl_handler_handles_missing_data_field(tmp_path: Path) -> None:
    """_JsonlFileHandler writes empty dict for data when extra.data is absent."""
    log_file = tmp_path / "no_data.jsonl"
    handler = _JsonlFileHandler(log_file)
    handler.setLevel(logging.INFO)

    test_logger = logging.getLogger("arcwright_ai.test_no_data")
    test_logger.addHandler(handler)
    test_logger.setLevel(logging.INFO)
    try:
        test_logger.info("plain.event")
    finally:
        test_logger.removeHandler(handler)
        handler.close()

    entry = json.loads(log_file.read_text(encoding="utf-8").strip())
    assert entry["data"] == {}


# ---------------------------------------------------------------------------
# Task 7.6 — Integration test: full CLI → engine → agent pipeline
# ---------------------------------------------------------------------------


def test_dispatch_story_end_to_end_with_mock_sdk(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """CLI dispatch --story with MockSDK: exit 0, checkpoint written, JSONL events present."""
    # Set up project structure
    _make_test_project(tmp_path, epic_num="2", story_num="1")

    # Monkeypatch working directory so _discover_project_root finds the project
    monkeypatch.chdir(tmp_path)

    # Monkeypatch load_config to avoid real config file
    test_config = RunConfig(api=ApiConfig(claude_api_key="test-key-ci"))
    monkeypatch.setattr("arcwright_ai.cli.dispatch.load_config", lambda *args, **kwargs: test_config)

    # Monkeypatch invoke_agent in engine/nodes.py to avoid real SDK
    async def _mock_invoke(*args: object, **kwargs: object) -> InvocationResult:
        logging.getLogger("arcwright_ai").info(
            "agent.response",
            extra={
                "data": {
                    "tokens_input": 300,
                    "tokens_output": 150,
                    "cost_usd": "0.03",
                    "session_id": "integration-test-session",
                }
            },
        )
        return InvocationResult(
            output_text="Mock agent output for integration test",
            tokens_input=300,
            tokens_output=150,
            total_cost=Decimal("0.03"),
            duration_ms=500,
            session_id="integration-test-session",
            num_turns=2,
            is_error=False,
        )

    monkeypatch.setattr("arcwright_ai.engine.nodes.invoke_agent", _mock_invoke)

    result = runner.invoke(app, ["dispatch", "--story", "2.1"], catch_exceptions=False)

    # Verify exit code
    assert result.exit_code == 0, f"Unexpected exit code {result.exit_code}:\n{result.output}"

    # Verify agent output checkpoint written
    agent_outputs = list(tmp_path.glob(".arcwright-ai/runs/*/stories/*/agent-output.md"))
    assert len(agent_outputs) == 1, "Expected exactly one agent-output.md checkpoint"
    assert "Mock agent output for integration test" in agent_outputs[0].read_text(encoding="utf-8")

    # Verify JSONL log events written
    log_files = list(tmp_path.glob(".arcwright-ai/runs/*/log.jsonl"))
    assert len(log_files) == 1, "Expected exactly one log.jsonl"
    lines = [ln for ln in log_files[0].read_text(encoding="utf-8").strip().split("\n") if ln]
    entries = [json.loads(line) for line in lines]
    events_by_name = {entry["event"] for entry in entries}
    assert "run.start" in events_by_name
    assert "story.start" in events_by_name
    assert "context.resolve" in events_by_name
    assert "agent.dispatch" in events_by_name
    assert "agent.response" in events_by_name

    # Budget evidence from invocation response event
    response_entries = [entry for entry in entries if entry["event"] == "agent.response"]
    assert len(response_entries) >= 1
    response_data = response_entries[-1].get("data", {})
    assert int(response_data.get("tokens_input", 0)) > 0
    assert int(response_data.get("tokens_output", 0)) > 0


# ---------------------------------------------------------------------------
# Task 7.7 — Neither --story nor --epic provided → error
# ---------------------------------------------------------------------------


def test_dispatch_requires_story_or_epic_option() -> None:
    """dispatch without --story or --epic exits with code 1."""
    result = runner.invoke(app, ["dispatch"])
    assert result.exit_code == 1


# ---------------------------------------------------------------------------
# Task 7.8 — Both --story and --epic provided → error
# ---------------------------------------------------------------------------


def test_dispatch_rejects_both_story_and_epic() -> None:
    """dispatch with both --story and --epic exits with code 1."""
    result = runner.invoke(app, ["dispatch", "--story", "2.1", "--epic", "2"])
    assert result.exit_code == 1


# ---------------------------------------------------------------------------
# Shared helpers for epic dispatch tests
# ---------------------------------------------------------------------------


def _make_epic_project(
    tmp_path: Path,
    epic_num: str = "5",
    story_count: int = 3,
) -> list[Path]:
    """Scaffold a minimal project with N story files for epic dispatch tests.

    Returns:
        List of created story file paths in story-number order.
    """
    (tmp_path / "_spec" / "planning-artifacts").mkdir(parents=True, exist_ok=True)
    impl = tmp_path / "_spec" / "implementation-artifacts"
    impl.mkdir(parents=True, exist_ok=True)
    files: list[Path] = []
    for i in range(1, story_count + 1):
        f = impl / f"{epic_num}-{i}-story-slug-{i}.md"
        f.write_text(f"# Story {epic_num}.{i}\n")
        files.append(f)
    return files


def _make_story_result(
    status: str = "success",
    estimated_cost: str = "0.01",
    total_tokens: int = 100,
) -> object:
    """Return a StoryState-like mock with configurable status and budget.

    Returns:
        Mock object with .status (TaskState) and .budget (BudgetState).
    """
    from decimal import Decimal
    from unittest.mock import MagicMock

    from arcwright_ai.core.lifecycle import TaskState as TS
    from arcwright_ai.core.types import BudgetState

    result = MagicMock()
    result.status = TS(status)
    result.budget = BudgetState(
        invocation_count=1,
        total_tokens=total_tokens,
        estimated_cost=Decimal(estimated_cost),
        max_cost=Decimal("10.0"),
    )
    return result


async def _noop_write_halt_report(*a: object, **k: object) -> object:
    """No-op stub for write_halt_report used in epic dispatch tests."""
    from unittest.mock import MagicMock

    return MagicMock()


async def _noop_append_entry(*a: object, **k: object) -> None:
    """No-op stub for append_entry used in epic dispatch tests."""


def _patch_epic_deps(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    invoke_results: list[object],
    *,
    raise_confirm: bool = False,
) -> dict[str, list[object]]:
    """Wire all mocks needed for epic dispatch unit tests.

    Patches load_config, build_story_graph, create_run, update_run_status,
    update_story_status, generate_run_id, and optionally typer.confirm.

    Args:
        monkeypatch: pytest monkeypatch fixture.
        tmp_path: Temporary directory used as project root.
        invoke_results: Ordered list of mock results returned by graph.ainvoke.
        raise_confirm: When True, typer.confirm raises typer.Abort (user rejects).

    Returns:
        Dict with keys ``invoke_calls``, ``create_run_calls``,
        ``update_run_calls``, ``update_story_calls``, and ``call_order``.
    """
    from arcwright_ai.core.config import ApiConfig, RunConfig

    test_config = RunConfig(api=ApiConfig(claude_api_key="test-key"))
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr("arcwright_ai.cli.dispatch.load_config", lambda *a, **k: test_config)

    call_log: dict[str, list[object]] = {
        "invoke_calls": [],
        "create_run_calls": [],
        "update_run_calls": [],
        "update_story_calls": [],
        "call_order": [],
    }

    results_iter = iter(invoke_results)

    def _make_graph() -> object:
        from unittest.mock import MagicMock

        g = MagicMock()

        async def _ainvoke(state: object) -> object:
            call_log["invoke_calls"].append(state)
            call_log["call_order"].append("ainvoke")  # type: ignore[arg-type]
            return next(results_iter)

        g.ainvoke = _ainvoke
        return g

    monkeypatch.setattr("arcwright_ai.cli.dispatch.build_story_graph", _make_graph)

    async def _create_run(project_root: Path, run_id: object, config: object, story_slugs: list[str]) -> Path:
        call_log["create_run_calls"].append({"run_id": str(run_id), "story_slugs": story_slugs})
        call_log["call_order"].append("create_run")  # type: ignore[arg-type]
        run_dir = project_root / ".arcwright-ai" / "runs" / str(run_id)
        run_dir.mkdir(parents=True, exist_ok=True)
        return run_dir

    monkeypatch.setattr("arcwright_ai.cli.dispatch.create_run", _create_run)

    async def _update_run_status(
        project_root: Path,
        run_id: str,
        *,
        status: object = None,
        last_completed_story: object = None,
        budget: object = None,
    ) -> None:
        call_log["update_run_calls"].append({"status": str(status), "last_completed": last_completed_story})

    monkeypatch.setattr("arcwright_ai.cli.dispatch.update_run_status", _update_run_status)
    # Also patch halt.py callsite so halt-path update_run_status calls are captured.
    monkeypatch.setattr("arcwright_ai.cli.halt.update_run_status", _update_run_status)
    # Prevent halt.py's write_halt_report from failing (no run.yaml in test env).
    monkeypatch.setattr("arcwright_ai.cli.halt.write_halt_report", _noop_write_halt_report)
    # Prevent halt.py's append_entry from failing (no provenance dir in test env).
    monkeypatch.setattr("arcwright_ai.cli.halt.append_entry", _noop_append_entry)

    async def _update_story_status(
        project_root: Path,
        run_id: str,
        story_slug: str,
        *,
        status: str,
        started_at: str | None = None,
        completed_at: str | None = None,
        retry_count: int | None = None,
    ) -> None:
        call_log["update_story_calls"].append({"story_slug": story_slug, "status": status})

    monkeypatch.setattr("arcwright_ai.cli.dispatch.update_story_status", _update_story_status)

    # Suppress confirmation prompt unless testing the reject path
    if raise_confirm:

        def _raise_abort(*a: object, **k: object) -> None:
            raise typer.Abort()

        monkeypatch.setattr("arcwright_ai.cli.dispatch.typer.confirm", _raise_abort)
    else:
        monkeypatch.setattr("arcwright_ai.cli.dispatch.typer.confirm", lambda *a, **k: None)

    return call_log


# ---------------------------------------------------------------------------
# Task 8.1 — Story ordering: 3 stories dispatched in number order
# ---------------------------------------------------------------------------


def test_epic_dispatch_story_ordering(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """3 stories from epic 5 are dispatched sequentially in story-number order."""
    results = [_make_story_result("success") for _ in range(3)]
    _make_epic_project(tmp_path, epic_num="5", story_count=3)
    call_log = _patch_epic_deps(monkeypatch, tmp_path, results)

    result = runner.invoke(app, ["dispatch", "--epic", "5", "--yes"])

    assert result.exit_code == 0, f"Unexpected exit {result.exit_code}:\n{result.output}"
    assert len(call_log["invoke_calls"]) == 3
    story_ids = [str(s.story_id) for s in call_log["invoke_calls"]]  # type: ignore[attr-defined]
    assert story_ids == sorted(story_ids), "Stories were not dispatched in order"
    assert story_ids[0].startswith("5-1-")
    assert story_ids[1].startswith("5-2-")
    assert story_ids[2].startswith("5-3-")


# ---------------------------------------------------------------------------
# Task 8.2 — BudgetState carry-forward between stories
# ---------------------------------------------------------------------------


def test_epic_dispatch_budget_carry_forward(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Story 2's initial budget has the accumulated cost from story 1's terminal budget."""
    from decimal import Decimal

    from arcwright_ai.core.types import BudgetState

    story1_result = _make_story_result("success", estimated_cost="0.05", total_tokens=500)
    story2_result = _make_story_result("success", estimated_cost="0.10", total_tokens=1000)

    _make_epic_project(tmp_path, epic_num="5", story_count=2)
    call_log = _patch_epic_deps(monkeypatch, tmp_path, [story1_result, story2_result])

    result = runner.invoke(app, ["dispatch", "--epic", "5", "--yes"])

    assert result.exit_code == 0, f"Unexpected exit {result.exit_code}:\n{result.output}"
    assert len(call_log["invoke_calls"]) == 2

    story2_initial_budget: BudgetState = call_log["invoke_calls"][1].budget  # type: ignore[attr-defined]
    assert story2_initial_budget.estimated_cost >= Decimal("0.05"), (
        "Story 2's initial budget should carry story 1's accumulated cost"
    )


def test_epic_dispatch_initializes_project_state_with_queued_stories(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Epic dispatch builds ProjectState with queued stories before execution."""
    from arcwright_ai.engine.state import ProjectState as RealProjectState

    captured: dict[str, object] = {}

    def _spy_project_state(*args: object, **kwargs: object) -> RealProjectState:
        project_state = RealProjectState(*args, **kwargs)
        captured["project_state"] = project_state
        captured["initial_statuses"] = [str(story.status) for story in project_state.stories]
        return project_state

    monkeypatch.setattr("arcwright_ai.cli.dispatch.ProjectState", _spy_project_state)

    results = [_make_story_result("success") for _ in range(2)]
    _make_epic_project(tmp_path, epic_num="5", story_count=2)
    _patch_epic_deps(monkeypatch, tmp_path, results)

    result = runner.invoke(app, ["dispatch", "--epic", "5", "--yes"])

    assert result.exit_code == 0, f"Unexpected exit {result.exit_code}:\n{result.output}"
    project_state = captured.get("project_state")
    assert project_state is not None
    assert len(project_state.stories) == 2  # type: ignore[union-attr]
    initial_statuses = captured.get("initial_statuses")
    assert initial_statuses == ["queued", "queued"]


# ---------------------------------------------------------------------------
# Task 8.3 — Pre-dispatch confirmation shown; user accepts
# ---------------------------------------------------------------------------


def test_epic_dispatch_confirmation_accept(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Pre-dispatch confirmation is displayed and when accepted, dispatch proceeds."""
    confirm_called: list[bool] = []
    results = [_make_story_result("success")]
    _make_epic_project(tmp_path, epic_num="5", story_count=1)

    # Override confirm mock to track calls and accept
    call_log = _patch_epic_deps(monkeypatch, tmp_path, results)
    monkeypatch.setattr(
        "arcwright_ai.cli.dispatch.typer.confirm",
        lambda *a, **k: confirm_called.append(True),
    )

    result = runner.invoke(app, ["dispatch", "--epic", "5"])  # no --yes

    assert result.exit_code == 0, f"Unexpected exit {result.exit_code}:\n{result.output}"
    assert confirm_called, "typer.confirm should have been called without --yes"
    assert len(call_log["invoke_calls"]) == 1


# ---------------------------------------------------------------------------
# Task 8.3 (reject path) — Pre-dispatch confirmation: user rejects → exit 0
# ---------------------------------------------------------------------------


def test_epic_dispatch_confirmation_reject(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """When user rejects confirmation, dispatch exits 0 (cancelled, not error)."""
    results: list[object] = []
    _make_epic_project(tmp_path, epic_num="5", story_count=1)
    call_log = _patch_epic_deps(monkeypatch, tmp_path, results, raise_confirm=True)

    result = runner.invoke(app, ["dispatch", "--epic", "5"])  # no --yes

    assert result.exit_code == 0, f"Cancelled dispatch should exit 0, got {result.exit_code}"
    assert len(call_log["invoke_calls"]) == 0, "No stories should be dispatched after rejection"


# ---------------------------------------------------------------------------
# Task 8.4 — --yes flag skips typer.confirm
# ---------------------------------------------------------------------------


def test_epic_dispatch_yes_flag_skips_confirmation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """--yes flag bypasses typer.confirm entirely."""
    confirm_called: list[bool] = []
    results = [_make_story_result("success")]
    _make_epic_project(tmp_path, epic_num="5", story_count=1)

    _patch_epic_deps(monkeypatch, tmp_path, results)
    monkeypatch.setattr(
        "arcwright_ai.cli.dispatch.typer.confirm",
        lambda *a, **k: confirm_called.append(True),
    )

    result = runner.invoke(app, ["dispatch", "--epic", "5", "--yes"])

    assert result.exit_code == 0, f"Unexpected exit {result.exit_code}:\n{result.output}"
    assert not confirm_called, "typer.confirm must NOT be called when --yes is provided"


# ---------------------------------------------------------------------------
# Task 8.5 — create_run() called before any story execution
# ---------------------------------------------------------------------------


def test_epic_dispatch_create_run_called_before_stories(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """create_run() is invoked before the first graph.ainvoke() call."""
    results = [_make_story_result("success")]
    _make_epic_project(tmp_path, epic_num="5", story_count=1)
    call_log = _patch_epic_deps(monkeypatch, tmp_path, results)

    result = runner.invoke(app, ["dispatch", "--epic", "5", "--yes"])

    assert result.exit_code == 0, f"Unexpected exit {result.exit_code}:\n{result.output}"
    order = call_log["call_order"]
    assert "create_run" in order
    assert "ainvoke" in order
    assert order.index("create_run") < order.index("ainvoke"), "create_run must be called before the first ainvoke"


# ---------------------------------------------------------------------------
# Task 8.6 — Halt on failure: story 2 of 3 fails, story 3 not dispatched
# ---------------------------------------------------------------------------


def test_epic_dispatch_halt_on_story_failure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """When story 2 fails (ESCALATED), story 3 is not dispatched and run is HALTED."""
    results = [
        _make_story_result("success"),
        _make_story_result("escalated"),  # story 2 fails
    ]
    _make_epic_project(tmp_path, epic_num="5", story_count=3)
    call_log = _patch_epic_deps(monkeypatch, tmp_path, results)

    result = runner.invoke(app, ["dispatch", "--epic", "5", "--yes"])

    # Non-zero exit signals halt
    assert result.exit_code != 0, "Failed epic should exit non-zero"
    # Only 2 stories invoked (story 3 must NOT be dispatched)
    assert len(call_log["invoke_calls"]) == 2, "Story 3 must not be invoked after halt"
    # run_status updated to HALTED
    halt_updates = [u for u in call_log["update_run_calls"] if "halted" in str(u.get("status", "")).lower()]
    assert halt_updates, "update_run_status should be called with HALTED status"


# ---------------------------------------------------------------------------
# Task 8.7 — Exit code mapping for different error types
# ---------------------------------------------------------------------------


def test_epic_dispatch_exit_code_agent_error(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """AgentError during story execution → exit code 2."""
    from arcwright_ai.core.exceptions import AgentError

    _make_epic_project(tmp_path, epic_num="5", story_count=1)
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
    monkeypatch.setattr("arcwright_ai.cli.dispatch.typer.confirm", lambda *a, **k: None)

    def _make_failing_graph() -> object:
        from unittest.mock import MagicMock

        g = MagicMock()

        async def _ainvoke(state: object) -> object:
            raise AgentError("mock agent crash")

        g.ainvoke = _ainvoke
        return g

    monkeypatch.setattr("arcwright_ai.cli.dispatch.build_story_graph", _make_failing_graph)

    result = runner.invoke(app, ["dispatch", "--epic", "5", "--yes"])
    assert result.exit_code == 2, f"AgentError should map to exit code 2, got {result.exit_code}"


def test_epic_dispatch_exit_code_validation_failure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Terminal RETRY status maps to validation exit code 1."""
    results = [_make_story_result("retry")]
    _make_epic_project(tmp_path, epic_num="5", story_count=1)
    _patch_epic_deps(monkeypatch, tmp_path, results)

    result = runner.invoke(app, ["dispatch", "--epic", "5", "--yes"])
    assert result.exit_code == 1, f"Validation failure should map to exit code 1, got {result.exit_code}"


def test_epic_dispatch_exit_code_config_error(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """ConfigError during story execution → exit code 3."""
    from arcwright_ai.core.exceptions import ConfigError

    _make_epic_project(tmp_path, epic_num="5", story_count=1)
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
    monkeypatch.setattr("arcwright_ai.cli.dispatch.typer.confirm", lambda *a, **k: None)

    def _make_failing_graph() -> object:
        from unittest.mock import MagicMock

        g = MagicMock()

        async def _ainvoke(state: object) -> object:
            raise ConfigError("missing key")

        g.ainvoke = _ainvoke
        return g

    monkeypatch.setattr("arcwright_ai.cli.dispatch.build_story_graph", _make_failing_graph)

    result = runner.invoke(app, ["dispatch", "--epic", "5", "--yes"])
    assert result.exit_code == 3, f"ConfigError should map to exit code 3, got {result.exit_code}"


def test_epic_dispatch_exit_code_scm_error(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """ScmError during story execution → exit code 4."""
    from arcwright_ai.core.exceptions import ScmError

    _make_epic_project(tmp_path, epic_num="5", story_count=1)
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
    monkeypatch.setattr("arcwright_ai.cli.dispatch.typer.confirm", lambda *a, **k: None)

    def _make_failing_graph() -> object:
        from unittest.mock import MagicMock

        g = MagicMock()

        async def _ainvoke(state: object) -> object:
            raise ScmError("git push failed")

        g.ainvoke = _ainvoke
        return g

    monkeypatch.setattr("arcwright_ai.cli.dispatch.build_story_graph", _make_failing_graph)

    result = runner.invoke(app, ["dispatch", "--epic", "5", "--yes"])
    assert result.exit_code == 4, f"ScmError should map to exit code 4, got {result.exit_code}"


# ---------------------------------------------------------------------------
# Task 8.8 — run_manager calls are best-effort (dispatch continues on write error)
# ---------------------------------------------------------------------------


def test_epic_dispatch_run_manager_calls_are_best_effort(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """update_story_status raising does not halt epic dispatch."""
    results = [_make_story_result("success"), _make_story_result("success")]
    _make_epic_project(tmp_path, epic_num="5", story_count=2)
    test_config = RunConfig(api=ApiConfig(claude_api_key="test-key"))
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr("arcwright_ai.cli.dispatch.load_config", lambda *a, **k: test_config)

    results_iter = iter(results)
    invoke_count: list[int] = [0]

    def _make_graph() -> object:
        from unittest.mock import MagicMock

        g = MagicMock()

        async def _ainvoke(state: object) -> object:
            invoke_count[0] += 1
            return next(results_iter)

        g.ainvoke = _ainvoke
        return g

    monkeypatch.setattr("arcwright_ai.cli.dispatch.build_story_graph", _make_graph)

    async def _create_run(project_root: Path, run_id: object, config: object, story_slugs: list[str]) -> Path:
        run_dir = project_root / ".arcwright-ai" / "runs" / str(run_id)
        run_dir.mkdir(parents=True, exist_ok=True)
        return run_dir

    monkeypatch.setattr("arcwright_ai.cli.dispatch.create_run", _create_run)

    async def _always_fail_update_run(*a: object, **k: object) -> None:
        raise OSError("disk full")

    async def _always_fail_update_story(*a: object, **k: object) -> None:
        raise OSError("disk full")

    monkeypatch.setattr("arcwright_ai.cli.dispatch.update_run_status", _always_fail_update_run)
    monkeypatch.setattr("arcwright_ai.cli.dispatch.update_story_status", _always_fail_update_story)
    monkeypatch.setattr("arcwright_ai.cli.dispatch.typer.confirm", lambda *a, **k: None)

    result = runner.invoke(app, ["dispatch", "--epic", "5", "--yes"])

    assert result.exit_code == 0, f"run_manager write failures must NOT halt dispatch, got exit {result.exit_code}"
    assert invoke_count[0] == 2, "Both stories should be dispatched despite run_manager failures"


# ---------------------------------------------------------------------------
# Task 8.9 — dispatch_command accepts --yes flag without error
# ---------------------------------------------------------------------------


def test_dispatch_command_accepts_yes_flag(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """dispatch_command signature includes --yes / -y without CLI error."""
    results = [_make_story_result("success")]
    _make_epic_project(tmp_path, epic_num="5", story_count=1)
    _patch_epic_deps(monkeypatch, tmp_path, results)

    # --yes long form
    result_long = runner.invoke(app, ["dispatch", "--epic", "5", "--yes"])
    assert result_long.exit_code == 0, f"--yes flag rejected: {result_long.output}"

    # -y short form — need fresh results iterator
    results2 = [_make_story_result("success")]
    _make_epic_project(tmp_path, story_count=1)
    _patch_epic_deps(monkeypatch, tmp_path, results2)

    result_short = runner.invoke(app, ["dispatch", "--epic", "5", "-y"])
    assert result_short.exit_code == 0, f"-y flag rejected: {result_short.output}"


def test_epic_dispatch_uses_run_manager_generate_run_id(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Epic dispatch uses generate_run_id() from dispatch callsite."""
    from arcwright_ai.core.types import RunId

    fixed_run_id = RunId("20260305-120000-abc123")
    results = [_make_story_result("success")]
    _make_epic_project(tmp_path, epic_num="5", story_count=1)
    call_log = _patch_epic_deps(monkeypatch, tmp_path, results)
    monkeypatch.setattr("arcwright_ai.cli.dispatch.generate_run_id", lambda: fixed_run_id)

    result = runner.invoke(app, ["dispatch", "--epic", "5", "--yes"])

    assert result.exit_code == 0, f"Unexpected exit {result.exit_code}:\n{result.output}"
    assert call_log["create_run_calls"], "create_run should have been called"
    assert call_log["create_run_calls"][0]["run_id"] == str(fixed_run_id)


# ---------------------------------------------------------------------------
# Story 5.3 — Shared helpers for resume tests
# ---------------------------------------------------------------------------


def _build_run_status_halted(
    run_id: str,
    epic_num: str,
    total_count: int,
    completed_count: int,
    budget_dict: dict | None = None,
) -> tuple[object, object]:
    """Return (RunSummary, RunStatus) for a halted run with configurable stories.

    Args:
        run_id: Synthetic run identifier string.
        epic_num: Epic number string (e.g., "5").
        total_count: Total number of stories in the run.
        completed_count: Number of stories already succeeded.
        budget_dict: Optional budget dict to embed in RunStatus; defaults to a
            small accumulated budget with 2 invocations per completed story.

    Returns:
        Tuple of (RunSummary, RunStatus) suitable for use as mock return values.
    """
    from arcwright_ai.output.run_manager import (
        RunStatus,
        RunStatusValue,
        RunSummary,
        StoryStatusEntry,
    )

    stories: dict[str, StoryStatusEntry] = {}
    for i in range(1, total_count + 1):
        slug = f"{epic_num}-{i}-story-slug-{i}"
        if i <= completed_count:
            status_str = "success"
        elif i == completed_count + 1:
            status_str = "halted"
        else:
            status_str = "queued"
        stories[slug] = StoryStatusEntry(status=status_str)

    last_completed = f"{epic_num}-{completed_count}-story-slug-{completed_count}" if completed_count > 0 else None
    default_budget = {
        "invocation_count": completed_count * 2,
        "total_tokens": completed_count * 500,
        "estimated_cost": str(Decimal("0.05") * completed_count),
        "max_cost": "100.0",
    }
    run_summary = RunSummary(
        run_id=run_id,
        status=RunStatusValue.HALTED,
        start_time="2026-03-01T10:00:00+00:00",
        story_count=total_count,
        completed_count=completed_count,
    )
    run_status = RunStatus(
        run_id=run_id,
        status=RunStatusValue.HALTED,
        start_time="2026-03-01T10:00:00+00:00",
        config_snapshot={"model_version": "test"},
        budget=budget_dict or default_budget,
        stories=stories,
        last_completed_story=last_completed,
    )
    return run_summary, run_status


def _build_run_status_completed(
    run_id: str,
    epic_num: str,
    total_count: int,
) -> tuple[object, object]:
    """Return (RunSummary, RunStatus) for an already-completed run.

    Args:
        run_id: Synthetic run identifier string.
        epic_num: Epic number string (e.g., "5").
        total_count: Total number of stories in the run (all successful).

    Returns:
        Tuple of (RunSummary, RunStatus) with COMPLETED status.
    """
    from arcwright_ai.output.run_manager import (
        RunStatus,
        RunStatusValue,
        RunSummary,
        StoryStatusEntry,
    )

    stories = {f"{epic_num}-{i}-story-slug-{i}": StoryStatusEntry(status="success") for i in range(1, total_count + 1)}
    run_summary = RunSummary(
        run_id=run_id,
        status=RunStatusValue.COMPLETED,
        start_time="2026-03-01T10:00:00+00:00",
        story_count=total_count,
        completed_count=total_count,
    )
    run_status = RunStatus(
        run_id=run_id,
        status=RunStatusValue.COMPLETED,
        start_time="2026-03-01T10:00:00+00:00",
        config_snapshot={"model_version": "test"},
        budget={
            "invocation_count": total_count * 2,
            "total_tokens": 1000,
            "estimated_cost": "0.10",
            "max_cost": "100.0",
        },
        stories=stories,
        last_completed_story=f"{epic_num}-{total_count}-story-slug-{total_count}",
    )
    return run_summary, run_status


def _patch_resume_run_manager(
    monkeypatch: pytest.MonkeyPatch,
    run_summaries: list[object],
    run_status_map: dict[str, object],
) -> None:
    """Patch list_runs and get_run_status at the dispatch callsite.

    Args:
        monkeypatch: pytest monkeypatch fixture.
        run_summaries: List of RunSummary objects returned by list_runs.
        run_status_map: Dict mapping run_id → RunStatus returned by get_run_status.
    """

    async def _mock_list_runs(project_root: object) -> list[object]:
        return run_summaries

    async def _mock_get_run_status(project_root: object, run_id: str) -> object:
        from arcwright_ai.core.exceptions import RunError

        if run_id not in run_status_map:
            raise RunError(f"Mock: run {run_id} not found")
        return run_status_map[run_id]

    monkeypatch.setattr("arcwright_ai.cli.dispatch.list_runs", _mock_list_runs)
    monkeypatch.setattr("arcwright_ai.cli.dispatch.get_run_status", _mock_get_run_status)


# ---------------------------------------------------------------------------
# Task 7.1 — _find_latest_run_for_epic: multiple runs, returns most recent
# ---------------------------------------------------------------------------


async def test_find_latest_run_for_epic_returns_most_recent(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """_find_latest_run_for_epic returns most recent matching run (not older ones)."""
    run_summary_new, run_status_new = _build_run_status_halted("run-002", "5", 3, 1)
    run_summary_old, run_status_old = _build_run_status_halted("run-001", "5", 3, 0)

    _patch_resume_run_manager(
        monkeypatch,
        [run_summary_new, run_summary_old],  # most recent first (as list_runs returns)
        {"run-002": run_status_new, "run-001": run_status_old},
    )

    result = await _find_latest_run_for_epic(tmp_path, "5")

    assert result is not None, "Expected a matching run to be returned"
    run_id, _run_status = result
    assert run_id == "run-002", f"Expected most recent run 'run-002', got {run_id!r}"


# ---------------------------------------------------------------------------
# Task 7.2 — _find_latest_run_for_epic: no matching run → None
# ---------------------------------------------------------------------------


async def test_find_latest_run_for_epic_returns_none_when_no_match(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """_find_latest_run_for_epic returns None when no run exists for the epic."""
    # Run exists but contains stories for epic 3, not epic 5
    run_summary, run_status = _build_run_status_halted("run-003", "3", 2, 1)
    _patch_resume_run_manager(
        monkeypatch,
        [run_summary],
        {"run-003": run_status},
    )

    result = await _find_latest_run_for_epic(tmp_path, "5")

    assert result is None, "Expected None when no run matches epic 5"


# ---------------------------------------------------------------------------
# Task 7.3 — _find_latest_run_for_epic: filters by epic number
# ---------------------------------------------------------------------------


async def test_find_latest_run_for_epic_filters_by_epic_number(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """_find_latest_run_for_epic ignores runs for other epics."""
    # Two runs: one for epic 3, one for epic 5
    run_summary_epic3, run_status_epic3 = _build_run_status_halted("run-epic3", "3", 2, 1)
    run_summary_epic5, run_status_epic5 = _build_run_status_halted("run-epic5", "5", 3, 2)

    _patch_resume_run_manager(
        monkeypatch,
        [run_summary_epic5, run_summary_epic3],
        {"run-epic3": run_status_epic3, "run-epic5": run_status_epic5},
    )

    result = await _find_latest_run_for_epic(tmp_path, "5")

    assert result is not None
    run_id, _ = result
    assert run_id == "run-epic5", f"Expected run for epic 5, got {run_id!r}"

    result_other = await _find_latest_run_for_epic(tmp_path, "3")
    assert result_other is not None
    run_id_other, _ = result_other
    assert run_id_other == "run-epic3", f"Expected run for epic 3, got {run_id_other!r}"


# ---------------------------------------------------------------------------
# Task 7.4 — Resume: 5-story epic, halt at story 3, resume dispatches stories 3-5
# ---------------------------------------------------------------------------


def test_resume_skips_completed_stories_dispatches_remaining(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """5-story epic halted at story 3: resume skips stories 1-2, dispatches 3-5."""
    _make_epic_project(tmp_path, epic_num="5", story_count=5)

    # Original run: stories 1-2 success, 3 halted, 4-5 queued
    run_summary, run_status = _build_run_status_halted("run-original-001", "5", 5, 2)
    _patch_resume_run_manager(monkeypatch, [run_summary], {"run-original-001": run_status})

    # Resume will dispatch stories 3, 4, 5 → all succeed
    results = [_make_story_result("success") for _ in range(3)]
    call_log = _patch_epic_deps(monkeypatch, tmp_path, results)

    result = runner.invoke(app, ["dispatch", "--epic", "5", "--yes", "--resume"])

    assert result.exit_code == 0, f"Expected exit 0, got {result.exit_code}:\n{result.output}"
    # Only 3 stories invoked (not the already-completed 1 and 2)
    assert len(call_log["invoke_calls"]) == 3, f"Expected 3 story dispatches, got {len(call_log['invoke_calls'])}"
    dispatched_ids = [str(state.story_id) for state in call_log["invoke_calls"]]  # type: ignore[attr-defined]
    for sid in dispatched_ids:
        assert not sid.startswith("5-1-") and not sid.startswith("5-2-"), (
            f"Completed stories must be skipped; got {sid!r}"
        )
    assert dispatched_ids[0].startswith("5-3-"), f"First dispatched story should be 5-3, got {dispatched_ids[0]}"


# ---------------------------------------------------------------------------
# Task 7.5 — Resume: budget carry-forward from halted run
# ---------------------------------------------------------------------------


def test_resume_budget_carry_forward(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Resume initializes first story with the accumulated budget from the prior run."""
    _make_epic_project(tmp_path, epic_num="5", story_count=3)

    halted_budget = {
        "invocation_count": 4,
        "total_tokens": 2000,
        "estimated_cost": "0.15",
        "max_cost": "100.0",
    }
    run_summary, run_status = _build_run_status_halted("run-b-001", "5", 3, 1, budget_dict=halted_budget)
    _patch_resume_run_manager(monkeypatch, [run_summary], {"run-b-001": run_status})

    results = [_make_story_result("success") for _ in range(2)]
    call_log = _patch_epic_deps(monkeypatch, tmp_path, results)

    result = runner.invoke(app, ["dispatch", "--epic", "5", "--yes", "--resume"])

    assert result.exit_code == 0, f"Expected exit 0, got {result.exit_code}:\n{result.output}"
    assert len(call_log["invoke_calls"]) == 2, "Stories 2-3 should be dispatched"

    # First resumed story should carry the prior run's budget
    first_budget = call_log["invoke_calls"][0].budget  # type: ignore[attr-defined]
    assert first_budget.estimated_cost >= Decimal("0.15"), (
        f"Expected carried-forward cost >= 0.15, got {first_budget.estimated_cost}"
    )
    assert first_budget.invocation_count >= 4, (
        f"Expected carried-forward invocation_count >= 4, got {first_budget.invocation_count}"
    )


# ---------------------------------------------------------------------------
# Task 7.6 — Resume on already-completed run → exit 0 with informative message
# ---------------------------------------------------------------------------


def test_resume_already_completed_run_exit_0(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """--resume on an already-completed run outputs informative message and exits 0."""
    _make_epic_project(tmp_path, epic_num="5", story_count=3)

    run_summary, run_status = _build_run_status_completed("run-done-001", "5", 3)
    _patch_resume_run_manager(monkeypatch, [run_summary], {"run-done-001": run_status})

    call_log = _patch_epic_deps(monkeypatch, tmp_path, [])

    result = runner.invoke(app, ["dispatch", "--epic", "5", "--yes", "--resume"])

    assert result.exit_code == 0, f"Completed run resume should exit 0, got {result.exit_code}"
    assert "already completed" in result.output.lower() or "all stories passed" in result.output.lower(), (
        f"Expected informative message, got:\n{result.output}"
    )
    assert len(call_log["invoke_calls"]) == 0, "No stories should be dispatched on completed run"


# ---------------------------------------------------------------------------
# Task 7.7 — Resume with no prior run → exit 3 with error message
# ---------------------------------------------------------------------------


def test_resume_no_prior_run_exit_3(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """--resume with no prior run outputs an error and exits with EXIT_CONFIG (3)."""
    _make_epic_project(tmp_path, epic_num="5", story_count=3)

    # No matching run exists for epic 5
    _patch_resume_run_manager(monkeypatch, [], {})
    call_log = _patch_epic_deps(monkeypatch, tmp_path, [])

    result = runner.invoke(app, ["dispatch", "--epic", "5", "--yes", "--resume"])

    assert result.exit_code == 3, f"Expected exit code 3, got {result.exit_code}:\n{result.output}"
    assert "no previous run" in result.output.lower() or "without --resume" in result.output.lower(), (
        f"Expected error message, got:\n{result.output}"
    )
    assert len(call_log["invoke_calls"]) == 0, "No stories should be dispatched when no prior run"


def test_resume_non_halted_run_exit_3(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """--resume rejects prior runs that are not HALTED (unless already COMPLETED)."""
    from arcwright_ai.output.run_manager import RunStatusValue

    _make_epic_project(tmp_path, epic_num="5", story_count=3)

    run_summary, run_status = _build_run_status_halted("run-running-001", "5", 3, 1)
    run_summary = run_summary.model_copy(update={"status": RunStatusValue.RUNNING})
    run_status = run_status.model_copy(update={"status": RunStatusValue.RUNNING})
    _patch_resume_run_manager(monkeypatch, [run_summary], {"run-running-001": run_status})
    call_log = _patch_epic_deps(monkeypatch, tmp_path, [])

    result = runner.invoke(app, ["dispatch", "--epic", "5", "--yes", "--resume"])

    assert result.exit_code == 3, f"Expected exit code 3, got {result.exit_code}:\n{result.output}"
    assert "not halted" in result.output.lower(), f"Expected non-halted error message, got:\n{result.output}"
    assert len(call_log["invoke_calls"]) == 0, "No stories should be dispatched for non-halted prior run"


# ---------------------------------------------------------------------------
# Task 7.8 — --resume with --story → error exit code 1
# ---------------------------------------------------------------------------


def test_resume_with_story_flag_errors(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """--resume combined with --story exits 1 with a clear error message."""
    result = runner.invoke(app, ["dispatch", "--story", "5.1", "--resume"])

    assert result.exit_code == 1, f"Expected exit code 1, got {result.exit_code}:\n{result.output}"
    assert "--resume" in result.output and "--story" in result.output, (
        f"Expected error mentioning --resume and --story, got:\n{result.output}"
    )


# ---------------------------------------------------------------------------
# Task 7.9 — --resume with --yes skips confirmation
# ---------------------------------------------------------------------------


def test_resume_with_yes_skips_confirmation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """--resume --yes bypasses typer.confirm entirely."""
    _make_epic_project(tmp_path, epic_num="5", story_count=3)

    run_summary, run_status = _build_run_status_halted("run-c-001", "5", 3, 1)
    _patch_resume_run_manager(monkeypatch, [run_summary], {"run-c-001": run_status})

    confirm_called: list[bool] = []
    results = [_make_story_result("success") for _ in range(2)]
    _patch_epic_deps(monkeypatch, tmp_path, results)
    # Override confirm mock to track calls
    monkeypatch.setattr(
        "arcwright_ai.cli.dispatch.typer.confirm",
        lambda *a, **k: confirm_called.append(True),
    )

    result = runner.invoke(app, ["dispatch", "--epic", "5", "--yes", "--resume"])

    assert result.exit_code == 0, f"Unexpected exit {result.exit_code}:\n{result.output}"
    assert not confirm_called, "typer.confirm must NOT be called when --yes is provided"


# ---------------------------------------------------------------------------
# Task 7.10 — New run_id generated for resumed dispatch
# ---------------------------------------------------------------------------


def test_resume_generates_new_run_id(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Resumed dispatch creates a new run_id different from the original halted run."""
    from arcwright_ai.core.types import RunId

    original_run_id = "20260301-100000-aaa111"
    _make_epic_project(tmp_path, epic_num="5", story_count=3)

    run_summary, run_status = _build_run_status_halted(original_run_id, "5", 3, 1)
    _patch_resume_run_manager(monkeypatch, [run_summary], {original_run_id: run_status})

    new_run_id = RunId("20260306-120000-bbb222")
    results = [_make_story_result("success") for _ in range(2)]
    call_log = _patch_epic_deps(monkeypatch, tmp_path, results)
    monkeypatch.setattr("arcwright_ai.cli.dispatch.generate_run_id", lambda: new_run_id)

    result = runner.invoke(app, ["dispatch", "--epic", "5", "--yes", "--resume"])

    assert result.exit_code == 0, f"Unexpected exit {result.exit_code}:\n{result.output}"
    assert call_log["create_run_calls"], "create_run should have been called"
    created_run_id = call_log["create_run_calls"][0]["run_id"]
    assert created_run_id == str(new_run_id), f"Expected new run_id {str(new_run_id)!r}, got {created_run_id!r}"
    assert created_run_id != original_run_id, "Resumed dispatch must use a NEW run_id"


# ---------------------------------------------------------------------------
# Task 7.11 — HaltController initialized with new run_id for resume
# ---------------------------------------------------------------------------


def test_resume_halt_controller_uses_new_run_id(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """HaltController is instantiated with the NEW run_id, not the original halted run_id."""
    from arcwright_ai.core.types import RunId

    original_run_id = "20260301-100000-ccc333"
    new_run_id = RunId("20260306-120000-ddd444")

    _make_epic_project(tmp_path, epic_num="5", story_count=3)

    run_summary, run_status = _build_run_status_halted(original_run_id, "5", 3, 1)
    _patch_resume_run_manager(monkeypatch, [run_summary], {original_run_id: run_status})

    halt_controller_run_ids: list[str] = []

    # Spy on HaltController.__init__ to capture the run_id it receives
    import arcwright_ai.cli.dispatch as dispatch_module
    from arcwright_ai.cli.halt import HaltController as RealHaltController

    original_init = RealHaltController.__init__

    def _spy_init(
        self: object,
        *,
        project_root: object,
        run_id: str,
        epic_spec: object,
        previous_run_id: object = None,
    ) -> None:
        halt_controller_run_ids.append(run_id)
        original_init(
            self, project_root=project_root, run_id=run_id, epic_spec=epic_spec, previous_run_id=previous_run_id
        )  # type: ignore[arg-type]

    monkeypatch.setattr(dispatch_module.HaltController, "__init__", _spy_init)
    monkeypatch.setattr("arcwright_ai.cli.dispatch.generate_run_id", lambda: new_run_id)

    results = [_make_story_result("success") for _ in range(2)]
    _patch_epic_deps(monkeypatch, tmp_path, results)

    result = runner.invoke(app, ["dispatch", "--epic", "5", "--yes", "--resume"])

    assert result.exit_code == 0, f"Unexpected exit {result.exit_code}:\n{result.output}"
    assert halt_controller_run_ids, "HaltController must have been instantiated"
    used_run_id = halt_controller_run_ids[-1]
    assert used_run_id == str(new_run_id), (
        f"HaltController should use new run_id {str(new_run_id)!r}, got {used_run_id!r}"
    )
    assert used_run_id != original_run_id, "HaltController must NOT use the original halted run_id"


# ---------------------------------------------------------------------------
# Task 8.1-8.3 / AC#14 — previous_run_id threading through dispatch (Story 5.4)
# ---------------------------------------------------------------------------


def test_resume_success_calls_write_success_summary_with_previous_run_id(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """(8.1 / AC#14a) Resume dispatch success path → write_success_summary() called
    with previous_run_id matching the original halted run ID."""
    from arcwright_ai.core.types import RunId

    original_run_id = "20260301-100000-src111"
    new_run_id = RunId("20260306-120000-new222")

    _make_epic_project(tmp_path, epic_num="5", story_count=3)
    run_summary, run_status = _build_run_status_halted(original_run_id, "5", 3, 1)
    _patch_resume_run_manager(monkeypatch, [run_summary], {original_run_id: run_status})

    captured_write_summary: dict[str, object] = {}

    async def _mock_write_success_summary(
        project_root: object,
        run_id: str,
        *,
        previous_run_id: object = None,
    ) -> object:
        captured_write_summary["run_id"] = run_id
        captured_write_summary["previous_run_id"] = previous_run_id
        from unittest.mock import MagicMock

        return MagicMock()

    monkeypatch.setattr("arcwright_ai.cli.dispatch.write_success_summary", _mock_write_success_summary)
    monkeypatch.setattr("arcwright_ai.cli.dispatch.generate_run_id", lambda: new_run_id)

    results = [_make_story_result("success") for _ in range(2)]
    _patch_epic_deps(monkeypatch, tmp_path, results)

    result = runner.invoke(app, ["dispatch", "--epic", "5", "--yes", "--resume"])

    assert result.exit_code == 0, f"Unexpected exit {result.exit_code}:\n{result.output}"
    assert captured_write_summary.get("previous_run_id") == original_run_id, (
        f"write_success_summary should be called with previous_run_id={original_run_id!r}, "
        f"got {captured_write_summary.get('previous_run_id')!r}"
    )
    assert captured_write_summary.get("run_id") == str(new_run_id)


def test_resume_halt_halt_controller_receives_previous_run_id(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """(8.2 / AC#14b) Resume dispatch halt path → HaltController constructed with
    previous_run_id matching the original halted run ID."""
    from arcwright_ai.core.types import RunId

    original_run_id = "20260301-100000-src333"
    new_run_id = RunId("20260306-120000-new444")

    _make_epic_project(tmp_path, epic_num="5", story_count=3)
    run_summary, run_status = _build_run_status_halted(original_run_id, "5", 3, 1)
    _patch_resume_run_manager(monkeypatch, [run_summary], {original_run_id: run_status})

    import arcwright_ai.cli.dispatch as dispatch_module
    from arcwright_ai.cli.halt import HaltController as RealHaltController

    captured_controller_kwargs: dict[str, object] = {}
    original_init = RealHaltController.__init__

    def _spy_init(
        self: object,
        *,
        project_root: object,
        run_id: str,
        epic_spec: object,
        previous_run_id: object = None,
    ) -> None:
        captured_controller_kwargs["previous_run_id"] = previous_run_id
        captured_controller_kwargs["run_id"] = run_id
        original_init(
            self,
            project_root=project_root,
            run_id=run_id,
            epic_spec=epic_spec,
            previous_run_id=previous_run_id,
        )  # type: ignore[arg-type]

    monkeypatch.setattr(dispatch_module.HaltController, "__init__", _spy_init)
    monkeypatch.setattr("arcwright_ai.cli.dispatch.generate_run_id", lambda: new_run_id)

    # Second story fails → halt path
    results = [_make_story_result("success"), _make_story_result("escalated")]
    _patch_epic_deps(monkeypatch, tmp_path, results)
    monkeypatch.setattr("arcwright_ai.cli.dispatch.write_stop_report", lambda *a, **k: None, raising=False)

    runner.invoke(app, ["dispatch", "--epic", "5", "--yes", "--resume"])

    # May exit non-zero (halt) but HaltController must have been constructed
    assert captured_controller_kwargs.get("previous_run_id") == original_run_id, (
        f"HaltController should receive previous_run_id={original_run_id!r}, "
        f"got {captured_controller_kwargs.get('previous_run_id')!r}"
    )


def test_normal_dispatch_halt_controller_gets_none_previous_run_id(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """(8.3 / AC#14c) Non-resume dispatch path → HaltController gets previous_run_id=None."""
    _make_epic_project(tmp_path, epic_num="5", story_count=2)

    import arcwright_ai.cli.dispatch as dispatch_module
    from arcwright_ai.cli.halt import HaltController as RealHaltController

    captured_controller_kwargs: dict[str, object] = {"previous_run_id": "NOT_SET"}
    original_init = RealHaltController.__init__

    def _spy_init(
        self: object,
        *,
        project_root: object,
        run_id: str,
        epic_spec: object,
        previous_run_id: object = None,
    ) -> None:
        captured_controller_kwargs["previous_run_id"] = previous_run_id
        original_init(
            self,
            project_root=project_root,
            run_id=run_id,
            epic_spec=epic_spec,
            previous_run_id=previous_run_id,
        )  # type: ignore[arg-type]

    monkeypatch.setattr(dispatch_module.HaltController, "__init__", _spy_init)

    results = [_make_story_result("success"), _make_story_result("success")]
    _patch_epic_deps(monkeypatch, tmp_path, results)

    result = runner.invoke(app, ["dispatch", "--epic", "5", "--yes"])

    assert result.exit_code == 0, f"Unexpected exit {result.exit_code}:\n{result.output}"
    assert captured_controller_kwargs.get("previous_run_id") is None, (
        f"Non-resume dispatch: HaltController.previous_run_id should be None, "
        f"got {captured_controller_kwargs.get('previous_run_id')!r}"
    )
