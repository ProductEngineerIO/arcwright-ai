"""Integration tests for arcwright_ai.scm.branch — Real git operations.

All tests are marked ``@pytest.mark.slow`` and require a real git binary.
Run with ``pytest -m slow`` to include them.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from arcwright_ai.scm.branch import (
    branch_exists,
    commit_story,
    create_branch,
    delete_branch,
    list_branches,
)
from arcwright_ai.scm.git import git
from arcwright_ai.scm.worktree import create_worktree

if TYPE_CHECKING:
    from pathlib import Path

pytestmark = [pytest.mark.slow, pytest.mark.asyncio]


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
async def git_repo(tmp_path: Path) -> Path:
    """Create a real git repository with an initial commit for integration testing.

    Args:
        tmp_path: pytest-provided temporary directory.

    Returns:
        Path: Root of the initialised git repository.
    """
    await git("init", cwd=tmp_path)
    await git("config", "user.email", "test@test.com", cwd=tmp_path)
    await git("config", "user.name", "Test", cwd=tmp_path)
    (tmp_path / "README.md").write_text("# Test")
    await git("add", ".", cwd=tmp_path)
    await git("commit", "-m", "Initial commit", cwd=tmp_path)
    (tmp_path / ".arcwright-ai" / "worktrees").mkdir(parents=True)
    return tmp_path


# ---------------------------------------------------------------------------
# AC #16a — Create branch with real git
# ---------------------------------------------------------------------------


async def test_create_branch_real_git(git_repo: Path) -> None:
    """Create branch in real repo — verify it appears in git branch --list."""
    slug = "integration-story"
    branch = f"arcwright-ai/{slug}"

    result = await create_branch(slug, project_root=git_repo)

    assert result == branch

    # Verify branch now exists via git
    list_result = await git("branch", "--list", branch, cwd=git_repo)
    assert branch in list_result.stdout

    # Cleanup
    await delete_branch(f"arcwright-ai/{slug}", project_root=git_repo, force=True)


# ---------------------------------------------------------------------------
# AC #16b — Create branch that already exists raises BranchError
# ---------------------------------------------------------------------------


async def test_create_branch_existing_raises_error(git_repo: Path) -> None:
    """Creating a branch that already exists raises BranchError."""
    from arcwright_ai.core.exceptions import BranchError

    slug = "duplicate-story"

    await create_branch(slug, project_root=git_repo)

    with pytest.raises(BranchError, match="already exists"):
        await create_branch(slug, project_root=git_repo)

    # Cleanup
    await delete_branch(f"arcwright-ai/{slug}", project_root=git_repo, force=True)


# ---------------------------------------------------------------------------
# AC #16c — Commit story with real git
# ---------------------------------------------------------------------------


async def test_commit_story_real_git(git_repo: Path) -> None:
    """commit_story commits changes in a real worktree — commit appears in git log."""
    slug = "commit-story"

    # Create a worktree (which also creates the branch)
    wt_path = await create_worktree(slug, project_root=git_repo)

    # Write a file into the worktree
    (wt_path / "output.md").write_text("# Agent output\n\nsome content")

    # Commit it
    commit_hash = await commit_story(
        story_slug=slug,
        story_title="Commit Story",
        story_path=f"_spec/implementation-artifacts/{slug}.md",
        run_id="20260307-120000-test001",
        worktree_path=wt_path,
    )

    assert commit_hash  # non-empty string

    # Verify commit in git log
    log_result = await git("log", "--oneline", cwd=wt_path)
    assert "[arcwright-ai] Commit Story" in log_result.stdout

    # Verify commit message body contains Story: and Run:
    full_log = await git("log", "-1", "--format=%B", cwd=wt_path)
    assert "Story:" in full_log.stdout
    assert "Run:" in full_log.stdout
    assert "20260307-120000-test001" in full_log.stdout

    # Cleanup — remove worktree (worktree must be clean after commit)
    from arcwright_ai.scm.worktree import remove_worktree

    await remove_worktree(slug, project_root=git_repo, delete_branch=True)


# ---------------------------------------------------------------------------
# AC #16d — Commit story with no changes raises BranchError
# ---------------------------------------------------------------------------


async def test_commit_story_no_changes_raises_error(git_repo: Path) -> None:
    """commit_story raises BranchError when there are no changes to commit."""
    from arcwright_ai.core.exceptions import BranchError

    slug = "no-changes-story"
    wt_path = await create_worktree(slug, project_root=git_repo)

    with pytest.raises(BranchError, match="No changes to commit"):
        await commit_story(
            story_slug=slug,
            story_title="No Changes",
            story_path=f"_spec/{slug}.md",
            run_id="20260307-120000-test002",
            worktree_path=wt_path,
        )

    # Cleanup (worktree has no commit, force-remove)
    await git("worktree", "remove", "--force", str(wt_path), cwd=git_repo)
    await delete_branch(f"arcwright-ai/{slug}", project_root=git_repo, force=True)


# ---------------------------------------------------------------------------
# AC #16e — branch_exists returns correct values
# ---------------------------------------------------------------------------


async def test_branch_exists_real_git(git_repo: Path) -> None:
    """branch_exists returns True for existing branch and False for non-existent."""
    slug = "exists-story"
    branch = f"arcwright-ai/{slug}"

    # Before creation
    assert await branch_exists(branch, project_root=git_repo) is False

    await create_branch(slug, project_root=git_repo)

    # After creation
    assert await branch_exists(branch, project_root=git_repo) is True

    # Non-existent
    assert await branch_exists("arcwright-ai/does-not-exist", project_root=git_repo) is False

    # Cleanup
    await delete_branch(branch, project_root=git_repo, force=True)


# ---------------------------------------------------------------------------
# AC #16f — list_branches returns correct arcwright branches
# ---------------------------------------------------------------------------


async def test_list_branches_real_git(git_repo: Path) -> None:
    """list_branches returns all arcwright branches, sorted."""
    slugs = ["zeta-story", "alpha-story", "mu-story"]
    branches = [f"arcwright-ai/{s}" for s in slugs]

    for slug in slugs:
        await create_branch(slug, project_root=git_repo)

    result = await list_branches(project_root=git_repo)

    # All created branches are present
    for branch in branches:
        assert branch in result

    # Result is sorted
    assert result == sorted(result)

    # Cleanup
    for branch in branches:
        await delete_branch(branch, project_root=git_repo, force=True)


# ---------------------------------------------------------------------------
# AC #16g — Delete branch with real git
# ---------------------------------------------------------------------------


async def test_delete_branch_real_git(git_repo: Path) -> None:
    """delete_branch removes the branch — no longer appears in git branch --list."""
    slug = "to-delete-story"
    branch = f"arcwright-ai/{slug}"

    await create_branch(slug, project_root=git_repo)
    assert await branch_exists(branch, project_root=git_repo) is True

    await delete_branch(branch, project_root=git_repo, force=True)

    assert await branch_exists(branch, project_root=git_repo) is False

    # Verify via git branch --list
    list_result = await git("branch", "--list", branch, cwd=git_repo)
    assert branch not in list_result.stdout


# ---------------------------------------------------------------------------
# AC #16h — Delete non-existent branch is idempotent
# ---------------------------------------------------------------------------


async def test_delete_branch_idempotent_real_git(git_repo: Path) -> None:
    """Deleting a non-existent branch raises no error (idempotent)."""
    branch = "arcwright-ai/never-created"

    # Should not raise
    await delete_branch(branch, project_root=git_repo)
    await delete_branch(branch, project_root=git_repo)
