"""Quality Gate — post-V3 lint, format, type-check, and test validation.

Executes after both V6 invariant checks and V3 reflexion pass.  Two-phase:

  Phase 1 (auto-fix): ``ruff check --fix`` + ``ruff format`` — deterministic,
      modifies files in-place, captures a summary of applied fixes.

  Phase 2 (check): ``ruff check``, ``mypy --strict``, ``pytest`` — diagnostic,
      exit codes determine pass/fail, stdout/stderr are captured per-tool.

Project type is auto-detected via ``detect_project_dir`` before any subprocess
is launched.  Non-Python and unknown project types are skipped with
``QualityGateResult.passed=True`` to avoid spurious failures against projects
that do not use the Python toolchain.
"""

from __future__ import annotations

import asyncio
import contextlib
import errno
import logging
import re
from typing import TYPE_CHECKING

from pydantic import Field

from arcwright_ai.core.types import ArcwrightModel

if TYPE_CHECKING:
    from pathlib import Path

__all__: list[str] = [
    "AutoFixEntry",
    "QualityFeedback",
    "QualityGateResult",
    "ToolResult",
    "detect_project_dir",
    "run_quality_gate",
]

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Compiled regex patterns
# ---------------------------------------------------------------------------

# Matches ruff output lines for auto-fixable issues, e.g.:
#   src/foo.py:10:1: I001 [*] Import block is un-sorted or un-formatted
#   src/baz.py:5:1: UP007 [*] Use `X | Y` for union type annotations
_RUFF_AUTOFIX_PATTERN: re.Pattern[str] = re.compile(
    r"^(.+?):(\d+):(\d+):\s+([A-Z]+\d+)\s+\[\*\]\s+(.+)$",
    re.MULTILINE,
)

# ---------------------------------------------------------------------------
# Per-tool timeout defaults (seconds)
# ---------------------------------------------------------------------------

_TIMEOUT_RUFF: int = 30
_TIMEOUT_MYPY: int = 120
_TIMEOUT_PYTEST: int = 300

# ---------------------------------------------------------------------------
# Project type detection
# ---------------------------------------------------------------------------

# Ordered list of (manifest_filename, project_type).  Earlier entries take
# priority over later ones regardless of search depth.
_MANIFEST_PRIORITY: list[tuple[str, str]] = [
    ("pyproject.toml", "python"),
    ("package.json", "node"),
    ("go.mod", "go"),
]


# ---------------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------------


class AutoFixEntry(ArcwrightModel):
    """A single auto-fix applied by ``ruff check --fix``.

    Attributes:
        file_path: Repository-relative path to the file that was modified.
        rule_id: Ruff rule identifier (e.g. ``"I001"``, ``"E501"``).
        description: Human-readable description of the applied fix.
    """

    file_path: str
    rule_id: str
    description: str


class ToolResult(ArcwrightModel):
    """Result of executing a single quality-check tool.

    Attributes:
        tool_name: Display name of the tool (e.g. ``"ruff check"``).
        passed: ``True`` when the tool exited with code 0.
        exit_code: Process exit code returned by the tool.
        stdout: Captured standard output (UTF-8, replacement errors).
        stderr: Captured standard error (UTF-8, replacement errors).
        timed_out: ``True`` when the tool exceeded its per-tool timeout.
    """

    tool_name: str
    passed: bool
    exit_code: int
    stdout: str = ""
    stderr: str = ""
    timed_out: bool = False


class QualityFeedback(ArcwrightModel):
    """Feedback payload from a Quality Gate execution.

    Consumed by ``PipelineResult.quality_feedback`` and injected into the
    retry prompt via ``build_prompt()`` when the gate fails.

    Attributes:
        passed: ``True`` only when all check-phase tools exit with code 0.
        auto_fix_summary: Auto-fixes applied during the fix phase (may be
            empty when no issues were auto-fixable).
        tool_results: Per-tool results from the check phase (ruff check,
            mypy --strict, pytest).
        skipped_reason: When set, the gate was bypassed because the detected
            project type is not yet supported by the Python toolchain.  A
            non-``None`` value means no subprocesses were launched and the
            gate passed automatically.  ``None`` means the gate ran normally.
    """

    passed: bool
    auto_fix_summary: list[AutoFixEntry] = Field(default_factory=list)
    tool_results: list[ToolResult] = Field(default_factory=list)
    skipped_reason: str | None = None


class QualityGateResult(ArcwrightModel):
    """Composite result from a Quality Gate execution run.

    Attributes:
        passed: ``True`` when all check-phase tools passed.
        feedback: Detailed feedback including auto-fix summary and per-tool
            diagnostics.
    """

    passed: bool
    feedback: QualityFeedback


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


async def _run_subprocess(
    cmd: list[str],
    *,
    cwd: Path,
    tool_name: str,
    timeout: int,
) -> ToolResult:
    """Execute a subprocess command with a per-tool timeout.

    Creates the subprocess and awaits its output using ``asyncio.wait_for``.
    On timeout the process is killed and a ``ToolResult`` with
    ``timed_out=True`` is returned rather than raising.

    Args:
        cmd: Command and argument list (first element is the executable).
        cwd: Working directory for the subprocess invocation.
        tool_name: Display name used for logging and ``ToolResult.tool_name``.
        timeout: Maximum seconds to wait for the process to finish.

    Returns:
        A ``ToolResult`` capturing stdout, stderr, exit code, and timeout flag.
    """
    logger.info(
        "quality_gate.tool.start",
        extra={"data": {"tool": tool_name, "cmd": " ".join(cmd), "cwd": str(cwd)}},
    )

    try:
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=str(cwd),
        )
    except OSError as exc:
        tool_binary = cmd[0] if cmd else tool_name
        if isinstance(exc, FileNotFoundError) or exc.errno == errno.ENOENT:
            detail = (
                f"Tool '{tool_name}' could not start because executable '{tool_binary}' was not found. "
                f"Install '{tool_binary}' and ensure it is available on PATH in the Arcwright runtime environment."
            )
        else:
            detail = (
                f"Tool '{tool_name}' could not start due to an OS error ({exc.__class__.__name__}): {exc}. "
                "Verify tool installation, permissions, and execution environment."
            )
        logger.warning(
            "quality_gate.tool.launch_error",
            extra={
                "data": {
                    "tool": tool_name,
                    "cmd": " ".join(cmd),
                    "cwd": str(cwd),
                    "error": str(exc),
                }
            },
        )
        return ToolResult(
            tool_name=tool_name,
            passed=False,
            exit_code=1,
            stdout="",
            stderr=detail,
            timed_out=False,
        )

    try:
        stdout_bytes, stderr_bytes = await asyncio.wait_for(
            proc.communicate(),
            timeout=float(timeout),
        )
    except TimeoutError:
        proc.kill()
        with contextlib.suppress(Exception):
            await proc.communicate()
        logger.warning(
            "quality_gate.tool.timeout",
            extra={"data": {"tool": tool_name, "timeout_seconds": timeout}},
        )
        return ToolResult(
            tool_name=tool_name,
            passed=False,
            exit_code=1,
            stdout="",
            stderr=f"Tool '{tool_name}' timed out after {timeout} seconds.",
            timed_out=True,
        )

    exit_code = proc.returncode if proc.returncode is not None else 1
    stdout = stdout_bytes.decode("utf-8", errors="replace")
    stderr = stderr_bytes.decode("utf-8", errors="replace")
    passed = exit_code == 0

    logger.info(
        "quality_gate.tool.complete",
        extra={"data": {"tool": tool_name, "exit_code": exit_code, "passed": passed}},
    )

    return ToolResult(
        tool_name=tool_name,
        passed=passed,
        exit_code=exit_code,
        stdout=stdout,
        stderr=stderr,
        timed_out=False,
    )


def _parse_auto_fixes(ruff_output: str) -> list[AutoFixEntry]:
    """Parse ``ruff check --fix`` output into a list of auto-fix entries.

    Only lines that include the ``[*]`` auto-fix indicator are captured;
    unfixable issues (without ``[*]``) are ignored here since they will
    appear again in the check phase.

    Args:
        ruff_output: Combined stdout+stderr from ``ruff check --fix``.

    Returns:
        List of ``AutoFixEntry`` objects, one per auto-fixed issue.
    """
    entries: list[AutoFixEntry] = []
    for match in _RUFF_AUTOFIX_PATTERN.finditer(ruff_output):
        entries.append(
            AutoFixEntry(
                file_path=match.group(1),
                rule_id=match.group(4),
                description=match.group(5).strip(),
            )
        )
    return entries


async def _run_auto_fix(cwd: Path, *, timeout: int) -> tuple[list[AutoFixEntry], list[ToolResult]]:
    """Execute the auto-fix phase: ``ruff check --fix`` then ``ruff format``.

    Parses the ``ruff check --fix`` stdout/stderr for ``[*]``-tagged issues
    to build the ``AutoFixEntry`` list.  The ``ruff format`` run is fire-and-
    forget for purposes of the summary (it does not emit per-rule diagnostics).

    Args:
        cwd: Working directory (i.e. ``worktree_path / "arcwright-ai"``).
        timeout: Per-subprocess timeout in seconds.

    Returns:
        Tuple of ``(auto_fix_summary, failing_auto_fix_tool_results)``.
    """
    fix_result = await _run_subprocess(
        ["ruff", "check", "--fix", "src/", "tests/"],
        cwd=cwd,
        tool_name="ruff check --fix",
        timeout=timeout,
    )

    combined_output = fix_result.stdout + "\n" + fix_result.stderr
    auto_fixes = _parse_auto_fixes(combined_output)
    auto_fix_tool_results: list[ToolResult] = []
    if not fix_result.passed:
        auto_fix_tool_results.append(fix_result)

    # Apply formatting (semantically neutral; all formatting divergences are fixed)
    format_result = await _run_subprocess(
        ["ruff", "format", "src/", "tests/"],
        cwd=cwd,
        tool_name="ruff format",
        timeout=timeout,
    )
    if not format_result.passed:
        auto_fix_tool_results.append(format_result)

    logger.info(
        "quality_gate.auto_fix_complete",
        extra={
            "data": {
                "auto_fixes_applied": len(auto_fixes),
                "auto_fix_tools_failed": len(auto_fix_tool_results),
            }
        },
    )
    return auto_fixes, auto_fix_tool_results


async def _run_checks(
    cwd: Path,
    *,
    timeout_ruff: int,
    timeout_mypy: int,
    timeout_pytest: int,
) -> list[ToolResult]:
    """Execute the check phase: ``ruff check``, ``mypy --strict``, ``pytest``.

    Tools run **sequentially** to avoid resource contention and to ensure
    clean per-tool diagnostic capture.  The check-phase ``ruff check`` runs
    against the already-auto-fixed code, so it only reports truly unfixable
    issues.

    Args:
        cwd: Working directory (i.e. ``worktree_path / "arcwright-ai"``).
        timeout_ruff: Per-tool timeout for ``ruff check``.
        timeout_mypy: Per-tool timeout for ``mypy --strict``.
        timeout_pytest: Per-tool timeout for ``pytest``.

    Returns:
        List of three ``ToolResult`` objects in order: ruff, mypy, pytest.
    """
    results: list[ToolResult] = []

    results.append(
        await _run_subprocess(
            ["ruff", "check", "src/", "tests/"],
            cwd=cwd,
            tool_name="ruff check",
            timeout=timeout_ruff,
        )
    )
    results.append(
        await _run_subprocess(
            ["mypy", "--strict", "src/"],
            cwd=cwd,
            tool_name="mypy --strict",
            timeout=timeout_mypy,
        )
    )
    results.append(
        await _run_subprocess(
            ["pytest"],
            cwd=cwd,
            tool_name="pytest",
            timeout=timeout_pytest,
        )
    )

    return results


def detect_project_dir(worktree_path: Path) -> tuple[str | None, Path]:
    """Determine the project type and working directory within a git worktree.

    Searches for manifest files in ``_MANIFEST_PRIORITY`` order, checking the
    worktree root (depth 0) before immediate subdirectories (depth 1).  A
    higher-priority manifest type always wins over a lower-priority one, even
    when the higher-priority manifest is found at depth 1 and a lower-priority
    manifest exists at depth 0.

    Args:
        worktree_path: Root directory of the git worktree to inspect.

    Returns:
        A ``(project_type, project_dir)`` tuple.  ``project_type`` is one of
        ``"python"``, ``"node"``, ``"go"``, or ``None`` when no supported
        manifest is found.  ``project_dir`` is the directory that contains the
        manifest file; when no manifest exists it equals ``worktree_path``.

    Emits:
        A ``quality_gate.project_type_detected`` log event with
        ``project_type`` and ``project_dir`` fields.
    """
    for filename, project_type in _MANIFEST_PRIORITY:
        # Depth 0 — check directly under worktree root
        if (worktree_path / filename).is_file():
            logger.info(
                "quality_gate.project_type_detected",
                extra={"data": {"project_type": project_type, "project_dir": str(worktree_path)}},
            )
            return (project_type, worktree_path)

        # Depth 1 — check immediate subdirectories only
        for child in worktree_path.iterdir():
            if child.is_dir() and (child / filename).is_file():
                logger.info(
                    "quality_gate.project_type_detected",
                    extra={"data": {"project_type": project_type, "project_dir": str(child)}},
                )
                return (project_type, child)

    # No recognised manifest found
    logger.info(
        "quality_gate.project_type_detected",
        extra={"data": {"project_type": None, "project_dir": str(worktree_path)}},
    )
    return (None, worktree_path)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


async def run_quality_gate(
    project_root: Path,
    worktree_path: Path,
    *,
    timeout: int = _TIMEOUT_PYTEST,
) -> QualityGateResult:
    """Orchestrate the Quality Gate: auto-fix phase then check phase.

    Detects the project type via ``detect_project_dir`` before doing any
    work.  Non-Python and unknown project types are skipped immediately;
    ``QualityGateResult.passed=True`` is returned with ``skipped_reason`` set
    in the feedback so callers can observe the bypass without misreading it as
    a quality failure.

    For Python projects, runs inside the directory that contains
    ``pyproject.toml`` (resolved by ``detect_project_dir``).

    Phase 1 (auto-fix) runs ``ruff check --fix`` and ``ruff format`` to
    eliminate trivially fixable issues before evaluation.  Phase 2 (check)
    runs ``ruff check``, ``mypy --strict``, and ``pytest``; any non-zero
    exit code yields ``FAIL_QUALITY``.

    Args:
        project_root: Root of the main repository checkout.  Retained for
            future extensibility; subprocess execution uses ``worktree_path``.
        worktree_path: Root of the isolated git worktree created by
            ``preflight_node``.  ``detect_project_dir`` locates the
            ``pyproject.toml`` within this tree and uses its parent as
            ``cwd`` for all subprocess calls.
        timeout: Maximum seconds allowed for the ``pytest`` run (the longest
            tool).  ``ruff`` tools use ``_TIMEOUT_RUFF`` and ``mypy`` uses
            ``_TIMEOUT_MYPY`` regardless of this parameter.

    Returns:
        A ``QualityGateResult`` with ``passed=True`` when all check-phase
        tools exit with code 0, along with a ``QualityFeedback`` payload
        that includes the auto-fix summary and per-tool diagnostics.  When
        the project type is not Python the result is also ``passed=True`` but
        ``feedback.skipped_reason`` is populated.
    """
    project_type, project_dir = detect_project_dir(worktree_path)

    logger.info(
        "quality_gate.start",
        extra={"data": {"worktree": str(worktree_path), "project_type": project_type, "project_dir": str(project_dir)}},
    )

    if project_type != "python":
        skip_msg = (
            f"Quality Gate skipped: project type '{project_type or 'unknown'}' is not yet supported. "
            "Gate will pass automatically."
        )
        logger.info(
            "quality_gate.skipped",
            extra={"data": {"project_type": project_type, "reason": skip_msg}},
        )
        feedback = QualityFeedback(passed=True, skipped_reason=skip_msg)
        return QualityGateResult(passed=True, feedback=feedback)

    # Phase 1: Auto-fix (ruff check --fix + ruff format)
    auto_fix_summary, auto_fix_tool_results = await _run_auto_fix(project_dir, timeout=_TIMEOUT_RUFF)

    # Phase 2: Check suite (ruff check, mypy --strict, pytest)
    tool_results = await _run_checks(
        project_dir,
        timeout_ruff=_TIMEOUT_RUFF,
        timeout_mypy=_TIMEOUT_MYPY,
        timeout_pytest=timeout,
    )
    if auto_fix_tool_results:
        tool_results = [*auto_fix_tool_results, *tool_results]

    passed = all(r.passed for r in tool_results)

    logger.info(
        "quality_gate.complete",
        extra={
            "data": {
                "passed": passed,
                "tool_results": [(r.tool_name, r.passed, r.exit_code) for r in tool_results],
                "auto_fixes_applied": len(auto_fix_summary),
            }
        },
    )

    feedback = QualityFeedback(
        passed=passed,
        auto_fix_summary=auto_fix_summary,
        tool_results=tool_results,
    )
    return QualityGateResult(passed=passed, feedback=feedback)
