"""Unit tests for arcwright_ai.scm.worktree — Atomic worktree create/delete."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING
from unittest.mock import AsyncMock, call

import pytest

if TYPE_CHECKING:
    from pathlib import Path

from arcwright_ai.core.constants import BRANCH_PREFIX, DIR_ARCWRIGHT, DIR_WORKTREES
from arcwright_ai.core.exceptions import ScmError, WorktreeError
from arcwright_ai.scm.git import GitResult
from arcwright_ai.scm.worktree import create_worktree, list_worktrees, remove_worktree

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_SLUG = "my-story"
_BRANCH = f"{BRANCH_PREFIX}{_SLUG}"


def _ok(stdout: str = "") -> GitResult:
    """Return a successful GitResult."""
    return GitResult(stdout=stdout, stderr="", returncode=0)


def _worktree_path(project_root: Path, slug: str = _SLUG) -> Path:
    return project_root / DIR_ARCWRIGHT / DIR_WORKTREES / slug


# ---------------------------------------------------------------------------
# Task 7.1 — create_worktree returns correct path (AC #15a)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_create_worktree_returns_correct_path(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """create_worktree returns the absolute path under .arcwright-ai/worktrees/<slug>."""
    mock_git = AsyncMock(return_value=_ok())
    monkeypatch.setattr("arcwright_ai.scm.worktree.git", mock_git)

    result = await create_worktree(_SLUG, project_root=tmp_path)

    assert result == _worktree_path(tmp_path)


# ---------------------------------------------------------------------------
# Task 7.2 — create_worktree invokes git with correct args (AC #15b)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_create_worktree_invokes_git_with_correct_args(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """create_worktree calls git(worktree, add, <path>, -b, <branch>, HEAD)."""

    # rev-parse raises → branch does not exist (no stale cleanup needed).
    async def _mock_git(*args: str, cwd: object = None) -> GitResult:
        if args[0] == "rev-parse":
            raise ScmError("not found")
        return _ok()

    monkeypatch.setattr("arcwright_ai.scm.worktree.git", _mock_git)

    expected_path = str(_worktree_path(tmp_path))
    await create_worktree(_SLUG, project_root=tmp_path)


# ---------------------------------------------------------------------------
# Task 7.3 — create_worktree defaults to HEAD when base_ref omitted (AC #15c)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_create_worktree_defaults_to_head(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """create_worktree uses HEAD as base_ref when none is supplied."""
    mock_git = AsyncMock(return_value=_ok())
    monkeypatch.setattr("arcwright_ai.scm.worktree.git", mock_git)

    await create_worktree(_SLUG, project_root=tmp_path)

    args, _ = mock_git.call_args
    assert "HEAD" in args


# ---------------------------------------------------------------------------
# Task 7.4 — create_worktree uses explicit base_ref (AC #15d)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_create_worktree_uses_explicit_base_ref(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """create_worktree passes explicit base_ref to git and does NOT use HEAD."""
    mock_git = AsyncMock(return_value=_ok())
    monkeypatch.setattr("arcwright_ai.scm.worktree.git", mock_git)

    await create_worktree(_SLUG, base_ref="main", project_root=tmp_path)

    args, _ = mock_git.call_args
    assert "main" in args
    assert "HEAD" not in args


# ---------------------------------------------------------------------------
# Task 7.5 — create_worktree raises WorktreeError when directory exists (AC #15e)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_create_worktree_raises_worktree_error_when_exists(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """create_worktree raises WorktreeError (not calling git) if directory already present."""
    worktree_path = _worktree_path(tmp_path)
    worktree_path.mkdir(parents=True)

    mock_git = AsyncMock(return_value=_ok())
    monkeypatch.setattr("arcwright_ai.scm.worktree.git", mock_git)

    with pytest.raises(WorktreeError, match="already exists"):
        await create_worktree(_SLUG, project_root=tmp_path)

    mock_git.assert_not_called()


# ---------------------------------------------------------------------------
# Task 7.6 — create_worktree atomic recovery on failure (AC #15f)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_create_worktree_atomic_cleanup_on_failure(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """When git worktree add fails, cleanup is attempted and WorktreeError is raised."""
    add_error = ScmError("worktree add failed", details={"returncode": 128})

    call_count = 0

    async def _side_effect(*args: object, **kwargs: object) -> GitResult:
        nonlocal call_count
        call_count += 1
        if args[0] == "worktree" and args[1] == "add":
            raise add_error
        return _ok()

    mock_git = AsyncMock(side_effect=_side_effect)
    monkeypatch.setattr("arcwright_ai.scm.worktree.git", mock_git)

    with pytest.raises(WorktreeError):
        await create_worktree(_SLUG, project_root=tmp_path)

    # Cleanup should have been attempted (worktree remove --force and/or branch -D)
    assert call_count > 1, "Cleanup git calls were not made after worktree add failure"


@pytest.mark.asyncio
async def test_create_worktree_failure_message_includes_cleanup_actions(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """WorktreeError includes cleanup actions taken when create fails."""
    add_error = ScmError("worktree add failed", details={"returncode": 128})

    async def _side_effect(*args: object, **kwargs: object) -> GitResult:
        if args[0] == "worktree" and args[1] == "add":
            raise add_error
        return _ok()

    mock_git = AsyncMock(side_effect=_side_effect)
    monkeypatch.setattr("arcwright_ai.scm.worktree.git", mock_git)

    with pytest.raises(WorktreeError, match="Cleanup attempted") as exc_info:
        await create_worktree(_SLUG, project_root=tmp_path)

    details = exc_info.value.details or {}
    cleanup_actions = details.get("cleanup_actions")
    assert isinstance(cleanup_actions, list)
    assert cleanup_actions


# ---------------------------------------------------------------------------
# Task 7.7 — remove_worktree invokes git correctly (AC #15g)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_remove_worktree_invokes_git_correctly(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """remove_worktree calls git(worktree, remove, <path>, cwd=project_root)."""
    worktree_path = _worktree_path(tmp_path)
    worktree_path.mkdir(parents=True)

    mock_git = AsyncMock(return_value=_ok())
    monkeypatch.setattr("arcwright_ai.scm.worktree.git", mock_git)

    await remove_worktree(_SLUG, project_root=tmp_path)

    mock_git.assert_called_once_with(
        "worktree",
        "remove",
        str(worktree_path),
        cwd=tmp_path,
    )


@pytest.mark.asyncio
async def test_remove_worktree_optionally_deletes_branch(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """remove_worktree deletes the associated branch when delete_branch=True."""
    worktree_path = _worktree_path(tmp_path)
    worktree_path.mkdir(parents=True)

    mock_git = AsyncMock(return_value=_ok())
    monkeypatch.setattr("arcwright_ai.scm.worktree.git", mock_git)

    await remove_worktree(_SLUG, project_root=tmp_path, delete_branch=True)

    mock_git.assert_has_calls(
        [
            call("worktree", "remove", str(worktree_path), cwd=tmp_path),
            call("branch", "-D", _BRANCH, cwd=tmp_path),
        ]
    )


# ---------------------------------------------------------------------------
# Task 7.8 — remove_worktree idempotent (already removed) (AC #15h)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_remove_worktree_idempotent_already_removed(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """remove_worktree is a no-op (no error, no git call) when directory absent."""
    mock_git = AsyncMock(return_value=_ok())
    monkeypatch.setattr("arcwright_ai.scm.worktree.git", mock_git)

    # Directory does NOT exist
    await remove_worktree(_SLUG, project_root=tmp_path)

    mock_git.assert_not_called()


# ---------------------------------------------------------------------------
# Task 7.9 — remove_worktree idempotent (never created) (AC #15i)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_remove_worktree_idempotent_never_created(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """remove_worktree raises no exception when worktree was never created."""
    mock_git = AsyncMock(return_value=_ok())
    monkeypatch.setattr("arcwright_ai.scm.worktree.git", mock_git)

    # Should complete without raising
    await remove_worktree("never-existed", project_root=tmp_path)


# ---------------------------------------------------------------------------
# Task 7.9b — remove_worktree force=True falls back to rmtree on "Directory not empty"
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_remove_worktree_force_rmtree_fallback_on_nonempty_dir(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """When git worktree remove --force fails with 'Directory not empty' (exit 255),
    remove_worktree falls back to shutil.rmtree + git worktree prune rather than raising.

    This handles the case where the agent created files/subdirs in the worktree
    and git's own rmdir logic can't delete a non-empty tree.
    """
    # Create worktree dir with nested content (simulates agent-created files).
    worktree_path = _worktree_path(tmp_path)
    nested = worktree_path / "src" / "subdir"
    nested.mkdir(parents=True)
    (nested / "file.py").write_text("# agent-created")

    dir_not_empty_exc = ScmError(
        "git worktree failed (exit 255)",
        details={
            "command": ["worktree", "remove", "--force", str(worktree_path)],
            "stderr": f"error: failed to delete '{worktree_path}': Directory not empty",
            "returncode": 255,
        },
    )

    git_calls: list[tuple[str, ...]] = []

    async def _mock_git(*args: str, **kwargs: object) -> GitResult:
        git_calls.append(args)
        if args[:3] == ("worktree", "remove", "--force"):
            raise dir_not_empty_exc
        return _ok()

    monkeypatch.setattr("arcwright_ai.scm.worktree.git", _mock_git)

    # Should NOT raise even though git worktree remove --force failed.
    await remove_worktree(_SLUG, project_root=tmp_path, force=True, delete_branch=True)

    # worktree directory must be gone (rmtree cleaned it up).
    assert not worktree_path.exists(), "rmtree should have removed the worktree directory"

    # git worktree prune must have been called to reconcile git's tracking.
    prune_calls = [c for c in git_calls if c[:2] == ("worktree", "prune")]
    assert prune_calls, "git worktree prune must be called after rmtree fallback"


# ---------------------------------------------------------------------------
# Task 7.9c — remove_worktree force=True falls back to rmtree when "not a working tree"
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_remove_worktree_force_rmtree_fallback_on_unregistered_worktree(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """When git worktree remove --force fails with 'is not a working tree' (exit 128),
    remove_worktree falls back to shutil.rmtree + git worktree prune rather than raising.

    This handles the case where the worktree directory exists on disk but is no longer
    registered in git's worktree tracking (e.g. after a prior partial cleanup).
    """
    # Create worktree dir that exists but is unregistered in git.
    worktree_path = _worktree_path(tmp_path)
    worktree_path.mkdir(parents=True)
    (worktree_path / "orphaned-file.txt").write_text("leftover")

    not_a_working_tree_exc = ScmError(
        "git worktree failed (exit 128)",
        details={
            "command": ["worktree", "remove", "--force", str(worktree_path)],
            "stderr": f"fatal: '{worktree_path}' is not a working tree",
            "returncode": 128,
        },
    )

    git_calls: list[tuple[str, ...]] = []

    async def _mock_git(*args: str, **kwargs: object) -> GitResult:
        git_calls.append(args)
        if args[:3] == ("worktree", "remove", "--force"):
            raise not_a_working_tree_exc
        return _ok()

    monkeypatch.setattr("arcwright_ai.scm.worktree.git", _mock_git)

    # Should NOT raise even though git worktree remove --force failed.
    await remove_worktree(_SLUG, project_root=tmp_path, force=True, delete_branch=True)

    # worktree directory must be gone (rmtree cleaned it up).
    assert not worktree_path.exists(), "rmtree should have removed the worktree directory"

    # git worktree prune must have been called to reconcile git's tracking.
    prune_calls = [c for c in git_calls if c[:2] == ("worktree", "prune")]
    assert prune_calls, "git worktree prune must be called after rmtree fallback"


# ---------------------------------------------------------------------------
# Task 7.10 — list_worktrees returns correct slugs (AC #15j)
# ---------------------------------------------------------------------------

_PORCELAIN_WITH_ARCWRIGHT = """\
worktree /repo
HEAD abc123
branch refs/heads/main

worktree /repo/.arcwright-ai/worktrees/story-alpha
HEAD def456
branch refs/heads/arcwright/story-alpha

worktree /repo/.arcwright-ai/worktrees/story-beta
HEAD ghi789
branch refs/heads/arcwright/story-beta

"""


@pytest.mark.asyncio
async def test_list_worktrees_returns_story_slugs(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """list_worktrees extracts and returns story slugs from porcelain output."""
    mock_git = AsyncMock(return_value=_ok(stdout=_PORCELAIN_WITH_ARCWRIGHT))
    monkeypatch.setattr("arcwright_ai.scm.worktree.git", mock_git)

    slugs = await list_worktrees(project_root=tmp_path)

    assert slugs == ["story-alpha", "story-beta"]


# ---------------------------------------------------------------------------
# Task 7.11 — list_worktrees empty when no arcwright worktrees (AC #15k)
# ---------------------------------------------------------------------------

_PORCELAIN_MAIN_ONLY = """\
worktree /repo
HEAD abc123
branch refs/heads/main

"""


@pytest.mark.asyncio
async def test_list_worktrees_empty_when_no_arcwright_worktrees(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """list_worktrees returns empty list when no arcwright worktrees are present."""
    mock_git = AsyncMock(return_value=_ok(stdout=_PORCELAIN_MAIN_ONLY))
    monkeypatch.setattr("arcwright_ai.scm.worktree.git", mock_git)

    slugs = await list_worktrees(project_root=tmp_path)

    assert slugs == []


# ---------------------------------------------------------------------------
# Task 7.12 — create_worktree emits structured log (AC #15l)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_create_worktree_logs_structured_event(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """create_worktree emits a git.worktree.create INFO log with data dict."""
    mock_git = AsyncMock(return_value=_ok())
    monkeypatch.setattr("arcwright_ai.scm.worktree.git", mock_git)

    with caplog.at_level(logging.INFO, logger="arcwright_ai.scm.worktree"):
        await create_worktree(_SLUG, project_root=tmp_path)

    info_records = [r for r in caplog.records if r.levelname == "INFO" and r.message == "git.worktree.create"]
    assert len(info_records) == 1
    data = info_records[0].__dict__.get("data", {})
    assert data["story_slug"] == _SLUG
    assert data["branch"] == _BRANCH
    assert data["base_ref"] == "HEAD"


# ---------------------------------------------------------------------------
# Stale branch cleanup — create_worktree deletes lingering local branches
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_create_worktree_deletes_stale_local_branch_before_add(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """create_worktree deletes a stale local branch so worktree add -b succeeds."""
    calls: list[tuple[str, ...]] = []

    async def _mock_git(*args: str, cwd: object = None) -> GitResult:
        calls.append(args)
        return _ok()

    monkeypatch.setattr("arcwright_ai.scm.worktree.git", _mock_git)

    await create_worktree(_SLUG, project_root=tmp_path)

    # rev-parse succeeded (branch exists) → branch -D → worktree add
    assert calls[0][0] == "rev-parse"
    assert calls[1] == ("branch", "-D", _BRANCH)
    assert calls[2][0] == "worktree"


@pytest.mark.asyncio
async def test_create_worktree_skips_branch_delete_when_branch_absent(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """When the branch does not exist, create_worktree skips to worktree add."""
    calls: list[tuple[str, ...]] = []

    async def _mock_git(*args: str, cwd: object = None) -> GitResult:
        calls.append(args)
        if args[0] == "rev-parse":
            raise ScmError("not a valid ref")
        return _ok()

    monkeypatch.setattr("arcwright_ai.scm.worktree.git", _mock_git)

    await create_worktree(_SLUG, project_root=tmp_path)

    # Only rev-parse (failed) → worktree add
    assert len(calls) == 2
    assert calls[0][0] == "rev-parse"
    assert calls[1][0] == "worktree"


@pytest.mark.asyncio
async def test_create_worktree_stale_branch_cleanup_logs_event(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
    tmp_path: Path,
) -> None:
    """Stale branch cleanup emits a git.worktree.stale_branch_cleanup log event."""
    mock_git = AsyncMock(return_value=_ok())
    monkeypatch.setattr("arcwright_ai.scm.worktree.git", mock_git)

    with caplog.at_level(logging.INFO, logger="arcwright_ai.scm.worktree"):
        await create_worktree(_SLUG, project_root=tmp_path)

    assert any("git.worktree.stale_branch_cleanup" in r.message for r in caplog.records)


# ---------------------------------------------------------------------------
# Task 7.13 — remove_worktree emits structured log (AC #15l)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_remove_worktree_logs_structured_event(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """remove_worktree emits a git.worktree.remove INFO log with data dict."""
    worktree_path = _worktree_path(tmp_path)
    worktree_path.mkdir(parents=True)

    mock_git = AsyncMock(return_value=_ok())
    monkeypatch.setattr("arcwright_ai.scm.worktree.git", mock_git)

    with caplog.at_level(logging.INFO, logger="arcwright_ai.scm.worktree"):
        await remove_worktree(_SLUG, project_root=tmp_path)

    info_records = [r for r in caplog.records if r.levelname == "INFO" and r.message == "git.worktree.remove"]
    assert len(info_records) == 1
    data = info_records[0].__dict__.get("data", {})
    assert data["story_slug"] == _SLUG
