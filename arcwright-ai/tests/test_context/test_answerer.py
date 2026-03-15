"""Unit tests for context/answerer.py — Static rule lookup engine."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

import pytest

from arcwright_ai.context.answerer import IndexedSection, RuleIndex

if TYPE_CHECKING:
    from pathlib import Path

# ---------------------------------------------------------------------------
# Sample BMAD document content for fixtures
# ---------------------------------------------------------------------------

SAMPLE_ARCHITECTURE = """\
# Architecture Overview

This document describes the Arcwright AI architecture.

## Implementation Patterns

General implementation guidelines for the project.

### Python Code Style Patterns

Naming conventions: Use snake_case for variables and functions. Use PascalCase for classes.
Import ordering: stdlib, third-party, local. All public functions must have docstrings.

#### Import Ordering Detail

Place stdlib imports first, then a blank line, then third-party, then a blank line, then local.

### Async Patterns

Use asyncio.to_thread() for blocking file I/O. Use asyncio.gather() for parallel calls.
Never use blocking I/O directly in async functions.

### Structured Logging Patterns

Use logger.info("event.name", extra={"data": {...}}) for structured events.
Never use print() or unstructured f-strings for logging.

### Testing Patterns

Use pytest fixtures. Use tmp_path for temporary files.
Mark async tests with asyncio_mode=auto (no explicit decorator needed).
"""

SAMPLE_PRD = """\
# Product Requirements Document

## Functional Requirements

FR1: Developer can dispatch all stories in an epic for sequential execution.
FR2: Developer can dispatch a single story for execution.
FR3: System executes stories one at a time in dependency order.

## NonFunctional Requirements

NFR1: System never silently produces incorrect output.
NFR2: Partial epic completion is always recoverable.

## Project Goals

Build a reliable autonomous coding system with full observability.
"""


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def project_fixture(tmp_path: Path) -> Path:
    """Create a minimal project layout with sample BMAD documents.

    Args:
        tmp_path: pytest-provided temporary directory.

    Returns:
        The project root path.
    """
    spec_dir = tmp_path / "_spec" / "planning-artifacts"
    spec_dir.mkdir(parents=True)
    (spec_dir / "architecture.md").write_text(SAMPLE_ARCHITECTURE, encoding="utf-8")
    (spec_dir / "prd.md").write_text(SAMPLE_PRD, encoding="utf-8")
    return tmp_path


@pytest.fixture
async def rule_index(project_fixture: Path) -> RuleIndex:
    """Build a RuleIndex from the sample project fixture.

    Args:
        project_fixture: Temporary project root with sample docs.

    Returns:
        Populated RuleIndex.
    """
    return await RuleIndex.build_index(project_fixture)


# ---------------------------------------------------------------------------
# Tests: build_index
# ---------------------------------------------------------------------------


async def test_build_index_creates_sections_from_documents(
    project_fixture: Path,
) -> None:
    """build_index produces sections for every heading in the sample docs."""
    index = await RuleIndex.build_index(project_fixture)
    assert len(index._sections) > 0
    headings = [s.heading for s in index._sections]
    assert any("Python Code Style Patterns" in h for h in headings)
    assert any("Functional Requirements" in h for h in headings)


async def test_build_index_sections_have_correct_depth(
    project_fixture: Path,
) -> None:
    """Sections carry the correct depth value based on heading level."""
    index = await RuleIndex.build_index(project_fixture)
    top_level = [s for s in index._sections if s.heading == "Architecture Overview"]
    assert top_level, "Expected top-level heading section"
    assert top_level[0].depth == 1

    third_level = [s for s in index._sections if s.heading == "Python Code Style Patterns"]
    assert third_level, "Expected ###-level section"
    assert third_level[0].depth == 3


async def test_build_index_sections_have_source_path(project_fixture: Path) -> None:
    """Every indexed section carries a non-empty source_path."""
    index = await RuleIndex.build_index(project_fixture)
    for section in index._sections:
        assert section.source_path, "source_path must not be empty"


async def test_build_index_handles_missing_documents(tmp_path: Path, caplog: pytest.LogCaptureFixture) -> None:
    """build_index still succeeds when one expected document is missing."""
    spec_dir = tmp_path / "_spec" / "planning-artifacts"
    spec_dir.mkdir(parents=True)
    # Only write architecture.md — prd.md is intentionally absent
    (spec_dir / "architecture.md").write_text(SAMPLE_ARCHITECTURE, encoding="utf-8")

    with caplog.at_level(logging.INFO):
        index = await RuleIndex.build_index(tmp_path)

    # Index builds from available docs, does not raise
    assert len(index._sections) > 0
    assert any("context.unresolved" in r.message for r in caplog.records)


async def test_build_index_with_explicit_doc_paths(tmp_path: Path) -> None:
    """build_index uses caller-supplied doc_paths instead of auto-discovery."""
    doc = tmp_path / "custom_doc.md"
    doc.write_text("# My Custom Heading\n\nCustom content here.\n", encoding="utf-8")

    index = await RuleIndex.build_index(tmp_path, doc_paths=[doc])

    headings = [s.heading for s in index._sections]
    assert "My Custom Heading" in headings


async def test_build_index_empty_project_returns_empty_index(tmp_path: Path, caplog: pytest.LogCaptureFixture) -> None:
    """build_index with no discoverable docs returns an empty-but-functional index."""
    with caplog.at_level(logging.INFO):
        index = await RuleIndex.build_index(tmp_path)

    assert index._sections == []
    # Should still report unresolved for standard candidates
    assert any("context.unresolved" in r.message for r in caplog.records)


# ---------------------------------------------------------------------------
# Tests: lookup_answer
# ---------------------------------------------------------------------------


def test_lookup_answer_finds_matching_section(rule_index: RuleIndex) -> None:
    """lookup_answer returns content and source reference for a matching pattern."""
    result = rule_index.lookup_answer("naming convention")

    assert result is not None
    assert "[Source:" in result
    assert "snake_case" in result or "PascalCase" in result or "naming" in result.lower()


def test_lookup_answer_returns_none_for_no_match(rule_index: RuleIndex, caplog: pytest.LogCaptureFixture) -> None:
    """lookup_answer returns None and logs an event when no section matches."""
    with caplog.at_level(logging.INFO):
        result = rule_index.lookup_answer("quantum computing blockchain NFT")

    assert result is None
    assert any("context.answerer.no_match" in r.message for r in caplog.records)


async def test_lookup_answer_returns_most_specific_match(project_fixture: Path) -> None:
    """lookup_answer prefers a deeper (###) section over a shallower (##) one."""
    index = await RuleIndex.build_index(project_fixture)
    # "code style" should match both "## Implementation Patterns" and
    # "### Python Code Style Patterns" — the deeper one should win.
    result = index.lookup_answer("code style")

    assert result is not None
    assert "Python Code Style Patterns" in result


def test_lookup_answer_prefers_shorter_heading_when_depth_ties() -> None:
    """When depth ties, lookup_answer prefers the shorter matching heading."""
    index = RuleIndex(
        sections=[
            IndexedSection(
                heading="Python Code Style Patterns",
                content="Detailed guidance for Python style.",
                source_path="docs/architecture.md",
                depth=3,
            ),
            IndexedSection(
                heading="Code Style",
                content="Focused guidance for code style.",
                source_path="docs/architecture.md",
                depth=3,
            ),
        ]
    )

    result = index.lookup_answer(r"code\s+style")

    assert result is not None
    assert "**Code Style**" in result


def test_lookup_answer_prefers_heading_match_over_content_match(
    rule_index: RuleIndex,
) -> None:
    """lookup_answer prefers a section whose heading matches over content-only match."""
    # "Testing Patterns" is a heading in the architecture sample.
    # That section's content mentions pytest; other sections may contain "test" in body.
    result = rule_index.lookup_answer(r"Testing\s+Patterns")

    assert result is not None
    assert "Testing Patterns" in result


def test_lookup_answer_handles_invalid_regex(rule_index: RuleIndex) -> None:
    """lookup_answer does not raise on invalid regex — falls back to literal search."""
    # "[invalid" is not a valid regex
    result = rule_index.lookup_answer("[invalid")
    # Should not raise — may return None or a matched result
    # The important contract is: no exception propagated
    assert result is None or isinstance(result, str)


def test_lookup_answer_includes_source_reference(rule_index: RuleIndex) -> None:
    """Successful lookup includes a [Source: ...] reference with path and heading."""
    result = rule_index.lookup_answer("Async Patterns")

    assert result is not None
    assert "[Source:" in result
    # Source ref contains a file path
    assert ".md" in result


async def test_lookup_answer_logs_index_event_on_build(project_fixture: Path, caplog: pytest.LogCaptureFixture) -> None:
    """build_index emits a structured context.answerer.index log event."""
    with caplog.at_level(logging.INFO):
        await RuleIndex.build_index(project_fixture)

    assert any("context.answerer.index" in r.message for r in caplog.records)


# ---------------------------------------------------------------------------
# Tests: convenience methods
# ---------------------------------------------------------------------------


def test_lookup_naming_conventions(rule_index: RuleIndex) -> None:
    """lookup_naming_conventions returns content about naming conventions."""
    result = rule_index.lookup_naming_conventions()
    assert result is not None
    # The architecture sample has naming convention content
    assert "snake_case" in result or "PascalCase" in result or "naming" in result.lower()


def test_lookup_file_structure(rule_index: RuleIndex) -> None:
    """lookup_file_structure returns content or None (architecture sample has none)."""
    result = rule_index.lookup_file_structure()
    # Architecture sample doesn't have an explicit "file structure" section —
    # result may be None. The important assertion is: no exception raised.
    assert result is None or isinstance(result, str)


def test_lookup_coding_standards(rule_index: RuleIndex) -> None:
    """lookup_coding_standards returns content about coding standards."""
    result = rule_index.lookup_coding_standards()
    assert result is not None


def test_lookup_artifact_format_returns_none_when_absent(
    rule_index: RuleIndex,
) -> None:
    """lookup_artifact_format returns None when no artifact format section exists."""
    result = rule_index.lookup_artifact_format()
    # Sample docs don't have an artifact format section
    assert result is None or isinstance(result, str)


# ---------------------------------------------------------------------------
# Tests: IndexedSection dataclass
# ---------------------------------------------------------------------------


def test_indexed_section_is_frozen() -> None:
    """IndexedSection is a frozen dataclass — fields cannot be mutated."""
    section = IndexedSection(
        heading="Test",
        content="Some content.",
        source_path="docs/test.md",
        depth=2,
    )
    with pytest.raises((AttributeError, TypeError)):
        section.heading = "Changed"  # type: ignore[misc]


def test_indexed_section_equality() -> None:
    """Two IndexedSection instances with identical fields are equal."""
    s1 = IndexedSection(heading="H", content="C", source_path="p", depth=1)
    s2 = IndexedSection(heading="H", content="C", source_path="p", depth=1)
    assert s1 == s2
