"""Core exceptions — Project-wide exception hierarchy."""

from __future__ import annotations

from typing import Any

__all__: list[str] = [
    "AgentBudgetError",
    "AgentError",
    "AgentTimeoutError",
    "ArcwrightError",
    "BranchError",
    "ConfigError",
    "ContextError",
    "ProjectError",
    "RunError",
    "ScmError",
    "ValidationError",
    "WorktreeError",
]


class ArcwrightError(Exception):
    """Base exception for all Arcwright AI errors.

    Attributes:
        message: Human-readable error description.
        details: Optional structured data for logging/debugging.
    """

    def __init__(self, message: str, details: dict[str, Any] | None = None) -> None:
        """Initialise the exception.

        Args:
            message: Human-readable description of the error.
            details: Optional structured context for logging or debugging.
        """
        super().__init__(message)
        self.message = message
        self.details = details


# ---------------------------------------------------------------------------
# Direct ArcwrightError subclasses
# ---------------------------------------------------------------------------


class ConfigError(ArcwrightError):
    """Raised when pyproject.toml or config.yaml is invalid, missing a key, or has unknown keys."""


class ProjectError(ArcwrightError):
    """Raised when the project is not initialised or the stories directory is missing."""


class ContextError(ArcwrightError):
    """Raised when a BMAD artifact cannot be read or an FR/AC reference cannot be resolved."""


class ValidationError(ArcwrightError):
    """Raised when story output fails V3 reflexion or V6 invariant checks."""


class RunError(ArcwrightError):
    """Raised on run.yaml I/O failure, state corruption, or unexpected run-directory state."""


# ---------------------------------------------------------------------------
# AgentError hierarchy
# ---------------------------------------------------------------------------


class AgentError(ArcwrightError):
    """Raised when the SDK returns an error, the session fails, or the response is malformed."""


class AgentTimeoutError(AgentError):
    """Raised when an agent session exceeds the time budget."""


class AgentBudgetError(AgentError):
    """Raised when token_ceiling or cost_ceiling is exceeded."""


# ---------------------------------------------------------------------------
# ScmError hierarchy
# ---------------------------------------------------------------------------


class ScmError(ArcwrightError):
    """Raised when a git subprocess returns non-zero, file permissions fail, or a branch conflicts."""


class WorktreeError(ScmError):
    """Raised when ``git worktree add`` or ``git worktree remove`` fails.

    The branch name should be included in ``details`` when available.
    """


class BranchError(ScmError):
    """Raised when a branch already exists or checkout fails."""
