"""SCM package — Git operations, worktree management, branch strategy, and PR generation."""

from __future__ import annotations

from arcwright_ai.scm.branch import (
    branch_exists,
    commit_story,
    create_branch,
    delete_branch,
    list_branches,
)
from arcwright_ai.scm.git import GitResult, git
from arcwright_ai.scm.pr import generate_pr_body
from arcwright_ai.scm.worktree import create_worktree, list_worktrees, remove_worktree

__all__: list[str] = [
    "GitResult",
    "branch_exists",
    "commit_story",
    "create_branch",
    "create_worktree",
    "delete_branch",
    "generate_pr_body",
    "git",
    "list_branches",
    "list_worktrees",
    "remove_worktree",
]
