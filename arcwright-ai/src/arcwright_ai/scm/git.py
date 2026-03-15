"""SCM git — Safe subprocess wrapper for git shell operations.

**Single Gateway Contract (Boundary 4)**
All git subprocess invocations in Arcwright AI MUST flow through the public
:func:`git` function defined here.  No other module may call
``subprocess.run``, ``asyncio.create_subprocess_exec``, or any other
subprocess primitive directly for git operations.  This is enforced by
code-review convention.

**No Force Operations**
As a project convention, no ``--force``, ``reset --hard``, or rebase
commands are used anywhere in the codebase.  This module does not enforce
that restriction technically, but it is documented here as the canonical
authority for all git interactions.
"""

from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING

from arcwright_ai.core.exceptions import ScmError
from arcwright_ai.core.types import ArcwrightModel

if TYPE_CHECKING:
    from pathlib import Path

__all__: list[str] = ["GitResult", "git"]

logger = logging.getLogger(__name__)

_GIT_LOCK_RETRIES: int = 3
"""Number of retry attempts allowed when ``.git/index.lock`` contention is detected."""


# ---------------------------------------------------------------------------
# Return type
# ---------------------------------------------------------------------------


class GitResult(ArcwrightModel):
    """Immutable result of a single git subprocess invocation.

    Attributes:
        stdout: Decoded standard output from the git process (trailing whitespace stripped).
        stderr: Decoded standard error from the git process (trailing whitespace stripped).
        returncode: Exit code returned by the git process.
    """

    stdout: str
    stderr: str
    returncode: int

    @property
    def success(self) -> bool:
        """Return whether the git command exited successfully.

        Returns:
            bool: ``True`` when ``returncode == 0``, ``False`` otherwise.
        """
        return self.returncode == 0


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


async def _run_git_command(args: tuple[str, ...], cwd: Path | None) -> GitResult:
    """Execute the git binary exactly once and return the raw result.

    Does NOT raise on non-zero exits — the caller is responsible for
    interpreting and handling error conditions.

    Args:
        args: Tuple of git subcommand and arguments.
        cwd: Working directory for the subprocess.  Uses the process
            working directory when ``None``.

    Returns:
        GitResult: The raw subprocess outcome.
    """
    proc = await asyncio.create_subprocess_exec(
        "git",
        *args,
        cwd=str(cwd) if cwd is not None else None,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout_bytes, stderr_bytes = await proc.communicate()
    stdout_str = stdout_bytes.decode("utf-8", errors="replace").strip()
    stderr_str = stderr_bytes.decode("utf-8", errors="replace").strip()
    return GitResult(stdout=stdout_str, stderr=stderr_str, returncode=proc.returncode)  # type: ignore[arg-type]


async def _classify_and_raise(
    args: tuple[str, ...],
    cwd: Path | None,
    result: GitResult,
    attempt: int,
    max_retries: int,
) -> bool:
    """Classify a failed git result, retry if transient, or raise ScmError.

    Args:
        args: Tuple of git subcommand and arguments.
        cwd: Working directory used for the git subprocess.
        result: Failed git result to classify.
        attempt: Zero-based attempt index for current invocation.
        max_retries: Maximum number of lock-contention retries.

    Returns:
        bool: ``True`` when the caller should retry, otherwise this function
            raises and never returns.

    Raises:
        ScmError: For all non-retryable failures and exhausted retries.
    """
    rc = result.returncode
    stderr = result.stderr

    logger.error(
        "git.command",
        extra={
            "data": {
                "args": list(args),
                "cwd": str(cwd),
                "stdout": result.stdout,
                "stderr": stderr,
                "returncode": rc,
            }
        },
    )

    if _is_lock_contention(stderr):
        if attempt < max_retries:
            logger.warning(
                "git.retry",
                extra={
                    "data": {
                        "args": list(args),
                        "attempt": attempt + 1,
                        "max_attempts": max_retries,
                        "reason": "lock_contention",
                    }
                },
            )
            await asyncio.sleep(0.1 * (2**attempt))
            return True

        raise ScmError(
            f"Git lock file contention after {max_retries} retries",
            details={
                "command": list(args),
                "stderr": stderr,
                "returncode": rc,
                "retries": max_retries,
            },
        )

    if _is_permission_denied(stderr):
        raise ScmError(
            f"Permission denied: git {' '.join(args)}",
            details={"command": list(args), "stderr": stderr, "returncode": rc},
        )

    if _is_not_a_repo(stderr):
        raise ScmError(
            f"Not a git repository: {cwd}",
            details={"command": list(args), "stderr": stderr, "returncode": rc, "cwd": str(cwd)},
        )

    command_name = args[0] if args else "(no-command)"
    raise ScmError(
        f"git {command_name} failed (exit {rc})",
        details={"command": list(args), "stderr": stderr, "returncode": rc},
    )


def _is_lock_contention(stderr: str) -> bool:
    """Return True if stderr indicates a .git/index.lock contention.

    Args:
        stderr: Standard error output from the git process.

    Returns:
        bool: ``True`` when lock contention is detected.
    """
    return "index.lock" in stderr or ("Unable to create" in stderr and ".lock" in stderr)


def _is_permission_denied(stderr: str) -> bool:
    """Return True if stderr indicates a permission denied error.

    Args:
        stderr: Standard error output from the git process.

    Returns:
        bool: ``True`` when permission denied is detected.
    """
    return "permission denied" in stderr.lower()


def _is_not_a_repo(stderr: str) -> bool:
    """Return True if stderr indicates the cwd is not inside a git repository.

    Args:
        stderr: Standard error output from the git process.

    Returns:
        bool: ``True`` when a not-a-git-repository error is detected.
    """
    return "not a git repository" in stderr.lower()


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


async def git(*args: str, cwd: Path | None = None) -> GitResult:
    """Execute a git command safely via an async subprocess.

    This is the **sole entry point** for all git subprocess invocations in
    Arcwright AI.  Every call is logged using the structured ``git.command``
    event type (Decision 8 — Logging & Observability).  Transient
    ``.git/index.lock`` failures are retried up to :data:`_GIT_LOCK_RETRIES`
    times with exponential backoff; each retry is logged as ``git.retry``.

    Args:
        *args: Git subcommand and its arguments, e.g. ``"status"``, ``"-s"``.
        cwd: Working directory for the subprocess.  Uses the process working
            directory when ``None``.

    Returns:
        GitResult: Immutable result containing ``stdout``, ``stderr``, and
            ``returncode``.  ``result.success`` is ``True`` when the process
            exited with code 0.

    Raises:
        ScmError: On any non-zero exit code.  The message is context-specific:
            lock contention, permission denied, not-a-repo, or a generic
            failure message for all other non-zero exits.  ``details`` always
            contains ``command`` (list[str]), ``stderr`` (str), and
            ``returncode`` (int).
    """
    for attempt in range(_GIT_LOCK_RETRIES + 1):
        result = await _run_git_command(args, cwd)

        if result.success:
            logger.info(
                "git.command",
                extra={
                    "data": {
                        "args": list(args),
                        "cwd": str(cwd),
                        "stdout": result.stdout,
                        "stderr": result.stderr,
                        "returncode": 0,
                        "stdout_len": len(result.stdout),
                        "stderr_len": len(result.stderr),
                    }
                },
            )
            return result

        should_retry = await _classify_and_raise(args, cwd, result, attempt, _GIT_LOCK_RETRIES)
        if should_retry:
            continue

    # Defensive guard — loop above always raises or returns before this point
    raise ScmError(  # pragma: no cover
        f"Git lock file contention after {_GIT_LOCK_RETRIES} retries",
        details={
            "command": list(args),
            "stderr": "",
            "returncode": -1,
            "retries": _GIT_LOCK_RETRIES,
        },
    )
