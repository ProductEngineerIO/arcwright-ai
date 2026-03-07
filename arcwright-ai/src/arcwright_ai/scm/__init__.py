"""SCM package — Git operations, worktree management, branch strategy, and PR generation."""

from __future__ import annotations

from arcwright_ai.scm.git import GitResult, git

# Planned public API — symbols implemented in future stories:
#   create_worktree  (scm/worktree.py — Story 6.2)
#   remove_worktree  (scm/worktree.py — Story 6.2)
#   commit_story     (scm/branch.py   — Story 6.3)
__all__: list[str] = ["GitResult", "git"]
