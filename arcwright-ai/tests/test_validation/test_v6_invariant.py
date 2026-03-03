"""Unit tests for arcwright_ai.validation.v6_invariant — V6 deterministic checks."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

import pytest

from arcwright_ai.core.exceptions import ValidationError
from arcwright_ai.validation.v6_invariant import (
    _CHECK_REGISTRY,
    V6CheckResult,
    V6ValidationResult,
    _extract_file_paths,
    check_file_existence,
    check_naming_conventions,
    check_python_syntax,
    check_yaml_validity,
    register_v6_check,
    run_v6_validation,
)

if TYPE_CHECKING:
    from pathlib import Path

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def valid_project(tmp_path: Path) -> Path:
    """Create a tmp_path project with valid Python and YAML files for V6 testing.

    Args:
        tmp_path: Pytest-provided temporary directory.

    Returns:
        Path to the created project root directory.
    """
    src = tmp_path / "src" / "my_module"
    src.mkdir(parents=True)
    (src / "__init__.py").write_text('"""Init."""\n', encoding="utf-8")
    (src / "main.py").write_text(
        '"""Main."""\n\n\ndef hello() -> str:\n    return "hello"\n',
        encoding="utf-8",
    )
    (tmp_path / "config.yaml").write_text("key: value\n", encoding="utf-8")
    return tmp_path


@pytest.fixture
def story_path(tmp_path: Path) -> Path:
    """Return a dummy story file path.

    Args:
        tmp_path: Pytest-provided temporary directory.

    Returns:
        Path to a (non-existent) story file for protocol contract.
    """
    return tmp_path / "3-1-story.md"


@pytest.fixture
def agent_output_with_files() -> str:
    """Return agent output text referencing created files using multiple patterns.

    Returns:
        Markdown agent output with file paths in headers, code blocks, and lists.
    """
    return (
        "# Implementation\n\n"
        "## File: src/my_module/__init__.py\n"
        '```python\n"""Init."""\n```\n\n'
        "## File: src/my_module/main.py\n"
        '```python\n"""Main."""\ndef hello() -> str:\n    return "hello"\n```\n'
        "\n- Created: config.yaml\n"
    )


# ---------------------------------------------------------------------------
# _extract_file_paths utility (internal — tested indirectly but also directly)
# ---------------------------------------------------------------------------


def test_extract_file_paths_header_pattern() -> None:
    """_extract_file_paths extracts paths from markdown # File: headers."""
    output = "## File: src/my_module/main.py\n### File: config.yaml\n"
    paths = _extract_file_paths(output)
    assert "src/my_module/main.py" in paths
    assert "config.yaml" in paths


def test_extract_file_paths_deduplicates() -> None:
    """_extract_file_paths returns unique paths only."""
    output = "## File: src/main.py\n## File: src/main.py\n"
    paths = _extract_file_paths(output)
    assert paths.count("src/main.py") == 1


# ---------------------------------------------------------------------------
# Task 8.1 — all-pass scenario
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_run_v6_validation_all_pass(valid_project: Path, story_path: Path) -> None:
    """run_v6_validation returns passed=True and no failures when all checks pass.

    Scenario: agent output references files that exist with valid names and
    valid Python/YAML syntax.
    """
    agent_output = "## File: src/my_module/__init__.py\n## File: src/my_module/main.py\n## File: config.yaml\n"
    result = await run_v6_validation(agent_output, valid_project, story_path)
    assert result.passed is True
    assert result.failures == []
    assert len(result.results) > 0


# ---------------------------------------------------------------------------
# Task 8.2 — file existence: missing files
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_check_file_existence_detects_missing_files(tmp_path: Path, story_path: Path) -> None:
    """check_file_existence returns passed=False when referenced files are absent.

    Scenario: agent output references src/missing.py which does not exist.
    The failure_detail must list the missing path.
    """
    agent_output = "## File: src/missing.py\n"
    result = await check_file_existence(agent_output, tmp_path, story_path)
    assert result.passed is False
    assert result.failure_detail is not None
    assert "src/missing.py" in result.failure_detail
    assert result.check_name == "file_existence"


# ---------------------------------------------------------------------------
# Task 8.3 — file existence: all exist
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_check_file_existence_passes_when_all_exist(valid_project: Path, story_path: Path) -> None:
    """check_file_existence returns passed=True when all referenced files exist."""
    agent_output = "## File: src/my_module/__init__.py\n## File: src/my_module/main.py\n"
    result = await check_file_existence(agent_output, valid_project, story_path)
    assert result.passed is True
    assert result.failure_detail is None


# ---------------------------------------------------------------------------
# Task 8.4 — file existence: no files referenced
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_check_file_existence_passes_when_no_files_referenced(tmp_path: Path, story_path: Path) -> None:
    """check_file_existence returns passed=True when no file paths are found.

    Scenario: agent output is pure text with no file references. Nothing to
    check, so result is passed.
    """
    agent_output = "The implementation is complete. All requirements met.\n"
    result = await check_file_existence(agent_output, tmp_path, story_path)
    assert result.passed is True
    assert result.check_name == "file_existence"


# ---------------------------------------------------------------------------
# Task 8.5 — naming conventions: violations detected
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_check_naming_conventions_detects_violations(tmp_path: Path, story_path: Path) -> None:
    """check_naming_conventions returns passed=False for non-snake_case Python files.

    Scenario: agent output references MyBadFile.py (PascalCase) and
    kebab-case.py (hyphenated filename).
    """
    agent_output = "## File: src/MyBadFile.py\n## File: src/kebab-case.py\n"
    result = await check_naming_conventions(agent_output, tmp_path, story_path)
    assert result.passed is False
    assert result.failure_detail is not None
    assert result.check_name == "naming_conventions"


@pytest.mark.asyncio
async def test_check_naming_conventions_detects_non_snake_case_directory(tmp_path: Path, story_path: Path) -> None:
    """check_naming_conventions fails when module directory component is not snake_case."""
    agent_output = "## File: src/BadDir/valid_module.py\n"
    result = await check_naming_conventions(agent_output, tmp_path, story_path)
    assert result.passed is False
    assert result.failure_detail is not None
    assert "must be snake_case" in result.failure_detail


# ---------------------------------------------------------------------------
# Task 8.6 — naming conventions: valid names pass
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_check_naming_conventions_passes_valid_names(tmp_path: Path, story_path: Path) -> None:
    """check_naming_conventions returns passed=True for correctly named Python files."""
    agent_output = (
        "## File: src/my_module/valid_module.py\n"
        "## File: tests/test_validation/test_thing.py\n"
        "## File: src/my_module/__init__.py\n"
    )
    result = await check_naming_conventions(agent_output, tmp_path, story_path)
    assert result.passed is True
    assert result.failure_detail is None


# ---------------------------------------------------------------------------
# Task 8.7 — Python syntax: errors detected
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_check_python_syntax_detects_errors(tmp_path: Path, story_path: Path) -> None:
    """check_python_syntax returns passed=False for files with invalid Python syntax.

    Scenario: create a .py file containing a syntax error, reference it in
    agent output. The failure_detail must include the filename and line info.
    """
    bad_file = tmp_path / "broken.py"
    bad_file.write_text("def foo(:\n    pass\n", encoding="utf-8")
    agent_output = "## File: broken.py\n"
    result = await check_python_syntax(agent_output, tmp_path, story_path)
    assert result.passed is False
    assert result.failure_detail is not None
    assert "broken.py" in result.failure_detail
    assert result.check_name == "python_syntax"


# ---------------------------------------------------------------------------
# Task 8.8 — Python syntax: valid files pass
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_check_python_syntax_passes_valid_files(valid_project: Path, story_path: Path) -> None:
    """check_python_syntax returns passed=True for syntactically correct Python files."""
    agent_output = "## File: src/my_module/__init__.py\n## File: src/my_module/main.py\n"
    result = await check_python_syntax(agent_output, valid_project, story_path)
    assert result.passed is True
    assert result.failure_detail is None


# ---------------------------------------------------------------------------
# Task 8.9 — YAML validity: invalid YAML detected
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_check_yaml_validity_detects_invalid_yaml(tmp_path: Path, story_path: Path) -> None:
    """check_yaml_validity returns passed=False for malformed YAML files.

    Scenario: create a .yaml file with invalid YAML content, reference it in
    agent output.
    """
    bad_yaml = tmp_path / "broken.yaml"
    bad_yaml.write_text("{invalid yaml:::\n  - oops\n", encoding="utf-8")
    agent_output = "## File: broken.yaml\n"
    result = await check_yaml_validity(agent_output, tmp_path, story_path)
    assert result.passed is False
    assert result.failure_detail is not None
    assert "broken.yaml" in result.failure_detail
    assert result.check_name == "yaml_validity"


@pytest.mark.asyncio
async def test_check_yaml_validity_detects_missing_required_sprint_status_keys(
    tmp_path: Path, story_path: Path
) -> None:
    """check_yaml_validity fails lightweight schema validation for sprint-status YAML."""
    sprint_status = tmp_path / "sprint-status.yaml"
    sprint_status.write_text("project: demo\n", encoding="utf-8")
    agent_output = "## File: sprint-status.yaml\n"
    result = await check_yaml_validity(agent_output, tmp_path, story_path)
    assert result.passed is False
    assert result.failure_detail is not None
    assert "missing required keys" in result.failure_detail


@pytest.mark.asyncio
async def test_check_yaml_validity_detects_untyped_pydantic_field(tmp_path: Path, story_path: Path) -> None:
    """check_yaml_validity flags Pydantic model fields declared without annotations."""
    model_file = tmp_path / "bad_model.py"
    model_file.write_text(
        "from pydantic import BaseModel\n\nclass BadModel(BaseModel):\n    bad = 1\n",
        encoding="utf-8",
    )
    agent_output = "## File: bad_model.py\n"
    result = await check_yaml_validity(agent_output, tmp_path, story_path)
    assert result.passed is False
    assert result.failure_detail is not None
    assert "must use a type annotation" in result.failure_detail


# ---------------------------------------------------------------------------
# Task 8.10 — YAML validity: valid YAML passes
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_check_yaml_validity_passes_valid_yaml(valid_project: Path, story_path: Path) -> None:
    """check_yaml_validity returns passed=True for well-formed YAML files."""
    agent_output = "## File: config.yaml\n"
    result = await check_yaml_validity(agent_output, valid_project, story_path)
    assert result.passed is True
    assert result.failure_detail is None


# ---------------------------------------------------------------------------
# Task 8.11 — registry extensibility
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_register_v6_check_extends_registry(tmp_path: Path, story_path: Path) -> None:
    """register_v6_check appends a custom check that executes during run_v6_validation.

    Scenario: register a custom check that always returns a specific result,
    run validation, verify the custom check's result appears in output.
    """
    sentinel: list[bool] = []

    async def custom_check(agent_output: str, project_root: Path, s_path: Path) -> V6CheckResult:
        sentinel.append(True)
        return V6CheckResult(check_name="custom_sentinel", passed=True)

    original_len = len(_CHECK_REGISTRY)
    register_v6_check(custom_check)  # type: ignore[arg-type]
    try:
        result = await run_v6_validation("no files here", tmp_path, story_path)
        check_names = [r.check_name for r in result.results]
        assert "custom_sentinel" in check_names
        assert sentinel == [True]
    finally:
        # Restore registry to original state
        del _CHECK_REGISTRY[original_len:]


# ---------------------------------------------------------------------------
# Task 8.12 — failures property
# ---------------------------------------------------------------------------


def test_v6_validation_result_failures_property() -> None:
    """V6ValidationResult.failures returns only the failed checks.

    Scenario: create a result with two passed and one failed check, assert
    failures contains exactly the failed check.
    """
    r1 = V6CheckResult(check_name="file_existence", passed=True)
    r2 = V6CheckResult(
        check_name="naming_conventions",
        passed=False,
        failure_detail="bad name",
    )
    r3 = V6CheckResult(check_name="python_syntax", passed=True)
    vr = V6ValidationResult(passed=False, results=[r1, r2, r3])
    assert len(vr.failures) == 1
    assert vr.failures[0].check_name == "naming_conventions"


# ---------------------------------------------------------------------------
# Task 8.13 — serialization round-trip
# ---------------------------------------------------------------------------


def test_v6_check_result_is_serializable() -> None:
    """V6CheckResult supports model_dump / model_validate round-trip correctly."""
    original = V6CheckResult(
        check_name="python_syntax",
        passed=False,
        failure_detail="SyntaxError at line 5",
    )
    dumped = original.model_dump()
    restored = V6CheckResult.model_validate(dumped)
    assert restored.check_name == original.check_name
    assert restored.passed == original.passed
    assert restored.failure_detail == original.failure_detail


def test_v6_validation_result_failures_included_in_serialization() -> None:
    """V6ValidationResult.failures is included in model_dump output (computed_field)."""
    r_fail = V6CheckResult(check_name="file_existence", passed=False, failure_detail="missing: x.py")
    r_pass = V6CheckResult(check_name="python_syntax", passed=True)
    vr = V6ValidationResult(passed=False, results=[r_fail, r_pass])
    dumped = vr.model_dump()
    assert "failures" in dumped
    assert len(dumped["failures"]) == 1
    assert dumped["failures"][0]["check_name"] == "file_existence"


# ---------------------------------------------------------------------------
# Task 8.14 — structured log events
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_run_v6_validation_emits_structured_log_events(
    tmp_path: Path, story_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """run_v6_validation emits validation.v6.start and validation.v6.complete log events.

    Scenario: run validation with no file references (all checks pass trivially),
    capture log output, confirm both structured events are present with expected
    data fields.
    """
    with caplog.at_level(logging.INFO, logger="arcwright_ai.validation.v6_invariant"):
        await run_v6_validation("no file references here", tmp_path, story_path)

    messages = [r.getMessage() for r in caplog.records]
    assert any("validation.v6.start" in m for m in messages), (
        f"Expected 'validation.v6.start' in log messages, got: {messages}"
    )
    assert any("validation.v6.complete" in m for m in messages), (
        f"Expected 'validation.v6.complete' in log messages, got: {messages}"
    )

    complete_records = [r for r in caplog.records if "validation.v6.complete" in r.getMessage()]
    assert len(complete_records) == 1
    data = complete_records[0].__dict__.get("data", {})
    assert "passed" in data
    assert "checks_run" in data
    assert "failures" in data


@pytest.mark.asyncio
async def test_run_v6_validation_wraps_unexpected_errors(tmp_path: Path, story_path: Path) -> None:
    """run_v6_validation wraps unexpected check exceptions as ValidationError."""

    async def exploding_check(agent_output: str, project_root: Path, s_path: Path) -> V6CheckResult:
        raise RuntimeError("boom")

    original_len = len(_CHECK_REGISTRY)
    register_v6_check(exploding_check)  # type: ignore[arg-type]
    try:
        with pytest.raises(ValidationError, match="Unexpected V6 validation execution error"):
            await run_v6_validation("", tmp_path, story_path)
    finally:
        del _CHECK_REGISTRY[original_len:]
