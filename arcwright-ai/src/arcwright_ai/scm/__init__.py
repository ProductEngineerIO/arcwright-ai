"""SCM package — Git operations, worktree management, branch strategy, and PR generation."""

from __future__ import annotations

from arcwright_ai.scm.git import GitResult, git
from arcwright_ai.scm.worktree import create_worktree, list_worktrees, remove_worktree

__all__: list[str] = [
    "GitResult",
    "create_worktree",
    "git",
    "list_worktrees",
    "remove_worktree",
]
