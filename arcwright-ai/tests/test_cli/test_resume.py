"""Tests for CLI resume command — _find_latest_run_for_epic, resume integration.

Uses typer.testing.CliRunner for command invocation.
All filesystem tests use tmp_path for full isolation.
"""

from __future__ import annotations

from decimal import Decimal
from typing import TYPE_CHECKING

from typer.testing import CliRunner

from arcwright_ai.cli.app import app
from arcwright_ai.cli.resume import _find_latest_run_for_epic
from tests.test_cli.test_dispatch import (
    _make_epic_project,
    _make_story_result,
    _patch_epic_deps,
)

if TYPE_CHECKING:
    from pathlib import Path

    import pytest

runner = CliRunner()


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
    """Patch list_runs and get_run_status at the resume module callsite.

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

    monkeypatch.setattr("arcwright_ai.cli.resume.list_runs", _mock_list_runs)
    monkeypatch.setattr("arcwright_ai.cli.resume.get_run_status", _mock_get_run_status)


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
    # Override confirm mock to track calls (patching at source module where called)
    monkeypatch.setattr(
        "arcwright_ai.cli.resume.typer.confirm",
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
