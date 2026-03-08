"""Unit tests for arcwright_ai.cli.clean — Worktree cleanup command.

Tests cover:
    - Default mode: only merged worktrees and branches are removed.
    - --all mode: all worktrees and branches are force-removed.
    - Idempotency (AC #4): second call is a no-op when state is already clean.
    - Partial failure (AC #12): best-effort continues on individual errors.
    - Output formatting (AC #5): correct count strings and "Nothing to clean".
    - Exit code on ScmError (AC boundary): exits with code 4 (EXIT_SCM).
    - Structured log events: clean.default and clean.all emitted with counts.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING
from unittest.mock import AsyncMock

import pytest
from typer.testing import CliRunner

from arcwright_ai.cli.app import app
from arcwright_ai.cli.clean import _clean_all, _clean_default, _list_merged_branches
from arcwright_ai.core.exceptions import ScmError, WorktreeError
from arcwright_ai.scm.git import GitResult

if TYPE_CHECKING:
    from pathlib import Path

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _ok(stdout: str = "") -> GitResult:
    """Return a successful GitResult."""
    return GitResult(stdout=stdout, stderr="", returncode=0)


runner = CliRunner()


# ---------------------------------------------------------------------------
# Task 6.1 — test_clean_default_removes_merged_worktrees_and_branches
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_clean_default_removes_merged_worktrees_and_branches(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """Default mode removes matched worktree and calls delete_branch(force=False)."""
    mock_git = AsyncMock(return_value=_ok("  arcwright/story-a"))
    mock_list_worktrees = AsyncMock(return_value=["story-a"])
    mock_remove_worktree = AsyncMock(return_value=None)
    mock_list_branches = AsyncMock(return_value=["arcwright/story-a"])
    mock_delete_branch = AsyncMock(return_value=None)

    monkeypatch.setattr("arcwright_ai.cli.clean.git", mock_git)
    monkeypatch.setattr("arcwright_ai.cli.clean.list_worktrees", mock_list_worktrees)
    monkeypatch.setattr("arcwright_ai.cli.clean.remove_worktree", mock_remove_worktree)
    monkeypatch.setattr("arcwright_ai.cli.clean.list_branches", mock_list_branches)
    monkeypatch.setattr("arcwright_ai.cli.clean.delete_branch", mock_delete_branch)

    worktrees, branches = await _clean_default(tmp_path)

    assert worktrees == 1
    assert branches == 1
    mock_remove_worktree.assert_awaited_once_with("story-a", project_root=tmp_path)
    mock_delete_branch.assert_awaited_once_with("arcwright/story-a", project_root=tmp_path, force=False)


# ---------------------------------------------------------------------------
# Task 6.2 — test_clean_default_skips_unmerged_worktrees
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_clean_default_skips_unmerged_worktrees(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """Default mode skips worktrees whose branches are NOT merged into HEAD."""
    mock_git = AsyncMock(return_value=_ok(""))  # no merged arcwright branches
    mock_list_worktrees = AsyncMock(return_value=["story-a"])
    mock_remove_worktree = AsyncMock(return_value=None)
    mock_list_branches = AsyncMock(return_value=["arcwright/story-a"])
    mock_delete_branch = AsyncMock(return_value=None)

    monkeypatch.setattr("arcwright_ai.cli.clean.git", mock_git)
    monkeypatch.setattr("arcwright_ai.cli.clean.list_worktrees", mock_list_worktrees)
    monkeypatch.setattr("arcwright_ai.cli.clean.remove_worktree", mock_remove_worktree)
    monkeypatch.setattr("arcwright_ai.cli.clean.list_branches", mock_list_branches)
    monkeypatch.setattr("arcwright_ai.cli.clean.delete_branch", mock_delete_branch)

    worktrees, branches = await _clean_default(tmp_path)

    assert worktrees == 0
    assert branches == 0
    mock_remove_worktree.assert_not_awaited()
    mock_delete_branch.assert_not_awaited()


# ---------------------------------------------------------------------------
# Task 6.3 — test_clean_default_cleans_orphaned_merged_branches
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_clean_default_cleans_orphaned_merged_branches(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """Default mode deletes merged branches even when no worktree exists."""
    mock_git = AsyncMock(return_value=_ok("  arcwright/story-a"))
    mock_list_worktrees = AsyncMock(return_value=[])  # no active worktrees
    mock_remove_worktree = AsyncMock(return_value=None)
    mock_list_branches = AsyncMock(return_value=["arcwright/story-a"])
    mock_delete_branch = AsyncMock(return_value=None)

    monkeypatch.setattr("arcwright_ai.cli.clean.git", mock_git)
    monkeypatch.setattr("arcwright_ai.cli.clean.list_worktrees", mock_list_worktrees)
    monkeypatch.setattr("arcwright_ai.cli.clean.remove_worktree", mock_remove_worktree)
    monkeypatch.setattr("arcwright_ai.cli.clean.list_branches", mock_list_branches)
    monkeypatch.setattr("arcwright_ai.cli.clean.delete_branch", mock_delete_branch)

    worktrees, branches = await _clean_default(tmp_path)

    assert worktrees == 0
    assert branches == 1
    mock_remove_worktree.assert_not_awaited()
    mock_delete_branch.assert_awaited_once_with("arcwright/story-a", project_root=tmp_path, force=False)


# ---------------------------------------------------------------------------
# Task 6.4 — test_clean_all_removes_all_worktrees_and_branches
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_clean_all_removes_all_worktrees_and_branches(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """--all mode removes every worktree and force-deletes every branch."""
    mock_list_worktrees = AsyncMock(return_value=["story-a", "story-b"])
    mock_remove_worktree = AsyncMock(return_value=None)
    mock_list_branches = AsyncMock(return_value=["arcwright/story-a", "arcwright/story-b"])
    mock_delete_branch = AsyncMock(return_value=None)

    monkeypatch.setattr("arcwright_ai.cli.clean.list_worktrees", mock_list_worktrees)
    monkeypatch.setattr("arcwright_ai.cli.clean.remove_worktree", mock_remove_worktree)
    monkeypatch.setattr("arcwright_ai.cli.clean.list_branches", mock_list_branches)
    monkeypatch.setattr("arcwright_ai.cli.clean.delete_branch", mock_delete_branch)

    worktrees, branches = await _clean_all(tmp_path)

    assert worktrees == 2
    assert branches == 2
    assert mock_remove_worktree.await_count == 2
    mock_delete_branch.assert_any_await("arcwright/story-a", project_root=tmp_path, force=True)
    mock_delete_branch.assert_any_await("arcwright/story-b", project_root=tmp_path, force=True)


# ---------------------------------------------------------------------------
# Task 6.5 — test_clean_nothing_to_clean (via CLI CliRunner)
# ---------------------------------------------------------------------------


def test_clean_nothing_to_clean(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """CLI outputs 'Nothing to clean' when no worktrees or branches exist."""
    from arcwright_ai.cli import clean as clean_mod

    mock_list_worktrees = AsyncMock(return_value=[])
    mock_list_branches = AsyncMock(return_value=[])
    mock_git = AsyncMock(return_value=_ok(""))

    monkeypatch.setattr(clean_mod, "list_worktrees", mock_list_worktrees)
    monkeypatch.setattr(clean_mod, "list_branches", mock_list_branches)
    monkeypatch.setattr(clean_mod, "git", mock_git)

    result = runner.invoke(app, ["clean", "--project-root", str(tmp_path)])

    assert result.exit_code == 0
    assert "Nothing to clean" in result.output


# ---------------------------------------------------------------------------
# Task 6.6 — test_clean_idempotent_second_run_is_noop
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_clean_idempotent_second_run_is_noop(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """Second call to _clean_default when state is already clean returns (0, 0)."""
    mock_git = AsyncMock(return_value=_ok(""))
    mock_list_worktrees = AsyncMock(return_value=[])
    mock_list_branches = AsyncMock(return_value=[])

    monkeypatch.setattr("arcwright_ai.cli.clean.git", mock_git)
    monkeypatch.setattr("arcwright_ai.cli.clean.list_worktrees", mock_list_worktrees)
    monkeypatch.setattr("arcwright_ai.cli.clean.list_branches", mock_list_branches)

    worktrees1, branches1 = await _clean_default(tmp_path)
    worktrees2, branches2 = await _clean_default(tmp_path)

    assert worktrees1 == 0 and branches1 == 0
    assert worktrees2 == 0 and branches2 == 0


# ---------------------------------------------------------------------------
# Task 6.7 — test_clean_partial_failure_continues
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_clean_partial_failure_continues(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """A WorktreeError on one slug does not prevent removal of subsequent slugs."""
    mock_git = AsyncMock(return_value=_ok("  arcwright/story-a\n  arcwright/story-b"))
    mock_list_worktrees = AsyncMock(return_value=["story-a", "story-b"])

    remove_call_count = 0

    async def _failing_remove(slug: str, *, project_root: Path) -> None:
        nonlocal remove_call_count
        remove_call_count += 1
        if slug == "story-a":
            raise WorktreeError(f"Cannot remove '{slug}'")

    mock_list_branches = AsyncMock(return_value=["arcwright/story-b"])
    mock_delete_branch = AsyncMock(return_value=None)

    monkeypatch.setattr("arcwright_ai.cli.clean.git", mock_git)
    monkeypatch.setattr("arcwright_ai.cli.clean.list_worktrees", mock_list_worktrees)
    monkeypatch.setattr("arcwright_ai.cli.clean.remove_worktree", _failing_remove)
    monkeypatch.setattr("arcwright_ai.cli.clean.list_branches", mock_list_branches)
    monkeypatch.setattr("arcwright_ai.cli.clean.delete_branch", mock_delete_branch)

    worktrees, branches = await _clean_default(tmp_path)

    # story-a failed, story-b succeeded
    assert remove_call_count == 2
    assert worktrees == 1
    assert branches == 1


# ---------------------------------------------------------------------------
# Task 6.8 — test_clean_reports_correct_counts (via CLI CliRunner)
# ---------------------------------------------------------------------------


def test_clean_reports_correct_counts(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """CLI output matches 'Removed N worktree(s), deleted M branch(es)' format."""
    from arcwright_ai.cli import clean as clean_mod

    mock_list_worktrees = AsyncMock(return_value=["story-a", "story-b"])
    mock_remove_worktree = AsyncMock(return_value=None)
    mock_list_branches = AsyncMock(return_value=["arcwright/story-a", "arcwright/story-b"])
    mock_delete_branch = AsyncMock(return_value=None)
    mock_git = AsyncMock(return_value=_ok("  arcwright/story-a\n  arcwright/story-b"))

    monkeypatch.setattr(clean_mod, "list_worktrees", mock_list_worktrees)
    monkeypatch.setattr(clean_mod, "remove_worktree", mock_remove_worktree)
    monkeypatch.setattr(clean_mod, "list_branches", mock_list_branches)
    monkeypatch.setattr(clean_mod, "delete_branch", mock_delete_branch)
    monkeypatch.setattr(clean_mod, "git", mock_git)

    result = runner.invoke(app, ["clean", "--project-root", str(tmp_path)])

    assert result.exit_code == 0
    assert "Removed 2 worktree(s), deleted 2 branch(es)" in result.output


# ---------------------------------------------------------------------------
# Task 6.9 — test_clean_scm_error_exits_with_code_4
# ---------------------------------------------------------------------------


def test_clean_scm_error_exits_with_code_4(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """An unrecoverable ScmError causes exit code 4 (EXIT_SCM)."""
    from arcwright_ai.cli import clean as clean_mod

    async def _boom(*, project_root: Path) -> set[str]:
        raise ScmError("git exploded")

    monkeypatch.setattr(clean_mod, "_list_merged_branches", _boom)
    mock_list_worktrees = AsyncMock(return_value=[])
    monkeypatch.setattr(clean_mod, "list_worktrees", mock_list_worktrees)

    result = runner.invoke(app, ["clean", "--project-root", str(tmp_path)])

    assert result.exit_code == 4


# ---------------------------------------------------------------------------
# Task 6.10 — test_clean_default_logs_structured_events
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_clean_default_logs_structured_events(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """_clean_default emits a 'clean.default' log event with counts."""
    mock_git = AsyncMock(return_value=_ok(""))
    mock_list_worktrees = AsyncMock(return_value=[])
    mock_list_branches = AsyncMock(return_value=[])

    monkeypatch.setattr("arcwright_ai.cli.clean.git", mock_git)
    monkeypatch.setattr("arcwright_ai.cli.clean.list_worktrees", mock_list_worktrees)
    monkeypatch.setattr("arcwright_ai.cli.clean.list_branches", mock_list_branches)

    with caplog.at_level(logging.INFO, logger="arcwright_ai.cli.clean"):
        await _clean_default(tmp_path)

    assert any("clean.default" in record.message for record in caplog.records)


# ---------------------------------------------------------------------------
# Task 6.11 — test_clean_all_logs_structured_events
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_clean_all_logs_structured_events(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """_clean_all emits a 'clean.all' log event with counts."""
    mock_list_worktrees = AsyncMock(return_value=[])
    mock_list_branches = AsyncMock(return_value=[])

    monkeypatch.setattr("arcwright_ai.cli.clean.list_worktrees", mock_list_worktrees)
    monkeypatch.setattr("arcwright_ai.cli.clean.list_branches", mock_list_branches)

    with caplog.at_level(logging.INFO, logger="arcwright_ai.cli.clean"):
        await _clean_all(tmp_path)

    assert any("clean.all" in record.message for record in caplog.records)


# ---------------------------------------------------------------------------
# Task 6.12 — _list_merged_branches parses output correctly
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_list_merged_branches_parses_output(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """_list_merged_branches returns only arcwright-prefixed branches from git output."""
    mock_git = AsyncMock(return_value=_ok("* main\n  arcwright/story-a\n  arcwright/story-b\n  feature/other"))
    monkeypatch.setattr("arcwright_ai.cli.clean.git", mock_git)

    result = await _list_merged_branches(project_root=tmp_path)

    assert result == {"arcwright/story-a", "arcwright/story-b"}
    mock_git.assert_awaited_once_with("branch", "--merged", cwd=tmp_path)


@pytest.mark.asyncio
async def test_list_merged_branches_handles_worktree_plus_prefix(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """_list_merged_branches handles '+' prefix for branches checked out in linked worktrees."""
    # git uses '+' to mark branches checked out in linked worktrees (not '  ')
    mock_git = AsyncMock(return_value=_ok("* main\n+ arcwright/story-a\n  feature/other"))
    monkeypatch.setattr("arcwright_ai.cli.clean.git", mock_git)

    result = await _list_merged_branches(project_root=tmp_path)

    assert result == {"arcwright/story-a"}


@pytest.mark.asyncio
async def test_list_merged_branches_returns_empty_set_when_none(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """_list_merged_branches returns empty set when no arcwright branches are merged."""
    mock_git = AsyncMock(return_value=_ok("* main\n  feature/other"))
    monkeypatch.setattr("arcwright_ai.cli.clean.git", mock_git)

    result = await _list_merged_branches(project_root=tmp_path)

    assert result == set()


# ---------------------------------------------------------------------------
# Clean --all mode via CliRunner
# ---------------------------------------------------------------------------


def test_clean_all_flag_invokes_clean_all(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """CLI --all flag causes force-deletion of all items."""
    from arcwright_ai.cli import clean as clean_mod

    mock_list_worktrees = AsyncMock(return_value=["story-x"])
    mock_remove_worktree = AsyncMock(return_value=None)
    mock_list_branches = AsyncMock(return_value=["arcwright/story-x"])
    mock_delete_branch = AsyncMock(return_value=None)

    monkeypatch.setattr(clean_mod, "list_worktrees", mock_list_worktrees)
    monkeypatch.setattr(clean_mod, "remove_worktree", mock_remove_worktree)
    monkeypatch.setattr(clean_mod, "list_branches", mock_list_branches)
    monkeypatch.setattr(clean_mod, "delete_branch", mock_delete_branch)

    result = runner.invoke(app, ["clean", "--all", "--project-root", str(tmp_path)])

    assert result.exit_code == 0
    assert "Removed 1 worktree(s), deleted 1 branch(es)" in result.output
    mock_delete_branch.assert_awaited_once_with("arcwright/story-x", project_root=tmp_path, force=True)
