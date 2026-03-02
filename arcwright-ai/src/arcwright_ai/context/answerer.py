"""Context answerer — Static rule lookup engine for agent context questions.

Indexes BMAD project documents by heading and enables pure regex-based lookup
of rules, naming conventions, coding standards, and artifact formats.

Design constraints (D4):
- Pure regex matching only — no fuzzy search, no LLM fallback.
- Unmatched queries return ``None`` and emit a structured log event.
- Missing documents are skipped with a ``context.unresolved`` event; never raise.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from typing import TYPE_CHECKING

from arcwright_ai.core.constants import DIR_SPEC
from arcwright_ai.core.exceptions import ContextError
from arcwright_ai.core.io import read_text_async

if TYPE_CHECKING:
    from pathlib import Path

__all__: list[str] = [
    "IndexedSection",
    "RuleIndex",
]

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Compiled regex patterns (module-level for reuse, per D4)
# ---------------------------------------------------------------------------

#: Matches markdown headings: captures hashes and heading text.
_HEADING_PATTERN: re.Pattern[str] = re.compile(r"^(#{1,6})\s+(.+)$", re.MULTILINE)

#: Horizontal rule variants used as section separators — strip from content.
_HORIZONTAL_RULE_PATTERN: re.Pattern[str] = re.compile(r"^(?:-{3,}|\*{3,}|_{3,})\s*$", re.MULTILINE)


# ---------------------------------------------------------------------------
# Data classes  (frozen, not Pydantic — no overhead needed for internal data)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class IndexedSection:
    """A single indexed section from a BMAD document.

    Attributes:
        heading: The section heading text (e.g. ``'Python Code Style Patterns'``).
        content: Full text content under this heading.
        source_path: Path of the source document as a string.
        depth: Heading nesting level (``#`` = 1, ``##`` = 2, ``###`` = 3, etc.).
    """

    heading: str
    content: str
    source_path: str
    depth: int


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


async def _index_document(doc_path: Path) -> list[IndexedSection]:
    """Parse a markdown document into a flat list of ``IndexedSection`` objects.

    Sections are delimited by markdown headings (``#`` through ``######``).
    Content for a heading extends to the next heading at the same or shallower
    depth, or to the end of the file.  Horizontal rules are stripped from
    section boundaries.

    Args:
        doc_path: Absolute path to the markdown document.

    Returns:
        List of ``IndexedSection`` instances, one per heading.
    """
    try:
        text = await read_text_async(doc_path)
    except OSError as error:
        context_error = ContextError(
            "failed to read context document",
            details={"path": str(doc_path), "cause": str(error)},
        )
        logger.info(
            "context.unresolved",
            extra={
                "data": {
                    "path": str(doc_path),
                    "reason": "file_read_error",
                    "error": context_error.message,
                }
            },
        )
        return []

    matches = list(_HEADING_PATTERN.finditer(text))
    if not matches:
        return []

    sections: list[IndexedSection] = []

    for idx, match in enumerate(matches):
        hashes = match.group(1)
        depth = len(hashes)
        heading = match.group(2).strip()

        # Content starts after the heading line (after the newline)
        content_start = match.end()

        # Content ends at the start of the next heading of same or shallower
        # depth, or at end of file
        content_end = len(text)
        for future_match in matches[idx + 1 :]:
            future_depth = len(future_match.group(1))
            if future_depth <= depth:
                content_end = future_match.start()
                break

        raw_content = text[content_start:content_end]

        # Strip leading/trailing whitespace and horizontal rules
        cleaned = _HORIZONTAL_RULE_PATTERN.sub("", raw_content).strip()

        sections.append(
            IndexedSection(
                heading=heading,
                content=cleaned,
                source_path=str(doc_path),
                depth=depth,
            )
        )

    return sections


def _score_match(section: IndexedSection, pattern: re.Pattern[str]) -> tuple[int, int, int, int]:
    """Score a section match for specificity ranking.

    Higher values in each position indicate a better/more-specific match.

    Args:
        section: The candidate ``IndexedSection``.
        pattern: Compiled query pattern.

    Returns:
        Tuple of ``(heading_match, depth, -heading_length, -content_length)``
        for sort comparison.
        Higher values indicate a more specific match.
    """
    heading_match = 1 if pattern.search(section.heading) else 0
    return (heading_match, section.depth, -len(section.heading), -len(section.content))


# ---------------------------------------------------------------------------
# Public class
# ---------------------------------------------------------------------------


class RuleIndex:
    """Static rule lookup index built from BMAD project documents.

    Indexes all markdown sections by heading, enabling regex-based lookup
    of project rules, conventions, and standards.  No fuzzy matching — pure
    regex per D4.

    Typical usage::

        index = await RuleIndex.build_index(project_root)
        answer = index.lookup_answer(r"naming\\s+convention")

    Attributes:
        _sections: Flat list of every ``IndexedSection`` loaded from documents.
    """

    def __init__(self, sections: list[IndexedSection]) -> None:
        """Initialise the index from a pre-built section list.

        Args:
            sections: All indexed sections, typically produced by
                :meth:`build_index`.
        """
        self._sections: list[IndexedSection] = sections
        self._patterns: dict[str, re.Pattern[str]] = {
            "artifact_format": re.compile(
                r"artifact\s+format|markdown\s+format|yaml\s+format|BMAD.*format",
                re.IGNORECASE | re.DOTALL,
            ),
            "coding_standards": re.compile(
                r"coding\s+standard|code\s+style|import\s+order|docstring|type\s+hint",
                re.IGNORECASE | re.DOTALL,
            ),
            "file_structure": re.compile(
                r"project\s+structure|file\s+structure|package.*structure|directory.*layout",
                re.IGNORECASE | re.DOTALL,
            ),
            "naming_conventions": re.compile(
                r"naming\s+convention|snake.?case|PascalCase|UPPER.?SNAKE",
                re.IGNORECASE | re.DOTALL,
            ),
        }

    # ------------------------------------------------------------------
    # Construction
    # ------------------------------------------------------------------

    @classmethod
    async def build_index(
        cls,
        project_root: Path,
        *,
        doc_paths: list[Path] | None = None,
    ) -> RuleIndex:
        """Build a ``RuleIndex`` from BMAD project documents.

        When *doc_paths* is not supplied, the method discovers documents from
        the conventional locations:

        * ``{project_root}/_spec/planning-artifacts/architecture.md``
        * ``{project_root}/_spec/planning-artifacts/prd.md``
        * All ``*.md`` files directly under ``{project_root}/docs/`` (if the
          directory exists).

        Missing documents are silently skipped — a ``context.unresolved`` log
        event is emitted and indexing continues.

        Args:
            project_root: Root directory of the Arcwright AI project.
            doc_paths: Explicit list of document paths to index.  When
                provided, auto-discovery is skipped entirely.

        Returns:
            A populated :class:`RuleIndex`.
        """
        import asyncio

        if doc_paths is None:
            spec_dir = project_root / DIR_SPEC / "planning-artifacts"
            docs_dir = project_root / "docs"

            candidates: list[Path] = [
                spec_dir / "architecture.md",
                spec_dir / "prd.md",
            ]
            if docs_dir.is_dir():
                candidates.extend(docs_dir.glob("*.md"))

            doc_paths = candidates

        # Filter out missing paths, logging each skip
        available: list[Path] = []
        for path in doc_paths:
            if path.exists():
                available.append(path)
            else:
                logger.info(
                    "context.unresolved",
                    extra={"data": {"path": str(path), "reason": "file_not_found"}},
                )

        # Parse all available documents concurrently
        if available:
            results = await asyncio.gather(
                *(_index_document(p) for p in available),
                return_exceptions=False,
            )
            all_sections: list[IndexedSection] = [section for doc_sections in results for section in doc_sections]
        else:
            all_sections = []

        logger.info(
            "context.answerer.index",
            extra={
                "data": {
                    "docs_loaded": len(available),
                    "sections_indexed": len(all_sections),
                }
            },
        )

        return cls(all_sections)

    # ------------------------------------------------------------------
    # Lookup
    # ------------------------------------------------------------------

    def _lookup_with_compiled_pattern(self, compiled: re.Pattern[str], *, logged_pattern: str) -> str | None:
        """Search the index using a precompiled regex pattern.

        Args:
            compiled: Precompiled regex used for matching.
            logged_pattern: Pattern string for structured log events.

        Returns:
            Formatted answer string with source reference, or ``None``.
        """
        matches: list[IndexedSection] = [
            section
            for section in self._sections
            if compiled.search(section.heading) or compiled.search(section.content)
        ]

        if not matches:
            logger.info(
                "context.answerer.no_match",
                extra={"data": {"pattern": logged_pattern}},
            )
            return None

        best = max(matches, key=lambda section: _score_match(section, compiled))

        anchor = best.heading.replace(" ", "-")
        source_ref = f"[Source: {best.source_path}#{anchor}]"

        return f"**{best.heading}**\n\n{best.content}\n\n{source_ref}"

    def lookup_answer(self, question_pattern: str) -> str | None:
        """Search the index for sections matching *question_pattern*.

        Pattern matching is case-insensitive regex only (D4).  When multiple
        sections match, the most specific result is returned using the
        following priority:

        1. Heading match > content-only match.
        2. Deeper nesting (higher ``depth``) > shallower.
        3. Shorter heading > longer heading.
        4. Shorter content > longer content (more focused answer).

        On no match a :data:`context.answerer.no_match` event is logged and
        ``None`` is returned.  On invalid regex the pattern is compiled via
        :func:`re.escape` as a fallback.

        Args:
            question_pattern: Regex string to search headings and content.

        Returns:
            Formatted answer string including a ``[Source: …]`` reference, or
            ``None`` if no matching section is found.
        """
        try:
            compiled = re.compile(question_pattern, re.IGNORECASE | re.DOTALL)
        except re.error:
            logger.warning(
                "context.answerer.invalid_pattern",
                extra={"data": {"pattern": question_pattern, "reason": "invalid_regex"}},
            )
            compiled = re.compile(re.escape(question_pattern), re.IGNORECASE | re.DOTALL)

        return self._lookup_with_compiled_pattern(compiled, logged_pattern=question_pattern)

    # ------------------------------------------------------------------
    # Convenience helpers  (AC #4)
    # ------------------------------------------------------------------

    def lookup_naming_conventions(self) -> str | None:
        """Return sections describing naming conventions.

        Returns:
            Answer string with ``[Source: …]`` reference, or ``None``.
        """
        pattern = self._patterns["naming_conventions"]
        return self._lookup_with_compiled_pattern(pattern, logged_pattern=pattern.pattern)

    def lookup_file_structure(self) -> str | None:
        """Return sections describing project or file structure.

        Returns:
            Answer string with ``[Source: …]`` reference, or ``None``.
        """
        pattern = self._patterns["file_structure"]
        return self._lookup_with_compiled_pattern(pattern, logged_pattern=pattern.pattern)

    def lookup_coding_standards(self) -> str | None:
        """Return sections describing coding standards or style.

        Returns:
            Answer string with ``[Source: …]`` reference, or ``None``.
        """
        pattern = self._patterns["coding_standards"]
        return self._lookup_with_compiled_pattern(pattern, logged_pattern=pattern.pattern)

    def lookup_artifact_format(self) -> str | None:
        """Return sections describing artifact format rules.

        Returns:
            Answer string with ``[Source: …]`` reference, or ``None``.
        """
        pattern = self._patterns["artifact_format"]
        return self._lookup_with_compiled_pattern(pattern, logged_pattern=pattern.pattern)
