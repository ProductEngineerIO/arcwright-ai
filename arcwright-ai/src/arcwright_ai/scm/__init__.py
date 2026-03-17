"""SCM package — Git operations, worktree management, branch strategy, and PR generation."""

from __future__ import annotations

from arcwright_ai.scm.branch import (
    branch_exists,
    commit_story,
    create_branch,
    delete_branch,
    fetch_and_sync,
    list_branches,
)
from arcwright_ai.scm.git import GitResult, git
from arcwright_ai.scm.pr import MergeOutcome, generate_pr_body, get_pull_request_merge_sha, merge_pull_request
from arcwright_ai.scm.worktree import create_worktree, list_worktrees, remove_worktree

__all__: list[str] = [
    "GitResult",
    "MergeOutcome",
    "branch_exists",
    "commit_story",
    "create_branch",
    "create_worktree",
    "delete_branch",
    "fetch_and_sync",
    "generate_pr_body",
    "get_pull_request_merge_sha",
    "git",
    "list_branches",
    "list_worktrees",
    "merge_pull_request",
    "remove_worktree",
]
