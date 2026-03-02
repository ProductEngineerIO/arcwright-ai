"""Context injector — BMAD artifact reader and reference resolver."""

from __future__ import annotations

import asyncio
import logging
import re
from dataclasses import dataclass
from typing import TYPE_CHECKING

from arcwright_ai.core.constants import DIR_SPEC
from arcwright_ai.core.exceptions import ContextError
from arcwright_ai.core.io import read_text_async
from arcwright_ai.core.types import ContextBundle

if TYPE_CHECKING:
    from pathlib import Path

__all__: list[str] = [
    "ParsedStory",
    "ResolvedReference",
    "build_context_bundle",
    "parse_story",
    "serialize_bundle_to_markdown",
]

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Compiled regex patterns (D4: strict regex only, no fuzzy matching)
# ---------------------------------------------------------------------------

_FR_PATTERN = re.compile(r"\bFR[-\u2010]?\d+\b", re.IGNORECASE)
_NFR_PATTERN = re.compile(r"\bNFR[-\u2010]?\d+\b", re.IGNORECASE)
_ARCH_PATTERN = re.compile(r"\b(?:Decision|D)\s*\d+\b", re.IGNORECASE)

# ---------------------------------------------------------------------------
# Data classes (internal — not Pydantic, no Pydantic overhead needed)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ParsedStory:
    """Parsed representation of a BMAD story markdown file.

    Attributes:
        raw_content: Full content of the story file.
        acceptance_criteria: Extracted acceptance criteria section text.
        fr_references: Deduplicated list of FR reference IDs found in the story.
        nfr_references: Deduplicated list of NFR reference IDs found in the story.
        architecture_references: Deduplicated list of architecture/Decision references.
    """

    raw_content: str
    acceptance_criteria: str
    fr_references: list[str]
    nfr_references: list[str]
    architecture_references: list[str]


@dataclass(frozen=True)
class ResolvedReference:
    """A successfully resolved reference to a BMAD artifact section.

    Attributes:
        ref_id: The reference identifier (e.g. ``FR-1``, ``Decision 4``).
        source_path: Path of the document from which this was resolved.
        section_anchor: Anchor/heading identifier within the document.
        content: Extracted section text containing the reference definition.
    """

    ref_id: str
    source_path: str
    section_anchor: str
    content: str


# ---------------------------------------------------------------------------
# Normalisation helpers
# ---------------------------------------------------------------------------


def _normalise_fr(ref: str) -> str:
    """Normalise an FR reference to ``FR<digits>`` form (strip dash, uppercase)."""
    return re.sub(r"[-\u2010]", "", ref.upper())


def _normalise_nfr(ref: str) -> str:
    """Normalise an NFR reference to ``NFR<digits>`` form (strip dash, uppercase)."""
    return re.sub(r"[-\u2010]", "", ref.upper())


def _normalise_arch(ref: str) -> str:
    """Normalise an architecture reference to ``Decision<digits>`` form."""
    # e.g. "D4", "D 4", "Decision 4" → all normalise to "Decision4" for matching
    m = re.search(r"\d+", ref)
    return f"Decision{m.group()}" if m else ref


# ---------------------------------------------------------------------------
# Step 1: Story parser
# ---------------------------------------------------------------------------


async def parse_story(story_path: Path) -> ParsedStory:
    """Read and parse a BMAD story markdown file.

    Extracts the acceptance criteria section and all FR, NFR, and architecture
    references found in the story text.  References are deduplicated and
    normalised.  Uses strict regex pattern matching only (D4).

    Args:
        story_path: Path to the BMAD story markdown file.

    Returns:
        Parsed story with extracted sections and reference lists.

    Raises:
        ContextError: If the story file is missing or cannot be read.
    """
    try:
        raw_content = await read_text_async(story_path)
    except OSError as exc:
        raise ContextError(
            f"Cannot read story file: {story_path}",
            details={"path": str(story_path), "error": str(exc)},
        ) from exc

    # Extract acceptance criteria section (text between ## Acceptance Criteria and next ##)
    ac_match = re.search(
        r"##\s+Acceptance Criteria.*?\n(.*?)(?=\n##\s|\Z)",
        raw_content,
        re.DOTALL | re.IGNORECASE,
    )
    acceptance_criteria = ac_match.group(1).strip() if ac_match else ""

    # Extract and deduplicate references
    fr_refs = list({_normalise_fr(r) for r in _FR_PATTERN.findall(raw_content)})
    nfr_refs = list({_normalise_nfr(r) for r in _NFR_PATTERN.findall(raw_content)})
    arch_refs = list({_normalise_arch(r) for r in _ARCH_PATTERN.findall(raw_content)})

    fr_refs.sort()
    nfr_refs.sort()
    arch_refs.sort()

    return ParsedStory(
        raw_content=raw_content,
        acceptance_criteria=acceptance_criteria,
        fr_references=fr_refs,
        nfr_references=nfr_refs,
        architecture_references=arch_refs,
    )


# ---------------------------------------------------------------------------
# Step 2: Reference resolvers
# ---------------------------------------------------------------------------


async def _resolve_fr_references(
    fr_refs: list[str],
    prd_path: Path,
) -> list[ResolvedReference]:
    """Resolve FR reference IDs to their definitions in the PRD document.

    Searches the PRD by line, finding lines that contain the FR identifier.
    Unresolved references are logged as ``context.unresolved`` events, not errors.

    Args:
        fr_refs: List of normalised FR reference IDs (e.g. ``["FR1", "FR16"]``).
        prd_path: Path to the PRD markdown document.

    Returns:
        List of resolved references with source provenance.
    """
    try:
        prd_content = await read_text_async(prd_path)
    except OSError:
        logger.info(
            "context.unresolved",
            extra={"data": {"ref": "prd-doc", "source": str(prd_path)}},
        )
        return []

    lines = prd_content.splitlines()
    resolved: list[ResolvedReference] = []

    for ref_id in fr_refs:
        # Match e.g. "FR1" or "FR-1" or "FR 1"
        digits = re.search(r"\d+", ref_id)
        if not digits:
            continue
        num = digits.group()
        pattern = re.compile(rf"\bFR[-\s]?{num}\b", re.IGNORECASE)

        matching_lines: list[str] = []
        for i, line in enumerate(lines):
            if pattern.search(line):
                # Grab the line + a small surrounding window for context
                start = max(0, i - 1)
                end = min(len(lines), i + 3)
                matching_lines.extend(lines[start:end])
                break  # first match is sufficient

        if matching_lines:
            content = "\n".join(dict.fromkeys(matching_lines))  # preserve order, deduplicate
            resolved.append(
                ResolvedReference(
                    ref_id=ref_id,
                    source_path=str(prd_path),
                    section_anchor=ref_id,
                    content=content,
                )
            )
        else:
            logger.info(
                "context.unresolved",
                extra={"data": {"ref": ref_id, "source": str(prd_path)}},
            )

    return resolved


async def _resolve_nfr_references(
    nfr_refs: list[str],
    prd_path: Path,
) -> list[ResolvedReference]:
    """Resolve NFR reference IDs to their definitions in the PRD document.

    Same resolution strategy as FR references — NFRs are also defined in the PRD.
    Unresolved references are logged as ``context.unresolved`` events.

    Args:
        nfr_refs: List of normalised NFR reference IDs (e.g. ``["NFR5", "NFR7"]``).
        prd_path: Path to the PRD markdown document.

    Returns:
        List of resolved references with source provenance.
    """
    try:
        prd_content = await read_text_async(prd_path)
    except OSError:
        logger.info(
            "context.unresolved",
            extra={"data": {"ref": "prd-doc", "source": str(prd_path)}},
        )
        return []

    lines = prd_content.splitlines()
    resolved: list[ResolvedReference] = []

    for ref_id in nfr_refs:
        digits = re.search(r"\d+", ref_id)
        if not digits:
            continue
        num = digits.group()
        pattern = re.compile(rf"\bNFR[-\s]?{num}\b", re.IGNORECASE)

        matching_lines: list[str] = []
        for i, line in enumerate(lines):
            if pattern.search(line):
                start = max(0, i - 1)
                end = min(len(lines), i + 3)
                matching_lines.extend(lines[start:end])
                break

        if matching_lines:
            content = "\n".join(dict.fromkeys(matching_lines))
            resolved.append(
                ResolvedReference(
                    ref_id=ref_id,
                    source_path=str(prd_path),
                    section_anchor=ref_id,
                    content=content,
                )
            )
        else:
            logger.info(
                "context.unresolved",
                extra={"data": {"ref": ref_id, "source": str(prd_path)}},
            )

    return resolved


async def _resolve_architecture_references(
    arch_refs: list[str],
    architecture_path: Path,
) -> list[ResolvedReference]:
    """Resolve architecture Decision references to sections in the architecture document.

    Splits the document by ``### `` headings and matches Decision/D references to
    heading text.  Section content spans from the heading to the next section
    separator (``---``) or the next ``### `` heading.
    Unresolved references are logged as ``context.unresolved`` events.

    Args:
        arch_refs: List of normalised architecture reference strings
            (e.g. ``["Decision4", "Decision1"]``).
        architecture_path: Path to the architecture markdown document.

    Returns:
        List of resolved references with source provenance.
    """
    try:
        arch_content = await read_text_async(architecture_path)
    except OSError:
        logger.info(
            "context.unresolved",
            extra={"data": {"ref": "arch-doc", "source": str(architecture_path)}},
        )
        return []

    # Split into sections by ### headings
    section_pattern = re.compile(r"(?m)^###\s+(.+)$")
    section_positions = [(m.start(), m.group(1)) for m in section_pattern.finditer(arch_content)]

    resolved: list[ResolvedReference] = []

    for ref_id in arch_refs:
        digits = re.search(r"\d+", ref_id)
        if not digits:
            continue
        num = digits.group()
        # Match heading containing "Decision N" or "D N"
        heading_pattern = re.compile(rf"\b(?:Decision|D)\s*{num}\b", re.IGNORECASE)

        matched_section: str | None = None
        matched_anchor: str | None = None

        for idx, (pos, heading) in enumerate(section_positions):
            if heading_pattern.search(heading):
                # Extract text from this heading to the next section or end of file
                section_start = pos
                section_end = section_positions[idx + 1][0] if idx + 1 < len(section_positions) else len(arch_content)
                section_text = arch_content[section_start:section_end].strip()
                # Trim at --- separator if present
                hr_match = re.search(r"\n---\n", section_text)
                if hr_match:
                    section_text = section_text[: hr_match.start()].strip()
                matched_section = section_text
                matched_anchor = re.sub(r"\s+", "-", heading.strip())
                break

        if matched_section is not None and matched_anchor is not None:
            resolved.append(
                ResolvedReference(
                    ref_id=ref_id,
                    source_path=str(architecture_path),
                    section_anchor=matched_anchor,
                    content=matched_section,
                )
            )
        else:
            logger.info(
                "context.unresolved",
                extra={"data": {"ref": ref_id, "source": str(architecture_path)}},
            )

    return resolved


# ---------------------------------------------------------------------------
# Step 3: Bundle builder
# ---------------------------------------------------------------------------


def _format_resolved_references(refs: list[ResolvedReference]) -> str:
    """Format a list of resolved references as a markdown string with source citations.

    Each reference is rendered as a markdown section with the reference ID as
    heading, the content, and a ``[Source: ...]`` citation.

    Args:
        refs: Resolved references to format.

    Returns:
        Formatted markdown string, or empty string if ``refs`` is empty.
    """
    if not refs:
        return ""
    parts: list[str] = []
    for ref in refs:
        parts.append(f"### {ref.ref_id}\n\n{ref.content}\n\n[Source: {ref.source_path}#{ref.section_anchor}]\n\n---")
    return "\n\n".join(parts)


async def build_context_bundle(
    story_path: Path,
    project_root: Path,
    *,
    prd_path: Path | None = None,
    architecture_path: Path | None = None,
) -> ContextBundle:
    """Resolve FR/NFR/architecture references from a story file into a context bundle.

    Parses the story, resolves all references in parallel using ``asyncio.gather``,
    assembles and returns a frozen ``ContextBundle``.  Missing PRD / architecture
    documents are treated as ``context.unresolved`` log events — not errors.
    Only a missing or unreadable *story* file raises ``ContextError``.

    Args:
        story_path: Path to the BMAD story markdown file.
        project_root: Root directory of the project.
        prd_path: Optional explicit path to PRD document.  If ``None``, derived
            from ``project_root / _spec / planning-artifacts / prd.md``.
        architecture_path: Optional explicit path to architecture document.  If
            ``None``, derived from ``project_root / _spec / planning-artifacts /
            architecture.md``.

    Returns:
        Assembled context bundle with resolved references.

    Raises:
        ContextError: If story file is missing or unreadable.
    """
    spec_dir = project_root / DIR_SPEC / "planning-artifacts"

    effective_prd = prd_path if prd_path is not None else spec_dir / "prd.md"
    effective_arch = architecture_path if architecture_path is not None else spec_dir / "architecture.md"

    parsed = await parse_story(story_path)

    fr_results, nfr_results, arch_results = await asyncio.gather(
        _resolve_fr_references(parsed.fr_references, effective_prd),
        _resolve_nfr_references(parsed.nfr_references, effective_prd),
        _resolve_architecture_references(parsed.architecture_references, effective_arch),
    )

    total_found = len(fr_results) + len(nfr_results) + len(arch_results)
    total_possible = len(parsed.fr_references) + len(parsed.nfr_references) + len(parsed.architecture_references)
    total_unresolved = total_possible - total_found

    logger.info(
        "context.resolve",
        extra={
            "data": {
                "story": str(story_path),
                "refs_found": total_found,
                "refs_unresolved": total_unresolved,
            }
        },
    )

    return ContextBundle(
        story_content=parsed.raw_content,
        architecture_sections=_format_resolved_references(arch_results),
        domain_requirements=_format_resolved_references(fr_results + nfr_results),
        answerer_rules="",
    )


# ---------------------------------------------------------------------------
# Step 4: Markdown serialisation
# ---------------------------------------------------------------------------


def serialize_bundle_to_markdown(bundle: ContextBundle) -> str:
    """Serialise a ``ContextBundle`` to a markdown checkpoint document.

    Produces a structured markdown document suitable for writing to disk as a
    context checkpoint.  All sections are included even when empty.

    Args:
        bundle: Assembled context bundle to serialise.

    Returns:
        Markdown-formatted string representation of the bundle.
    """
    return (
        "# Context Bundle\n\n"
        "## Story Content\n\n"
        f"{bundle.story_content}\n\n"
        "## Resolved Requirements\n\n"
        f"{bundle.domain_requirements}\n\n"
        "## Architecture Sections\n\n"
        f"{bundle.architecture_sections}\n\n"
        "## Answerer Rules\n\n"
        f"{bundle.answerer_rules}\n"
    )
