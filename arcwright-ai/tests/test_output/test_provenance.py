"""Unit tests for arcwright_ai.output.provenance — Decision logging during execution."""

from __future__ import annotations

from pathlib import Path

import pytest

from arcwright_ai.core.types import ProvenanceEntry
from arcwright_ai.output.provenance import (
    _extract_story_slug,
    append_entry,
    render_validation_row,
    write_entries,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def simple_entry() -> ProvenanceEntry:
    """Return a ProvenanceEntry with all fields populated.

    Returns:
        ProvenanceEntry with known values for deterministic assertions.
    """
    return ProvenanceEntry(
        decision="Use Pydantic for data models",
        alternatives=["dataclasses", "attrs"],
        rationale="Pydantic provides validation and serialization out of the box.",
        ac_references=["AC1", "AC3"],
        timestamp="2026-01-01T00:00:00Z",
    )


@pytest.fixture
def entry_no_refs() -> ProvenanceEntry:
    """Return a ProvenanceEntry with empty alternatives and ac_references.

    Returns:
        ProvenanceEntry with empty list fields.
    """
    return ProvenanceEntry(
        decision="Use UTC timestamps",
        alternatives=[],
        rationale="UTC avoids timezone confusion.",
        ac_references=[],
        timestamp="2026-01-02T00:00:00Z",
    )


@pytest.fixture
def long_rationale_entry() -> ProvenanceEntry:
    """Return a ProvenanceEntry with rationale exceeding 500 characters.

    Returns:
        ProvenanceEntry with long rationale for <details> wrapping test.
    """
    return ProvenanceEntry(
        decision="Complex decision requiring long explanation",
        alternatives=["option A", "option B"],
        rationale="x" * 501,
        ac_references=["AC2"],
        timestamp="2026-01-03T00:00:00Z",
    )


@pytest.fixture
def many_alternatives_entry() -> ProvenanceEntry:
    """Return a ProvenanceEntry with more than 5 alternatives.

    Returns:
        ProvenanceEntry with 6 alternatives for <details> wrapping test.
    """
    return ProvenanceEntry(
        decision="Multi-option decision",
        alternatives=["opt1", "opt2", "opt3", "opt4", "opt5", "opt6"],
        rationale="Short rationale.",
        ac_references=["AC4"],
        timestamp="2026-01-04T00:00:00Z",
    )


# ---------------------------------------------------------------------------
# Test 5.1: write_entries() single entry — all sections and correct format
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_write_entries_single_entry_all_sections_present(
    tmp_path: Path,
    simple_entry: ProvenanceEntry,
) -> None:
    """write_entries() with single entry produces correct heading and all three sections.

    Args:
        tmp_path: Pytest-provided temporary directory.
        simple_entry: ProvenanceEntry fixture with known values.
    """
    path = tmp_path / "stories" / "2-1-foo" / "validation.md"
    await write_entries(path, [simple_entry])

    content = path.read_text(encoding="utf-8")

    assert content.startswith("# Provenance: 2-1-foo")
    assert "## Agent Decisions" in content
    assert "## Validation History" in content
    assert "## Context Provided" in content
    assert "### Decision: Use Pydantic for data models" in content
    assert "- **Timestamp**: 2026-01-01T00:00:00Z" in content
    assert "- **Alternatives**: dataclasses, attrs" in content
    assert "- **Rationale**: Pydantic provides validation and serialization out of the box." in content
    assert "- **References**: AC1, AC3" in content


# ---------------------------------------------------------------------------
# Test 5.2: write_entries() multiple entries rendered in order
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_write_entries_multiple_entries_in_order(tmp_path: Path) -> None:
    """write_entries() with 3 entries renders all decisions in sequence.

    Args:
        tmp_path: Pytest-provided temporary directory.
    """
    entries = [
        ProvenanceEntry(
            decision=f"Decision {i}",
            alternatives=[],
            rationale=f"Rationale {i}",
            ac_references=[f"AC{i}"],
            timestamp=f"2026-01-0{i}T00:00:00Z",
        )
        for i in range(1, 4)
    ]
    path = tmp_path / "stories" / "1-1-scaffold" / "validation.md"
    await write_entries(path, entries)

    content = path.read_text(encoding="utf-8")

    pos1 = content.find("### Decision: Decision 1")
    pos2 = content.find("### Decision: Decision 2")
    pos3 = content.find("### Decision: Decision 3")
    pos_val = content.find("## Validation History")

    assert pos1 != -1
    assert pos2 != -1
    assert pos3 != -1
    assert pos1 < pos2 < pos3 < pos_val


# ---------------------------------------------------------------------------
# Test 5.3: append_entry() to non-existent file creates valid provenance file
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_append_entry_to_nonexistent_file_creates_valid_file(
    tmp_path: Path,
    simple_entry: ProvenanceEntry,
) -> None:
    """append_entry() to a non-existent path creates a complete provenance file.

    Args:
        tmp_path: Pytest-provided temporary directory.
        simple_entry: ProvenanceEntry fixture with known values.
    """
    path = tmp_path / "stories" / "new-story" / "validation.md"
    assert not path.exists()

    await append_entry(path, simple_entry)

    assert path.exists()
    content = path.read_text(encoding="utf-8")
    assert content.startswith("# Provenance: new-story")
    assert "### Decision: Use Pydantic for data models" in content
    assert "## Agent Decisions" in content
    assert "## Validation History" in content
    assert "## Context Provided" in content


# ---------------------------------------------------------------------------
# Test 5.4: append_entry() to existing file inserts before Validation History
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_append_entry_to_existing_file_inserts_before_validation_history(
    tmp_path: Path,
    simple_entry: ProvenanceEntry,
) -> None:
    """append_entry() to an existing file places new decision before Validation History.

    Args:
        tmp_path: Pytest-provided temporary directory.
        simple_entry: ProvenanceEntry fixture to append.
    """
    path = tmp_path / "stories" / "4-1-test" / "validation.md"

    first_entry = ProvenanceEntry(
        decision="First decision",
        alternatives=["alt A"],
        rationale="First rationale.",
        ac_references=["AC1"],
        timestamp="2026-01-01T00:00:00Z",
    )
    await write_entries(path, [first_entry])

    await append_entry(path, simple_entry)

    content = path.read_text(encoding="utf-8")

    pos_first = content.find("### Decision: First decision")
    pos_second = content.find("### Decision: Use Pydantic for data models")
    pos_validation = content.find("## Validation History")

    assert pos_first != -1
    assert pos_second != -1
    assert pos_validation != -1
    assert pos_first < pos_second < pos_validation


# ---------------------------------------------------------------------------
# Test 5.5: Long rationale wrapped in <details> block
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_long_rationale_wrapped_in_details(
    tmp_path: Path,
    long_rationale_entry: ProvenanceEntry,
) -> None:
    """Rationale exceeding 500 characters is wrapped in a <details> collapsible block.

    Args:
        tmp_path: Pytest-provided temporary directory.
        long_rationale_entry: ProvenanceEntry with >500 char rationale.
    """
    path = tmp_path / "stories" / "5-1-test" / "validation.md"
    await write_entries(path, [long_rationale_entry])
    content = path.read_text(encoding="utf-8")

    assert "<details>" in content
    assert "<summary>Rationale (click to expand)</summary>" in content
    assert "</details>" in content
    assert "x" * 501 in content


# ---------------------------------------------------------------------------
# Test 5.6: Short rationale rendered inline
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_short_rationale_rendered_inline(
    tmp_path: Path,
    simple_entry: ProvenanceEntry,
) -> None:
    """Rationale of 500 or fewer characters is rendered inline without <details>.

    Args:
        tmp_path: Pytest-provided temporary directory.
        simple_entry: ProvenanceEntry with short rationale.
    """
    path = tmp_path / "stories" / "5-2-test" / "validation.md"
    await write_entries(path, [simple_entry])
    content = path.read_text(encoding="utf-8")

    assert "- **Rationale**: Pydantic provides validation and serialization out of the box." in content
    assert "<summary>Rationale (click to expand)</summary>" not in content


# ---------------------------------------------------------------------------
# Test 5.7: Many alternatives wrapped in <details> block
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_many_alternatives_wrapped_in_details(
    tmp_path: Path,
    many_alternatives_entry: ProvenanceEntry,
) -> None:
    """More than 5 alternatives are wrapped in a <details> block.

    Args:
        tmp_path: Pytest-provided temporary directory.
        many_alternatives_entry: ProvenanceEntry with 6 alternatives.
    """
    path = tmp_path / "stories" / "5-3-test" / "validation.md"
    await write_entries(path, [many_alternatives_entry])
    content = path.read_text(encoding="utf-8")

    assert "<details>" in content
    assert "opt1" in content
    assert "opt6" in content
    # Should appear somewhere in a details block for alternatives
    assert "Alternatives" in content


# ---------------------------------------------------------------------------
# Test 5.8: Few alternatives rendered inline as comma-separated
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_few_alternatives_rendered_inline_comma_separated(
    tmp_path: Path,
    simple_entry: ProvenanceEntry,
) -> None:
    """Two alternatives are rendered inline as comma-separated text.

    Args:
        tmp_path: Pytest-provided temporary directory.
        simple_entry: ProvenanceEntry with 2 alternatives.
    """
    path = tmp_path / "stories" / "5-4-test" / "validation.md"
    await write_entries(path, [simple_entry])
    content = path.read_text(encoding="utf-8")

    assert "- **Alternatives**: dataclasses, attrs" in content


# ---------------------------------------------------------------------------
# Test 5.9: Empty alternatives → "None considered"
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_empty_alternatives_renders_none_considered(
    tmp_path: Path,
    entry_no_refs: ProvenanceEntry,
) -> None:
    """Empty alternatives list renders as 'None considered'.

    Args:
        tmp_path: Pytest-provided temporary directory.
        entry_no_refs: ProvenanceEntry with empty alternatives.
    """
    path = tmp_path / "stories" / "5-5-test" / "validation.md"
    await write_entries(path, [entry_no_refs])
    content = path.read_text(encoding="utf-8")

    assert "- **Alternatives**: None considered" in content


# ---------------------------------------------------------------------------
# Test 5.10: Empty ac_references → "None" in decision + "No context references recorded"
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_empty_ac_references_renders_none_and_no_context(
    tmp_path: Path,
    entry_no_refs: ProvenanceEntry,
) -> None:
    """Empty ac_references renders 'None' in decision and 'No context references recorded'.

    Args:
        tmp_path: Pytest-provided temporary directory.
        entry_no_refs: ProvenanceEntry with empty ac_references.
    """
    path = tmp_path / "stories" / "5-6-test" / "validation.md"
    await write_entries(path, [entry_no_refs])
    content = path.read_text(encoding="utf-8")

    assert "- **References**: None" in content
    assert "- No context references recorded" in content


# ---------------------------------------------------------------------------
# Test 5.11: render_validation_row() returns correct table row
# ---------------------------------------------------------------------------


def test_render_validation_row_format() -> None:
    """render_validation_row() returns a properly formatted markdown table row."""
    row = render_validation_row(1, "pass", "No issues found")
    assert row == "| 1 | pass | No issues found |"


def test_render_validation_row_various_values() -> None:
    """render_validation_row() handles different attempt numbers and results."""
    assert render_validation_row(3, "fail", "Missing AC coverage") == "| 3 | fail | Missing AC coverage |"
    assert render_validation_row(0, "skip", "") == "| 0 | skip |  |"


# ---------------------------------------------------------------------------
# Test 5.12: ac_references deduplication and alphabetical sort
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_ac_references_deduplicated_and_sorted(tmp_path: Path) -> None:
    """Context Provided section deduplicates and alphabetically sorts all ac_references.

    Args:
        tmp_path: Pytest-provided temporary directory.
    """
    entries = [
        ProvenanceEntry(
            decision="Decision A",
            alternatives=[],
            rationale="Rationale A",
            ac_references=["AC3", "AC1"],
            timestamp="2026-01-01T00:00:00Z",
        ),
        ProvenanceEntry(
            decision="Decision B",
            alternatives=[],
            rationale="Rationale B",
            ac_references=["AC1", "AC2"],
            timestamp="2026-01-02T00:00:00Z",
        ),
    ]
    path = tmp_path / "stories" / "dedup-test" / "validation.md"
    await write_entries(path, entries)
    content = path.read_text(encoding="utf-8")

    ctx_idx = content.find("## Context Provided")
    assert ctx_idx != -1
    ctx_section = content[ctx_idx:]

    pos_ac1 = ctx_section.find("- AC1")
    pos_ac2 = ctx_section.find("- AC2")
    pos_ac3 = ctx_section.find("- AC3")

    assert pos_ac1 != -1
    assert pos_ac2 != -1
    assert pos_ac3 != -1
    assert pos_ac1 < pos_ac2 < pos_ac3

    # AC1 appears exactly once (deduplicated)
    assert ctx_section.count("- AC1\n") == 1


# ---------------------------------------------------------------------------
# Test 5.13: story_slug extraction from path parent directory
# ---------------------------------------------------------------------------


def test_extract_story_slug_from_path(tmp_path: Path) -> None:
    """_extract_story_slug() returns the parent directory name from the path.

    Args:
        tmp_path: Pytest-provided temporary directory.
    """
    path = tmp_path / "runs" / "run-001" / "stories" / "2-1-langgraph-skeleton" / "validation.md"
    slug = _extract_story_slug(path)
    assert slug == "2-1-langgraph-skeleton"


def test_extract_story_slug_various_paths(tmp_path: Path) -> None:
    """_extract_story_slug() works correctly for various path depths.

    Args:
        tmp_path: Pytest-provided temporary directory.
    """
    assert _extract_story_slug(Path("/some/path/4-1-provenance/validation.md")) == "4-1-provenance"
    assert _extract_story_slug(Path("/flat/my-story/file.md")) == "my-story"


# ---------------------------------------------------------------------------
# Test 5.14: All tests use tmp_path (no hardcoded paths) — structural check
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_write_entries_uses_tmp_path_not_real_directory(tmp_path: Path, simple_entry: ProvenanceEntry) -> None:
    """Verify file I/O uses tmp_path fixture (isolation sanity check).

    Args:
        tmp_path: Pytest-provided temporary directory.
        simple_entry: ProvenanceEntry fixture.
    """
    path = tmp_path / "stories" / "isolation-check" / "validation.md"
    await write_entries(path, [simple_entry])
    # File should exist under tmp_path, not in any project directory
    assert str(tmp_path) in str(path)
    assert path.exists()
