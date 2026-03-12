"""Tests for the CLI status command — live and historical run visibility.

Uses typer.testing.CliRunner for command invocation.
All tests mock list_runs and get_run_status at callsite.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from typer.testing import CliRunner

from arcwright_ai.cli.app import app
from arcwright_ai.core.exceptions import RunError
from arcwright_ai.output.run_manager import RunStatus, RunStatusValue, RunSummary, StoryStatusEntry

if TYPE_CHECKING:
    from pathlib import Path

    import pytest

runner = CliRunner()


# ---------------------------------------------------------------------------
# Fixtures / helpers
# ---------------------------------------------------------------------------


def _make_run_summary(
    run_id: str = "20260306-143052-a1b2c3",
    status: RunStatusValue = RunStatusValue.COMPLETED,
    start_time: str = "2026-03-06T14:30:52+00:00",
    story_count: int = 2,
    completed_count: int = 2,
) -> RunSummary:
    """Build a synthetic RunSummary for testing."""
    return RunSummary(
        run_id=run_id,
        status=status,
        start_time=start_time,
        story_count=story_count,
        completed_count=completed_count,
    )


def _make_run_status(
    run_id: str = "20260306-143052-a1b2c3",
    status: RunStatusValue = RunStatusValue.COMPLETED,
    start_time: str = "2026-03-06T14:30:52+00:00",
    stories: dict[str, StoryStatusEntry] | None = None,
    budget: dict | None = None,
) -> RunStatus:
    """Build a synthetic RunStatus for testing."""
    if stories is None:
        stories = {
            "setup-scaffold": StoryStatusEntry(
                status="success",
                retry_count=0,
                started_at="2026-03-06T14:30:55+00:00",
                completed_at="2026-03-06T15:00:00+00:00",
            ),
            "core-types": StoryStatusEntry(
                status="success",
                retry_count=0,
                started_at="2026-03-06T15:00:05+00:00",
                completed_at="2026-03-06T15:30:00+00:00",
            ),
        }
    if budget is None:
        budget = {
            "invocation_count": 12,
            "total_tokens": 145230,
            "estimated_cost": "3.42",
            "max_cost": "10.0",
        }
    return RunStatus(
        run_id=run_id,
        status=status,
        start_time=start_time,
        config_snapshot={},
        budget=budget,
        stories=stories,
        last_completed_story=None,
    )


def _make_async_return(value):  # type: ignore[no-untyped-def]
    """Create an async function that returns the given value."""

    async def _inner(*args, **kwargs):  # type: ignore[no-untyped-def]
        return value

    return _inner


def _make_async_raise(exc):  # type: ignore[no-untyped-def]
    """Create an async function that raises the given exception."""

    async def _inner(*args, **kwargs):  # type: ignore[no-untyped-def]
        raise exc

    return _inner


# ---------------------------------------------------------------------------
# AC #3 — no runs exist → "No runs found" message, exit 0
# ---------------------------------------------------------------------------


def test_status_no_runs_displays_no_runs_message(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    """When no runs exist, status displays "No runs found" and exits 0."""
    monkeypatch.setattr("arcwright_ai.cli.status.list_runs", _make_async_return([]))

    result = runner.invoke(app, ["status", "--path", str(tmp_path)])

    assert result.exit_code == 0
    assert "No runs found" in result.stderr
    assert "arcwright-ai dispatch" in result.stderr


# ---------------------------------------------------------------------------
# AC #1 — no run-id, latest run shown
# ---------------------------------------------------------------------------


def test_status_no_run_id_shows_latest_run(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    """With no run-id, status shows latest run info from list_runs()[0]."""
    summary = _make_run_summary()
    run_status = _make_run_status()

    monkeypatch.setattr("arcwright_ai.cli.status.list_runs", _make_async_return([summary]))
    monkeypatch.setattr("arcwright_ai.cli.status.get_run_status", _make_async_return(run_status))

    result = runner.invoke(app, ["status", "--path", str(tmp_path)])

    assert result.exit_code == 0
    assert "20260306-143052-a1b2c3" in result.stderr
    assert "completed" in result.stderr


# ---------------------------------------------------------------------------
# AC #2 — specific run-id shows that run
# ---------------------------------------------------------------------------


def test_status_with_run_id_shows_specific_run(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    """With a valid run-id argument, status shows that specific run."""
    run_id = "20260306-143052-a1b2c3"
    run_status = _make_run_status(run_id=run_id)

    monkeypatch.setattr("arcwright_ai.cli.status.get_run_status", _make_async_return(run_status))

    result = runner.invoke(app, ["status", run_id, "--path", str(tmp_path)])

    assert result.exit_code == 0
    assert run_id in result.stderr


# ---------------------------------------------------------------------------
# AC #2 — invalid run-id → "Run not found" error, exit 1
# ---------------------------------------------------------------------------


def test_status_invalid_run_id_exits_1(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    """With an invalid run-id, status shows error and exits with code 1."""
    monkeypatch.setattr(
        "arcwright_ai.cli.status.get_run_status",
        _make_async_raise(RunError("Run not found: bad-id", details={})),
    )

    result = runner.invoke(app, ["status", "bad-id", "--path", str(tmp_path)])

    assert result.exit_code == 1
    assert "Run not found: bad-id" in result.stderr
    assert "arcwright-ai status" in result.stderr


# ---------------------------------------------------------------------------
# AC #5 — story breakdown: completed / pending / failed
# ---------------------------------------------------------------------------


def test_status_story_breakdown_categorization(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Status command correctly categorizes stories into completed/failed/pending."""
    stories = {
        "setup-scaffold": StoryStatusEntry(status="success"),
        "core-types": StoryStatusEntry(status="done"),
        "agent-invoker": StoryStatusEntry(status="failed"),
        "validation-pipeline": StoryStatusEntry(status="queued"),
        "escalated-story": StoryStatusEntry(status="escalated"),
    }
    run_status = _make_run_status(stories=stories)
    summary = _make_run_summary()

    monkeypatch.setattr("arcwright_ai.cli.status.list_runs", _make_async_return([summary]))
    monkeypatch.setattr("arcwright_ai.cli.status.get_run_status", _make_async_return(run_status))

    result = runner.invoke(app, ["status", "--path", str(tmp_path)])

    assert result.exit_code == 0
    assert "2 completed" in result.stderr
    assert "setup-scaffold" in result.stderr
    assert "core-types" in result.stderr
    assert "2 failed" in result.stderr
    assert "agent-invoker" in result.stderr
    assert "escalated-story" in result.stderr
    assert "1 pending" in result.stderr
    assert "validation-pipeline" in result.stderr


# ---------------------------------------------------------------------------
# AC #5 — budget/cost display
# ---------------------------------------------------------------------------


def test_status_budget_cost_display(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Status command displays budget/cost fields with proper formatting from run.yaml."""
    budget = {
        "invocation_count": 12,
        "total_tokens": 145230,
        "estimated_cost": "3.42",
        "max_cost": "10.0",
    }
    run_status = _make_run_status(budget=budget)
    summary = _make_run_summary()

    monkeypatch.setattr("arcwright_ai.cli.status.list_runs", _make_async_return([summary]))
    monkeypatch.setattr("arcwright_ai.cli.status.get_run_status", _make_async_return(run_status))

    result = runner.invoke(app, ["status", "--path", str(tmp_path)])

    assert result.exit_code == 0
    assert "12" in result.stderr
    assert "145,230" in result.stderr
    assert "$3.42" in result.stderr


# ---------------------------------------------------------------------------
# AC #5 — budget zero values display N/A
# ---------------------------------------------------------------------------


def test_status_budget_zero_values_display_formatted(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Status command shows $0.00 and 0 for zero budget values (not N/A)."""
    budget = {
        "invocation_count": 0,
        "total_tokens": 0,
        "estimated_cost": "0",
        "max_cost": "10.0",
    }
    run_status = _make_run_status(budget=budget)
    summary = _make_run_summary()

    monkeypatch.setattr("arcwright_ai.cli.status.list_runs", _make_async_return([summary]))
    monkeypatch.setattr("arcwright_ai.cli.status.get_run_status", _make_async_return(run_status))

    result = runner.invoke(app, ["status", "--path", str(tmp_path)])

    assert result.exit_code == 0
    assert "$0.00" in result.stderr


def test_status_budget_remaining_unlimited_when_max_invocations_zero(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Status shows 'unlimited' remaining when invocation ceiling is configured as unlimited."""
    budget = {
        "invocation_count": 12,
        "total_tokens": 145230,
        "estimated_cost": "3.42",
        "max_cost": "10.0",
        "max_invocations": 0,
    }
    run_status = _make_run_status(budget=budget)
    summary = _make_run_summary()

    monkeypatch.setattr("arcwright_ai.cli.status.list_runs", _make_async_return([summary]))
    monkeypatch.setattr("arcwright_ai.cli.status.get_run_status", _make_async_return(run_status))

    result = runner.invoke(app, ["status", "--path", str(tmp_path)])

    assert result.exit_code == 0
    assert "Remaining:" in result.stderr
    assert "unlimited" in result.stderr


# ---------------------------------------------------------------------------
# AC #4 — running run shows status "running"
# ---------------------------------------------------------------------------


def test_status_running_run_shows_running_status(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    """For a run currently in-progress, status shows 'running'."""
    stories = {
        "setup-scaffold": StoryStatusEntry(status="success"),
        "core-types": StoryStatusEntry(status="running"),
    }
    run_status = _make_run_status(status=RunStatusValue.RUNNING, stories=stories)
    summary = _make_run_summary(status=RunStatusValue.RUNNING)

    monkeypatch.setattr("arcwright_ai.cli.status.list_runs", _make_async_return([summary]))
    monkeypatch.setattr("arcwright_ai.cli.status.get_run_status", _make_async_return(run_status))

    result = runner.invoke(app, ["status", "--path", str(tmp_path)])

    assert result.exit_code == 0
    assert "running" in result.stderr


# ---------------------------------------------------------------------------
# AC #1 — halted run shows status "halted"
# ---------------------------------------------------------------------------


def test_status_halted_run_shows_halted_status(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    """For a halted run, status shows 'halted'."""
    stories = {
        "setup-scaffold": StoryStatusEntry(status="success"),
        "core-types": StoryStatusEntry(status="halted"),
    }
    run_status = _make_run_status(status=RunStatusValue.HALTED, stories=stories)
    summary = _make_run_summary(status=RunStatusValue.HALTED)

    monkeypatch.setattr("arcwright_ai.cli.status.list_runs", _make_async_return([summary]))
    monkeypatch.setattr("arcwright_ai.cli.status.get_run_status", _make_async_return(run_status))

    result = runner.invoke(app, ["status", "--path", str(tmp_path)])

    assert result.exit_code == 0
    assert "halted" in result.stderr


# ---------------------------------------------------------------------------
# AC #1 — timed-out run shows status "timed_out"
# ---------------------------------------------------------------------------


def test_status_timed_out_run_shows_timed_out_status(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    """For a timed-out run, status shows 'timed_out'."""
    stories = {
        "setup-scaffold": StoryStatusEntry(status="success", completed_at="2026-03-06T15:00:00+00:00"),
        "core-types": StoryStatusEntry(status="timed_out", completed_at="2026-03-06T15:30:00+00:00"),
    }
    run_status = _make_run_status(status=RunStatusValue.TIMED_OUT, stories=stories)
    summary = _make_run_summary(status=RunStatusValue.TIMED_OUT)

    monkeypatch.setattr("arcwright_ai.cli.status.list_runs", _make_async_return([summary]))
    monkeypatch.setattr("arcwright_ai.cli.status.get_run_status", _make_async_return(run_status))

    result = runner.invoke(app, ["status", "--path", str(tmp_path)])

    assert result.exit_code == 0
    assert "timed_out" in result.stderr


# ---------------------------------------------------------------------------
# AC #5 — all output goes to stderr (err=True)
# ---------------------------------------------------------------------------


def test_status_all_output_goes_to_stderr(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """All _status_async echo calls pass err=True (output to stderr)."""
    import asyncio

    import arcwright_ai.cli.status as _status_mod

    summary = _make_run_summary()
    run_status = _make_run_status()

    monkeypatch.setattr("arcwright_ai.cli.status.list_runs", _make_async_return([summary]))
    monkeypatch.setattr("arcwright_ai.cli.status.get_run_status", _make_async_return(run_status))

    echo_calls: list[dict] = []

    def mock_echo(message: object = "", *, err: bool = False, nl: bool = True, **kwargs: object) -> None:
        """Capture typer.echo calls without writing to terminal."""
        echo_calls.append({"message": message, "err": err})

    monkeypatch.setattr("arcwright_ai.cli.status.typer.echo", mock_echo)

    asyncio.run(_status_mod._status_async(tmp_path, None))

    assert len(echo_calls) > 0
    non_stderr = [c for c in echo_calls if c["err"] is not True]
    assert non_stderr == [], f"Some echo calls had err != True: {non_stderr}"


# ---------------------------------------------------------------------------
# AC #5 — no-runs message goes to stderr
# ---------------------------------------------------------------------------


def test_status_no_runs_output_goes_to_stderr(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """No-runs message is emitted with err=True (to stderr)."""
    import asyncio
    import contextlib

    import typer as _typer

    import arcwright_ai.cli.status as _status_mod

    monkeypatch.setattr("arcwright_ai.cli.status.list_runs", _make_async_return([]))

    echo_calls: list[dict] = []

    def mock_echo(message: object = "", *, err: bool = False, nl: bool = True, **kwargs: object) -> None:
        """Capture typer.echo calls."""
        echo_calls.append({"message": message, "err": err})

    monkeypatch.setattr("arcwright_ai.cli.status.typer.echo", mock_echo)

    with contextlib.suppress(_typer.Exit):
        asyncio.run(_status_mod._status_async(tmp_path, None))

    assert any("No runs found" in str(c["message"]) for c in echo_calls)
    assert all(c["err"] is True for c in echo_calls), f"Some echo calls had err != True: {echo_calls}"


# ---------------------------------------------------------------------------
# AC #6 — status command appears in --help
# ---------------------------------------------------------------------------


def test_status_command_appears_in_help() -> None:
    """The status command appears in arcwright-ai --help output."""
    result = runner.invoke(app, ["--help"])
    assert "status" in result.output


# ---------------------------------------------------------------------------
# AC #1 — per-story breakdown table displayed when per_story is non-empty
# ---------------------------------------------------------------------------


def test_status_per_story_breakdown_displayed(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Per-story cost table appears when budget has per_story data."""
    budget = {
        "invocation_count": 4,
        "total_tokens": 12350,
        "estimated_cost": "1.17",
        "max_cost": "10.0",
        "per_story": {
            "7-1-budgetstate": {
                "tokens_input": 2100,
                "tokens_output": 2100,
                "cost": "0.39",
                "invocations": 1,
            },
            "7-2-budget-check": {
                "tokens_input": 4125,
                "tokens_output": 4025,
                "cost": "0.78",
                "invocations": 3,
            },
        },
    }
    run_status = _make_run_status(budget=budget)
    summary = _make_run_summary()

    monkeypatch.setattr("arcwright_ai.cli.status.list_runs", _make_async_return([summary]))
    monkeypatch.setattr("arcwright_ai.cli.status.get_run_status", _make_async_return(run_status))

    result = runner.invoke(app, ["status", "--path", str(tmp_path)])

    assert result.exit_code == 0
    assert "Per-Story Breakdown:" in result.stderr
    assert "7-1-budgetstate" in result.stderr
    assert "$0.39" in result.stderr
    assert "$0.78" in result.stderr


# ---------------------------------------------------------------------------
# AC #1 — per-story table hidden when per_story is empty or missing
# ---------------------------------------------------------------------------


def test_status_per_story_empty_no_table(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Per-story breakdown section is absent when budget has empty per_story."""
    budget = {
        "invocation_count": 0,
        "total_tokens": 0,
        "estimated_cost": "0",
        "max_cost": "10.0",
        "per_story": {},
    }
    run_status = _make_run_status(budget=budget)
    summary = _make_run_summary()

    monkeypatch.setattr("arcwright_ai.cli.status.list_runs", _make_async_return([summary]))
    monkeypatch.setattr("arcwright_ai.cli.status.get_run_status", _make_async_return(run_status))

    result = runner.invoke(app, ["status", "--path", str(tmp_path)])

    assert result.exit_code == 0
    assert "Per-Story Breakdown:" not in result.stderr
