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
    fetch_and_sync,
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


# ---------------------------------------------------------------------------
# Story 9.2 — fetch_and_sync integration tests (AC: #14)
# ---------------------------------------------------------------------------


@pytest.fixture
async def bare_remote_and_clone(tmp_path: Path) -> tuple[Path, Path]:
    """Create a bare remote repo and a clone of it for fetch integration tests.

    Returns (bare_path, clone_path) where:
    - bare_path is a bare git repository acting as the "remote"
    - clone_path is a full clone with 'origin' pointing at bare_path

    Args:
        tmp_path: pytest-provided temporary directory.

    Returns:
        Tuple of (bare_repo_path, clone_path).
    """
    bare = tmp_path / "bare.git"
    clone = tmp_path / "clone"

    # Create bare repo
    await git("init", "--bare", str(bare), cwd=tmp_path)

    # Create scratch repo to populate the bare
    scratch = tmp_path / "scratch"
    scratch.mkdir()
    await git("init", cwd=scratch)
    await git("config", "user.email", "test@test.com", cwd=scratch)
    await git("config", "user.name", "Test", cwd=scratch)
    (scratch / "README.md").write_text("# Initial")
    await git("add", ".", cwd=scratch)
    await git("commit", "-m", "Initial commit", cwd=scratch)
    await git("remote", "add", "origin", str(bare), cwd=scratch)
    await git("push", "origin", "HEAD:main", cwd=scratch)

    # Clone from bare
    await git("clone", str(bare), str(clone), cwd=tmp_path)
    await git("config", "user.email", "test@test.com", cwd=clone)
    await git("config", "user.name", "Test", cwd=clone)
    # Ensure worktrees directory exists
    (clone / ".arcwright-ai" / "worktrees").mkdir(parents=True)

    return bare, clone


async def test_fetch_and_sync_real_git(bare_remote_and_clone: tuple[Path, Path]) -> None:
    """fetch_and_sync with real git + bare remote returns updated SHA (AC: #14a)."""
    bare, clone = bare_remote_and_clone

    # Push a new commit to bare from scratch
    scratch = bare.parent / "scratch"
    (scratch / "new_file.txt").write_text("New content")
    await git("add", ".", cwd=scratch)
    await git("commit", "-m", "Second commit", cwd=scratch)
    await git("push", "origin", "HEAD:main", cwd=scratch)

    # Get expected SHA from bare
    expected_result = await git("rev-parse", "main", cwd=bare)
    expected_sha = expected_result.stdout.strip()

    # fetch_and_sync should fetch and return that SHA
    result = await fetch_and_sync("main", "origin", project_root=clone)

    assert result == expected_sha


async def test_fetch_and_sync_diverged_local(bare_remote_and_clone: tuple[Path, Path]) -> None:
    """fetch_and_sync with diverged local — ff-only fails gracefully, returns remote tip (AC: #14b)."""
    bare, clone = bare_remote_and_clone
    scratch = bare.parent / "scratch"

    # Push new commit to remote so local diverges
    (scratch / "remote_only.txt").write_text("Remote")
    await git("add", ".", cwd=scratch)
    await git("commit", "-m", "Remote-only commit", cwd=scratch)
    await git("push", "origin", "HEAD:main", cwd=scratch)

    # Create a diverging local commit on clone's main branch
    await git("checkout", "main", cwd=clone)
    (clone / "local_only.txt").write_text("Local")
    await git("add", ".", cwd=clone)
    await git("commit", "--allow-empty-message", "-m", "", cwd=clone)

    # fetch_and_sync should handle ff-only failure and still return remote tip
    result_sha = await fetch_and_sync("main", "origin", project_root=clone)

    # Verify it returns a valid SHA (non-empty)
    assert len(result_sha) == 40


async def test_worktree_from_fetched_sha(bare_remote_and_clone: tuple[Path, Path]) -> None:
    """Worktree created with fetched SHA as base_ref has the correct starting commit (AC: #14c)."""
    bare, clone = bare_remote_and_clone
    scratch = bare.parent / "scratch"

    # Push a fresh commit to remote
    (scratch / "feature.txt").write_text("Feature")
    await git("add", ".", cwd=scratch)
    await git("commit", "-m", "Feature commit", cwd=scratch)
    await git("push", "origin", "HEAD:main", cwd=scratch)

    # Use fetch_and_sync to get the latest SHA
    resolved_sha = await fetch_and_sync("main", "origin", project_root=clone)

    # Create worktree using the resolved SHA
    slug = "9-2-worktree-test"
    wt_path = await create_worktree(slug, resolved_sha, project_root=clone)

    # Verify the worktree HEAD matches the resolved SHA
    head_result = await git("rev-parse", "HEAD", cwd=wt_path)
    assert head_result.stdout.strip() == resolved_sha

    # Cleanup
    from arcwright_ai.scm.worktree import remove_worktree

    await remove_worktree(slug, project_root=clone, delete_branch=True, force=True)
