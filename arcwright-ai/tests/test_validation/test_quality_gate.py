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
    _detect_node_quality_scripts,  # type: ignore[reportPrivateUsage]
    _ensure_node_deps,  # type: ignore[reportPrivateUsage]
    _parse_auto_fixes,  # type: ignore[reportPrivateUsage]
    _run_auto_fix,  # type: ignore[reportPrivateUsage]
    _run_checks,  # type: ignore[reportPrivateUsage]
    _run_node_checks,  # type: ignore[reportPrivateUsage]
    _run_subprocess,  # type: ignore[reportPrivateUsage]
    detect_project_dir,
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


@pytest.fixture
def mock_detect_python_project(monkeypatch: pytest.MonkeyPatch) -> None:
    """Monkeypatch detect_project_dir to return python project at arcwright-ai subdir."""

    def _detect(worktree_path: Path) -> tuple[str | None, Path]:
        return ("python", worktree_path / "arcwright-ai")

    monkeypatch.setattr("arcwright_ai.validation.quality_gate.detect_project_dir", _detect)


@pytest.mark.asyncio
async def test_run_quality_gate_full_pass(
    mock_detect_python_project: None,
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
    mock_detect_python_project: None,
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
    mock_detect_python_project: None,
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
    """run_quality_gate passes detect_project_dir result as cwd to tools."""
    captured_cwd: list[Path] = []

    def _detect(worktree_path: Path) -> tuple[str | None, Path]:
        return ("python", worktree_path / "arcwright-ai")

    monkeypatch.setattr("arcwright_ai.validation.quality_gate.detect_project_dir", _detect)

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
    mock_detect_python_project: None,
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


# ---------------------------------------------------------------------------
# Test 10.14 — detect_project_dir
# ---------------------------------------------------------------------------


def test_detect_project_dir_pyproject_at_root(tmp_path: Path) -> None:
    """4.1: pyproject.toml at worktree root returns (python, worktree_path)."""
    (tmp_path / "pyproject.toml").touch()
    project_type, project_dir = detect_project_dir(tmp_path)
    assert project_type == "python"
    assert project_dir == tmp_path


def test_detect_project_dir_pyproject_one_level_deep(tmp_path: Path) -> None:
    """4.2: pyproject.toml one level deep returns (python, worktree_path/subdir)."""
    subdir = tmp_path / "myapp"
    subdir.mkdir()
    (subdir / "pyproject.toml").touch()
    project_type, project_dir = detect_project_dir(tmp_path)
    assert project_type == "python"
    assert project_dir == subdir


def test_detect_project_dir_package_json_at_root(tmp_path: Path) -> None:
    """4.3: package.json at root (no pyproject.toml) returns (node, worktree_path)."""
    (tmp_path / "package.json").touch()
    project_type, project_dir = detect_project_dir(tmp_path)
    assert project_type == "node"
    assert project_dir == tmp_path


def test_detect_project_dir_go_mod_at_root(tmp_path: Path) -> None:
    """4.4: go.mod at root (no higher-priority manifests) returns (go, worktree_path)."""
    (tmp_path / "go.mod").touch()
    project_type, project_dir = detect_project_dir(tmp_path)
    assert project_type == "go"
    assert project_dir == tmp_path


def test_detect_project_dir_no_manifest(tmp_path: Path) -> None:
    """4.5: no manifest at any depth returns (None, worktree_path)."""
    project_type, project_dir = detect_project_dir(tmp_path)
    assert project_type is None
    assert project_dir == tmp_path


def test_detect_project_dir_polyglot_python_wins(tmp_path: Path) -> None:
    """4.6: both pyproject.toml and package.json at root — python wins."""
    (tmp_path / "pyproject.toml").touch()
    (tmp_path / "package.json").touch()
    project_type, project_dir = detect_project_dir(tmp_path)
    assert project_type == "python"
    assert project_dir == tmp_path


def test_detect_project_dir_priority_over_depth(tmp_path: Path) -> None:
    """4.7: package.json at root + pyproject.toml one level deep — python still wins."""
    (tmp_path / "package.json").touch()
    subdir = tmp_path / "app"
    subdir.mkdir()
    (subdir / "pyproject.toml").touch()
    project_type, project_dir = detect_project_dir(tmp_path)
    assert project_type == "python"
    assert project_dir == subdir


# ---------------------------------------------------------------------------
# Test 10.14 — run_quality_gate auto-detection integration
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_run_quality_gate_skips_node_project_without_scripts(tmp_path: Path) -> None:
    """4.8: node project with no quality scripts skips gate — passed=True, skipped_reason set."""
    (tmp_path / "package.json").write_text('{"name": "test"}', encoding="utf-8")
    # node_modules present so _ensure_node_deps is a no-op
    (tmp_path / "node_modules").mkdir()
    result = await run_quality_gate(PROJECT_ROOT, tmp_path)
    assert result.passed is True
    assert result.feedback.passed is True
    assert result.feedback.skipped_reason is not None
    assert "no lint/typecheck scripts" in result.feedback.skipped_reason
    assert result.feedback.tool_results == []


@pytest.mark.asyncio
async def test_run_quality_gate_skips_unknown_project(tmp_path: Path) -> None:
    """4.9: unknown project (no manifest) skips gate — passed=True, skipped_reason set."""
    result = await run_quality_gate(PROJECT_ROOT, tmp_path)
    assert result.passed is True
    assert result.feedback.passed is True
    assert result.feedback.skipped_reason is not None
    assert "unknown" in result.feedback.skipped_reason
    assert result.feedback.tool_results == []


@pytest.mark.asyncio
async def test_run_quality_gate_uses_detected_project_dir_at_root(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """4.10: python project at worktree root — subprocesses use worktree_path as cwd."""
    (tmp_path / "pyproject.toml").touch()
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

    await run_quality_gate(PROJECT_ROOT, tmp_path)

    # cwd must be tmp_path itself, not tmp_path / "arcwright-ai"
    assert len(captured_cwd) == 2
    assert all(cwd == tmp_path for cwd in captured_cwd)


# ---------------------------------------------------------------------------
# Test 10.14 — QualityFeedback.skipped_reason serialization
# ---------------------------------------------------------------------------


def test_quality_feedback_skipped_reason_none_round_trip() -> None:
    """4.11a: skipped_reason=None serializes cleanly and round-trips."""
    feedback = QualityFeedback(passed=True)
    assert feedback.skipped_reason is None
    dumped = feedback.model_dump(round_trip=True)
    restored = QualityFeedback.model_validate(dumped)
    assert restored.skipped_reason is None


def test_quality_feedback_skipped_reason_set_round_trip() -> None:
    """4.11b: skipped_reason with value round-trips correctly."""
    msg = "Quality Gate skipped: no lint/typecheck scripts found in package.json. Gate will pass automatically."
    feedback = QualityFeedback(passed=True, skipped_reason=msg)
    dumped = feedback.model_dump(round_trip=True)
    restored = QualityFeedback.model_validate(dumped)
    assert restored.skipped_reason == msg
    assert restored.passed is True


# ---------------------------------------------------------------------------
# Test — _detect_node_quality_scripts
# ---------------------------------------------------------------------------


def test_detect_node_quality_scripts_missing_file(tmp_path: Path) -> None:
    """Returns empty list when package.json does not exist."""
    result = _detect_node_quality_scripts(tmp_path / "package.json")
    assert result == []


def test_detect_node_quality_scripts_empty_scripts(tmp_path: Path) -> None:
    """Returns empty list when scripts object is empty."""
    (tmp_path / "package.json").write_text('{"scripts": {}}', encoding="utf-8")
    result = _detect_node_quality_scripts(tmp_path / "package.json")
    assert result == []


def test_detect_node_quality_scripts_no_matching_scripts(tmp_path: Path) -> None:
    """Returns empty list when no scripts match quality prefixes."""
    pkg = '{"scripts": {"build": "next build", "dev": "next dev", "start": "next start"}}'
    (tmp_path / "package.json").write_text(pkg, encoding="utf-8")
    result = _detect_node_quality_scripts(tmp_path / "package.json")
    assert result == []


def test_detect_node_quality_scripts_lint_and_typecheck(tmp_path: Path) -> None:
    """Detects lint:md and typecheck scripts."""
    pkg = '{"scripts": {"lint:md": "markdownlint", "typecheck": "tsc --noEmit", "build": "next"}}'
    (tmp_path / "package.json").write_text(pkg, encoding="utf-8")
    result = _detect_node_quality_scripts(tmp_path / "package.json")
    assert ("npm run lint:md", "lint:md") in result
    assert ("npm run typecheck", "typecheck") in result
    assert len(result) == 2


def test_detect_node_quality_scripts_all_variant_preferred(tmp_path: Path) -> None:
    """typecheck:all is preferred over individual typecheck variants."""
    pkg = (
        '{"scripts": {"typecheck": "tsc", "typecheck:api": "tsc api",'
        ' "typecheck:all": "npm run typecheck && npm run typecheck:api"}}'
    )
    (tmp_path / "package.json").write_text(pkg, encoding="utf-8")
    result = _detect_node_quality_scripts(tmp_path / "package.json")
    assert ("npm run typecheck:all", "typecheck:all") in result
    assert len(result) == 1


def test_detect_node_quality_scripts_multiple_lint_variants(tmp_path: Path) -> None:
    """Multiple lint variants without :all returns all individually."""
    pkg = '{"scripts": {"lint": "eslint", "lint:md": "markdownlint", "lint:css": "stylelint"}}'
    (tmp_path / "package.json").write_text(pkg, encoding="utf-8")
    result = _detect_node_quality_scripts(tmp_path / "package.json")
    assert len(result) == 3
    script_keys = [s[1] for s in result]
    assert "lint" in script_keys
    assert "lint:css" in script_keys
    assert "lint:md" in script_keys


def test_detect_node_quality_scripts_malformed_json(tmp_path: Path) -> None:
    """Returns empty list for malformed JSON."""
    (tmp_path / "package.json").write_text("not valid json", encoding="utf-8")
    result = _detect_node_quality_scripts(tmp_path / "package.json")
    assert result == []


# ---------------------------------------------------------------------------
# Test — _ensure_node_deps
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_ensure_node_deps_already_present(tmp_path: Path) -> None:
    """Returns None when node_modules directory already exists."""
    (tmp_path / "node_modules").mkdir()
    result = await _ensure_node_deps(tmp_path, timeout=10)
    assert result is None


@pytest.mark.asyncio
async def test_ensure_node_deps_runs_npm_ci(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Runs `npm ci` when package-lock.json exists and node_modules is absent."""
    (tmp_path / "package-lock.json").touch()
    captured_cmd: list[list[str]] = []

    async def _mock_subprocess(cmd: list[str], *, cwd: Path, tool_name: str, timeout: int) -> ToolResult:
        captured_cmd.append(cmd)
        return ToolResult(tool_name=tool_name, passed=True, exit_code=0)

    monkeypatch.setattr("arcwright_ai.validation.quality_gate._run_subprocess", _mock_subprocess)
    result = await _ensure_node_deps(tmp_path, timeout=120)
    assert result is not None
    assert result.passed is True
    assert captured_cmd[0] == ["npm", "ci"]


@pytest.mark.asyncio
async def test_ensure_node_deps_runs_npm_install(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Falls back to `npm install` when no package-lock.json."""
    captured_cmd: list[list[str]] = []

    async def _mock_subprocess(cmd: list[str], *, cwd: Path, tool_name: str, timeout: int) -> ToolResult:
        captured_cmd.append(cmd)
        return ToolResult(tool_name=tool_name, passed=True, exit_code=0)

    monkeypatch.setattr("arcwright_ai.validation.quality_gate._run_subprocess", _mock_subprocess)
    result = await _ensure_node_deps(tmp_path, timeout=120)
    assert result is not None
    assert captured_cmd[0] == ["npm", "install"]


# ---------------------------------------------------------------------------
# Test — _run_node_checks
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_run_node_checks_all_pass(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """All npm scripts passing returns all-pass ToolResults."""

    async def _mock_subprocess(cmd: list[str], *, cwd: Path, tool_name: str, timeout: int) -> ToolResult:
        return ToolResult(tool_name=tool_name, passed=True, exit_code=0)

    monkeypatch.setattr("arcwright_ai.validation.quality_gate._run_subprocess", _mock_subprocess)
    scripts = [("npm run lint:md", "lint:md"), ("npm run typecheck", "typecheck")]
    results = await _run_node_checks(tmp_path, scripts, timeout=60)
    assert len(results) == 2
    assert all(r.passed for r in results)


@pytest.mark.asyncio
async def test_run_node_checks_some_fail(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Failing npm scripts produce ToolResults with passed=False."""
    call_count = 0

    async def _mock_subprocess(cmd: list[str], *, cwd: Path, tool_name: str, timeout: int) -> ToolResult:
        nonlocal call_count
        call_count += 1
        if call_count == 2:
            return ToolResult(tool_name=tool_name, passed=False, exit_code=1, stderr="Type error")
        return ToolResult(tool_name=tool_name, passed=True, exit_code=0)

    monkeypatch.setattr("arcwright_ai.validation.quality_gate._run_subprocess", _mock_subprocess)
    scripts = [("npm run lint:md", "lint:md"), ("npm run typecheck", "typecheck")]
    results = await _run_node_checks(tmp_path, scripts, timeout=60)
    assert len(results) == 2
    assert results[0].passed is True
    assert results[1].passed is False


# ---------------------------------------------------------------------------
# Test — run_quality_gate Node.js integration
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_run_quality_gate_node_runs_checks(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Node project with quality scripts runs them and reports pass."""
    pkg = '{"scripts": {"lint:md": "markdownlint .", "typecheck": "tsc --noEmit"}}'
    (tmp_path / "package.json").write_text(pkg, encoding="utf-8")
    (tmp_path / "node_modules").mkdir()

    async def _mock_subprocess(cmd: list[str], *, cwd: Path, tool_name: str, timeout: int) -> ToolResult:
        return ToolResult(tool_name=tool_name, passed=True, exit_code=0)

    monkeypatch.setattr("arcwright_ai.validation.quality_gate._run_subprocess", _mock_subprocess)
    result = await run_quality_gate(PROJECT_ROOT, tmp_path)
    assert result.passed is True
    assert result.feedback.skipped_reason is None
    assert len(result.feedback.tool_results) == 2
    tool_names = [r.tool_name for r in result.feedback.tool_results]
    assert "npm run lint:md" in tool_names
    assert "npm run typecheck" in tool_names


@pytest.mark.asyncio
async def test_run_quality_gate_node_fails_on_check_failure(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Node quality gate fails when a script fails."""
    pkg = '{"scripts": {"lint:md": "markdownlint .", "typecheck": "tsc --noEmit"}}'
    (tmp_path / "package.json").write_text(pkg, encoding="utf-8")
    (tmp_path / "node_modules").mkdir()

    async def _mock_subprocess(cmd: list[str], *, cwd: Path, tool_name: str, timeout: int) -> ToolResult:
        if "typecheck" in cmd:
            return ToolResult(tool_name=tool_name, passed=False, exit_code=1, stderr="TS2322: Type error")
        return ToolResult(tool_name=tool_name, passed=True, exit_code=0)

    monkeypatch.setattr("arcwright_ai.validation.quality_gate._run_subprocess", _mock_subprocess)
    result = await run_quality_gate(PROJECT_ROOT, tmp_path)
    assert result.passed is False
    assert result.feedback.passed is False
    failing = [r.tool_name for r in result.feedback.tool_results if not r.passed]
    assert "npm run typecheck" in failing


@pytest.mark.asyncio
async def test_run_quality_gate_node_install_failure(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Gate fails immediately when npm install fails."""
    pkg = '{"scripts": {"typecheck": "tsc --noEmit"}}'
    (tmp_path / "package.json").write_text(pkg, encoding="utf-8")
    # No node_modules → triggers install

    async def _mock_subprocess(cmd: list[str], *, cwd: Path, tool_name: str, timeout: int) -> ToolResult:
        return ToolResult(tool_name=tool_name, passed=False, exit_code=1, stderr="npm ERR!")

    monkeypatch.setattr("arcwright_ai.validation.quality_gate._run_subprocess", _mock_subprocess)
    result = await run_quality_gate(PROJECT_ROOT, tmp_path)
    assert result.passed is False
    assert len(result.feedback.tool_results) == 1
    assert result.feedback.tool_results[0].tool_name == "npm install"
