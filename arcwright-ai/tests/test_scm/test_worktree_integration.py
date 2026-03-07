"""Integration tests for arcwright_ai.scm.worktree — Real git operations.

All tests are marked ``@pytest.mark.slow`` and require a real git binary.
Run with ``pytest -m slow`` to include them.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from arcwright_ai.core.constants import DIR_ARCWRIGHT, DIR_WORKTREES
from arcwright_ai.scm.git import git
from arcwright_ai.scm.worktree import create_worktree, remove_worktree

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


# ---------------------------------------------------------------------------
# AC #16a — Create worktree with real git
# ---------------------------------------------------------------------------


async def test_create_worktree_real_git(git_repo: Path) -> None:
    """Create worktree in a real repo — directory exists, branch exists, files isolated."""
    slug = "integration-story"
    branch = f"arcwright/{slug}"

    wt_path = await create_worktree(slug, project_root=git_repo)

    # Directory exists
    assert wt_path.exists()
    assert wt_path.is_dir()

    # Branch was created
    branch_result = await git("branch", "--list", branch, cwd=git_repo)
    assert branch in branch_result.stdout

    # File isolation: a file created in the main checkout is NOT present in the worktree
    # (unless it was committed before the worktree was created — README.md IS present
    # in both because it was committed before the worktree was checked out).
    # We verify the worktree directory is structurally separate from the main checkout.
    assert wt_path.resolve() != git_repo.resolve()

    # Cleanup (worktree is clean — nothing written to it, so remove succeeds without --force)
    await remove_worktree(slug, project_root=git_repo)


# ---------------------------------------------------------------------------
# AC #16b — Remove worktree with real git
# ---------------------------------------------------------------------------


async def test_remove_worktree_real_git(git_repo: Path) -> None:
    """Remove worktree — directory gone, not in git worktree list output."""
    slug = "to-be-removed"

    wt_path = await create_worktree(slug, project_root=git_repo)
    assert wt_path.exists()

    await remove_worktree(slug, project_root=git_repo)

    # Directory is gone
    assert not wt_path.exists()

    # git worktree list no longer shows it
    list_result = await git("worktree", "list", "--porcelain", cwd=git_repo)
    assert str(wt_path) not in list_result.stdout


# ---------------------------------------------------------------------------
# AC #16c — Full lifecycle: create → verify isolation → remove → verify cleanup
# ---------------------------------------------------------------------------


async def test_worktree_full_lifecycle(git_repo: Path) -> None:
    """Full lifecycle: create → write + commit file in worktree → isolated from main → remove → cleanup."""
    slug = "lifecycle-story"

    wt_path = await create_worktree(slug, project_root=git_repo)

    # Write a file inside the worktree and commit it (simulating agent output)
    isolated_file = wt_path / "lifecycle-test.txt"
    isolated_file.write_text("lifecycle content")
    assert isolated_file.exists()

    # Commit the file so the worktree is clean and can be removed normally
    await git("add", "lifecycle-test.txt", cwd=wt_path)
    await git("commit", "-m", "story: lifecycle-story output", cwd=wt_path)

    # The committed file in the worktree branch must NOT appear in main checkout
    assert not (git_repo / "lifecycle-test.txt").exists()

    # Remove the worktree (now clean after commit)
    await remove_worktree(slug, project_root=git_repo)

    # Directory is gone
    assert not wt_path.exists()

    # Main checkout is untouched
    assert (git_repo / "README.md").exists()


# ---------------------------------------------------------------------------
# AC #16d — Idempotent remove: second call is a no-op
# ---------------------------------------------------------------------------


async def test_remove_worktree_idempotent_real_git(git_repo: Path) -> None:
    """remove_worktree is idempotent — removing an already-removed worktree does not raise."""
    slug = "idempotent-story"

    await create_worktree(slug, project_root=git_repo)
    await remove_worktree(slug, project_root=git_repo)

    # Second remove — must be a no-op with no exception
    await remove_worktree(slug, project_root=git_repo)
