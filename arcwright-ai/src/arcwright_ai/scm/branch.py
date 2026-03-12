"""SCM branch — Branch management and commit strategy.

**Branch Naming Convention**
All branches are namespaced under ``arcwright/`` to keep them greppable and
isolated from any human-created branches.  Example: ``arcwright/my-story``.

**Commit Message Format**
``[arcwright] <story-title>\\n\\nStory: <story-path>\\nRun: <run-id>``

**No Force Operations**
No ``--force``, ``reset --hard``, or rebase commands are used.  An existing
branch is an error, not a silent overwrite.

**Push/PR Integration**
Branches may be pushed to a configured remote as a best-effort step after
successful local commits.

**Single Gateway (Boundary 4)**
All git subprocess calls go through :func:`arcwright_ai.scm.git.git`.  No
``subprocess`` or ``asyncio.create_subprocess_exec`` calls are made directly.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from arcwright_ai.core.constants import BRANCH_PREFIX, COMMIT_MESSAGE_TEMPLATE
from arcwright_ai.core.exceptions import BranchError, ScmError
from arcwright_ai.scm.git import git

if TYPE_CHECKING:
    from pathlib import Path

__all__: list[str] = [
    "branch_exists",
    "commit_story",
    "create_branch",
    "delete_branch",
    "delete_remote_branch",
    "list_branches",
    "push_branch",
]

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# branch_exists
# ---------------------------------------------------------------------------


async def branch_exists(branch_name: str, *, project_root: Path) -> bool:
    """Return whether a local branch exists in the repository.

    Uses ``git rev-parse --verify refs/heads/<branch_name>`` to check for a
    local branch only (not remote tracking refs or tags).

    Args:
        branch_name: Full branch name to check (e.g. ``arcwright/my-story``).
        project_root: Absolute path to the root of the git repository.

    Returns:
        bool: ``True`` if the branch exists locally, ``False`` otherwise.
    """
    try:
        await git("rev-parse", "--verify", f"refs/heads/{branch_name}", cwd=project_root)
        return True
    except ScmError as exc:
        message = (exc.message or "").lower()
        stderr = ""
        if exc.details and "stderr" in exc.details:
            stderr = str(exc.details["stderr"]).lower()

        branch_missing = any(
            phrase in text
            for phrase in ("unknown revision", "needed a single revision", "not a valid ref")
            for text in (message, stderr)
        )
        if branch_missing:
            return False

        logger.error(
            "git.branch.exists.error",
            extra={
                "data": {
                    "branch": branch_name,
                    "project_root": str(project_root),
                    "error": exc.message,
                    "details": exc.details,
                }
            },
        )
        raise


# ---------------------------------------------------------------------------
# create_branch
# ---------------------------------------------------------------------------


async def create_branch(
    story_slug: str,
    base_ref: str | None = None,
    *,
    project_root: Path,
) -> str:
    """Create a new local branch named ``arcwright/<story_slug>``.

    The branch is created at ``base_ref`` (defaulting to ``HEAD``).  If the
    branch already exists a :class:`~arcwright_ai.core.exceptions.BranchError`
    is raised — no force operations are performed per D7.

    Args:
        story_slug: Story identifier used to build the branch name.  The
            final branch name is ``arcwright/<story_slug>``.
        base_ref: Git ref at which to create the branch.  Defaults to
            ``"HEAD"`` when ``None``.
        project_root: Absolute path to the root of the git repository.

    Returns:
        str: The full branch name that was created (``arcwright/<story_slug>``).

    Raises:
        BranchError: If the branch already exists, or if the underlying git
            command fails for any other reason.
    """
    branch_name = BRANCH_PREFIX + story_slug
    resolved_base = base_ref if base_ref is not None else "HEAD"

    if await branch_exists(branch_name, project_root=project_root):
        raise BranchError(
            f"Branch '{branch_name}' already exists for story '{story_slug}'",
            details={"branch": branch_name, "story_slug": story_slug},
        )

    try:
        await git("branch", branch_name, resolved_base, cwd=project_root)
    except ScmError as exc:
        logger.error(
            "git.branch.create.error",
            extra={
                "data": {
                    "story_slug": story_slug,
                    "branch": branch_name,
                    "base_ref": resolved_base,
                    "project_root": str(project_root),
                    "error": exc.message,
                    "details": exc.details,
                }
            },
        )
        raise BranchError(
            f"Failed to create branch '{branch_name}' at '{resolved_base}'",
            details={"branch": branch_name, "story_slug": story_slug, "base_ref": resolved_base},
        ) from exc

    logger.info(
        "git.branch.create",
        extra={"data": {"story_slug": story_slug, "branch": branch_name, "base_ref": resolved_base}},
    )
    return branch_name


# ---------------------------------------------------------------------------
# commit_story
# ---------------------------------------------------------------------------


async def commit_story(
    story_slug: str,
    story_title: str,
    story_path: str,
    run_id: str,
    *,
    worktree_path: Path,
) -> str:
    """Stage all changes in a worktree and commit with a structured message.

    Stages everything with ``git add .`` then commits using
    :data:`~arcwright_ai.core.constants.COMMIT_MESSAGE_TEMPLATE`.  The
    resulting commit hash is returned.

    All operations run with ``cwd=worktree_path`` — only files in the
    worktree's working directory are staged.

    Args:
        story_slug: Story identifier for log events and error context.
        story_title: Human-readable story title used in the commit subject.
        story_path: Spec-relative path to the story file (e.g.
            ``_spec/implementation-artifacts/6-3-…md``).
        run_id: Unique run identifier embedded in the commit body.
        worktree_path: Absolute path to the worktree root where the story
            agent wrote its output.

    Returns:
        str: The full commit hash of the new commit (output of
            ``git rev-parse HEAD``).

    Raises:
        BranchError: If there are no staged changes to commit, or if the
            commit command fails for any other reason.
    """
    await git("add", ".", cwd=worktree_path)

    # Detect "nothing to commit" before attempting the commit.
    # `git status --porcelain` outputs nothing when the working tree is clean;
    # this is more reliable than parsing stderr because git emits the
    # "nothing to commit" message to stdout (not stderr) in most versions.
    status_result = await git("status", "--porcelain", cwd=worktree_path)
    if not status_result.stdout.strip():
        logger.error(
            "git.commit.error",
            extra={
                "data": {
                    "story_slug": story_slug,
                    "worktree_path": str(worktree_path),
                    "run_id": run_id,
                    "reason": "no_changes",
                }
            },
        )
        raise BranchError(
            f"No changes to commit for story '{story_slug}'",
            details={"story_slug": story_slug, "worktree_path": str(worktree_path)},
        )

    message = COMMIT_MESSAGE_TEMPLATE.format(
        story_title=story_title,
        story_path=story_path,
        run_id=run_id,
    )

    try:
        await git("commit", "-m", message, cwd=worktree_path)
    except ScmError as exc:
        stderr_lower = exc.message.lower() if exc.message else ""
        # Also check details for stderr content
        details_stderr = ""
        if exc.details and "stderr" in exc.details:
            details_stderr = str(exc.details["stderr"]).lower()

        nothing_to_commit = any(
            phrase in text
            for phrase in ("nothing to commit", "nothing added to commit")
            for text in (stderr_lower, details_stderr)
        )
        if nothing_to_commit:
            logger.error(
                "git.commit.error",
                extra={
                    "data": {
                        "story_slug": story_slug,
                        "worktree_path": str(worktree_path),
                        "run_id": run_id,
                        "reason": "nothing_to_commit",
                        "error": exc.message,
                        "details": exc.details,
                    }
                },
            )
            raise BranchError(
                f"No changes to commit for story '{story_slug}'",
                details={"story_slug": story_slug, "worktree_path": str(worktree_path)},
            ) from exc
        logger.error(
            "git.commit.error",
            extra={
                "data": {
                    "story_slug": story_slug,
                    "worktree_path": str(worktree_path),
                    "run_id": run_id,
                    "reason": "commit_failed",
                    "error": exc.message,
                    "details": exc.details,
                }
            },
        )
        raise BranchError(
            f"Commit failed for story '{story_slug}'",
            details={"story_slug": story_slug, "worktree_path": str(worktree_path)},
        ) from exc

    hash_result = await git("rev-parse", "HEAD", cwd=worktree_path)
    commit_hash = hash_result.stdout.strip()

    logger.info(
        "git.commit",
        extra={
            "data": {
                "story_slug": story_slug,
                "commit_hash": commit_hash,
                "worktree_path": str(worktree_path),
                "run_id": run_id,
            }
        },
    )
    return commit_hash


# ---------------------------------------------------------------------------
# push_branch
# ---------------------------------------------------------------------------


async def push_branch(
    branch_name: str,
    *,
    project_root: Path,
    remote: str = "origin",
) -> bool:
    """Push a local branch to a remote repository (best-effort).

    Calls ``git push <remote> <branch_name>`` via the :func:`~arcwright_ai.scm.git.git`
    wrapper.  :class:`~arcwright_ai.core.exceptions.ScmError` is caught, logged as a
    warning, and not re-raised so that push failures never halt story execution
    (AC: #1, #2).

    If the remote is already up-to-date (branch already pushed) this is a no-op —
    git treats it as a successful push (AC: #10).

    Args:
        branch_name: Full branch name to push (e.g. ``arcwright/my-story``).
        project_root: Absolute path to the root of the git repository.
        remote: Remote name to push to.  Defaults to ``"origin"``.

    Returns:
        ``True`` when push succeeded, ``False`` when push failed and was
        downgraded to warning.
    """
    try:
        await git("push", remote, branch_name, cwd=project_root)
    except ScmError as exc:
        logger.warning(
            "git.push.error",
            extra={
                "data": {
                    "branch": branch_name,
                    "remote": remote,
                    "project_root": str(project_root),
                    "error": exc.message,
                    "details": exc.details,
                }
            },
        )
        return False

    logger.info(
        "git.push",
        extra={
            "data": {
                "branch": branch_name,
                "remote": remote,
                "project_root": str(project_root),
            }
        },
    )
    return True


# ---------------------------------------------------------------------------
# delete_remote_branch
# ---------------------------------------------------------------------------


async def delete_remote_branch(
    branch_name: str,
    *,
    project_root: Path,
    remote: str = "origin",
) -> bool:
    """Delete a branch from a remote repository (best-effort).

    Calls ``git push <remote> --delete <branch_name>`` to remove the remote
    tracking branch.  This is used during stale worktree cleanup to prevent
    non-fast-forward rejections when a fresh branch is later pushed to the
    same remote ref.

    Best-effort: :class:`~arcwright_ai.core.exceptions.ScmError` is caught,
    logged as a warning, and not re-raised.  This mirrors the push_branch
    contract — remote failures never halt execution.

    Args:
        branch_name: Full branch name to delete (e.g. ``arcwright/my-story``).
        project_root: Absolute path to the root of the git repository.
        remote: Remote name.  Defaults to ``"origin"``.

    Returns:
        ``True`` when the remote branch was deleted (or did not exist),
        ``False`` when the deletion failed.
    """
    try:
        await git("push", remote, "--delete", branch_name, cwd=project_root)
    except ScmError as exc:
        # "remote ref does not exist" means the branch is already gone — success.
        stderr = ""
        if exc.details and "stderr" in exc.details:
            stderr = str(exc.details["stderr"]).lower()
        if "remote ref does not exist" in stderr or "unable to delete" in stderr:
            logger.info(
                "git.remote_branch.delete",
                extra={
                    "data": {
                        "branch": branch_name,
                        "remote": remote,
                        "already_absent": True,
                    }
                },
            )
            return True

        logger.warning(
            "git.remote_branch.delete.error",
            extra={
                "data": {
                    "branch": branch_name,
                    "remote": remote,
                    "project_root": str(project_root),
                    "error": exc.message,
                    "details": exc.details,
                }
            },
        )
        return False

    logger.info(
        "git.remote_branch.delete",
        extra={
            "data": {
                "branch": branch_name,
                "remote": remote,
            }
        },
    )
    return True


# ---------------------------------------------------------------------------
# list_branches
# ---------------------------------------------------------------------------


async def list_branches(*, project_root: Path) -> list[str]:
    """Return a sorted list of all local arcwright-namespaced branches.

    Queries ``git branch --list "arcwright/*"`` and parses the output.

    Args:
        project_root: Absolute path to the root of the git repository.

    Returns:
        list[str]: Sorted list of branch names matching ``arcwright/*``.
            Returns an empty list when no arcwright branches exist.
    """
    result = await git("branch", "--list", f"{BRANCH_PREFIX}*", cwd=project_root)
    branches: list[str] = []
    for line in result.stdout.splitlines():
        # Strip the leading "* " (current branch) or "  " (other branches)
        name = line.lstrip("* ").strip()
        if name:
            branches.append(name)
    return sorted(branches)


# ---------------------------------------------------------------------------
# delete_branch
# ---------------------------------------------------------------------------


async def delete_branch(
    branch_name: str,
    *,
    project_root: Path,
    force: bool = False,
) -> None:
    """Delete a local branch, defaulting to safe (merged-only) deletion.

    This operation is idempotent — deleting a non-existent branch is a
    no-op per NFR19.

    Args:
        branch_name: Full branch name to delete (e.g. ``arcwright/my-story``).
        project_root: Absolute path to the root of the git repository.
        force: When ``False`` (default), use ``git branch -d`` which only
            deletes if the branch is fully merged.  When ``True``, use
            ``git branch -D`` which force-deletes regardless of merge status.

    Raises:
        BranchError: If the deletion fails (e.g. branch is not fully merged
            and ``force=False``).
    """
    if not await branch_exists(branch_name, project_root=project_root):
        logger.info(
            "git.branch.delete",
            extra={"data": {"branch": branch_name, "already_absent": True}},
        )
        return

    flag = "-D" if force else "-d"
    try:
        await git("branch", flag, branch_name, cwd=project_root)
    except ScmError as exc:
        logger.error(
            "git.branch.delete.error",
            extra={
                "data": {
                    "branch": branch_name,
                    "force": force,
                    "project_root": str(project_root),
                    "error": exc.message,
                    "details": exc.details,
                }
            },
        )
        raise BranchError(
            f"Failed to delete branch '{branch_name}'",
            details={"branch": branch_name, "force": force},
        ) from exc

    logger.info(
        "git.branch.delete",
        extra={"data": {"branch": branch_name, "force": force}},
    )
