"""Pytest configuration and shared fixtures for Arcwright AI tests."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pathlib import Path

import pytest


@pytest.fixture
def tmp_project(tmp_path: Path) -> Path:
    """Scaffold a minimal Arcwright AI project directory for integration tests.

    Creates the expected directory layout under a temporary path::

        .arcwright-ai/   — runtime state directory (runs, provenance, tmp)
        _spec/           — BMAD planning artifacts directory

    Returns:
        Path: Root of the temporary project directory.
    """
    (tmp_path / ".arcwright-ai").mkdir()
    (tmp_path / "_spec").mkdir()
    return tmp_path
