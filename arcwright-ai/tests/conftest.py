"""Pytest configuration and shared fixtures for Arcwright AI tests."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pathlib import Path

import pytest

from arcwright_ai.scm.git import git


@pytest.fixture
async def bare_remote_and_clone(tmp_path: Path) -> tuple[Path, Path, Path]:
    """Create a bare remote repo, a working clone, and a scratch clone for test scenarios.

    Sets up a three-node git topology used by SCM integration tests:

    - ``bare`` acts as the "remote" server (bare repository)
    - ``clone`` acts as the CI/CD main clone where worktrees are created
    - ``scratch`` acts as a secondary clone used to simulate PR merge operations

    Args:
        tmp_path: pytest-provided temporary directory.

    Returns:
        Tuple of (bare_repo_path, clone_path, scratch_path).
    """
    bare = tmp_path / "bare.git"
    clone = tmp_path / "clone"
    scratch = tmp_path / "scratch"

    # Create bare repo
    await git("init", "--bare", str(bare), cwd=tmp_path)

    # Populate the bare repo via scratch
    scratch.mkdir()
    await git("init", cwd=scratch)
    await git("config", "user.email", "test@test.com", cwd=scratch)
    await git("config", "user.name", "Test", cwd=scratch)
    (scratch / "README.md").write_text("# Initial\n")
    await git("add", ".", cwd=scratch)
    await git("commit", "-m", "Initial commit", cwd=scratch)
    await git("remote", "add", "origin", str(bare), cwd=scratch)
    await git("push", "origin", "HEAD:main", cwd=scratch)

    # Clone from bare (this is the "main" clone used for worktrees)
    await git("clone", str(bare), str(clone), cwd=tmp_path)
    await git("config", "user.email", "test@test.com", cwd=clone)
    await git("config", "user.name", "Test", cwd=clone)
    (clone / ".arcwright-ai" / "worktrees").mkdir(parents=True)

    return bare, clone, scratch


@pytest.fixture
def tmp_project(tmp_path: Path) -> Path:
    """Scaffold a minimal Arcwright AI project directory for integration tests.

    Creates the expected directory layout under a temporary path::

        .arcwright-ai/   — runtime state directory (runs, provenance, tmp)
        _spec/           — BMAD planning artifacts directory

    Returns:
        Path: Root of the temporary project directory.
    """
    (tmp_path / ".arcwright-ai").mkdir()
    (tmp_path / "_spec").mkdir()
    return tmp_path
