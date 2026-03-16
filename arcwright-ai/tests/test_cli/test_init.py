"""Tests for the CLI init command.

Uses typer.testing.CliRunner for command invocation.
All tests use tmp_path for full filesystem isolation.
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

import pytest
from typer.testing import CliRunner

if TYPE_CHECKING:
    from pathlib import Path

from arcwright_ai.cli.app import app
from arcwright_ai.core.constants import (
    CONFIG_FILENAME,
    DIR_ARCWRIGHT,
    DIR_RUNS,
    DIR_TMP,
    DIR_WORKTREES,
)

runner = CliRunner()

_ANSI_RE = re.compile(r"\x1b\[[0-9;]*m")


def _strip_ansi(text: str) -> str:
    return _ANSI_RE.sub("", text)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def fresh_project(tmp_path: Path) -> Path:
    """Project directory with _spec/ and planning-artifacts but no .arcwright-ai/."""
    (tmp_path / "_spec" / "planning-artifacts").mkdir(parents=True)
    (tmp_path / "_spec" / "implementation-artifacts").mkdir(parents=True)
    return tmp_path


@pytest.fixture()
def initialized_project(fresh_project: Path) -> Path:
    """Already-initialized project (runner.invoke has been called once)."""
    runner.invoke(app, ["init", "--path", str(fresh_project)])
    return fresh_project


# ---------------------------------------------------------------------------
# Task 4.2 — fresh project scaffold
# ---------------------------------------------------------------------------


def test_init_fresh_project(fresh_project: Path) -> None:
    """arcwright-ai init creates .arcwright-ai/ with all required subdirectories."""
    result = runner.invoke(app, ["init", "--path", str(fresh_project)], catch_exceptions=False)
    assert result.exit_code == 0
    arcwright = fresh_project / DIR_ARCWRIGHT
    assert arcwright.is_dir()
    assert (arcwright / CONFIG_FILENAME).is_file()
    assert (arcwright / DIR_RUNS).is_dir()
    assert (arcwright / DIR_TMP).is_dir()
    assert (arcwright / DIR_WORKTREES).is_dir()


# ---------------------------------------------------------------------------
# Task 4.3 — .gitignore created when absent
# ---------------------------------------------------------------------------


def test_init_creates_gitignore(fresh_project: Path) -> None:
    """arcwright-ai init creates .gitignore when none exists."""
    gitignore = fresh_project / ".gitignore"
    assert not gitignore.exists()

    result = runner.invoke(app, ["init", "--path", str(fresh_project)], catch_exceptions=False)
    assert result.exit_code == 0

    assert gitignore.exists()
    content = gitignore.read_text(encoding="utf-8")
    assert ".arcwright-ai/tmp/" in content
    assert ".arcwright-ai/runs/" in content


# ---------------------------------------------------------------------------
# Task 4.4 — .gitignore with unrelated content — entries appended
# ---------------------------------------------------------------------------


def test_init_appends_gitignore(fresh_project: Path) -> None:
    """Existing .gitignore with unrelated content gets arcwright entries appended."""
    gitignore = fresh_project / ".gitignore"
    original = "__pycache__/\n*.pyc\n"
    gitignore.write_text(original, encoding="utf-8")

    result = runner.invoke(app, ["init", "--path", str(fresh_project)], catch_exceptions=False)
    assert result.exit_code == 0

    content = gitignore.read_text(encoding="utf-8")
    assert "__pycache__/" in content
    assert ".arcwright-ai/tmp/" in content
    assert ".arcwright-ai/runs/" in content


# ---------------------------------------------------------------------------
# Task 4.5 — no duplicates added
# ---------------------------------------------------------------------------


def test_init_gitignore_no_duplicates(fresh_project: Path) -> None:
    """Re-running init does not duplicate .gitignore entries."""
    gitignore = fresh_project / ".gitignore"
    pre_existing = ".arcwright-ai/tmp/\n.arcwright-ai/runs/\n"
    gitignore.write_text(pre_existing, encoding="utf-8")

    result = runner.invoke(app, ["init", "--path", str(fresh_project)], catch_exceptions=False)
    assert result.exit_code == 0

    lines = gitignore.read_text(encoding="utf-8").splitlines()
    assert lines.count(".arcwright-ai/tmp/") == 1
    assert lines.count(".arcwright-ai/runs/") == 1


# ---------------------------------------------------------------------------
# Task 4.6 — partial entries — only missing entry appended
# ---------------------------------------------------------------------------


def test_init_gitignore_partial_entries(fresh_project: Path) -> None:
    """Only the missing .gitignore entry is appended when one already exists."""
    gitignore = fresh_project / ".gitignore"
    gitignore.write_text(".arcwright-ai/tmp/\n", encoding="utf-8")

    result = runner.invoke(app, ["init", "--path", str(fresh_project)], catch_exceptions=False)
    assert result.exit_code == 0

    lines = gitignore.read_text(encoding="utf-8").splitlines()
    assert lines.count(".arcwright-ai/tmp/") == 1
    assert ".arcwright-ai/runs/" in lines


# ---------------------------------------------------------------------------
# Task 4.7 — idempotent: preserves existing config
# ---------------------------------------------------------------------------


def test_init_idempotent_preserves_config(initialized_project: Path) -> None:
    """Re-running init does NOT overwrite an existing config.yaml."""
    config_path = initialized_project / DIR_ARCWRIGHT / CONFIG_FILENAME
    custom_content = '# custom\nmodel:\n  version: "custom-model"\n'
    config_path.write_text(custom_content, encoding="utf-8")

    result = runner.invoke(app, ["init", "--path", str(initialized_project)], catch_exceptions=False)
    assert result.exit_code == 0

    assert config_path.read_text(encoding="utf-8") == custom_content


# ---------------------------------------------------------------------------
# Task 4.8 — idempotent: creates missing dirs only
# ---------------------------------------------------------------------------


def test_init_idempotent_creates_missing_dirs(initialized_project: Path) -> None:
    """Re-init creates any missing subdirectory without touching existing ones."""
    tmp_dir = initialized_project / DIR_ARCWRIGHT / DIR_TMP
    tmp_dir.rmdir()
    assert not tmp_dir.exists()

    result = runner.invoke(app, ["init", "--path", str(initialized_project)], catch_exceptions=False)
    assert result.exit_code == 0
    assert tmp_dir.is_dir()


# ---------------------------------------------------------------------------
# Task 4.9 — BMAD artifact detection
# ---------------------------------------------------------------------------


def test_init_detects_bmad_artifacts(fresh_project: Path) -> None:
    """Detected BMAD artifacts are reported in command output."""
    planning = fresh_project / "_spec" / "planning-artifacts"
    impl = fresh_project / "_spec" / "implementation-artifacts"

    (planning / "prd.md").write_text("# PRD", encoding="utf-8")
    (planning / "architecture.md").write_text("# Architecture", encoding="utf-8")
    (planning / "epics.md").write_text("# Epics", encoding="utf-8")
    (impl / "1-1-scaffold.md").write_text("# Story", encoding="utf-8")
    (impl / "1-2-core.md").write_text("# Story", encoding="utf-8")

    result = runner.invoke(app, ["init", "--path", str(fresh_project)], catch_exceptions=False)
    assert result.exit_code == 0

    # Output goes to stderr; CliRunner mixes stderr+stdout in result.output
    output = result.output
    assert "prd" in output.lower() or "PRD" in output
    assert "architecture" in output.lower() or "Architecture" in output
    # At least the story count should appear
    assert "2" in output or "stories" in output.lower()


# ---------------------------------------------------------------------------
# Task 4.10 — no _spec/ directory → graceful message
# ---------------------------------------------------------------------------


def test_init_no_spec_directory(tmp_path: Path) -> None:
    """init works when _spec/ does not exist and reports no BMAD artifacts."""
    result = runner.invoke(app, ["init", "--path", str(tmp_path)], catch_exceptions=False)
    assert result.exit_code == 0
    assert "No BMAD artifacts" in result.output or "no bmad" in result.output.lower()


# ---------------------------------------------------------------------------
# Task 4.11 — exit code is 0
# ---------------------------------------------------------------------------


def test_init_exit_code_zero(fresh_project: Path) -> None:
    """arcwright-ai init exits with code 0 on success."""
    result = runner.invoke(app, ["init", "--path", str(fresh_project)])
    assert result.exit_code == 0


# ---------------------------------------------------------------------------
# Task 4.12 — default config has no api section
# ---------------------------------------------------------------------------


def test_init_default_config_has_no_api_section(fresh_project: Path) -> None:
    """The generated config.yaml must not contain an api section or api keys."""
    result = runner.invoke(app, ["init", "--path", str(fresh_project)], catch_exceptions=False)
    assert result.exit_code == 0

    config_path = fresh_project / DIR_ARCWRIGHT / CONFIG_FILENAME
    content = config_path.read_text(encoding="utf-8")
    assert "api:" not in content
    assert "claude_api_key" not in content


def test_init_help_lists_path_options() -> None:
    """init --help shows --path/-p options for project root selection."""
    result = runner.invoke(app, ["init", "--help"], catch_exceptions=False)
    assert result.exit_code == 0
    plain = _strip_ansi(result.output)
    assert "--path" in plain
    assert "-p" in plain


def test_root_help_lists_init_command() -> None:
    """CLI root help includes the init command."""
    result = runner.invoke(app, ["--help"], catch_exceptions=False)
    assert result.exit_code == 0
    assert "init" in result.output


# ---------------------------------------------------------------------------
# .env.example creation
# ---------------------------------------------------------------------------


def test_init_creates_env_example(fresh_project: Path) -> None:
    """arcwright-ai init creates .env.example at the project root."""
    result = runner.invoke(app, ["init", "--path", str(fresh_project)], catch_exceptions=False)
    assert result.exit_code == 0

    env_example = fresh_project / ".env.example"
    assert env_example.is_file()
    content = env_example.read_text(encoding="utf-8")
    assert "ARCWRIGHT_API_CLAUDE_API_KEY" in content
    assert "LANGCHAIN_TRACING_V2" in content


def test_init_preserves_existing_env_example(initialized_project: Path) -> None:
    """Re-running init does not overwrite a user-modified .env.example."""
    env_example = initialized_project / ".env.example"
    env_example.write_text("# custom\n", encoding="utf-8")

    runner.invoke(app, ["init", "--path", str(initialized_project)], catch_exceptions=False)
    assert env_example.read_text(encoding="utf-8") == "# custom\n"


def test_init_gitignore_includes_dotenv(fresh_project: Path) -> None:
    """arcwright-ai init adds .env to .gitignore."""
    runner.invoke(app, ["init", "--path", str(fresh_project)], catch_exceptions=False)
    content = (fresh_project / ".gitignore").read_text(encoding="utf-8")
    assert ".env" in content.splitlines()
