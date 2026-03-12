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
    assert expected_msg == "[arcwright] My Story\n\nStory: _spec/s.md\nRun: 20260307-001122-abc123"


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
    raw_output = "  arcwright/story-z\n* arcwright/story-a\n  arcwright/story-m"
    mock_git = AsyncMock(return_value=_ok(stdout=raw_output))
    monkeypatch.setattr("arcwright_ai.scm.branch.git", mock_git)

    result = await list_branches(project_root=tmp_path)

    assert result == ["arcwright/story-a", "arcwright/story-m", "arcwright/story-z"]
    mock_git.assert_called_once_with("branch", "--list", "arcwright/*", cwd=tmp_path)


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
            details={"stderr": "error: unable to delete 'arcwright/my-story': remote ref does not exist"},
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
