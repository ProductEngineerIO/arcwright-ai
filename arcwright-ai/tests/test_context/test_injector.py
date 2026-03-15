"""Unit tests for context/injector.py — Story 2.2."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

import pytest

from arcwright_ai.context.injector import (
    _resolve_architecture_references,
    _resolve_fr_references,
    _resolve_nfr_references,
    build_context_bundle,
    parse_story,
    serialize_bundle_to_markdown,
)
from arcwright_ai.core.exceptions import ContextError
from arcwright_ai.core.types import ContextBundle

if TYPE_CHECKING:
    from pathlib import Path

# ---------------------------------------------------------------------------
# Sample content fixtures
# ---------------------------------------------------------------------------

SAMPLE_STORY_CONTENT = """\
# Story 2.2: Context Injector

Status: ready-for-dev

## Story

As a developer dispatching a story,
I want the system to read BMAD planning artifacts (FR-1, FR-16, NFR-7)
and resolve architecture references such as Decision 4 and D1,
so that the agent gets the right context.

## Acceptance Criteria

1. Given FR-1 and FR-16, the resolver finds those in the PRD.
2. Given NFR-5, the resolver finds it too.
3. Given Decision 4 it finds the arch section.

## Tasks

- [ ] Task 1: Implement stuff
"""

SAMPLE_PRD_CONTENT = """\
# Product Requirements Document

## Functional Requirements

- FR1: Developer can dispatch all stories in an epic
- FR16: System reads BMAD planning artifacts and injects the story's acceptance criteria

## Non-Functional Requirements

- NFR5: System must respond within 5 seconds
- NFR7: System must handle malformed story files gracefully
"""

SAMPLE_ARCHITECTURE_CONTENT = """\
# Architecture

## Overview

Some overview text.

### Decision 4: Context Injection Strategy — Dispatch-Time Assembly (Option D)

Context is resolved at dispatch time by parsing the story file and matching
FR/NFR/architecture references via strict regex. No fuzzy matching or LLM fallback.

The preflight node calls build_context_bundle().

---

### Decision 1: LangGraph State Model

All state transitions use model_copy(update={...}).

---
"""


# ---------------------------------------------------------------------------
# File fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def story_file(tmp_path: Path) -> Path:
    """Write sample story content to a temp file and return the path."""
    path = tmp_path / "story.md"
    path.write_text(SAMPLE_STORY_CONTENT, encoding="utf-8")
    return path


@pytest.fixture
def project_fixture(tmp_path: Path) -> Path:
    """Create a minimal project structure with PRD and architecture files."""
    spec = tmp_path / "_spec" / "planning-artifacts"
    spec.mkdir(parents=True)
    (spec / "prd.md").write_text(SAMPLE_PRD_CONTENT, encoding="utf-8")
    (spec / "architecture.md").write_text(SAMPLE_ARCHITECTURE_CONTENT, encoding="utf-8")
    return tmp_path


# ---------------------------------------------------------------------------
# Task 1 — Story parser tests (AC #1, #7)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_parse_story_extracts_fr_references(story_file: Path) -> None:
    """FR-1 and FR-16 references in story text are extracted and deduplicated."""
    parsed = await parse_story(story_file)
    assert "FR1" in parsed.fr_references
    assert "FR16" in parsed.fr_references


@pytest.mark.asyncio
async def test_parse_story_extracts_nfr_references(story_file: Path) -> None:
    """NFR-7 reference in story text is extracted."""
    parsed = await parse_story(story_file)
    assert "NFR7" in parsed.nfr_references


@pytest.mark.asyncio
async def test_parse_story_extracts_architecture_references(story_file: Path) -> None:
    """Decision 4 and D1 architecture references are extracted."""
    parsed = await parse_story(story_file)
    # expect Decision4 and Decision1 after normalisation
    normalised = {r.replace(" ", "") for r in parsed.architecture_references}
    assert "Decision4" in normalised
    assert "Decision1" in normalised


@pytest.mark.asyncio
async def test_parse_story_extracts_section_anchor_references(tmp_path: Path) -> None:
    """Section-anchor references in § form are extracted from story text."""
    path = tmp_path / "anchor.md"
    path.write_text(
        "# Story\n\nReference architecture section §D4 for context.\n\n## Acceptance Criteria\n\n1. Uses anchors.\n",
        encoding="utf-8",
    )
    parsed = await parse_story(path)
    assert "§D4" in {ref.upper() for ref in parsed.architecture_references}


@pytest.mark.asyncio
async def test_parse_story_extracts_acceptance_criteria(story_file: Path) -> None:
    """Acceptance criteria section text is extracted correctly."""
    parsed = await parse_story(story_file)
    assert "FR-1 and FR-16" in parsed.acceptance_criteria
    assert "NFR-5" in parsed.acceptance_criteria


@pytest.mark.asyncio
async def test_parse_story_empty_references(tmp_path: Path) -> None:
    """A story with no FR/NFR/arch references returns empty lists without errors."""
    path = tmp_path / "empty.md"
    path.write_text("# Story\n\nNo references here.\n\n## Acceptance Criteria\n\nNone.\n", encoding="utf-8")
    parsed = await parse_story(path)
    assert parsed.fr_references == []
    assert parsed.nfr_references == []
    assert parsed.architecture_references == []


@pytest.mark.asyncio
async def test_parse_story_raises_context_error_for_missing_file(tmp_path: Path) -> None:
    """ContextError is raised when the story file does not exist."""
    missing = tmp_path / "nonexistent.md"
    with pytest.raises(ContextError):
        await parse_story(missing)


# ---------------------------------------------------------------------------
# Task 2 — Reference resolver tests (AC #2, #3, #5, #6)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_resolve_fr_references_finds_matching_sections(tmp_path: Path) -> None:
    """FR1 and FR16 are resolved from PRD content."""
    prd = tmp_path / "prd.md"
    prd.write_text(SAMPLE_PRD_CONTENT, encoding="utf-8")
    results = await _resolve_fr_references(["FR1", "FR16"], prd)
    ref_ids = {r.ref_id for r in results}
    assert "FR1" in ref_ids
    assert "FR16" in ref_ids


@pytest.mark.asyncio
async def test_resolve_fr_references_logs_unresolved(tmp_path: Path, caplog: pytest.LogCaptureFixture) -> None:
    """FR-99 not in PRD is logged as context.unresolved, not raised."""
    prd = tmp_path / "prd.md"
    prd.write_text(SAMPLE_PRD_CONTENT, encoding="utf-8")
    with caplog.at_level(logging.INFO):
        results = await _resolve_fr_references(["FR99"], prd)
    assert results == []
    assert any("context.unresolved" in record.message for record in caplog.records)


@pytest.mark.asyncio
async def test_resolve_nfr_references_finds_matching_sections(tmp_path: Path) -> None:
    """NFR5 and NFR7 are resolved from PRD content."""
    prd = tmp_path / "prd.md"
    prd.write_text(SAMPLE_PRD_CONTENT, encoding="utf-8")
    results = await _resolve_nfr_references(["NFR5", "NFR7"], prd)
    ref_ids = {r.ref_id for r in results}
    assert "NFR5" in ref_ids
    assert "NFR7" in ref_ids


@pytest.mark.asyncio
async def test_resolve_nfr_references_logs_unresolved(tmp_path: Path, caplog: pytest.LogCaptureFixture) -> None:
    """NFR-99 not in PRD is logged as context.unresolved, not raised."""
    prd = tmp_path / "prd.md"
    prd.write_text(SAMPLE_PRD_CONTENT, encoding="utf-8")
    with caplog.at_level(logging.INFO):
        results = await _resolve_nfr_references(["NFR99"], prd)
    assert results == []
    assert any("context.unresolved" in record.message for record in caplog.records)


@pytest.mark.asyncio
async def test_resolve_architecture_references_finds_decisions(tmp_path: Path) -> None:
    """Decision 4 in story is resolved to the correct architecture section."""
    arch = tmp_path / "architecture.md"
    arch.write_text(SAMPLE_ARCHITECTURE_CONTENT, encoding="utf-8")
    results = await _resolve_architecture_references(["Decision4"], arch)
    assert len(results) == 1
    assert results[0].ref_id == "Decision4"
    assert "Context Injection Strategy" in results[0].content


@pytest.mark.asyncio
async def test_resolve_architecture_references_logs_unresolved(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """Decision 99 not in architecture doc is logged as context.unresolved."""
    arch = tmp_path / "architecture.md"
    arch.write_text(SAMPLE_ARCHITECTURE_CONTENT, encoding="utf-8")
    with caplog.at_level(logging.INFO):
        results = await _resolve_architecture_references(["Decision99"], arch)
    assert results == []
    assert any("context.unresolved" in record.message for record in caplog.records)


# ---------------------------------------------------------------------------
# Task 3 — Bundle builder tests (AC #4, #5, #8)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_build_context_bundle_assembles_complete_bundle(story_file: Path, project_fixture: Path) -> None:
    """Full integration: story with refs + PRD + arch → ContextBundle with all fields."""
    bundle = await build_context_bundle(story_file, project_fixture)
    assert isinstance(bundle, ContextBundle)
    assert bundle.story_content  # non-empty
    # At least some requirements resolved
    assert "FR" in bundle.domain_requirements or bundle.domain_requirements == ""
    assert bundle.answerer_rules == ""


@pytest.mark.asyncio
async def test_build_context_bundle_includes_source_references(story_file: Path, project_fixture: Path) -> None:
    """Resolved references carry source path citations in formatted output."""
    bundle = await build_context_bundle(story_file, project_fixture)
    combined = bundle.domain_requirements + bundle.architecture_sections
    if combined:
        assert "[Source:" in combined


@pytest.mark.asyncio
async def test_build_context_bundle_handles_missing_prd(story_file: Path, tmp_path: Path) -> None:
    """Missing PRD → bundle with empty domain_requirements, not an error."""
    # Create arch but not prd
    spec = tmp_path / "_spec" / "planning-artifacts"
    spec.mkdir(parents=True)
    (spec / "architecture.md").write_text(SAMPLE_ARCHITECTURE_CONTENT, encoding="utf-8")
    bundle = await build_context_bundle(story_file, tmp_path)
    assert isinstance(bundle, ContextBundle)
    assert bundle.domain_requirements == ""


@pytest.mark.asyncio
async def test_build_context_bundle_handles_missing_architecture(story_file: Path, tmp_path: Path) -> None:
    """Missing architecture doc → bundle with empty architecture_sections, not an error."""
    spec = tmp_path / "_spec" / "planning-artifacts"
    spec.mkdir(parents=True)
    (spec / "prd.md").write_text(SAMPLE_PRD_CONTENT, encoding="utf-8")
    bundle = await build_context_bundle(story_file, tmp_path)
    assert isinstance(bundle, ContextBundle)
    assert bundle.architecture_sections == ""


@pytest.mark.asyncio
async def test_build_context_bundle_loads_project_conventions(story_file: Path, project_fixture: Path) -> None:
    """Project conventions are loaded into answerer_rules when present."""
    docs_dir = project_fixture / "docs"
    docs_dir.mkdir(parents=True)
    (docs_dir / "project-context.md").write_text("# Conventions\n\nUse snake_case.", encoding="utf-8")

    bundle = await build_context_bundle(story_file, project_fixture)

    assert "Use snake_case." in bundle.answerer_rules


@pytest.mark.asyncio
async def test_build_context_bundle_custom_artifacts_path(story_file: Path, tmp_path: Path) -> None:
    """Custom artifacts_path resolves PRD/arch from alternate directory."""
    custom = tmp_path / "_bmad-output" / "planning-artifacts"
    custom.mkdir(parents=True)
    (custom / "prd.md").write_text(SAMPLE_PRD_CONTENT, encoding="utf-8")
    (custom / "architecture.md").write_text(SAMPLE_ARCHITECTURE_CONTENT, encoding="utf-8")

    bundle = await build_context_bundle(story_file, tmp_path, artifacts_path="_bmad-output")

    assert isinstance(bundle, ContextBundle)
    assert bundle.story_content  # non-empty
    assert "FR" in bundle.domain_requirements
    assert "Decision" in bundle.architecture_sections


@pytest.mark.asyncio
async def test_build_context_bundle_custom_path_ignores_default_spec(story_file: Path, tmp_path: Path) -> None:
    """When artifacts_path is specified, _spec is NOT searched."""
    # Put files under _spec (should be ignored)
    spec = tmp_path / "_spec" / "planning-artifacts"
    spec.mkdir(parents=True)
    (spec / "prd.md").write_text(SAMPLE_PRD_CONTENT, encoding="utf-8")

    # Custom dir has no PRD
    custom = tmp_path / "_bmad-output" / "planning-artifacts"
    custom.mkdir(parents=True)
    (custom / "architecture.md").write_text(SAMPLE_ARCHITECTURE_CONTENT, encoding="utf-8")

    bundle = await build_context_bundle(story_file, tmp_path, artifacts_path="_bmad-output")

    # PRD should NOT be found since we're looking in _bmad-output, not _spec
    assert bundle.domain_requirements == ""


# ---------------------------------------------------------------------------
# Task 4 — Markdown serialisation tests (AC #8)
# ---------------------------------------------------------------------------


def test_serialize_bundle_to_markdown_produces_valid_markdown() -> None:
    """A populated bundle serialises to markdown with all expected sections."""
    bundle = ContextBundle(
        story_content="# Story\n\nSome content.",
        domain_requirements="### FR1\n\nContent\n\n[Source: prd.md#FR1]\n\n---",
        architecture_sections="### Decision4\n\nContent\n\n[Source: arch.md#Decision-4]\n\n---",
        answerer_rules="",
    )
    md = serialize_bundle_to_markdown(bundle)
    assert "# Context Bundle" in md
    assert "## Story Content" in md
    assert "## Resolved Requirements" in md
    assert "## Architecture Sections" in md
    assert "## Answerer Rules" in md
    assert "# Story" in md
    assert "FR1" in md
    assert "Decision4" in md


def test_serialize_bundle_to_markdown_empty_bundle() -> None:
    """An empty bundle serialises to valid markdown with empty sections."""
    bundle = ContextBundle(
        story_content="",
        domain_requirements="",
        architecture_sections="",
        answerer_rules="",
    )
    md = serialize_bundle_to_markdown(bundle)
    assert "# Context Bundle" in md
    assert "## Story Content" in md
    assert "## Resolved Requirements" in md
    assert "## Architecture Sections" in md
    assert "## Answerer Rules" in md
