"""Unit tests for arcwright_ai.scm.branch — Branch management and commit strategy."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING
from unittest.mock import AsyncMock, call

import pytest

if TYPE_CHECKING:
    from pathlib import Path

from arcwright_ai.core.constants import BRANCH_PREFIX, COMMIT_MESSAGE_TEMPLATE
from arcwright_ai.core.exceptions import BranchError, ScmError
from arcwright_ai.scm.branch import (
    branch_exists,
    commit_story,
    create_branch,
    delete_branch,
    delete_remote_branch,
    fetch_and_sync,
    list_branches,
    push_branch,
)
from arcwright_ai.scm.git import GitResult

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_SLUG = "my-story"
_BRANCH = f"{BRANCH_PREFIX}{_SLUG}"


def _ok(stdout: str = "") -> GitResult:
    """Return a successful GitResult."""
    return GitResult(stdout=stdout, stderr="", returncode=0)


# ---------------------------------------------------------------------------
# Task 8.1 — test_create_branch_returns_correct_name (AC: #15a)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_create_branch_returns_correct_name(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """create_branch returns the namespaced branch name arcwright/<story-slug>."""
    mock_git = AsyncMock(return_value=_ok())
    mock_branch_exists = AsyncMock(return_value=False)
    monkeypatch.setattr("arcwright_ai.scm.branch.git", mock_git)
    monkeypatch.setattr("arcwright_ai.scm.branch.branch_exists", mock_branch_exists)

    result = await create_branch(_SLUG, project_root=tmp_path)

    assert result == _BRANCH


# ---------------------------------------------------------------------------
# Task 8.2 — test_create_branch_invokes_git_with_correct_args (AC: #15b)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_create_branch_invokes_git_with_correct_args(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """create_branch calls git('branch', branch_name, base_ref, cwd=project_root)."""
    mock_git = AsyncMock(return_value=_ok())
    mock_branch_exists = AsyncMock(return_value=False)
    monkeypatch.setattr("arcwright_ai.scm.branch.git", mock_git)
    monkeypatch.setattr("arcwright_ai.scm.branch.branch_exists", mock_branch_exists)

    await create_branch(_SLUG, project_root=tmp_path)

    mock_git.assert_called_once_with("branch", _BRANCH, "HEAD", cwd=tmp_path)


# ---------------------------------------------------------------------------
# Task 8.3 — test_create_branch_defaults_to_head (AC: #15c)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_create_branch_defaults_to_head(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """create_branch uses 'HEAD' as base_ref when none is supplied."""
    mock_git = AsyncMock(return_value=_ok())
    mock_branch_exists = AsyncMock(return_value=False)
    monkeypatch.setattr("arcwright_ai.scm.branch.git", mock_git)
    monkeypatch.setattr("arcwright_ai.scm.branch.branch_exists", mock_branch_exists)

    await create_branch(_SLUG, project_root=tmp_path)

    args, _ = mock_git.call_args
    assert "HEAD" in args


# ---------------------------------------------------------------------------
# Task 8.4 — test_create_branch_uses_explicit_base_ref (AC: #15d)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_create_branch_uses_explicit_base_ref(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """create_branch passes explicit base_ref and does NOT use HEAD."""
    mock_git = AsyncMock(return_value=_ok())
    mock_branch_exists = AsyncMock(return_value=False)
    monkeypatch.setattr("arcwright_ai.scm.branch.git", mock_git)
    monkeypatch.setattr("arcwright_ai.scm.branch.branch_exists", mock_branch_exists)

    await create_branch(_SLUG, base_ref="main", project_root=tmp_path)

    args, _ = mock_git.call_args
    assert "main" in args
    assert "HEAD" not in args


# ---------------------------------------------------------------------------
# Task 8.5 — test_create_branch_raises_branch_error_when_exists (AC: #15e)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_create_branch_raises_branch_error_when_exists(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """create_branch raises BranchError when branch already exists; git branch NOT called."""
    mock_git = AsyncMock(return_value=_ok())
    mock_branch_exists = AsyncMock(return_value=True)
    monkeypatch.setattr("arcwright_ai.scm.branch.git", mock_git)
    monkeypatch.setattr("arcwright_ai.scm.branch.branch_exists", mock_branch_exists)

    with pytest.raises(BranchError, match="already exists"):
        await create_branch(_SLUG, project_root=tmp_path)

    mock_git.assert_not_called()


# ---------------------------------------------------------------------------
# Task 8.6 — test_commit_story_invokes_git_add_and_commit (AC: #15f)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_commit_story_invokes_git_add_and_commit(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """commit_story calls git add . then git commit -m <message>."""
    commit_hash = "deadbeef"
    side_effects: list[GitResult] = [
        _ok(),  # git add .
        _ok(stdout="M output.md"),  # git status --porcelain (has changes)
        _ok(),  # git commit -m ...
        _ok(stdout=commit_hash),  # git rev-parse HEAD
    ]
    mock_git = AsyncMock(side_effect=side_effects)
    monkeypatch.setattr("arcwright_ai.scm.branch.git", mock_git)

    await commit_story(
        story_slug=_SLUG,
        story_title="My Story",
        story_path="_spec/s.md",
        run_id="20260307-001122-abc123",
        worktree_path=tmp_path,
    )

    assert mock_git.call_count == 4
    first_call = mock_git.call_args_list[0]
    assert first_call == call("add", ".", cwd=tmp_path)
    commit_call = mock_git.call_args_list[2]
    assert commit_call.args[0] == "commit"
    assert commit_call.args[1] == "-m"


# ---------------------------------------------------------------------------
# Task 8.7 — test_commit_story_uses_commit_message_template (AC: #15g)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_commit_story_uses_commit_message_template(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """commit_story formats message with COMMIT_MESSAGE_TEMPLATE correctly."""
    commit_hash = "abc123def"
    side_effects: list[GitResult] = [
        _ok(),  # git add .
        _ok(stdout="M output.md"),  # git status --porcelain
        _ok(),  # git commit -m ...
        _ok(stdout=commit_hash),  # git rev-parse HEAD
    ]
    mock_git = AsyncMock(side_effect=side_effects)
    monkeypatch.setattr("arcwright_ai.scm.branch.git", mock_git)

    slug = "s"
    title = "My Story"
    path = "_spec/s.md"
    run = "20260307-001122-abc123"
    expected_msg = COMMIT_MESSAGE_TEMPLATE.format(story_title=title, story_path=path, run_id=run)

    await commit_story(
        story_slug=slug,
        story_title=title,
        story_path=path,
        run_id=run,
        worktree_path=tmp_path,
    )

    commit_call = mock_git.call_args_list[2]
    assert commit_call == call("commit", "-m", expected_msg, cwd=tmp_path)
    assert expected_msg == "[arcwright-ai] My Story\n\nStory: _spec/s.md\nRun: 20260307-001122-abc123"


# ---------------------------------------------------------------------------
# Task 8.8 — test_commit_story_returns_commit_hash (AC: #15h)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_commit_story_returns_commit_hash(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """commit_story returns the commit hash from git rev-parse HEAD."""
    commit_hash = "abc123def"
    side_effects: list[GitResult] = [
        _ok(),  # git add .
        _ok(stdout="M output.md"),  # git status --porcelain
        _ok(),  # git commit -m ...
        _ok(stdout=commit_hash),  # git rev-parse HEAD
    ]
    mock_git = AsyncMock(side_effect=side_effects)
    monkeypatch.setattr("arcwright_ai.scm.branch.git", mock_git)

    result = await commit_story(
        story_slug=_SLUG,
        story_title="My Story",
        story_path="_spec/s.md",
        run_id="run-001",
        worktree_path=tmp_path,
    )

    assert result == commit_hash


# ---------------------------------------------------------------------------
# Task 8.9 — test_commit_story_raises_branch_error_on_nothing_to_commit (AC: #15i)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_commit_story_raises_branch_error_on_nothing_to_commit(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """commit_story raises BranchError when git status --porcelain returns empty (nothing staged)."""
    side_effects: list[GitResult] = [
        _ok(),  # git add .
        _ok(stdout=""),  # git status --porcelain — empty means nothing to commit
    ]
    mock_git = AsyncMock(side_effect=side_effects)
    monkeypatch.setattr("arcwright_ai.scm.branch.git", mock_git)

    with pytest.raises(BranchError, match="No changes to commit"):
        await commit_story(
            story_slug=_SLUG,
            story_title="My Story",
            story_path="_spec/s.md",
            run_id="run-001",
            worktree_path=tmp_path,
        )


# ---------------------------------------------------------------------------
# Task 8.10 — test_branch_exists_returns_true (AC: #15j)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_branch_exists_returns_true(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """branch_exists returns True when git rev-parse --verify succeeds."""
    mock_git = AsyncMock(return_value=_ok(stdout="abc123"))
    monkeypatch.setattr("arcwright_ai.scm.branch.git", mock_git)

    result = await branch_exists(_BRANCH, project_root=tmp_path)

    assert result is True
    mock_git.assert_called_once_with("rev-parse", "--verify", f"refs/heads/{_BRANCH}", cwd=tmp_path)


# ---------------------------------------------------------------------------
# Task 8.11 — test_branch_exists_returns_false (AC: #15k)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_branch_exists_returns_false(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """branch_exists returns False when git rev-parse --verify raises ScmError."""
    mock_git = AsyncMock(side_effect=ScmError("unknown revision"))
    monkeypatch.setattr("arcwright_ai.scm.branch.git", mock_git)

    result = await branch_exists(_BRANCH, project_root=tmp_path)

    assert result is False


@pytest.mark.asyncio
async def test_branch_exists_reraises_non_not_found_scm_error(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """branch_exists re-raises SCM errors that are not branch-not-found cases."""
    mock_git = AsyncMock(side_effect=ScmError("Not a git repository", details={"stderr": "not a git repository"}))
    monkeypatch.setattr("arcwright_ai.scm.branch.git", mock_git)

    with pytest.raises(ScmError, match="Not a git repository"):
        await branch_exists(_BRANCH, project_root=tmp_path)


# ---------------------------------------------------------------------------
# Task 8.12 — test_list_branches_returns_sorted_list (AC: #15l)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_list_branches_returns_sorted_list(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """list_branches returns a sorted list of arcwright branch names."""
    raw_output = "  arcwright-ai/story-z\n* arcwright-ai/story-a\n  arcwright-ai/story-m"
    mock_git = AsyncMock(return_value=_ok(stdout=raw_output))
    monkeypatch.setattr("arcwright_ai.scm.branch.git", mock_git)

    result = await list_branches(project_root=tmp_path)

    assert result == ["arcwright-ai/story-a", "arcwright-ai/story-m", "arcwright-ai/story-z"]
    mock_git.assert_called_once_with("branch", "--list", "arcwright-ai/*", cwd=tmp_path)


# ---------------------------------------------------------------------------
# Task 8.13 — test_list_branches_returns_empty_when_none (AC: #15m)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_list_branches_returns_empty_when_none(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """list_branches returns an empty list when no arcwright branches exist."""
    mock_git = AsyncMock(return_value=_ok(stdout=""))
    monkeypatch.setattr("arcwright_ai.scm.branch.git", mock_git)

    result = await list_branches(project_root=tmp_path)

    assert result == []


# ---------------------------------------------------------------------------
# Task 8.14 — test_delete_branch_invokes_git_with_d_flag (AC: #15n)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_delete_branch_invokes_git_with_d_flag(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """delete_branch calls git branch -d <name> by default (safe delete)."""
    mock_git = AsyncMock(return_value=_ok())
    mock_branch_exists = AsyncMock(return_value=True)
    monkeypatch.setattr("arcwright_ai.scm.branch.git", mock_git)
    monkeypatch.setattr("arcwright_ai.scm.branch.branch_exists", mock_branch_exists)

    await delete_branch(_BRANCH, project_root=tmp_path)

    mock_git.assert_called_once_with("branch", "-d", _BRANCH, cwd=tmp_path)


# ---------------------------------------------------------------------------
# Task 8.15 — test_delete_branch_invokes_git_with_D_flag_when_force (AC: #15o)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_delete_branch_invokes_git_with_D_flag_when_force(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """delete_branch calls git branch -D <name> when force=True."""
    mock_git = AsyncMock(return_value=_ok())
    mock_branch_exists = AsyncMock(return_value=True)
    monkeypatch.setattr("arcwright_ai.scm.branch.git", mock_git)
    monkeypatch.setattr("arcwright_ai.scm.branch.branch_exists", mock_branch_exists)

    await delete_branch(_BRANCH, project_root=tmp_path, force=True)

    mock_git.assert_called_once_with("branch", "-D", _BRANCH, cwd=tmp_path)


# ---------------------------------------------------------------------------
# Task 8.16 — test_delete_branch_idempotent_nonexistent (AC: #15p)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_delete_branch_idempotent_nonexistent(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """delete_branch is a no-op when the branch does not exist; git branch NOT called."""
    mock_git = AsyncMock(return_value=_ok())
    mock_branch_exists = AsyncMock(return_value=False)
    monkeypatch.setattr("arcwright_ai.scm.branch.git", mock_git)
    monkeypatch.setattr("arcwright_ai.scm.branch.branch_exists", mock_branch_exists)

    await delete_branch(_BRANCH, project_root=tmp_path)

    mock_git.assert_not_called()


# ---------------------------------------------------------------------------
# Task 8.17 — test_create_branch_logs_structured_event (AC: #15q)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_create_branch_logs_structured_event(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
    tmp_path: Path,
) -> None:
    """create_branch emits a structured git.branch.create log event."""
    mock_git = AsyncMock(return_value=_ok())
    mock_branch_exists = AsyncMock(return_value=False)
    monkeypatch.setattr("arcwright_ai.scm.branch.git", mock_git)
    monkeypatch.setattr("arcwright_ai.scm.branch.branch_exists", mock_branch_exists)

    with caplog.at_level(logging.INFO, logger="arcwright_ai.scm.branch"):
        await create_branch(_SLUG, project_root=tmp_path)

    assert any("git.branch.create" in r.message for r in caplog.records)


# ---------------------------------------------------------------------------
# Task 8.18 — test_commit_story_logs_structured_event (AC: #15q)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_commit_story_logs_structured_event(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
    tmp_path: Path,
) -> None:
    """commit_story emits a structured git.commit log event."""
    side_effects: list[GitResult] = [
        _ok(),  # git add .
        _ok(stdout="M output.md"),  # git status --porcelain
        _ok(),  # git commit -m ...
        _ok(stdout="deadbeef"),  # git rev-parse HEAD
    ]
    mock_git = AsyncMock(side_effect=side_effects)
    monkeypatch.setattr("arcwright_ai.scm.branch.git", mock_git)

    with caplog.at_level(logging.INFO, logger="arcwright_ai.scm.branch"):
        await commit_story(
            story_slug=_SLUG,
            story_title="My Story",
            story_path="_spec/s.md",
            run_id="run-001",
            worktree_path=tmp_path,
        )

    assert any("git.commit" in r.message for r in caplog.records)


# ---------------------------------------------------------------------------
# Story 6.7 — push_branch tests (Task 5.1)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_push_branch_calls_git_push_with_correct_args(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """push_branch calls git('push', remote, branch_name, cwd=project_root)."""
    mock_git = AsyncMock(return_value=_ok())
    monkeypatch.setattr("arcwright_ai.scm.branch.git", mock_git)

    result = await push_branch(_BRANCH, project_root=tmp_path)

    mock_git.assert_called_once_with("push", "origin", _BRANCH, cwd=tmp_path)
    assert result is True


@pytest.mark.asyncio
async def test_push_branch_uses_custom_remote(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """push_branch passes the remote argument to git."""
    mock_git = AsyncMock(return_value=_ok())
    monkeypatch.setattr("arcwright_ai.scm.branch.git", mock_git)

    result = await push_branch(_BRANCH, project_root=tmp_path, remote="upstream")

    mock_git.assert_called_once_with("push", "upstream", _BRANCH, cwd=tmp_path)
    assert result is True


@pytest.mark.asyncio
async def test_push_branch_does_not_raise_on_scm_error(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """push_branch swallows ScmError and returns False (best-effort, non-fatal)."""
    mock_git = AsyncMock(side_effect=ScmError("push failed", details={}))
    monkeypatch.setattr("arcwright_ai.scm.branch.git", mock_git)

    # Must not raise
    result = await push_branch(_BRANCH, project_root=tmp_path)

    assert result is False


@pytest.mark.asyncio
async def test_push_branch_logs_warning_on_scm_error(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
    tmp_path: Path,
) -> None:
    """push_branch logs git.push.error at WARNING level on ScmError."""
    mock_git = AsyncMock(side_effect=ScmError("network timeout", details={}))
    monkeypatch.setattr("arcwright_ai.scm.branch.git", mock_git)

    with caplog.at_level(logging.WARNING, logger="arcwright_ai.scm.branch"):
        await push_branch(_BRANCH, project_root=tmp_path)

    assert any("git.push.error" in r.message for r in caplog.records)


@pytest.mark.asyncio
async def test_push_branch_logs_structured_event_on_success(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
    tmp_path: Path,
) -> None:
    """push_branch emits a structured git.push log event on success."""
    mock_git = AsyncMock(return_value=_ok())
    monkeypatch.setattr("arcwright_ai.scm.branch.git", mock_git)

    with caplog.at_level(logging.INFO, logger="arcwright_ai.scm.branch"):
        await push_branch(_BRANCH, project_root=tmp_path)

    assert any("git.push" in r.message for r in caplog.records)


# ---------------------------------------------------------------------------
# Merge-ours reconciliation strategy (with worktree_path)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_push_branch_merge_ours_reconciles_non_fast_forward(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """push_branch fetches + merges --strategy=ours then retries push when worktree_path is given."""
    calls: list[tuple[str, ...]] = []
    worktree = tmp_path / "worktree"

    async def _mock_git(*args: str, cwd: object = None) -> GitResult:
        calls.append(args)
        # First push fails with non-fast-forward
        if args == ("push", "origin", _BRANCH) and len([c for c in calls if c == ("push", "origin", _BRANCH)]) == 1:
            raise ScmError(
                "git push failed (exit 1)",
                details={"stderr": "! [rejected] (non-fast-forward)\nerror: failed to push"},
            )
        return _ok()

    monkeypatch.setattr("arcwright_ai.scm.branch.git", _mock_git)

    result = await push_branch(_BRANCH, project_root=tmp_path, worktree_path=worktree)

    assert result is True
    # Calls: push (fail) → fetch → merge --strategy=ours → push (succeed)
    assert calls[0] == ("push", "origin", _BRANCH)
    assert calls[1] == ("fetch", "origin", _BRANCH)
    assert calls[2][0] == "merge"
    assert "--strategy=ours" in calls[2]
    assert "FETCH_HEAD" in calls[2]
    assert calls[3] == ("push", "origin", _BRANCH)


@pytest.mark.asyncio
async def test_push_branch_merge_ours_runs_merge_in_worktree(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """merge-ours fetch and merge run in the worktree_path, not project_root."""
    cwd_log: list[object] = []
    worktree = tmp_path / "worktree"
    push_count = 0

    async def _mock_git(*args: str, cwd: object = None) -> GitResult:
        nonlocal push_count
        cwd_log.append((args[0], cwd))
        if args[:2] == ("push", "origin") and push_count == 0:
            push_count += 1
            raise ScmError(
                "git push failed",
                details={"stderr": "non-fast-forward"},
            )
        return _ok()

    monkeypatch.setattr("arcwright_ai.scm.branch.git", _mock_git)

    await push_branch(_BRANCH, project_root=tmp_path, worktree_path=worktree)

    # fetch and merge should use worktree as cwd
    fetch_entry = [e for e in cwd_log if e[0] == "fetch"]
    merge_entry = [e for e in cwd_log if e[0] == "merge"]
    assert fetch_entry[0][1] == worktree
    assert merge_entry[0][1] == worktree
    # push should use project_root
    push_entries = [e for e in cwd_log if e[0] == "push"]
    assert all(e[1] == tmp_path for e in push_entries)


@pytest.mark.asyncio
async def test_push_branch_merge_ours_falls_back_to_force_with_lease_on_merge_failure(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """When merge-ours fails (e.g. fetch error), falls back to --force-with-lease."""
    calls: list[tuple[str, ...]] = []
    worktree = tmp_path / "worktree"

    async def _mock_git(*args: str, cwd: object = None) -> GitResult:
        calls.append(args)
        # First push: non-fast-forward
        if args == ("push", "origin", _BRANCH) and len([c for c in calls if c == ("push", "origin", _BRANCH)]) == 1:
            raise ScmError(
                "git push failed",
                details={"stderr": "non-fast-forward"},
            )
        # Fetch fails (e.g. remote branch missing from a race)
        if args[0] == "fetch":
            raise ScmError("fetch failed", details={"stderr": "could not read from remote"})
        return _ok()

    monkeypatch.setattr("arcwright_ai.scm.branch.git", _mock_git)

    result = await push_branch(_BRANCH, project_root=tmp_path, worktree_path=worktree)

    assert result is True
    # Should have fallen through to --force-with-lease
    assert ("push", "--force-with-lease", "origin", _BRANCH) in calls


@pytest.mark.asyncio
async def test_push_branch_merge_ours_push_after_merge_fails_returns_false(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """When push after merge-ours also fails, returns False (no further retry)."""
    worktree = tmp_path / "worktree"

    async def _mock_git(*args: str, cwd: object = None) -> GitResult:
        # All pushes fail
        if args[0] == "push":
            raise ScmError(
                "git push failed",
                details={"stderr": "non-fast-forward"},
            )
        # fetch and merge succeed
        return _ok()

    monkeypatch.setattr("arcwright_ai.scm.branch.git", _mock_git)

    result = await push_branch(_BRANCH, project_root=tmp_path, worktree_path=worktree)

    assert result is False


@pytest.mark.asyncio
async def test_push_branch_merge_ours_logs_retry_event(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
    tmp_path: Path,
) -> None:
    """push_branch logs git.push.retry_merge_ours before the reconciliation."""
    worktree = tmp_path / "worktree"
    push_count = 0

    async def _mock_git(*args: str, cwd: object = None) -> GitResult:
        nonlocal push_count
        if args[:2] == ("push", "origin") and push_count == 0:
            push_count += 1
            raise ScmError("fail", details={"stderr": "non-fast-forward"})
        return _ok()

    monkeypatch.setattr("arcwright_ai.scm.branch.git", _mock_git)

    with caplog.at_level(logging.INFO, logger="arcwright_ai.scm.branch"):
        result = await push_branch(_BRANCH, project_root=tmp_path, worktree_path=worktree)

    assert result is True
    assert any("git.push.retry_merge_ours" in r.message for r in caplog.records)


# ---------------------------------------------------------------------------
# --force-with-lease fallback (without worktree_path)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_push_branch_retries_with_force_with_lease_on_non_fast_forward(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """push_branch retries with --force-with-lease when no worktree_path is given."""
    calls: list[tuple[str, ...]] = []

    async def _mock_git(*args: str, cwd: object = None) -> GitResult:
        calls.append(args)
        if "--force-with-lease" not in args:
            raise ScmError(
                "git push failed (exit 1)",
                details={"stderr": "! [rejected] (non-fast-forward)\nerror: failed to push"},
            )
        return _ok()

    monkeypatch.setattr("arcwright_ai.scm.branch.git", _mock_git)

    result = await push_branch(_BRANCH, project_root=tmp_path)

    assert result is True
    assert len(calls) == 2
    assert calls[0] == ("push", "origin", _BRANCH)
    assert calls[1] == ("push", "--force-with-lease", "origin", _BRANCH)


@pytest.mark.asyncio
async def test_push_branch_force_with_lease_retry_returns_false_on_failure(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """push_branch returns False when --force-with-lease retry also fails."""
    mock_git = AsyncMock(
        side_effect=ScmError(
            "git push failed (exit 1)",
            details={"stderr": "! [rejected] (non-fast-forward)\nerror: failed to push"},
        )
    )
    monkeypatch.setattr("arcwright_ai.scm.branch.git", mock_git)

    result = await push_branch(_BRANCH, project_root=tmp_path)

    assert result is False
    assert mock_git.await_count == 2


@pytest.mark.asyncio
async def test_push_branch_does_not_retry_on_unrelated_errors(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """push_branch does NOT retry for non-fast-forward unrelated errors."""
    mock_git = AsyncMock(side_effect=ScmError("network timeout", details={"stderr": "fatal: unable to access remote"}))
    monkeypatch.setattr("arcwright_ai.scm.branch.git", mock_git)

    result = await push_branch(_BRANCH, project_root=tmp_path)

    assert result is False
    mock_git.assert_called_once()  # No retry


@pytest.mark.asyncio
async def test_push_branch_force_with_lease_retry_logs_info(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
    tmp_path: Path,
) -> None:
    """push_branch logs git.push.retry_force_with_lease before the fallback retry."""

    async def _mock_git(*args: str, cwd: object = None) -> GitResult:
        if "--force-with-lease" not in args:
            raise ScmError(
                "git push failed (exit 1)",
                details={"stderr": "! [rejected] (non-fast-forward)"},
            )
        return _ok()

    monkeypatch.setattr("arcwright_ai.scm.branch.git", _mock_git)

    with caplog.at_level(logging.INFO, logger="arcwright_ai.scm.branch"):
        result = await push_branch(_BRANCH, project_root=tmp_path)

    assert result is True
    assert any("git.push.retry_force_with_lease" in r.message for r in caplog.records)


# ---------------------------------------------------------------------------
# delete_remote_branch tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_delete_remote_branch_calls_git_push_delete(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """delete_remote_branch calls git push --delete with correct args."""
    mock_git = AsyncMock(return_value=_ok())
    monkeypatch.setattr("arcwright_ai.scm.branch.git", mock_git)

    result = await delete_remote_branch(_BRANCH, project_root=tmp_path)

    mock_git.assert_called_once_with("push", "origin", "--delete", _BRANCH, cwd=tmp_path)
    assert result is True


@pytest.mark.asyncio
async def test_delete_remote_branch_uses_custom_remote(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """delete_remote_branch passes the remote argument to git."""
    mock_git = AsyncMock(return_value=_ok())
    monkeypatch.setattr("arcwright_ai.scm.branch.git", mock_git)

    result = await delete_remote_branch(_BRANCH, project_root=tmp_path, remote="upstream")

    mock_git.assert_called_once_with("push", "upstream", "--delete", _BRANCH, cwd=tmp_path)
    assert result is True


@pytest.mark.asyncio
async def test_delete_remote_branch_returns_true_when_already_absent(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """delete_remote_branch returns True when remote branch does not exist."""
    mock_git = AsyncMock(
        side_effect=ScmError(
            "push failed",
            details={"stderr": "error: unable to delete 'arcwright-ai/my-story': remote ref does not exist"},
        )
    )
    monkeypatch.setattr("arcwright_ai.scm.branch.git", mock_git)

    result = await delete_remote_branch(_BRANCH, project_root=tmp_path)

    assert result is True


@pytest.mark.asyncio
async def test_delete_remote_branch_returns_false_on_network_error(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """delete_remote_branch swallows ScmError for non-trivial failures and returns False."""
    mock_git = AsyncMock(side_effect=ScmError("network timeout", details={"stderr": "fatal: network error"}))
    monkeypatch.setattr("arcwright_ai.scm.branch.git", mock_git)

    result = await delete_remote_branch(_BRANCH, project_root=tmp_path)

    assert result is False


@pytest.mark.asyncio
async def test_delete_remote_branch_logs_warning_on_failure(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
    tmp_path: Path,
) -> None:
    """delete_remote_branch logs git.remote_branch.delete.error at WARNING on failure."""
    mock_git = AsyncMock(side_effect=ScmError("network timeout", details={"stderr": "fatal: network error"}))
    monkeypatch.setattr("arcwright_ai.scm.branch.git", mock_git)

    with caplog.at_level(logging.WARNING, logger="arcwright_ai.scm.branch"):
        await delete_remote_branch(_BRANCH, project_root=tmp_path)

    assert any("git.remote_branch.delete.error" in r.message for r in caplog.records)


# ---------------------------------------------------------------------------
# Story 9.2 — fetch_and_sync unit tests (AC: #1, #2, #3, #4, #13)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_fetch_and_sync_calls_git_fetch(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """fetch_and_sync calls git fetch <remote> <default_branch> with correct args (AC: #13a)."""
    sha = "abc1234567890abcdef1234567890abcdef123456"
    mock_git = AsyncMock(
        side_effect=[
            _ok(),  # fetch
            _ok(sha),  # rev-parse remote/branch
            _ok("HEAD"),  # rev-parse --abbrev-ref HEAD (detached)
        ]
    )
    monkeypatch.setattr("arcwright_ai.scm.branch.git", mock_git)

    await fetch_and_sync("main", "origin", project_root=tmp_path)

    mock_git.assert_any_call("fetch", "origin", "main", cwd=tmp_path)


@pytest.mark.asyncio
async def test_fetch_and_sync_resolves_remote_sha(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """fetch_and_sync calls git rev-parse and returns resolved SHA (AC: #13b, #13c)."""
    sha = "deadbeef1234567890deadbeef1234567890dead"
    mock_git = AsyncMock(
        side_effect=[
            _ok(),  # fetch
            _ok(sha + "\n"),  # rev-parse (with trailing newline)
            _ok("HEAD"),  # rev-parse --abbrev-ref HEAD
        ]
    )
    monkeypatch.setattr("arcwright_ai.scm.branch.git", mock_git)

    result = await fetch_and_sync("main", "origin", project_root=tmp_path)

    assert result == sha
    mock_git.assert_any_call("rev-parse", "origin/main", cwd=tmp_path)


@pytest.mark.asyncio
async def test_fetch_and_sync_ff_merge_on_default_branch(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """When on default branch, fetch_and_sync attempts git merge --ff-only (AC: #13d)."""
    sha = "cafebabe1234567890cafebabe1234567890cafe"
    mock_git = AsyncMock(
        side_effect=[
            _ok(),  # fetch
            _ok(sha),  # rev-parse origin/main
            _ok("main"),  # rev-parse --abbrev-ref HEAD → on default branch
            _ok(),  # merge --ff-only (success)
        ]
    )
    monkeypatch.setattr("arcwright_ai.scm.branch.git", mock_git)

    result = await fetch_and_sync("main", "origin", project_root=tmp_path)

    assert result == sha
    mock_git.assert_any_call("merge", "--ff-only", "origin/main", cwd=tmp_path)


@pytest.mark.asyncio
async def test_fetch_and_sync_ff_merge_failure_continues(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
    tmp_path: Path,
) -> None:
    """When ff-only fails, a warning is logged and the remote SHA is still returned (AC: #13e)."""
    sha = "fedc1234567890abcdef1234567890abcdef1234"
    mock_git = AsyncMock(
        side_effect=[
            _ok(),  # fetch
            _ok(sha),  # rev-parse origin/main
            _ok("main"),  # rev-parse --abbrev-ref HEAD
            ScmError(
                "merge diverged", details={"stderr": "fatal: Not possible to fast-forward"}
            ),  # merge --ff-only fails
        ]
    )
    monkeypatch.setattr("arcwright_ai.scm.branch.git", mock_git)

    with caplog.at_level(logging.WARNING, logger="arcwright_ai.scm.branch"):
        result = await fetch_and_sync("main", "origin", project_root=tmp_path)

    assert result == sha
    assert any("git.fetch_and_sync.ff_failed" in r.message for r in caplog.records)


@pytest.mark.asyncio
async def test_fetch_and_sync_skips_merge_not_on_default(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """When not on default branch, fetch_and_sync skips merge and returns SHA (AC: #13f)."""
    sha = "aabbccdd1234567890aabbccdd1234567890aabb"
    merge_call = AsyncMock()
    mock_git = AsyncMock(
        side_effect=[
            _ok(),  # fetch
            _ok(sha),  # rev-parse origin/main
            _ok("feature/other-branch"),  # rev-parse --abbrev-ref HEAD → NOT on default
        ]
    )
    monkeypatch.setattr("arcwright_ai.scm.branch.git", mock_git)

    result = await fetch_and_sync("main", "origin", project_root=tmp_path)

    assert result == sha
    # Verify no merge call was made (only 3 calls total: fetch, rev-parse SHA, rev-parse HEAD)
    assert mock_git.call_count == 3
    merge_call.assert_not_called()


@pytest.mark.asyncio
async def test_fetch_and_sync_network_failure_raises_scm_error(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """When git fetch fails, ScmError is raised with network connectivity message (AC: #4, #13g)."""
    mock_git = AsyncMock(side_effect=ScmError("fatal: unable to connect", details={"stderr": "network error"}))
    monkeypatch.setattr("arcwright_ai.scm.branch.git", mock_git)

    with pytest.raises(ScmError) as exc_info:
        await fetch_and_sync("main", "origin", project_root=tmp_path)

    assert "check network connectivity" in exc_info.value.message
    assert exc_info.value.details is not None
    assert exc_info.value.details["remote"] == "origin"
    assert exc_info.value.details["branch"] == "main"


@pytest.mark.asyncio
async def test_fetch_and_sync_logs_structured_event(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
    tmp_path: Path,
) -> None:
    """fetch_and_sync emits a structured git.fetch_and_sync log event on success (AC: #13h)."""
    sha = "1234abcd5678efgh1234abcd5678efgh12345678"
    mock_git = AsyncMock(
        side_effect=[
            _ok(),  # fetch
            _ok(sha),  # rev-parse
            _ok("HEAD"),  # rev-parse --abbrev-ref HEAD (detached)
        ]
    )
    monkeypatch.setattr("arcwright_ai.scm.branch.git", mock_git)

    with caplog.at_level(logging.INFO, logger="arcwright_ai.scm.branch"):
        await fetch_and_sync("main", "origin", project_root=tmp_path)

    assert any("git.fetch_and_sync" in r.message for r in caplog.records)


@pytest.mark.asyncio
async def test_fetch_and_sync_logs_ff_merge_event_on_success(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
    tmp_path: Path,
) -> None:
    """fetch_and_sync emits git.fetch_and_sync.ff_merge when ff-only merge succeeds (AC: #2, #13h)."""
    sha = "1234567890abcdef1234567890abcdef12345678"
    mock_git = AsyncMock(
        side_effect=[
            _ok(),
            _ok(sha),
            _ok("main"),
            _ok(),
        ]
    )
    monkeypatch.setattr("arcwright_ai.scm.branch.git", mock_git)

    with caplog.at_level(logging.INFO, logger="arcwright_ai.scm.branch"):
        await fetch_and_sync("main", "origin", project_root=tmp_path)

    assert any("git.fetch_and_sync.ff_merge" in r.message for r in caplog.records)


@pytest.mark.asyncio
async def test_fetch_and_sync_logs_fetch_failed_event(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
    tmp_path: Path,
) -> None:
    """fetch_and_sync emits git.fetch_and_sync.fetch_failed when fetch fails (AC: #13h)."""
    mock_git = AsyncMock(side_effect=ScmError("fatal: unable to connect", details={"stderr": "network error"}))
    monkeypatch.setattr("arcwright_ai.scm.branch.git", mock_git)

    with caplog.at_level(logging.ERROR, logger="arcwright_ai.scm.branch"), pytest.raises(ScmError):
        await fetch_and_sync("main", "origin", project_root=tmp_path)

    assert any("git.fetch_and_sync.fetch_failed" in r.message for r in caplog.records)
