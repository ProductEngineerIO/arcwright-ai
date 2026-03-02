"""Tests for the CLI validate-setup command.

Uses typer.testing.CliRunner for command invocation.
All tests use tmp_path for full filesystem isolation.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
from typer.testing import CliRunner

if TYPE_CHECKING:
    from pathlib import Path

from arcwright_ai.cli.app import app
from arcwright_ai.core.constants import CONFIG_FILENAME, DIR_ARCWRIGHT

runner = CliRunner()


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def valid_project(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Fully initialized project that passes all validate-setup checks.

    Args:
        tmp_path: Pytest temporary directory.
        monkeypatch: Pytest monkeypatch fixture.

    Returns:
        Path to the project root.
    """
    # Set API key via environment variable
    monkeypatch.setenv("ARCWRIGHT_API_CLAUDE_API_KEY", "sk-ant-test-key")

    # Create .arcwright-ai/config.yaml (no api section per NFR6)
    arcwright = tmp_path / DIR_ARCWRIGHT
    arcwright.mkdir()
    config_content = (
        'model:\n  version: "claude-opus-4-5"\n'
        "limits:\n"
        "  tokens_per_story: 200000\n"
        "  cost_per_run: 10.0\n"
        "  retry_budget: 3\n"
        "  timeout_per_story: 300\n"
        'methodology:\n  artifacts_path: "_spec"\n  type: "bmad"\n'
        'scm:\n  branch_template: "arcwright/{story_slug}"\n'
        "reproducibility:\n  enabled: false\n  retention: 30\n"
    )
    (arcwright / CONFIG_FILENAME).write_text(config_content, encoding="utf-8")

    # Create planning artifacts
    planning = tmp_path / "_spec" / "planning-artifacts"
    planning.mkdir(parents=True)
    (planning / "prd.md").write_text("# PRD\n", encoding="utf-8")
    (planning / "architecture.md").write_text("# Architecture\n", encoding="utf-8")
    (planning / "epics.md").write_text("# Epics\n", encoding="utf-8")

    # Create story artifacts with acceptance criteria
    impl = tmp_path / "_spec" / "implementation-artifacts"
    impl.mkdir(parents=True)
    (impl / "1-1-scaffold.md").write_text(
        "# Story 1.1\n\n## Acceptance Criteria\n\n1. Given...\n",
        encoding="utf-8",
    )

    return tmp_path


# ---------------------------------------------------------------------------
# 3.2 — All checks pass
# ---------------------------------------------------------------------------


def test_validate_setup_all_pass(valid_project: Path) -> None:
    """All 5 checks pass → exit code 0 and ✅ for each check."""
    result = runner.invoke(app, ["validate-setup", "--path", str(valid_project)], catch_exceptions=False)
    assert result.exit_code == 0
    assert result.output.count("✅") >= 5
    assert "All checks passed" in result.output


# ---------------------------------------------------------------------------
# 3.3 — Missing API key
# ---------------------------------------------------------------------------


def test_validate_setup_missing_api_key(valid_project: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """No API key anywhere → ❌ for Claude API key check, exit code 3."""
    monkeypatch.delenv("ARCWRIGHT_API_CLAUDE_API_KEY", raising=False)
    # Ensure global config doesn't exist by pointing home to tmp
    monkeypatch.setenv("HOME", str(valid_project / "fakehome"))
    result = runner.invoke(app, ["validate-setup", "--path", str(valid_project)])
    assert result.exit_code == 3
    assert "❌" in result.output
    assert "Claude API key" in result.output
    assert "NOT FOUND" in result.output


# ---------------------------------------------------------------------------
# 3.4 — Wrong artifacts path
# ---------------------------------------------------------------------------


def test_validate_setup_wrong_artifacts_path(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Config has wrong artifacts_path → structure check fails with NOT FOUND."""
    monkeypatch.setenv("ARCWRIGHT_API_CLAUDE_API_KEY", "sk-ant-test-key")

    arcwright = tmp_path / DIR_ARCWRIGHT
    arcwright.mkdir()
    config_content = (
        'model:\n  version: "claude-opus-4-5"\n'
        "limits:\n"
        "  tokens_per_story: 200000\n"
        "  cost_per_run: 10.0\n"
        "  retry_budget: 3\n"
        "  timeout_per_story: 300\n"
        'methodology:\n  artifacts_path: "wrong-dir"\n  type: "bmad"\n'
        'scm:\n  branch_template: "arcwright/{story_slug}"\n'
        "reproducibility:\n  enabled: false\n  retention: 30\n"
    )
    (arcwright / CONFIG_FILENAME).write_text(config_content, encoding="utf-8")

    result = runner.invoke(app, ["validate-setup", "--path", str(tmp_path)])
    assert result.exit_code == 3
    assert "NOT FOUND" in result.output
    assert "wrong-dir" in result.output


# ---------------------------------------------------------------------------
# 3.5 — Missing planning artifacts
# ---------------------------------------------------------------------------


def test_validate_setup_missing_planning_artifacts(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """planning-artifacts dir exists but is empty → planning check fails with Missing."""
    monkeypatch.setenv("ARCWRIGHT_API_CLAUDE_API_KEY", "sk-ant-test-key")

    arcwright = tmp_path / DIR_ARCWRIGHT
    arcwright.mkdir()
    config_content = (
        'model:\n  version: "claude-opus-4-5"\n'
        "limits:\n"
        "  tokens_per_story: 200000\n"
        "  cost_per_run: 10.0\n"
        "  retry_budget: 3\n"
        "  timeout_per_story: 300\n"
        'methodology:\n  artifacts_path: "_spec"\n  type: "bmad"\n'
        'scm:\n  branch_template: "arcwright/{story_slug}"\n'
        "reproducibility:\n  enabled: false\n  retention: 30\n"
    )
    (arcwright / CONFIG_FILENAME).write_text(config_content, encoding="utf-8")

    # Create structure dir but empty planning-artifacts
    planning = tmp_path / "_spec" / "planning-artifacts"
    planning.mkdir(parents=True)
    impl = tmp_path / "_spec" / "implementation-artifacts"
    impl.mkdir(parents=True)
    (impl / "1-1-story.md").write_text("## Acceptance Criteria\n", encoding="utf-8")

    result = runner.invoke(app, ["validate-setup", "--path", str(tmp_path)])
    assert result.exit_code == 3
    assert "Missing" in result.output


# ---------------------------------------------------------------------------
# 3.6 — Missing story artifacts
# ---------------------------------------------------------------------------


def test_validate_setup_missing_story_artifacts(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Planning artifacts exist but implementation-artifacts/ is empty → stories check fails."""
    monkeypatch.setenv("ARCWRIGHT_API_CLAUDE_API_KEY", "sk-ant-test-key")

    arcwright = tmp_path / DIR_ARCWRIGHT
    arcwright.mkdir()
    config_content = (
        'model:\n  version: "claude-opus-4-5"\n'
        "limits:\n"
        "  tokens_per_story: 200000\n"
        "  cost_per_run: 10.0\n"
        "  retry_budget: 3\n"
        "  timeout_per_story: 300\n"
        'methodology:\n  artifacts_path: "_spec"\n  type: "bmad"\n'
        'scm:\n  branch_template: "arcwright/{story_slug}"\n'
        "reproducibility:\n  enabled: false\n  retention: 30\n"
    )
    (arcwright / CONFIG_FILENAME).write_text(config_content, encoding="utf-8")

    planning = tmp_path / "_spec" / "planning-artifacts"
    planning.mkdir(parents=True)
    (planning / "prd.md").write_text("# PRD\n", encoding="utf-8")
    (planning / "architecture.md").write_text("# Architecture\n", encoding="utf-8")
    (planning / "epics.md").write_text("# Epics\n", encoding="utf-8")

    impl = tmp_path / "_spec" / "implementation-artifacts"
    impl.mkdir(parents=True)
    # No story files

    result = runner.invoke(app, ["validate-setup", "--path", str(tmp_path)])
    assert result.exit_code == 3
    assert "No story files found" in result.output


# ---------------------------------------------------------------------------
# 3.7 — Invalid config
# ---------------------------------------------------------------------------


def test_validate_setup_invalid_config(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Malformed config → config check fails with specific error."""
    monkeypatch.setenv("ARCWRIGHT_API_CLAUDE_API_KEY", "sk-ant-test-key")

    arcwright = tmp_path / DIR_ARCWRIGHT
    arcwright.mkdir()
    # tokens_per_story must be an int — "not-a-number" is invalid
    config_content = (
        'model:\n  version: "claude-opus-4-5"\n'
        'limits:\n  tokens_per_story: "not-a-number"\n'
        "  cost_per_run: 10.0\n  retry_budget: 3\n  timeout_per_story: 300\n"
        'methodology:\n  artifacts_path: "_spec"\n  type: "bmad"\n'
        'scm:\n  branch_template: "arcwright/{story_slug}"\n'
        "reproducibility:\n  enabled: false\n  retention: 30\n"
    )
    (arcwright / CONFIG_FILENAME).write_text(config_content, encoding="utf-8")

    planning = tmp_path / "_spec" / "planning-artifacts"
    planning.mkdir(parents=True)
    (planning / "prd.md").write_text("# PRD\n", encoding="utf-8")
    (planning / "architecture.md").write_text("# Architecture\n", encoding="utf-8")
    (planning / "epics.md").write_text("# Epics\n", encoding="utf-8")

    impl = tmp_path / "_spec" / "implementation-artifacts"
    impl.mkdir(parents=True)
    (impl / "1-1-story.md").write_text("## Acceptance Criteria\n", encoding="utf-8")

    result = runner.invoke(app, ["validate-setup", "--path", str(tmp_path)])
    assert result.exit_code == 3
    assert "INVALID" in result.output
    assert "Fix:" in result.output


# ---------------------------------------------------------------------------
# 3.8 — Dependent check skipping: no API key → config check skipped
# ---------------------------------------------------------------------------


def test_validate_setup_dependent_check_skipping_api(valid_project: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """No API key → check 5 (config valid) shows Cannot-validate skip message."""
    monkeypatch.delenv("ARCWRIGHT_API_CLAUDE_API_KEY", raising=False)
    monkeypatch.setenv("HOME", str(valid_project / "fakehome"))

    result = runner.invoke(app, ["validate-setup", "--path", str(valid_project)])
    assert result.exit_code == 3
    assert "Cannot validate" in result.output
    assert "Claude API key" in result.output


# ---------------------------------------------------------------------------
# 3.9 — Dependent check skipping: bad structure → planning/story checks skipped
# ---------------------------------------------------------------------------


def test_validate_setup_dependent_check_skipping_structure(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Non-existent artifacts path → checks 3 and 4 show Cannot-validate skip messages."""
    monkeypatch.setenv("ARCWRIGHT_API_CLAUDE_API_KEY", "sk-ant-test-key")

    arcwright = tmp_path / DIR_ARCWRIGHT
    arcwright.mkdir()
    config_content = (
        'model:\n  version: "claude-opus-4-5"\n'
        "limits:\n"
        "  tokens_per_story: 200000\n"
        "  cost_per_run: 10.0\n"
        "  retry_budget: 3\n"
        "  timeout_per_story: 300\n"
        'methodology:\n  artifacts_path: "nonexistent-path"\n  type: "bmad"\n'
        'scm:\n  branch_template: "arcwright/{story_slug}"\n'
        "reproducibility:\n  enabled: false\n  retention: 30\n"
    )
    (arcwright / CONFIG_FILENAME).write_text(config_content, encoding="utf-8")
    # Do NOT create nonexistent-path/

    result = runner.invoke(app, ["validate-setup", "--path", str(tmp_path)])
    assert result.exit_code == 3
    output = result.output
    assert "Cannot validate" in output
    assert "BMAD project structure" in output


# ---------------------------------------------------------------------------
# 3.10 — Any failing check → exit code 3
# ---------------------------------------------------------------------------


def test_validate_setup_exit_code_three_on_failure(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Any failing check results in exit code 3."""
    monkeypatch.delenv("ARCWRIGHT_API_CLAUDE_API_KEY", raising=False)
    monkeypatch.setenv("HOME", str(tmp_path / "fakehome"))

    result = runner.invoke(app, ["validate-setup", "--path", str(tmp_path)])
    assert result.exit_code == 3


# ---------------------------------------------------------------------------
# 3.11 — Help lists --path / -p option
# ---------------------------------------------------------------------------


def test_validate_setup_help_lists_path_option() -> None:
    """`validate-setup --help` shows --path and -p options."""
    result = runner.invoke(app, ["validate-setup", "--help"], catch_exceptions=False)
    assert result.exit_code == 0
    assert "--path" in result.output
    assert "-p" in result.output


# ---------------------------------------------------------------------------
# 3.12 — Root help lists validate-setup command
# ---------------------------------------------------------------------------


def test_root_help_lists_validate_setup_command() -> None:
    """CLI root `--help` includes validate-setup."""
    result = runner.invoke(app, ["--help"], catch_exceptions=False)
    assert "validate-setup" in result.output


# ---------------------------------------------------------------------------
# 3.13 — Uninitialized project (no .arcwright-ai/)
# ---------------------------------------------------------------------------


def test_validate_setup_uninitialized_project(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """No .arcwright-ai/ → command still runs; artifacts still checked at default path."""
    monkeypatch.setenv("ARCWRIGHT_API_CLAUDE_API_KEY", "sk-ant-test-key")
    # No .arcwright-ai/ created; no _spec/ either

    result = runner.invoke(app, ["validate-setup", "--path", str(tmp_path)])
    # Should not crash — just report failures
    assert result.exit_code == 3
    # BMAD structure check should report NOT FOUND since _spec/ doesn't exist
    assert "BMAD project structure" in result.output


def test_validate_setup_missing_acceptance_criteria_in_story(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Stories without acceptance criteria should include actionable fix guidance."""
    monkeypatch.setenv("ARCWRIGHT_API_CLAUDE_API_KEY", "sk-ant-test-key")

    arcwright = tmp_path / DIR_ARCWRIGHT
    arcwright.mkdir()
    config_content = (
        'model:\n  version: "claude-opus-4-5"\n'
        "limits:\n"
        "  tokens_per_story: 200000\n"
        "  cost_per_run: 10.0\n"
        "  retry_budget: 3\n"
        "  timeout_per_story: 300\n"
        'methodology:\n  artifacts_path: "_spec"\n  type: "bmad"\n'
        'scm:\n  branch_template: "arcwright/{story_slug}"\n'
        "reproducibility:\n  enabled: false\n  retention: 30\n"
    )
    (arcwright / CONFIG_FILENAME).write_text(config_content, encoding="utf-8")

    planning = tmp_path / "_spec" / "planning-artifacts"
    planning.mkdir(parents=True)
    (planning / "prd.md").write_text("# PRD\n", encoding="utf-8")
    (planning / "architecture.md").write_text("# Architecture\n", encoding="utf-8")
    (planning / "epics.md").write_text("# Epics\n", encoding="utf-8")

    impl = tmp_path / "_spec" / "implementation-artifacts"
    impl.mkdir(parents=True)
    (impl / "1-1-story.md").write_text("# Story 1.1\n\nNo AC here\n", encoding="utf-8")

    result = runner.invoke(app, ["validate-setup", "--path", str(tmp_path)])
    assert result.exit_code == 3
    assert "Fix:" in result.output


def test_validate_setup_absolute_artifacts_path_falls_back_to_default(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Absolute methodology.artifacts_path should be ignored for project-local validation."""
    monkeypatch.setenv("ARCWRIGHT_API_CLAUDE_API_KEY", "sk-ant-test-key")

    arcwright = tmp_path / DIR_ARCWRIGHT
    arcwright.mkdir()
    config_content = (
        'model:\n  version: "claude-opus-4-5"\n'
        "limits:\n"
        "  tokens_per_story: 200000\n"
        "  cost_per_run: 10.0\n"
        "  retry_budget: 3\n"
        "  timeout_per_story: 300\n"
        'methodology:\n  artifacts_path: "/tmp/outside"\n  type: "bmad"\n'
        'scm:\n  branch_template: "arcwright/{story_slug}"\n'
        "reproducibility:\n  enabled: false\n  retention: 30\n"
    )
    (arcwright / CONFIG_FILENAME).write_text(config_content, encoding="utf-8")

    planning = tmp_path / "_spec" / "planning-artifacts"
    planning.mkdir(parents=True)
    (planning / "prd.md").write_text("# PRD\n", encoding="utf-8")
    (planning / "architecture.md").write_text("# Architecture\n", encoding="utf-8")
    (planning / "epics.md").write_text("# Epics\n", encoding="utf-8")

    impl = tmp_path / "_spec" / "implementation-artifacts"
    impl.mkdir(parents=True)
    (impl / "1-1-story.md").write_text("## Acceptance Criteria\n", encoding="utf-8")

    result = runner.invoke(app, ["validate-setup", "--path", str(tmp_path)])
    assert result.exit_code == 0
    assert "detected at ./_spec/" in result.output
