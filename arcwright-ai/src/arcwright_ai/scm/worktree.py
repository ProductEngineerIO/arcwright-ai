"""SCM worktree — Atomic worktree create/delete with recovery.

**Isolation Contract (Architectural Constraint 4)**
Git worktrees are the primary isolation and safety boundary.  Create and
remove operations are atomic: any failure during ``create_worktree`` triggers
best-effort cleanup so that no partial worktrees or orphaned branches are left
on disk.  No force operations are used in the normal create/remove paths.

**Idempotency (NFR19)**
``remove_worktree`` is a no-op when the worktree directory does not exist,
making repeated calls safe.

**Single Gateway Contract (Boundary 4)**
All git operations route through :func:`arcwright_ai.scm.git.git`.  This
module never calls ``subprocess`` directly.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import shutil
from pathlib import Path

from arcwright_ai.core.constants import BRANCH_PREFIX, DIR_ARCWRIGHT, DIR_WORKTREES
from arcwright_ai.core.exceptions import ScmError, WorktreeError
from arcwright_ai.scm.git import git

__all__: list[str] = ["create_worktree", "list_worktrees", "remove_worktree"]

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------


async def _cleanup_partial_worktree(
    worktree_path: Path,
    branch_name: str,
    project_root: Path,
) -> list[str]:
    """Best-effort cleanup after a failed ``git worktree add`` operation.

    Attempts to remove the worktree from git's tracking, scrub any partial
    directory from disk, and delete the branch if it was created.  Every
    operation is wrapped in a silent try/except — this function must NEVER
    raise.

    Args:
        worktree_path: Absolute path to the (possibly partial) worktree directory.
        branch_name: Branch that may have been created by the failed ``worktree add``.
        project_root: Root of the main git repository (used as ``cwd`` for git calls).
    """
    cleanup_actions: list[str] = []

    try:
        await git("worktree", "remove", "--force", str(worktree_path), cwd=project_root)
        cleanup_actions.append("git worktree remove --force")
    except ScmError:
        pass

    if worktree_path.exists():
        shutil.rmtree(str(worktree_path), ignore_errors=True)
        cleanup_actions.append("filesystem rmtree")

    try:
        await git("branch", "-D", branch_name, cwd=project_root)
        cleanup_actions.append("git branch -D")
    except ScmError:
        pass

    if not cleanup_actions:
        cleanup_actions.append("none")

    logger.warning(
        "git.worktree.cleanup",
        extra={
            "data": {
                "worktree_path": str(worktree_path),
                "branch": branch_name,
                "cleanup_actions": cleanup_actions,
            }
        },
    )
    return cleanup_actions


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


async def create_worktree(
    story_slug: str,
    base_ref: str | None = None,
    *,
    project_root: Path,
) -> Path:
    """Create an isolated git worktree for a story and return its path.

    Creates the worktree at ``<project_root>/.arcwright-ai/worktrees/<story_slug>``
    on a new branch named ``arcwright/<story_slug>``.  If the operation fails
    mid-way, :func:`_cleanup_partial_worktree` restores a consistent state
    before the error is re-raised.

    Args:
        story_slug: Identifier for the story (used as directory name and branch suffix).
        base_ref: Git ref to base the new branch on.  Defaults to ``HEAD`` when ``None``.
        project_root: Absolute path to the root of the main git repository.

    Returns:
        Path: Absolute path to the newly created worktree directory.

    Raises:
        WorktreeError: If a worktree for ``story_slug`` already exists, or if
            ``git worktree add`` fails for any reason.
    """
    worktree_path: Path = project_root / DIR_ARCWRIGHT / DIR_WORKTREES / story_slug

    # AC #4 — refuse to clobber an existing worktree.
    if worktree_path.exists():
        raise WorktreeError(
            f"Worktree already exists for '{story_slug}'",
            details={"path": str(worktree_path), "story_slug": story_slug},
        )

    # Ensure parent directory exists before git sees the path.
    worktree_path.parent.mkdir(parents=True, exist_ok=True)

    branch_name: str = BRANCH_PREFIX + story_slug
    resolved_base_ref: str = base_ref if base_ref is not None else "HEAD"

    # Delete stale local branch from a prior run if it still exists.
    # Arcwright-namespaced branches are exclusively tool-owned, so this is
    # safe.  Without this, ``git worktree add -b`` would fail with
    # "a branch named '...' already exists" when a prior run committed
    # but the branch was never cleaned up.
    try:
        await git("rev-parse", "--verify", f"refs/heads/{branch_name}", cwd=project_root)
        # Branch exists — delete it.
        with contextlib.suppress(ScmError):
            await git("branch", "-D", branch_name, cwd=project_root)
        logger.info(
            "git.worktree.stale_branch_cleanup",
            extra={
                "data": {
                    "story_slug": story_slug,
                    "branch": branch_name,
                }
            },
        )
    except ScmError:
        pass  # Branch does not exist — proceed normally.

    try:
        await git(
            "worktree",
            "add",
            str(worktree_path),
            "-b",
            branch_name,
            resolved_base_ref,
            cwd=project_root,
        )
    except ScmError as exc:
        cleanup_actions = await _cleanup_partial_worktree(worktree_path, branch_name, project_root)
        logger.error(
            "git.worktree.create.error",
            extra={
                "data": {
                    "story_slug": story_slug,
                    "worktree_path": str(worktree_path),
                    "branch": branch_name,
                    "base_ref": resolved_base_ref,
                    "cleanup_actions": cleanup_actions,
                    "error": exc.message,
                }
            },
        )
        raise WorktreeError(
            f"Failed to create worktree for '{story_slug}': {exc.message}. "
            f"Cleanup attempted: {', '.join(cleanup_actions)}.",
            details={
                "story_slug": story_slug,
                "worktree_path": str(worktree_path),
                "branch": branch_name,
                "base_ref": resolved_base_ref,
                "cleanup_actions": cleanup_actions,
                **(exc.details or {}),
            },
        ) from exc

    logger.info(
        "git.worktree.create",
        extra={
            "data": {
                "story_slug": story_slug,
                "worktree_path": str(worktree_path),
                "branch": branch_name,
                "base_ref": resolved_base_ref,
            }
        },
    )
    return worktree_path


async def remove_worktree(
    story_slug: str,
    *,
    project_root: Path,
    delete_branch: bool = False,
    force: bool = False,
) -> None:
    """Remove the git worktree for a story.

    Idempotent: if the worktree directory does not exist (already removed or
    never created), the call is a no-op and no error is raised.

    Args:
        story_slug: Identifier for the story whose worktree should be removed.
        project_root: Absolute path to the root of the main git repository.
        delete_branch: If True, also delete the story branch after removing the worktree.
        force: If True, pass ``--force`` to ``git worktree remove`` so that
            worktrees with modified or untracked files are removed without error.
            Use when cleaning up stale worktrees from prior escalations.

    Raises:
        WorktreeError: If ``git worktree remove`` fails for a reason other than
            the worktree already being absent.
    """
    worktree_path: Path = project_root / DIR_ARCWRIGHT / DIR_WORKTREES / story_slug

    # AC #7 & #8 — idempotent: directory already gone → no-op.
    if not worktree_path.exists():
        logger.info(
            "git.worktree.remove",
            extra={
                "data": {
                    "story_slug": story_slug,
                    "already_absent": True,
                    "branch": BRANCH_PREFIX + story_slug,
                    "branch_deleted": False,
                }
            },
        )
        return

    branch_name: str = BRANCH_PREFIX + story_slug

    git_remove_args = ["worktree", "remove"]
    if force:
        git_remove_args.append("--force")
    git_remove_args.append(str(worktree_path))

    try:
        await git(*git_remove_args, cwd=project_root)
    except ScmError as exc:
        # If the directory existed but git no longer tracks the worktree (race
        # condition or leftover directory), treat the missing-worktree case as
        # success by checking if the directory is now gone.
        if not worktree_path.exists():
            # Directory is gone — consider this a success.
            pass
        elif force:
            # When force=True, git may fail for several reasons:
            # - "directory not empty": git's own rmdir can't handle subdirs
            # - "is not a working tree": directory exists but unregistered in git
            # In all such cases fall back to shutil.rmtree + git worktree prune.
            stderr_lower = (exc.details or {}).get("stderr", "").lower()
            if "directory not empty" in stderr_lower:
                reason = "directory_not_empty_fallback"
            elif "is not a working tree" in stderr_lower:
                reason = "unregistered_worktree_fallback"
            else:
                reason = "force_rmtree_fallback"
            logger.info(
                "git.worktree.force_rmtree",
                extra={
                    "data": {
                        "story_slug": story_slug,
                        "worktree_path": str(worktree_path),
                        "reason": reason,
                    }
                },
            )
            await asyncio.to_thread(shutil.rmtree, str(worktree_path), ignore_errors=True)
            # Prune git's now-dangling worktree reference.
            with contextlib.suppress(ScmError):
                await git("worktree", "prune", cwd=project_root)
        else:
            logger.error(
                "git.worktree.remove.error",
                extra={
                    "data": {
                        "story_slug": story_slug,
                        "worktree_path": str(worktree_path),
                        "branch": branch_name,
                        "delete_branch": delete_branch,
                        "error": exc.message,
                    }
                },
            )
            raise WorktreeError(
                f"Failed to remove worktree for '{story_slug}': {exc.message}",
                details={
                    "story_slug": story_slug,
                    "worktree_path": str(worktree_path),
                    "branch": branch_name,
                    "delete_branch": delete_branch,
                    **(exc.details or {}),
                },
            ) from exc

    branch_deleted = False
    if delete_branch:
        with contextlib.suppress(ScmError):
            await git("branch", "-D", branch_name, cwd=project_root)
            branch_deleted = True

    logger.info(
        "git.worktree.remove",
        extra={
            "data": {
                "story_slug": story_slug,
                "worktree_path": str(worktree_path),
                "branch": branch_name,
                "branch_deleted": branch_deleted,
            }
        },
    )


async def list_worktrees(*, project_root: Path) -> list[str]:
    """Return story slugs for all active arcwright-managed worktrees.

    Parses the ``git worktree list --porcelain`` output and filters for
    worktrees whose path falls under ``.arcwright-ai/worktrees/``.

    Args:
        project_root: Absolute path to the root of the main git repository.

    Returns:
        list[str]: Sorted list of story slugs for all currently active
            arcwright-managed worktrees.  Returns an empty list when none exist.
    """
    result = await git("worktree", "list", "--porcelain", cwd=project_root)

    slugs: list[str] = []

    for line in result.stdout.splitlines():
        if not line.startswith("worktree "):
            continue
        path_str = line[len("worktree ") :]
        path_parts = Path(path_str).parts
        for index, part in enumerate(path_parts):
            if part != DIR_ARCWRIGHT:
                continue
            if index + 2 >= len(path_parts):
                continue
            if path_parts[index + 1] != DIR_WORKTREES:
                continue
            slugs.append(path_parts[index + 2])
            break

    return sorted(slugs)
