"""Integration tests for arcwright_ai.cli.clean — Real git cleanup operations.

All tests are marked ``@pytest.mark.slow`` and require a real git binary.
Run with ``pytest -m slow`` to include them.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from arcwright_ai.cli.clean import clean_all, clean_default
from arcwright_ai.core.constants import BRANCH_PREFIX, DIR_ARCWRIGHT, DIR_WORKTREES
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
    (tmp_path / DIR_ARCWRIGHT / DIR_WORKTREES).mkdir(parents=True)
    return tmp_path


async def _create_merged_worktree(slug: str, repo: Path) -> None:
    """Create a worktree, commit a file in it, then merge the branch into main.

    After this helper runs, ``git branch --merged`` will include
    ``arcwright/<slug>`` so the default cleanup should remove it.

    Args:
        slug: Story slug for the worktree.
        repo: Root of the git repository.
    """
    wt_path = await create_worktree(slug, project_root=repo)
    (wt_path / "story.txt").write_text(f"work for {slug}")
    await git("add", ".", cwd=wt_path)
    await git("commit", "-m", f"Work: {slug}", cwd=wt_path)
    await git("merge", "--no-ff", f"{BRANCH_PREFIX}{slug}", cwd=repo)


async def _create_unmerged_worktree(slug: str, repo: Path) -> None:
    """Create a worktree with a commit that has NOT been merged into main.

    After this helper runs, ``git branch --merged`` will NOT include
    ``arcwright/<slug>`` so the default cleanup should skip it.

    Args:
        slug: Story slug for the worktree.
        repo: Root of the git repository.
    """
    wt_path = await create_worktree(slug, project_root=repo)
    (wt_path / "story.txt").write_text(f"unmerged work for {slug}")
    await git("add", ".", cwd=wt_path)
    await git("commit", "-m", f"Unmerged: {slug}", cwd=wt_path)
    # Deliberately do NOT merge into main


# ---------------------------------------------------------------------------
# Task 7.2 — test_clean_default_removes_merged_worktree_integration
# ---------------------------------------------------------------------------


async def test_clean_default_removes_merged_worktree_integration(git_repo: Path) -> None:
    """Default cleanup removes merged worktree directory and its branch."""
    slug = "merged-story"
    branch = f"{BRANCH_PREFIX}{slug}"
    worktree_path = git_repo / DIR_ARCWRIGHT / DIR_WORKTREES / slug

    await _create_merged_worktree(slug, git_repo)
    assert worktree_path.exists()

    worktrees, branches = await clean_default(project_root=git_repo)

    assert worktrees == 1
    assert branches == 1
    assert not worktree_path.exists()

    # Branch should be gone
    branch_list = await git("branch", "--list", branch, cwd=git_repo)
    assert branch not in branch_list.stdout


# ---------------------------------------------------------------------------
# Task 7.3 — test_clean_default_preserves_unmerged_worktree_integration
# ---------------------------------------------------------------------------


async def test_clean_default_preserves_unmerged_worktree_integration(git_repo: Path) -> None:
    """Default cleanup skips worktrees with unmerged branches."""
    slug = "unmerged-story"
    branch = f"{BRANCH_PREFIX}{slug}"
    worktree_path = git_repo / DIR_ARCWRIGHT / DIR_WORKTREES / slug

    await _create_unmerged_worktree(slug, git_repo)
    assert worktree_path.exists()

    worktrees, branches = await clean_default(project_root=git_repo)

    assert worktrees == 0
    assert branches == 0
    assert worktree_path.exists()

    # Branch should still exist
    branch_list = await git("branch", "--list", branch, cwd=git_repo)
    assert branch in branch_list.stdout


# ---------------------------------------------------------------------------
# Task 7.4 — test_clean_all_removes_everything_integration
# ---------------------------------------------------------------------------


async def test_clean_all_removes_everything_integration(git_repo: Path) -> None:
    """--all cleanup removes all worktrees including unmerged ones."""
    merged_slug = "merged-story"
    unmerged_slug = "unmerged-story"
    merged_path = git_repo / DIR_ARCWRIGHT / DIR_WORKTREES / merged_slug
    unmerged_path = git_repo / DIR_ARCWRIGHT / DIR_WORKTREES / unmerged_slug

    await _create_merged_worktree(merged_slug, git_repo)
    await _create_unmerged_worktree(unmerged_slug, git_repo)

    assert merged_path.exists()
    assert unmerged_path.exists()

    worktrees, branches = await clean_all(project_root=git_repo)

    assert worktrees == 2
    assert branches == 2
    assert not merged_path.exists()
    assert not unmerged_path.exists()

    # Both branches gone
    branch_list_result = await git("branch", "--list", f"{BRANCH_PREFIX}*", cwd=git_repo)
    assert branch_list_result.stdout.strip() == ""


# ---------------------------------------------------------------------------
# Task 7.5 — test_clean_idempotent_integration
# ---------------------------------------------------------------------------


async def test_clean_idempotent_integration(git_repo: Path) -> None:
    """Running cleanup twice returns zero counts on the second call."""
    slug = "story-to-clean"

    await _create_merged_worktree(slug, git_repo)

    # First run cleans up
    worktrees1, branches1 = await clean_default(project_root=git_repo)
    assert worktrees1 == 1
    assert branches1 == 1

    # Second run is a no-op
    worktrees2, branches2 = await clean_default(project_root=git_repo)
    assert worktrees2 == 0
    assert branches2 == 0
