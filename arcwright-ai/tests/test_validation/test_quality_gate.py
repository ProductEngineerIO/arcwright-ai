"""Unit tests for arcwright_ai.validation.quality_gate (Story 10.12)."""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from arcwright_ai.validation.quality_gate import (
    AutoFixEntry,
    QualityFeedback,
    QualityGateResult,
    ToolResult,
    _parse_auto_fixes,  # type: ignore[reportPrivateUsage]
    _run_auto_fix,  # type: ignore[reportPrivateUsage]
    _run_checks,  # type: ignore[reportPrivateUsage]
    _run_subprocess,  # type: ignore[reportPrivateUsage]
    run_quality_gate,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

PROJECT_ROOT = Path("/project")
WORKTREE_PATH = Path("/project/.arcwright-ai/worktrees/10-12-story")
PROJECT_DIR = WORKTREE_PATH / "arcwright-ai"


# ---------------------------------------------------------------------------
# Test 6.1 — _run_subprocess: success, failure, timeout
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_run_subprocess_success(tmp_path: Path) -> None:
    """_run_subprocess returns passed=True for exit code 0."""
    result = await _run_subprocess(
        ["python3", "-c", "print('ok')"],
        cwd=tmp_path,
        tool_name="python test",
        timeout=10,
    )
    assert result.passed is True
    assert result.exit_code == 0
    assert result.timed_out is False
    assert "ok" in result.stdout


@pytest.mark.asyncio
async def test_run_subprocess_failure(tmp_path: Path) -> None:
    """_run_subprocess returns passed=False for non-zero exit code."""
    result = await _run_subprocess(
        ["python3", "-c", "import sys; sys.exit(1)"],
        cwd=tmp_path,
        tool_name="python fail",
        timeout=10,
    )
    assert result.passed is False
    assert result.exit_code == 1
    assert result.timed_out is False


@pytest.mark.asyncio
async def test_run_subprocess_captures_stderr(tmp_path: Path) -> None:
    """_run_subprocess captures stderr output."""
    result = await _run_subprocess(
        ["python3", "-c", "import sys; sys.stderr.write('err output\\n')"],
        cwd=tmp_path,
        tool_name="python stderr",
        timeout=10,
    )
    assert "err output" in result.stderr


@pytest.mark.asyncio
async def test_run_subprocess_timeout(tmp_path: Path) -> None:
    """_run_subprocess treats exceeded timeout as failure with timed_out=True."""
    result = await _run_subprocess(
        ["python3", "-c", "import time; time.sleep(10)"],
        cwd=tmp_path,
        tool_name="slow tool",
        timeout=1,
    )
    assert result.passed is False
    assert result.timed_out is True
    assert result.exit_code == 1
    assert "timed out" in result.stderr.lower()


@pytest.mark.asyncio
async def test_run_subprocess_tool_name_in_result(tmp_path: Path) -> None:
    """_run_subprocess preserves tool_name in the returned ToolResult."""
    result = await _run_subprocess(
        ["python3", "-c", "pass"],
        cwd=tmp_path,
        tool_name="my-custom-tool",
        timeout=10,
    )
    assert result.tool_name == "my-custom-tool"


@pytest.mark.asyncio
async def test_run_subprocess_launch_error_returns_actionable_diagnostic(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Missing executable is treated as a failed ToolResult with actionable guidance."""

    async def _raise_missing(*args: object, **kwargs: object) -> object:
        raise FileNotFoundError("No such file or directory")

    monkeypatch.setattr(asyncio, "create_subprocess_exec", _raise_missing)
    result = await _run_subprocess(
        ["ruff", "check", "src/"],
        cwd=tmp_path,
        tool_name="ruff check",
        timeout=10,
    )
    assert result.passed is False
    assert result.timed_out is False
    assert "not found" in result.stderr.lower()
    assert "install 'ruff'" in result.stderr.lower()


# ---------------------------------------------------------------------------
# Test 6.2 — _run_auto_fix: no changes, fixes applied, captures summary
# ---------------------------------------------------------------------------


def test_parse_auto_fixes_no_fixable_output() -> None:
    """_parse_auto_fixes returns empty list when ruff output has no [*] entries."""
    ruff_output = "src/foo.py:10:1: E501 Line too long (100 > 88)\n"
    fixes = _parse_auto_fixes(ruff_output)
    assert fixes == []


def test_parse_auto_fixes_single_fix() -> None:
    """_parse_auto_fixes extracts one AutoFixEntry from a single [*] line."""
    ruff_output = "src/foo.py:10:1: I001 [*] Import block is un-sorted or un-formatted\n"
    fixes = _parse_auto_fixes(ruff_output)
    assert len(fixes) == 1
    assert fixes[0].file_path == "src/foo.py"
    assert fixes[0].rule_id == "I001"
    assert fixes[0].description == "Import block is un-sorted or un-formatted"


def test_parse_auto_fixes_multiple_fixes() -> None:
    """_parse_auto_fixes extracts multiple AutoFixEntry objects from multi-line output."""
    ruff_output = (
        "src/foo.py:10:1: I001 [*] Import block is un-sorted or un-formatted\n"
        "src/bar.py:25:5: F841 local variable 'x' is assigned to but never used\n"
        "src/baz.py:5:1: UP007 [*] Use `X | Y` for union type annotations\n"
    )
    fixes = _parse_auto_fixes(ruff_output)
    assert len(fixes) == 2
    assert fixes[0].file_path == "src/foo.py"
    assert fixes[0].rule_id == "I001"
    assert fixes[1].file_path == "src/baz.py"
    assert fixes[1].rule_id == "UP007"


@pytest.mark.asyncio
async def test_run_auto_fix_no_changes(monkeypatch: pytest.MonkeyPatch) -> None:
    """_run_auto_fix returns empty fixes and no failures when auto-fix tools pass."""

    async def _mock_subprocess(cmd: list[str], *, cwd: Path, tool_name: str, timeout: int) -> ToolResult:
        # ruff check --fix with no fixes: empty stdout
        return ToolResult(tool_name=tool_name, passed=True, exit_code=0, stdout="", stderr="")

    monkeypatch.setattr("arcwright_ai.validation.quality_gate._run_subprocess", _mock_subprocess)
    fixes, failed_tools = await _run_auto_fix(PROJECT_DIR, timeout=30)
    assert fixes == []
    assert failed_tools == []


@pytest.mark.asyncio
async def test_run_auto_fix_with_fixes_applied(monkeypatch: pytest.MonkeyPatch) -> None:
    """_run_auto_fix returns AutoFixEntry list when ruff check --fix applied fixes."""
    fix_calls: list[str] = []

    async def _mock_subprocess(cmd: list[str], *, cwd: Path, tool_name: str, timeout: int) -> ToolResult:
        fix_calls.append(tool_name)
        if tool_name == "ruff check --fix":
            stdout = "src/foo.py:10:1: I001 [*] Import block is un-sorted or un-formatted\n"
            return ToolResult(tool_name=tool_name, passed=True, exit_code=0, stdout=stdout, stderr="")
        # ruff format
        return ToolResult(tool_name=tool_name, passed=True, exit_code=0, stdout="", stderr="")

    monkeypatch.setattr("arcwright_ai.validation.quality_gate._run_subprocess", _mock_subprocess)
    fixes, failed_tools = await _run_auto_fix(PROJECT_DIR, timeout=30)
    assert len(fixes) == 1
    assert fixes[0].rule_id == "I001"
    assert failed_tools == []
    # Both ruff check --fix and ruff format were called
    assert "ruff check --fix" in fix_calls
    assert "ruff format" in fix_calls


@pytest.mark.asyncio
async def test_run_auto_fix_calls_both_tools(monkeypatch: pytest.MonkeyPatch) -> None:
    """_run_auto_fix calls ruff check --fix then ruff format."""
    called: list[str] = []

    async def _mock_subprocess(cmd: list[str], *, cwd: Path, tool_name: str, timeout: int) -> ToolResult:
        called.append(tool_name)
        return ToolResult(tool_name=tool_name, passed=True, exit_code=0, stdout="", stderr="")

    monkeypatch.setattr("arcwright_ai.validation.quality_gate._run_subprocess", _mock_subprocess)
    _, _ = await _run_auto_fix(PROJECT_DIR, timeout=30)
    assert called == ["ruff check --fix", "ruff format"]


@pytest.mark.asyncio
async def test_run_auto_fix_collects_failed_auto_fix_tools(monkeypatch: pytest.MonkeyPatch) -> None:
    """_run_auto_fix surfaces failures from ruff check --fix and/or ruff format."""

    async def _mock_subprocess(cmd: list[str], *, cwd: Path, tool_name: str, timeout: int) -> ToolResult:
        if tool_name == "ruff check --fix":
            return ToolResult(tool_name=tool_name, passed=False, exit_code=1, stderr="ruff unavailable")
        return ToolResult(tool_name=tool_name, passed=True, exit_code=0, stdout="", stderr="")

    monkeypatch.setattr("arcwright_ai.validation.quality_gate._run_subprocess", _mock_subprocess)
    fixes, failed_tools = await _run_auto_fix(PROJECT_DIR, timeout=30)
    assert fixes == []
    assert len(failed_tools) == 1
    assert failed_tools[0].tool_name == "ruff check --fix"


# ---------------------------------------------------------------------------
# Test 6.3 — _run_checks: all pass, some fail, timeout on one tool
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_run_checks_all_pass(monkeypatch: pytest.MonkeyPatch) -> None:
    """_run_checks returns three passing ToolResults when all tools exit 0."""

    async def _mock_subprocess(cmd: list[str], *, cwd: Path, tool_name: str, timeout: int) -> ToolResult:
        return ToolResult(tool_name=tool_name, passed=True, exit_code=0, stdout="All good", stderr="")

    monkeypatch.setattr("arcwright_ai.validation.quality_gate._run_subprocess", _mock_subprocess)
    results = await _run_checks(PROJECT_DIR, timeout_ruff=30, timeout_mypy=120, timeout_pytest=300)
    assert len(results) == 3
    assert all(r.passed for r in results)
    tool_names = [r.tool_name for r in results]
    assert "ruff check" in tool_names
    assert "mypy --strict" in tool_names
    assert "pytest" in tool_names


@pytest.mark.asyncio
async def test_run_checks_some_fail(monkeypatch: pytest.MonkeyPatch) -> None:
    """_run_checks returns failing ToolResult for tools that exit non-zero."""

    async def _mock_subprocess(cmd: list[str], *, cwd: Path, tool_name: str, timeout: int) -> ToolResult:
        if tool_name == "mypy --strict":
            return ToolResult(tool_name=tool_name, passed=False, exit_code=1, stdout="", stderr="error: Missing return")
        return ToolResult(tool_name=tool_name, passed=True, exit_code=0, stdout="", stderr="")

    monkeypatch.setattr("arcwright_ai.validation.quality_gate._run_subprocess", _mock_subprocess)
    results = await _run_checks(PROJECT_DIR, timeout_ruff=30, timeout_mypy=120, timeout_pytest=300)
    assert len(results) == 3
    mypy_result = next(r for r in results if r.tool_name == "mypy --strict")
    assert mypy_result.passed is False
    assert "Missing return" in mypy_result.stderr


@pytest.mark.asyncio
async def test_run_checks_timeout_on_one_tool(monkeypatch: pytest.MonkeyPatch) -> None:
    """_run_checks returns timed_out=True for a tool that times out."""

    async def _mock_subprocess(cmd: list[str], *, cwd: Path, tool_name: str, timeout: int) -> ToolResult:
        if tool_name == "pytest":
            return ToolResult(
                tool_name=tool_name,
                passed=False,
                exit_code=1,
                stdout="",
                stderr="Tool 'pytest' timed out after 300 seconds.",
                timed_out=True,
            )
        return ToolResult(tool_name=tool_name, passed=True, exit_code=0, stdout="", stderr="")

    monkeypatch.setattr("arcwright_ai.validation.quality_gate._run_subprocess", _mock_subprocess)
    results = await _run_checks(PROJECT_DIR, timeout_ruff=30, timeout_mypy=120, timeout_pytest=300)
    pytest_result = next(r for r in results if r.tool_name == "pytest")
    assert pytest_result.passed is False
    assert pytest_result.timed_out is True


@pytest.mark.asyncio
async def test_run_checks_all_three_run_sequentially(monkeypatch: pytest.MonkeyPatch) -> None:
    """_run_checks executes all three tools and returns a list of three results."""
    called: list[str] = []

    async def _mock_subprocess(cmd: list[str], *, cwd: Path, tool_name: str, timeout: int) -> ToolResult:
        called.append(tool_name)
        return ToolResult(tool_name=tool_name, passed=True, exit_code=0, stdout="", stderr="")

    monkeypatch.setattr("arcwright_ai.validation.quality_gate._run_subprocess", _mock_subprocess)
    results = await _run_checks(PROJECT_DIR, timeout_ruff=30, timeout_mypy=120, timeout_pytest=300)
    assert len(results) == 3
    assert called == ["ruff check", "mypy --strict", "pytest"]


# ---------------------------------------------------------------------------
# Test 6.4 — run_quality_gate: full pass, auto-fix only, check failures
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_auto_fix_no_changes(monkeypatch: pytest.MonkeyPatch) -> None:
    """Monkeypatch _run_auto_fix to return empty fix list and no failures."""

    async def _auto_fix(cwd: Path, *, timeout: int) -> tuple[list[AutoFixEntry], list[ToolResult]]:
        return [], []

    monkeypatch.setattr("arcwright_ai.validation.quality_gate._run_auto_fix", _auto_fix)


@pytest.fixture
def mock_checks_all_pass(monkeypatch: pytest.MonkeyPatch) -> None:
    """Monkeypatch _run_checks to return all-pass results."""

    async def _checks(
        cwd: Path,
        *,
        timeout_ruff: int,
        timeout_mypy: int,
        timeout_pytest: int,
    ) -> list[ToolResult]:
        return [
            ToolResult(tool_name="ruff check", passed=True, exit_code=0),
            ToolResult(tool_name="mypy --strict", passed=True, exit_code=0),
            ToolResult(tool_name="pytest", passed=True, exit_code=0),
        ]

    monkeypatch.setattr("arcwright_ai.validation.quality_gate._run_checks", _checks)


@pytest.fixture
def mock_checks_mypy_fail(monkeypatch: pytest.MonkeyPatch) -> None:
    """Monkeypatch _run_checks so only mypy fails."""

    async def _checks(
        cwd: Path,
        *,
        timeout_ruff: int,
        timeout_mypy: int,
        timeout_pytest: int,
    ) -> list[ToolResult]:
        return [
            ToolResult(tool_name="ruff check", passed=True, exit_code=0),
            ToolResult(
                tool_name="mypy --strict",
                passed=False,
                exit_code=1,
                stderr="error: Missing return statement  [return]",
            ),
            ToolResult(tool_name="pytest", passed=True, exit_code=0),
        ]

    monkeypatch.setattr("arcwright_ai.validation.quality_gate._run_checks", _checks)


@pytest.mark.asyncio
async def test_run_quality_gate_full_pass(
    mock_auto_fix_no_changes: None,
    mock_checks_all_pass: None,
) -> None:
    """run_quality_gate returns QualityGateResult with passed=True when all tools pass."""
    result = await run_quality_gate(PROJECT_ROOT, WORKTREE_PATH)
    assert result.passed is True
    assert result.feedback.passed is True
    assert result.feedback.auto_fix_summary == []
    assert len(result.feedback.tool_results) == 3
    assert all(r.passed for r in result.feedback.tool_results)


@pytest.mark.asyncio
async def test_run_quality_gate_auto_fix_only(
    monkeypatch: pytest.MonkeyPatch,
    mock_checks_all_pass: None,
) -> None:
    """run_quality_gate captures auto-fix summary even when checks all pass."""

    async def _auto_fix(cwd: Path, *, timeout: int) -> tuple[list[AutoFixEntry], list[ToolResult]]:
        return [AutoFixEntry(file_path="src/foo.py", rule_id="I001", description="Import sorting")], []

    monkeypatch.setattr("arcwright_ai.validation.quality_gate._run_auto_fix", _auto_fix)
    result = await run_quality_gate(PROJECT_ROOT, WORKTREE_PATH)
    assert result.passed is True
    assert len(result.feedback.auto_fix_summary) == 1
    assert result.feedback.auto_fix_summary[0].rule_id == "I001"


@pytest.mark.asyncio
async def test_run_quality_gate_check_failure(
    mock_auto_fix_no_changes: None,
    mock_checks_mypy_fail: None,
) -> None:
    """run_quality_gate returns passed=False when any check tool fails."""
    result = await run_quality_gate(PROJECT_ROOT, WORKTREE_PATH)
    assert result.passed is False
    assert result.feedback.passed is False
    failing = [r for r in result.feedback.tool_results if not r.passed]
    assert len(failing) == 1
    assert failing[0].tool_name == "mypy --strict"


@pytest.mark.asyncio
async def test_run_quality_gate_uses_arcwright_ai_subdir(monkeypatch: pytest.MonkeyPatch) -> None:
    """run_quality_gate executes tools inside worktree/arcwright-ai subdir."""
    captured_cwd: list[Path] = []

    async def _auto_fix(cwd: Path, *, timeout: int) -> tuple[list[AutoFixEntry], list[ToolResult]]:
        captured_cwd.append(cwd)
        return [], []

    async def _checks(
        cwd: Path,
        *,
        timeout_ruff: int,
        timeout_mypy: int,
        timeout_pytest: int,
    ) -> list[ToolResult]:
        captured_cwd.append(cwd)
        return [
            ToolResult(tool_name="ruff check", passed=True, exit_code=0),
            ToolResult(tool_name="mypy --strict", passed=True, exit_code=0),
            ToolResult(tool_name="pytest", passed=True, exit_code=0),
        ]

    monkeypatch.setattr("arcwright_ai.validation.quality_gate._run_auto_fix", _auto_fix)
    monkeypatch.setattr("arcwright_ai.validation.quality_gate._run_checks", _checks)

    await run_quality_gate(PROJECT_ROOT, WORKTREE_PATH)

    expected_dir = WORKTREE_PATH / "arcwright-ai"
    assert all(cwd == expected_dir for cwd in captured_cwd)


@pytest.mark.asyncio
async def test_run_quality_gate_fails_when_auto_fix_tool_fails(
    monkeypatch: pytest.MonkeyPatch,
    mock_checks_all_pass: None,
) -> None:
    """Failed auto-fix tools must force FAIL_QUALITY even if check-phase tools pass."""

    async def _auto_fix(cwd: Path, *, timeout: int) -> tuple[list[AutoFixEntry], list[ToolResult]]:
        return (
            [],
            [
                ToolResult(
                    tool_name="ruff check --fix",
                    passed=False,
                    exit_code=1,
                    stderr="Tool 'ruff check --fix' could not start because executable 'ruff' was not found.",
                )
            ],
        )

    monkeypatch.setattr("arcwright_ai.validation.quality_gate._run_auto_fix", _auto_fix)
    result = await run_quality_gate(PROJECT_ROOT, WORKTREE_PATH)

    assert result.passed is False
    assert result.feedback.passed is False
    failing = [r for r in result.feedback.tool_results if not r.passed]
    assert len(failing) == 1
    assert failing[0].tool_name == "ruff check --fix"


# ---------------------------------------------------------------------------
# Test 6.5 — QualityFeedback model serialization
# ---------------------------------------------------------------------------


def test_quality_feedback_serialization_round_trip() -> None:
    """QualityFeedback.model_dump() + model_validate() round-trip."""
    feedback = QualityFeedback(
        passed=False,
        auto_fix_summary=[
            AutoFixEntry(file_path="src/foo.py", rule_id="I001", description="Import sorting"),
        ],
        tool_results=[
            ToolResult(
                tool_name="mypy --strict",
                passed=False,
                exit_code=1,
                stdout="",
                stderr="error: Missing return statement  [return]",
            ),
        ],
    )
    dumped = feedback.model_dump(round_trip=True)
    restored = QualityFeedback.model_validate(dumped)
    assert restored.passed == feedback.passed
    assert len(restored.auto_fix_summary) == 1
    assert restored.auto_fix_summary[0].rule_id == "I001"
    assert len(restored.tool_results) == 1
    assert restored.tool_results[0].tool_name == "mypy --strict"


def test_quality_gate_result_serialization_round_trip() -> None:
    """QualityGateResult.model_dump() + model_validate() round-trip."""
    feedback = QualityFeedback(
        passed=True,
        auto_fix_summary=[],
        tool_results=[
            ToolResult(tool_name="ruff check", passed=True, exit_code=0),
            ToolResult(tool_name="mypy --strict", passed=True, exit_code=0),
            ToolResult(tool_name="pytest", passed=True, exit_code=0),
        ],
    )
    result = QualityGateResult(passed=True, feedback=feedback)
    dumped = result.model_dump(round_trip=True)
    restored = QualityGateResult.model_validate(dumped)
    assert restored.passed is True
    assert len(restored.feedback.tool_results) == 3


def test_tool_result_timed_out_round_trip() -> None:
    """ToolResult with timed_out=True serializes and deserializes correctly."""
    tool = ToolResult(
        tool_name="pytest",
        passed=False,
        exit_code=1,
        stderr="Tool 'pytest' timed out after 300 seconds.",
        timed_out=True,
    )
    restored = ToolResult.model_validate(tool.model_dump(round_trip=True))
    assert restored.timed_out is True
    assert restored.passed is False
    assert "timed out" in restored.stderr
