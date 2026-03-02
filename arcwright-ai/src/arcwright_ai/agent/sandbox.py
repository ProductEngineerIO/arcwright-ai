"""Agent sandbox — Path validation and filesystem boundary enforcement."""

from __future__ import annotations

import logging
import os
from typing import TYPE_CHECKING, Protocol, runtime_checkable

from arcwright_ai.core.constants import DIR_ARCWRIGHT, DIR_TMP
from arcwright_ai.core.exceptions import SandboxViolation

if TYPE_CHECKING:
    from pathlib import Path

__all__: list[str] = [
    "PathValidator",
    "validate_path",
    "validate_temp_path",
]

logger = logging.getLogger(__name__)


@runtime_checkable
class PathValidator(Protocol):
    """Protocol for path validation functions.

    The invoker depends on this protocol, not the concrete ``validate_path``
    function, enabling dependency injection and test doubles.
    """

    def __call__(self, path: Path, project_root: Path, operation: str) -> bool:
        """Validate that *path* is permitted for *operation* within *project_root*.

        Args:
            path: The file path to validate.
            project_root: The project root directory — the sandbox boundary.
            operation: Description of the file operation (e.g., "read", "write",
                "delete") for error context.

        Returns:
            ``True`` if the path is allowed.

        Raises:
            SandboxViolation: If the path violates sandbox rules.
        """
        ...


def validate_path(path: Path, project_root: Path, operation: str) -> bool:
    """Validate that a file operation path is within the project boundary.

    Resolves the path, checks for path traversal and symlink escapes, and
    ensures the resolved path falls within *project_root*.

    Args:
        path: The file path to validate (may be relative or absolute).
        project_root: The project root directory — the sandbox boundary.
        operation: Description of the file operation for error messages.

    Returns:
        ``True`` if the path is within the project boundary.

    Raises:
        SandboxViolation: If the path is outside the project boundary,
            contains path traversal components, or escapes via symlink.
    """
    # Defense-in-depth: reject any path containing ".." components explicitly
    if ".." in path.parts:
        logger.info(
            "agent.sandbox.deny",
            extra={
                "data": {
                    "path": str(path),
                    "operation": operation,
                    "reason": "path_traversal",
                }
            },
        )
        raise SandboxViolation(
            f"Path traversal detected in '{path}' for operation '{operation}' — '..' components are not permitted.",
            details={"path": str(path), "operation": operation},
        )

    resolved_root = project_root.resolve()
    resolved_path = path.resolve()  # also follows symlinks

    # Symlink escape: log event if the original path is a symlink
    if path.exists() and path.is_symlink():
        logger.debug(
            "agent.sandbox.symlink_resolved",
            extra={
                "data": {
                    "original": str(path),
                    "resolved": str(resolved_path),
                    "operation": operation,
                }
            },
        )

    # Boundary check using os.path.commonpath for robustness
    try:
        common = os.path.commonpath([str(resolved_root), str(resolved_path)])
        within = common == str(resolved_root)
    except ValueError:
        # commonpath raises ValueError on different drives (Windows); treat as outside
        within = False

    if not within:
        logger.info(
            "agent.sandbox.deny",
            extra={
                "data": {
                    "path": str(path),
                    "resolved": str(resolved_path),
                    "project_root": str(resolved_root),
                    "operation": operation,
                    "reason": "outside_boundary",
                }
            },
        )
        raise SandboxViolation(
            f"Path '{path}' (resolved: '{resolved_path}') is outside the project "
            f"boundary '{resolved_root}' for operation '{operation}'.",
            details={
                "path": str(path),
                "resolved": str(resolved_path),
                "project_root": str(resolved_root),
                "operation": operation,
            },
        )

    logger.debug(
        "agent.sandbox.allow",
        extra={"data": {"path": str(path), "operation": operation}},
    )
    return True


def validate_temp_path(path: Path, project_root: Path) -> bool:
    """Validate that a temp file path targets ``.arcwright-ai/tmp/`` only.

    First validates the path is within the project boundary, then checks
    it targets the designated temp directory.

    Args:
        path: The temp file path to validate.
        project_root: The project root directory.

    Returns:
        ``True`` if the path is within ``.arcwright-ai/tmp/``.

    Raises:
        SandboxViolation: If the path is outside the project boundary or
            targets a directory other than ``.arcwright-ai/tmp/``.
    """
    # First ensure within project boundary
    validate_path(path, project_root, "write_temp")

    tmp_dir = (project_root / DIR_ARCWRIGHT / DIR_TMP).resolve()
    resolved_path = path.resolve()

    if not resolved_path.is_relative_to(tmp_dir):
        logger.info(
            "agent.sandbox.deny",
            extra={
                "data": {
                    "path": str(path),
                    "resolved": str(resolved_path),
                    "expected_tmp": str(tmp_dir),
                    "reason": "wrong_temp_directory",
                }
            },
        )
        raise SandboxViolation(
            f"Temp files must target {tmp_dir}, got: {resolved_path}",
            details={
                "path": str(path),
                "resolved": str(resolved_path),
                "expected_tmp": str(tmp_dir),
            },
        )

    logger.debug(
        "agent.sandbox.allow_temp",
        extra={"data": {"path": str(path)}},
    )
    return True
