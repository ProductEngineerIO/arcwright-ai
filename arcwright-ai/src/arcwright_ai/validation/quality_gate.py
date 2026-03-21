"""Quality Gate — post-V3 lint, format, type-check, and test validation.

Executes after both V6 invariant checks and V3 reflexion pass.  Two-phase:

  Phase 1 (auto-fix): ``ruff check --fix`` + ``ruff format`` — deterministic,
      modifies files in-place, captures a summary of applied fixes.

  Phase 2 (check): ``ruff check``, ``mypy --strict``, ``pytest`` — diagnostic,
      exit codes determine pass/fail, stdout/stderr are captured per-tool.

All subprocesses run inside ``worktree_path / "arcwright-ai"`` because that
directory owns ``pyproject.toml``, ``src/``, and ``tests/``.
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
    """

    passed: bool
    auto_fix_summary: list[AutoFixEntry] = Field(default_factory=list)
    tool_results: list[ToolResult] = Field(default_factory=list)


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

    Runs inside the ``worktree_path / "arcwright-ai"`` subdirectory, which
    owns ``pyproject.toml``, ``src/``, and ``tests/``.

    Phase 1 (auto-fix) runs ``ruff check --fix`` and ``ruff format`` to
    eliminate trivially fixable issues before evaluation.  Phase 2 (check)
    runs ``ruff check``, ``mypy --strict``, and ``pytest``; any non-zero
    exit code yields ``FAIL_QUALITY``.

    Args:
        project_root: Root of the main repository checkout.  Retained for
            future extensibility; subprocess execution uses ``worktree_path``.
        worktree_path: Root of the isolated git worktree created by
            ``preflight_node``.  The ``arcwright-ai/`` subdirectory is used
            as ``cwd`` for all subprocess calls.
        timeout: Maximum seconds allowed for the ``pytest`` run (the longest
            tool).  ``ruff`` tools use ``_TIMEOUT_RUFF`` and ``mypy`` uses
            ``_TIMEOUT_MYPY`` regardless of this parameter.

    Returns:
        A ``QualityGateResult`` with ``passed=True`` when all check-phase
        tools exit with code 0, along with a ``QualityFeedback`` payload
        that includes the auto-fix summary and per-tool diagnostics.
    """
    # The project directory inside the worktree contains pyproject.toml, src/, tests/
    project_dir = worktree_path / "arcwright-ai"

    logger.info(
        "quality_gate.start",
        extra={"data": {"worktree": str(worktree_path), "project_dir": str(project_dir)}},
    )

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
