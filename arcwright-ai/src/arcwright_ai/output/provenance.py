"""Output provenance — Decision logging during agent execution."""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

from arcwright_ai.core.io import read_text_async, write_text_async

if TYPE_CHECKING:
    from pathlib import Path

    from arcwright_ai.core.types import ProvenanceEntry

__all__: list[str] = [
    "append_entry",
    "append_entry_to_section",
    "merge_validation_checkpoint",
    "render_validation_row",
    "write_entries",
]

# ---------------------------------------------------------------------------
# Private rendering helpers
# ---------------------------------------------------------------------------

_VALIDATION_SECTION_HEADER = "## Validation History"
_CONTEXT_SECTION_HEADER = "## Context Provided"
_AGENT_DECISIONS_HEADER = "## Agent Decisions"
_IMPLEMENTATION_DECISIONS_HEADER = "## Implementation Decisions"


def _extract_story_slug(path: Path) -> str:
    """Return the parent directory name of *path*, used as the story slug.

    For example, for ``.arcwright-ai/runs/run-001/stories/2-1-foo/validation.md``
    this returns ``"2-1-foo"``.

    Args:
        path: Fully-resolved path to the provenance file.

    Returns:
        The immediate parent directory name of the file.
    """
    return path.parent.name


def _render_decision_section(entry: ProvenanceEntry) -> str:
    """Render a single agent decision as a markdown subsection.

    Applies collapsible ``<details>`` wrapping when:

    * ``rationale`` exceeds 500 characters.
    * ``alternatives`` contains more than 5 items.

    Args:
        entry: The provenance entry to render.

    Returns:
        Markdown string for the decision subsection, ending with a trailing
        newline so adjacent sections are separated by a blank line.
    """
    lines: list[str] = [f"### Decision: {entry.decision}", ""]

    # Timestamp
    lines.append(f"- **Timestamp**: {entry.timestamp}")

    # Alternatives
    if not entry.alternatives:
        lines.append("- **Alternatives**: None considered")
    elif len(entry.alternatives) > 5:
        alts_inner = ", ".join(entry.alternatives)
        lines.append(
            "- **Alternatives**: <details><summary>Alternatives (click to expand)</summary>"
            f"\n\n{alts_inner}\n\n</details>"
        )
    else:
        lines.append(f"- **Alternatives**: {', '.join(entry.alternatives)}")

    # Rationale
    if len(entry.rationale) > 500:
        lines.append(
            "- **Rationale**: <details><summary>Rationale (click to expand)</summary>"
            f"\n\n{entry.rationale}\n\n</details>"
        )
    else:
        lines.append(f"- **Rationale**: {entry.rationale}")

    # References
    refs = ", ".join(entry.ac_references) if entry.ac_references else "None"
    lines.append(f"- **References**: {refs}")

    lines.append("")
    return "\n".join(lines)


def render_validation_row(attempt: int, result: str, feedback: str) -> str:
    """Render a single row for the Validation History markdown table.

    Intended for use by Story 4.4 when wiring validation results into
    provenance files.

    Args:
        attempt: The validation attempt number (1-based).
        result: The validation outcome string (e.g. ``"pass"`` or ``"fail"``).
        feedback: Human-readable feedback summary for this attempt.

    Returns:
        A markdown table row string: ``| attempt | result | feedback |``.
    """
    return f"| {attempt} | {result} | {feedback} |"


def _render_validation_history(rows: list[str] | None = None) -> str:
    """Render the Validation History markdown section.

    Args:
        rows: Optional list of pre-formatted table row strings produced by
            :func:`render_validation_row`.  When ``None`` or empty, a single
            placeholder row is emitted.

    Returns:
        Markdown string for the full ``## Validation History`` section.
    """
    header = f"{_VALIDATION_SECTION_HEADER}\n\n| Attempt | Result | Feedback |\n|---------|--------|----------|"
    if not rows:
        return header + "\n| — | — | — |"
    return header + "\n" + "\n".join(rows)


def _render_context_provided(entries: list[ProvenanceEntry]) -> str:
    """Render the Context Provided section from a list of provenance entries.

    Collects all ``ac_references`` across every entry, deduplicates them, and
    sorts alphabetically.

    Args:
        entries: All provenance entries whose references should be included.

    Returns:
        Markdown string for the full ``## Context Provided`` section.
    """
    all_refs: set[str] = set()
    for entry in entries:
        all_refs.update(entry.ac_references)

    if not all_refs:
        return f"{_CONTEXT_SECTION_HEADER}\n\n- No context references recorded"

    sorted_refs = sorted(all_refs)
    bullets = "\n".join(f"- {ref}" for ref in sorted_refs)
    return f"{_CONTEXT_SECTION_HEADER}\n\n{bullets}"


def _parse_refs_from_decisions(content: str, before_marker: str) -> set[str]:
    """Extract all ``ac_references`` values from rendered decision sections.

    Scans lines of *content* up to *before_marker* looking for lines that
    start with ``- **References**:`` and parses the comma-separated values.

    Args:
        content: Markdown content to scan.
        before_marker: Stop scanning at this substring if found.

    Returns:
        Set of reference strings gathered from all decision sections.
    """
    cutoff = content.find(before_marker)
    scan_area = content[:cutoff] if cutoff != -1 else content
    refs: set[str] = set()
    for line in scan_area.splitlines():
        stripped = line.strip()
        if stripped.startswith("- **References**:"):
            refs_part = stripped[len("- **References**:") :].strip()
            if refs_part and refs_part != "None":
                for part in refs_part.split(","):
                    ref = part.strip()
                    if ref:
                        refs.add(ref)
    return refs


# ---------------------------------------------------------------------------
# Public async API
# ---------------------------------------------------------------------------


async def write_entries(path: Path, entries: list[ProvenanceEntry]) -> None:
    """Write a complete provenance markdown file from scratch.

    Creates parent directories as needed.  The file is structured as three
    top-level sections: ``## Agent Decisions``, ``## Validation History``, and
    ``## Context Provided``.

    Args:
        path: Destination path for the provenance file.  The path contract
            is ``.arcwright-ai/runs/<run-id>/stories/<story-slug>/validation.md``.
            This function does **not** construct the path — callers are
            responsible for passing the fully resolved ``Path``.
        entries: Ordered list of provenance entries to render.
    """
    story_slug = _extract_story_slug(path)
    decisions_body = "\n".join(_render_decision_section(e) for e in entries)

    content = (
        f"# Provenance: {story_slug}\n\n"
        f"{_AGENT_DECISIONS_HEADER}\n\n"
        f"{decisions_body}\n"
        f"{_IMPLEMENTATION_DECISIONS_HEADER}\n\n"
        f"{_render_validation_history()}\n\n"
        f"{_render_context_provided(entries)}\n"
    )

    await asyncio.to_thread(path.parent.mkdir, parents=True, exist_ok=True)
    await write_text_async(path, content)


async def append_entry(path: Path, entry: ProvenanceEntry) -> None:
    """Append a single provenance entry to an existing file.

    If *path* does not exist, delegates to :func:`write_entries` to create a
    fresh provenance file.  Otherwise reads the existing content, inserts the
    new decision subsection immediately before ``## Validation History``, and
    updates the ``## Context Provided`` section with any new references.

    Args:
        path: Path to the target provenance file.
        entry: The new provenance entry to append.
    """
    exists = await asyncio.to_thread(path.exists)
    if not exists:
        await write_entries(path, [entry])
        return

    content = await read_text_async(path)

    # Insert new decision before ## Validation History
    new_decision = _render_decision_section(entry)
    val_idx = content.find(_VALIDATION_SECTION_HEADER)
    if val_idx == -1:
        content = content + "\n" + new_decision
    else:
        content = content[:val_idx] + new_decision + "\n" + content[val_idx:]

    # Rebuild ## Context Provided from all reference lines in updated content
    ctx_idx = content.find(_CONTEXT_SECTION_HEADER)
    existing_refs = _parse_refs_from_decisions(content, _CONTEXT_SECTION_HEADER)

    if ctx_idx != -1:
        if not existing_refs:
            new_ctx = f"{_CONTEXT_SECTION_HEADER}\n\n- No context references recorded\n"
        else:
            sorted_refs = sorted(existing_refs)
            bullets = "\n".join(f"- {ref}" for ref in sorted_refs)
            new_ctx = f"{_CONTEXT_SECTION_HEADER}\n\n{bullets}\n"
        content = content[:ctx_idx] + new_ctx

    await write_text_async(path, content)


async def append_entry_to_section(path: Path, entry: ProvenanceEntry, *, section: str = "agent") -> None:
    """Append a single provenance entry to either the agent or implementation section.

    When *section* is ``"implementation"``, the entry is inserted into the
    ``## Implementation Decisions`` block.  When *section* is ``"agent"``
    (the default), behaviour is identical to :func:`append_entry`.

    If the target section header is absent from the file, it is injected
    immediately before ``## Validation History`` so subsequent calls work
    correctly.  If the file does not exist, a fresh provenance file is
    created first via :func:`write_entries`.

    Args:
        path: Path to the target provenance file.
        entry: The new provenance entry to append.
        section: ``"agent"`` (default) or ``"implementation"``.
    """
    if section == "agent":
        await append_entry(path, entry)
        return

    # --- implementation section ---
    exists = await asyncio.to_thread(path.exists)
    if not exists:
        # Bootstrap file, then insert into implementation section recursively.
        await write_entries(path, [])
        await append_entry_to_section(path, entry, section="implementation")
        return

    content = await read_text_async(path)
    new_decision = _render_decision_section(entry)

    impl_idx = content.find(_IMPLEMENTATION_DECISIONS_HEADER)
    if impl_idx == -1:
        # Inject the Implementation Decisions section before Validation History.
        val_idx = content.find(_VALIDATION_SECTION_HEADER)
        impl_block = f"{_IMPLEMENTATION_DECISIONS_HEADER}\n\n{new_decision}\n"
        if val_idx == -1:
            content = content.rstrip("\n") + "\n\n" + impl_block
        else:
            content = content[:val_idx] + impl_block + "\n" + content[val_idx:]
    else:
        # Find the end of the Implementation Decisions section (next ## header or EOF).
        val_idx = content.find(_VALIDATION_SECTION_HEADER, impl_idx)
        end_of_impl = val_idx if val_idx != -1 else len(content)
        # Insert the new decision block before the next section.
        content = content[:end_of_impl].rstrip("\n") + "\n\n" + new_decision + "\n" + content[end_of_impl:]

    await write_text_async(path, content)


async def merge_validation_checkpoint(
    path: Path,
    attempt: int,
    outcome: str,
    feedback: str,
) -> None:
    """Merge a validation result row into the ``## Validation History`` section.

    Preserves every existing ``## Agent Decisions`` and
    ``## Implementation Decisions`` entry in the file.  If the file does not
    exist, a fresh provenance file is created in the 3-section format with the
    validation row as its first history entry.  If the file exists but has no
    ``## Validation History`` section, the section is injected before
    ``## Context Provided`` (or appended) so that subsequent
    :func:`append_entry` calls work correctly.

    This function replaces the previous unconditional overwrite with
    ``_serialize_validation_checkpoint()``, which destroyed ``## Agent
    Decisions`` entries written by ``agent_dispatch_node``.

    Args:
        path: Path to the target provenance file.
        attempt: 1-based validation attempt number.
        outcome: Pipeline outcome string (e.g. ``"pass"`` or ``"fail_v6"``).
        feedback: Human-readable feedback summary for this attempt.
    """
    new_row = render_validation_row(attempt, outcome, feedback)

    exists = await asyncio.to_thread(path.exists)
    if not exists:
        story_slug = _extract_story_slug(path)
        content = (
            f"# Provenance: {story_slug}\n\n"
            f"{_AGENT_DECISIONS_HEADER}\n\n"
            f"{_render_validation_history([new_row])}\n\n"
            f"{_CONTEXT_SECTION_HEADER}\n\n- No context references recorded\n"
        )
        await asyncio.to_thread(path.parent.mkdir, parents=True, exist_ok=True)
        await write_text_async(path, content)
        return

    content = await read_text_async(path)
    val_idx = content.find(_VALIDATION_SECTION_HEADER)

    if val_idx == -1:
        # Ensure legacy/corrupt files are normalized enough for PR extraction:
        # we must have an Agent Decisions header and a Context section marker.
        if _AGENT_DECISIONS_HEADER not in content:
            first_decision_idx = content.find("### Decision:")
            if first_decision_idx != -1:
                content = (
                    content[:first_decision_idx].rstrip("\n")
                    + "\n\n"
                    + _AGENT_DECISIONS_HEADER
                    + "\n\n"
                    + content[first_decision_idx:].lstrip("\n")
                )
            else:
                content = content.rstrip("\n") + "\n\n" + _AGENT_DECISIONS_HEADER + "\n"

        if _CONTEXT_SECTION_HEADER not in content:
            content = content.rstrip("\n") + "\n\n" + _CONTEXT_SECTION_HEADER + "\n\n- No context references recorded\n"

        # File exists but lacks the Validation History section (may be in wrong
        # format from a previous bug).  Inject the section before Context
        # Provided if present, otherwise append it.  This preserves any Agent
        # Decisions content already in the file.
        ctx_idx = content.find(_CONTEXT_SECTION_HEADER)
        if ctx_idx != -1:
            content = content[:ctx_idx] + _render_validation_history([new_row]) + "\n\n" + content[ctx_idx:]
        else:
            content = content.rstrip("\n") + "\n\n" + _render_validation_history([new_row]) + "\n"
        await write_text_async(path, content)
        return

    # File is in provenance format — append the new row to the table.
    ctx_idx = content.find(_CONTEXT_SECTION_HEADER, val_idx)
    end_idx = ctx_idx if ctx_idx != -1 else len(content)
    val_section = content[val_idx:end_idx]

    placeholder = "| — | — | — |"
    if placeholder in val_section:
        # Replace placeholder with first real row
        val_section = val_section.replace(placeholder, new_row, 1)
    else:
        # Append after the last table row
        val_section = val_section.rstrip("\n") + "\n" + new_row + "\n"

    content = content[:val_idx] + val_section + content[end_idx:]
    await write_text_async(path, content)
