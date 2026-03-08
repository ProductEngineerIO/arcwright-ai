"""CLI clean — Removes stale arcwright worktrees and branches.

Implements the ``arcwright-ai clean`` command with two modes:
- Default: removes only merged worktrees and branches.
- ``--all``: force-removes everything regardless of merge status.

All git operations go through :mod:`arcwright_ai.scm.git` — no subprocess
calls are made directly from this module per Decision 7.
"""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path
from typing import Annotated

import typer

from arcwright_ai.core.constants import BRANCH_PREFIX, EXIT_SCM
from arcwright_ai.core.exceptions import BranchError, ScmError, WorktreeError
from arcwright_ai.scm.branch import delete_branch, list_branches
from arcwright_ai.scm.git import git
from arcwright_ai.scm.worktree import list_worktrees, remove_worktree

__all__: list[str] = ["clean_all", "clean_command", "clean_default"]

logger = logging.getLogger(__name__)


async def _list_merged_branches(*, project_root: Path) -> set[str]:
    """Return the set of arcwright-namespaced branches merged into HEAD.

    Calls ``git branch --merged``, parses the output, and filters for branches
    starting with :data:`~arcwright_ai.core.constants.BRANCH_PREFIX`.

    Args:
        project_root: Absolute path to the root of the git repository.

    Returns:
        set[str]: Branch names (e.g. ``arcwright/my-story``) that are fully
            merged into the current HEAD.  Returns an empty set when no
            arcwright branches are merged.
    """
    result = await git("branch", "--merged", cwd=project_root)
    merged: set[str] = set()
    for line in result.stdout.splitlines():
        # git branch output prefixes:
        #   "* " — the current branch in the main worktree
        #   "+ " — a branch checked out in a linked worktree
        #   "  " — any other branch
        name = line.lstrip("*+ ").strip()
        if name.startswith(BRANCH_PREFIX):
            merged.add(name)
    return merged


async def _clean_default(project_root: Path) -> tuple[int, int]:
    """Remove completed (merged) arcwright worktrees and their branches.

    Executes two passes:
    1. Removes all worktrees whose corresponding branch is merged into HEAD.
    2. Deletes all arcwright branches that were in the merged set.

    Each removal is attempted independently — a single failure is logged
    as a warning and the rest are still processed (best-effort per AC #12).
    Branch deletion must happen after worktree removal because git refuses
    to delete a branch that is checked out in an active worktree.

    Args:
        project_root: Absolute path to the root of the git repository.

    Returns:
        tuple[int, int]: ``(worktrees_removed, branches_deleted)`` counts.
    """
    merged_branches = await _list_merged_branches(project_root=project_root)
    slugs = await list_worktrees(project_root=project_root)

    worktrees_removed = 0
    for slug in slugs:
        branch_name = BRANCH_PREFIX + slug
        if branch_name not in merged_branches:
            continue
        try:
            await remove_worktree(slug, project_root=project_root)
            worktrees_removed += 1
        except WorktreeError as exc:
            logger.warning(
                "clean.worktree.skip",
                extra={"data": {"slug": slug, "error": exc.message}},
            )

    # Second pass: delete branches (after worktree removal frees any checked-out branches)
    remaining_branches = await list_branches(project_root=project_root)
    branches_deleted = 0
    for branch_name in remaining_branches:
        if branch_name not in merged_branches:
            continue
        try:
            await delete_branch(branch_name, project_root=project_root, force=False)
            branches_deleted += 1
        except BranchError as exc:
            logger.warning(
                "clean.branch.skip",
                extra={"data": {"branch": branch_name, "error": exc.message}},
            )

    logger.info(
        "clean.default",
        extra={"data": {"worktrees_removed": worktrees_removed, "branches_deleted": branches_deleted}},
    )
    return worktrees_removed, branches_deleted


async def clean_default(*, project_root: Path) -> tuple[int, int]:
    """Public wrapper for default cleanup mode.

    Args:
        project_root: Absolute path to the root of the git repository.

    Returns:
        tuple[int, int]: ``(worktrees_removed, branches_deleted)`` counts.
    """
    return await _clean_default(project_root)


async def _clean_all(project_root: Path) -> tuple[int, int]:
    """Remove ALL arcwright worktrees and branches regardless of merge status.

    Executes two passes:
    1. Removes all arcwright-managed worktrees.
    2. Force-deletes all remaining arcwright branches (``git branch -D``).

    Each removal is best-effort: failures are logged as warnings and the
    remaining items are still processed (AC #12).

    Args:
        project_root: Absolute path to the root of the git repository.

    Returns:
        tuple[int, int]: ``(worktrees_removed, branches_deleted)`` counts.
    """
    slugs = await list_worktrees(project_root=project_root)
    worktrees_removed = 0
    for slug in slugs:
        try:
            await remove_worktree(slug, project_root=project_root)
            worktrees_removed += 1
        except WorktreeError as exc:
            logger.warning(
                "clean.worktree.skip",
                extra={"data": {"slug": slug, "error": exc.message}},
            )

    # Second pass: force-delete all arcwright branches
    remaining_branches = await list_branches(project_root=project_root)
    branches_deleted = 0
    for branch_name in remaining_branches:
        try:
            await delete_branch(branch_name, project_root=project_root, force=True)
            branches_deleted += 1
        except BranchError as exc:
            logger.warning(
                "clean.branch.skip",
                extra={"data": {"branch": branch_name, "error": exc.message}},
            )

    logger.info(
        "clean.all",
        extra={"data": {"worktrees_removed": worktrees_removed, "branches_deleted": branches_deleted}},
    )
    return worktrees_removed, branches_deleted


async def clean_all(*, project_root: Path) -> tuple[int, int]:
    """Public wrapper for ``--all`` cleanup mode.

    Args:
        project_root: Absolute path to the root of the git repository.

    Returns:
        tuple[int, int]: ``(worktrees_removed, branches_deleted)`` counts.
    """
    return await _clean_all(project_root)


def clean_command(
    all_: Annotated[
        bool,
        typer.Option("--all", help="Remove ALL arcwright worktrees and branches, including unmerged."),
    ] = False,
    project_root: Annotated[
        Path | None,
        typer.Option("--project-root", help="Root of the git repository. Defaults to the current working directory."),
    ] = None,
) -> None:
    """Remove stale arcwright worktrees and branches.

    Default mode removes only worktrees and branches that are fully merged
    into HEAD.  Use ``--all`` to force-remove everything regardless of merge
    status.  All operations are local git commands — no network required.

    Args:
        all_: When ``True``, remove all arcwright worktrees and branches
            including unmerged ones (``git branch -D``).  Defaults to
            ``False`` (merged-only, ``git branch -d``).
        project_root: Root of the git repository.  Defaults to the current
            working directory when ``None``.

    Raises:
        typer.Exit: With exit code 4 (``EXIT_SCM``) when an unrecoverable
            SCM error occurs.
    """
    resolved_root = project_root or Path.cwd()
    try:
        worktrees_removed, branches_deleted = asyncio.run(
            _clean_all(resolved_root) if all_ else _clean_default(resolved_root)
        )
    except ScmError as exc:
        typer.echo(f"Error: {exc.message}", err=True)
        raise typer.Exit(code=EXIT_SCM) from exc

    if worktrees_removed == 0 and branches_deleted == 0:
        typer.echo("Nothing to clean")
    else:
        typer.echo(f"Removed {worktrees_removed} worktree(s), deleted {branches_deleted} branch(es)")
