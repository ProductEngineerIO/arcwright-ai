"""Tests for the CLI version command and --version flag.

Covers:
- `arcwright-ai version` subcommand prints version string and exits 0 (AC #1, #3)
- `arcwright-ai --version` flag prints version string and exits 0 (AC #2, #3)
- Version string matches arcwright_ai.__version__ (AC #3)
"""

from __future__ import annotations

from typer.testing import CliRunner

import arcwright_ai
from arcwright_ai.cli.app import app

runner = CliRunner()


def test_version_subcommand_outputs_version() -> None:
    """arcwright-ai version prints 'arcwright-ai X.Y.Z' and exits 0."""
    result = runner.invoke(app, ["version"])
    assert result.exit_code == 0
    assert f"arcwright-ai {arcwright_ai.__version__}" in result.output


def test_version_flag_outputs_version() -> None:
    """arcwright-ai --version prints 'arcwright-ai X.Y.Z' and exits 0."""
    result = runner.invoke(app, ["--version"])
    assert result.exit_code == 0
    assert f"arcwright-ai {arcwright_ai.__version__}" in result.output


def test_version_string_matches_package_version() -> None:
    """Version output embeds the exact __version__ attribute."""
    result = runner.invoke(app, ["version"])
    assert arcwright_ai.__version__ in result.output
