"""Output summary — Run summary and halt report generation.

This module is the single writer for ``summary.md`` inside a run directory.
It exposes three async public functions — one per run outcome — and must
NEVER import from ``engine/``, ``agent/``, ``validation/``, ``context/``,
``scm/``, or ``cli/`` packages.  Its full dependency surface is:
``core/constants``, ``core/exceptions``, ``core/io``, ``output/run_manager``.
"""

from __future__ import annotations

import asyncio
import re
from typing import TYPE_CHECKING, Any

from arcwright_ai.core.constants import DIR_ARCWRIGHT, DIR_RUNS, SUMMARY_FILENAME
from arcwright_ai.core.io import write_text_async
from arcwright_ai.output.run_manager import RunStatusValue, get_run_status

if TYPE_CHECKING:
    from pathlib import Path

__all__: list[str] = [
    "write_halt_report",
    "write_success_summary",
    "write_timeout_summary",
]

# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------


def _extract_epic_from_slug(slug: str) -> str:
    """Parse the epic number from a story slug.

    Args:
        slug: Story slug in the format ``N-N-name`` (e.g. ``"4-3-run-summary"``).

    Returns:
        The epic number as a string (e.g. ``"4"``), or ``"<EPIC>"`` if the
        slug doesn't match the expected pattern.
    """
    match = re.match(r"^(\d+)-", slug)
    if match:
        return match.group(1)
    return "<EPIC>"


def _summary_path(project_root: Path, run_id: str) -> Path:
    """Return the path for ``summary.md`` inside a run directory.

    Args:
        project_root: Absolute path to the target project root.
        run_id: Run identifier string.

    Returns:
        Path to ``.arcwright-ai/runs/<run-id>/summary.md``.
    """
    return project_root / DIR_ARCWRIGHT / DIR_RUNS / run_id / SUMMARY_FILENAME


def _format_budget_field(value: Any) -> str:
    """Format a budget field for display, returning ``"N/A"`` for empty values.

    Args:
        value: Budget field value from ``run.yaml`` (may be int, str, or None).

    Returns:
        The string representation of *value*, or ``"N/A"`` when *value* is
        ``0``, ``"0"``, ``None``, or an empty string.
    """
    if value is None or value == 0 or value == "0" or value == "":
        return "N/A"
    return str(value)


def _truncate_output(text: str, max_chars: int = 2000) -> tuple[str, bool]:
    """Truncate text to its last *max_chars* characters.

    Args:
        text: The text to truncate.
        max_chars: Maximum number of characters to keep from the end.

    Returns:
        A 2-tuple ``(truncated_text, was_truncated)`` where *was_truncated*
        is ``True`` when the original text exceeded *max_chars*.
    """
    if len(text) <= max_chars:
        return text, False
    return text[-max_chars:], True


def _escape_markdown_table_cell(text: str) -> str:
    """Escape markdown table control characters in a table cell value.

    Args:
        text: Raw table-cell text.

    Returns:
        Escaped text safe for markdown table rendering.
    """
    normalized = text.replace("\r\n", "\n").replace("\r", "\n")
    escaped_pipes = normalized.replace("|", "\\|")
    return escaped_pipes.replace("\n", "<br>")


def _format_resume_epic_target(epic_num: str) -> str:
    """Format resume epic argument, preserving placeholder semantics.

    Args:
        epic_num: Parsed epic number or ``"<EPIC>"`` placeholder.

    Returns:
        ``"EPIC-<N>"`` for parsed numbers, otherwise ``"<EPIC>"``.
    """
    if epic_num == "<EPIC>":
        return "<EPIC>"
    return f"EPIC-{epic_num}"


# ---------------------------------------------------------------------------
# Public async write functions
# ---------------------------------------------------------------------------


async def write_success_summary(project_root: Path, run_id: str) -> Path:
    """Write a run success summary to ``summary.md``.

    Reads ``run.yaml`` via :func:`~arcwright_ai.output.run_manager.get_run_status`,
    builds a structured markdown document, and writes it to
    ``.arcwright-ai/runs/<run-id>/summary.md``.

    The function is idempotent — each call overwrites any previous
    ``summary.md`` at the target path.

    Args:
        project_root: Absolute path to the target project root.
        run_id: Run identifier string.

    Returns:
        Path to the written ``summary.md`` file.

    Raises:
        RunError: If the run ID cannot be found (no ``run.yaml``).
    """
    run_status = await get_run_status(project_root, run_id)

    lines: list[str] = []

    # Heading
    lines.append(f"# Run Summary: {run_id}")
    lines.append("")

    # Overview
    lines.append("## Overview")
    lines.append("")
    total_stories = len(run_status.stories)
    completed_count = sum(
        1
        for entry in run_status.stories.values()
        if entry.status in (RunStatusValue.COMPLETED, "success", "done", "completed")
    )
    lines.append(f"- **Run ID:** {run_status.run_id}")
    lines.append(f"- **Status:** {run_status.status}")
    lines.append(f"- **Start Time:** {run_status.start_time}")
    lines.append(f"- **Total Stories:** {total_stories}")
    lines.append(f"- **Completed Stories:** {completed_count}")
    lines.append("- **Duration:** N/A")
    lines.append("")

    # Stories Completed
    lines.append("## Stories Completed")
    lines.append("")
    for slug, entry in run_status.stories.items():
        is_done = entry.status in (RunStatusValue.COMPLETED, "success", "done", "completed")
        checkbox = "[x]" if is_done else "[ ]"
        line = f"- {checkbox} {slug} (status: {entry.status})"
        if entry.started_at:
            line += f", started: {entry.started_at}"
        if entry.completed_at:
            line += f", completed: {entry.completed_at}"
        lines.append(line)
    lines.append("")

    # Cost Summary
    budget = run_status.budget
    lines.append("## Cost Summary")
    lines.append("")
    lines.append(f"- **Invocations:** {_format_budget_field(budget.get('invocation_count', 0))}")
    lines.append(f"- **Total Tokens:** {_format_budget_field(budget.get('total_tokens', 0))}")
    lines.append(f"- **Estimated Cost:** {_format_budget_field(budget.get('estimated_cost', '0'))}")
    lines.append("")

    # Provenance References
    lines.append("## Provenance References")
    lines.append("")
    for slug in run_status.stories:
        lines.append(f"- .arcwright-ai/runs/{run_id}/stories/{slug}/")
    lines.append("")

    # Next Steps
    lines.append("## Next Steps")
    lines.append("")
    lines.append("All stories completed successfully. Review provenance artifacts for decision audit trail.")
    lines.append("")

    content = "\n".join(lines)
    path = _summary_path(project_root, run_id)
    await asyncio.to_thread(path.parent.mkdir, parents=True, exist_ok=True)
    await write_text_async(path, content)
    return path


async def write_halt_report(
    project_root: Path,
    run_id: str,
    *,
    halted_story: str,
    halt_reason: str,
    validation_history: list[dict[str, Any]],
    last_agent_output: str,
    suggested_fix: str,
) -> Path:
    """Write a structured halt report to ``summary.md``.

    Builds a diagnostic markdown document containing the 4 required NFR18
    fields (halted story, validation failures, retry history, suggested fix)
    plus run context and last agent output.

    The function is idempotent — each call overwrites any previous
    ``summary.md`` at the target path.

    Args:
        project_root: Absolute path to the target project root.
        run_id: Run identifier string.
        halted_story: Slug of the story that caused the halt.
        halt_reason: Human-readable description of why execution halted.
        validation_history: List of validation attempt dicts, each with keys
            ``attempt`` (int), ``outcome`` (str), and ``failures`` (str).
        last_agent_output: Raw output from the last agent invocation.
        suggested_fix: Human-readable suggestion for resolving the failure.

    Returns:
        Path to the written ``summary.md`` file.

    Raises:
        RunError: If the run ID cannot be found (no ``run.yaml``).
    """
    run_status = await get_run_status(project_root, run_id)
    epic_num = _extract_epic_from_slug(halted_story)
    resume_epic_target = _format_resume_epic_target(epic_num)

    lines: list[str] = []

    # Heading
    lines.append(f"# Run Summary: {run_id}")
    lines.append("")

    # Halted Story (NFR18 field 1)
    lines.append("## Halted Story")
    lines.append("")
    lines.append(f"- **Story Slug:** {halted_story}")
    lines.append(f"- **Epic ID:** {epic_num}")
    lines.append(f"- **Halt Reason:** {halt_reason}")
    lines.append(f"- **Run ID:** {run_id}")
    lines.append("")

    # Validation Failures (NFR18 field 2)
    lines.append("## Validation Failures")
    lines.append("")
    if validation_history:
        for attempt_dict in validation_history:
            attempt_num = attempt_dict.get("attempt", "?")
            outcome = attempt_dict.get("outcome", "unknown")
            failures = attempt_dict.get("failures", "")
            lines.append(f"### Attempt {attempt_num}")
            lines.append(f"- **Outcome:** {outcome}")
            if failures:
                lines.append(f"- **Failures:** {failures}")
            lines.append("")
    else:
        lines.append("No validation history recorded.")
        lines.append("")

    # Retry History table (NFR18 field 3)
    lines.append("## Retry History")
    lines.append("")
    lines.append("| Attempt | Outcome | Feedback |")
    lines.append("| --- | --- | --- |")
    if validation_history:
        for attempt_dict in validation_history:
            attempt_num = attempt_dict.get("attempt", "?")
            outcome = str(attempt_dict.get("outcome", "unknown"))
            feedback = attempt_dict.get("failures", "")
            if len(feedback) > 200:
                feedback = feedback[:200] + "..."
            safe_outcome = _escape_markdown_table_cell(outcome)
            safe_feedback = _escape_markdown_table_cell(feedback)
            lines.append(f"| {attempt_num} | {safe_outcome} | {safe_feedback} |")
    else:
        lines.append("| — | — | — |")
    lines.append("")

    # Last Agent Output
    lines.append("## Last Agent Output")
    lines.append("")
    truncated_text, was_truncated = _truncate_output(last_agent_output)
    total_length = len(last_agent_output)
    if was_truncated:
        if total_length > 2000:
            lines.append(f"*... truncated ({total_length} chars total) ...*")
            lines.append("")
            lines.append("<details>")
            lines.append("<summary>Last 2000 characters of agent output</summary>")
            lines.append("")
            lines.append("```")
            lines.append(truncated_text)
            lines.append("```")
            lines.append("")
            lines.append("</details>")
        else:
            lines.append("```")
            lines.append(truncated_text)
            lines.append("```")
    else:
        lines.append("```")
        lines.append(truncated_text)
        lines.append("```")
    lines.append("")

    # Suggested Fix (NFR18 field 4)
    lines.append("## Suggested Fix")
    lines.append("")
    lines.append(suggested_fix)
    lines.append("")
    lines.append("To resume from this story, run:")
    lines.append("")
    lines.append("```")
    lines.append(f"arcwright-ai dispatch --epic {resume_epic_target} --resume")
    lines.append("```")
    lines.append("")

    # Run Context
    lines.append("## Run Context")
    lines.append("")
    completed_stories = [
        slug
        for slug, entry in run_status.stories.items()
        if entry.status in (RunStatusValue.COMPLETED, "success", "done", "completed")
    ]
    remaining_stories = [
        slug
        for slug, entry in run_status.stories.items()
        if entry.status not in (RunStatusValue.COMPLETED, "success", "done", "completed", "halted")
    ]
    lines.append(f"- **Stories Completed:** {len(completed_stories)}")
    lines.append(f"- **Stories Remaining:** {len(remaining_stories)}")
    budget = run_status.budget
    lines.append(f"- **Invocations at Halt:** {_format_budget_field(budget.get('invocation_count', 0))}")
    lines.append(f"- **Tokens at Halt:** {_format_budget_field(budget.get('total_tokens', 0))}")
    lines.append(f"- **Cost at Halt:** {_format_budget_field(budget.get('estimated_cost', '0'))}")
    lines.append("")

    content = "\n".join(lines)
    path = _summary_path(project_root, run_id)
    await asyncio.to_thread(path.parent.mkdir, parents=True, exist_ok=True)
    await write_text_async(path, content)
    return path


async def write_timeout_summary(project_root: Path, run_id: str) -> Path:
    """Write a timeout summary to ``summary.md``.

    Reads ``run.yaml`` via :func:`~arcwright_ai.output.run_manager.get_run_status`,
    builds a structured markdown document for a timed-out run, and writes it
    to ``.arcwright-ai/runs/<run-id>/summary.md``.

    The function is idempotent — each call overwrites any previous
    ``summary.md`` at the target path.

    Args:
        project_root: Absolute path to the target project root.
        run_id: Run identifier string.

    Returns:
        Path to the written ``summary.md`` file.

    Raises:
        RunError: If the run ID cannot be found (no ``run.yaml``).
    """
    run_status = await get_run_status(project_root, run_id)

    completed_stories = {
        slug: entry
        for slug, entry in run_status.stories.items()
        if entry.status in (RunStatusValue.COMPLETED, "success", "done", "completed")
    }
    remaining_stories = {
        slug: entry
        for slug, entry in run_status.stories.items()
        if entry.status not in (RunStatusValue.COMPLETED, "success", "done", "completed")
    }

    # Derive resume epic from first remaining story
    resume_epic = "<EPIC>"
    if remaining_stories:
        first_remaining = next(iter(remaining_stories))
        resume_epic = _extract_epic_from_slug(first_remaining)
    resume_epic_target = _format_resume_epic_target(resume_epic)

    lines: list[str] = []

    # Heading
    lines.append(f"# Run Summary: {run_id}")
    lines.append("")

    # Overview
    lines.append("## Overview")
    lines.append("")
    lines.append(f"- **Run ID:** {run_status.run_id}")
    lines.append("- **Status:** timed_out")
    lines.append(f"- **Start Time:** {run_status.start_time}")
    lines.append(f"- **Stories Completed:** {len(completed_stories)}")
    lines.append(f"- **Stories Remaining:** {len(remaining_stories)}")
    lines.append("- **Duration:** N/A")
    lines.append("")

    # Stories Completed
    lines.append("## Stories Completed")
    lines.append("")
    if completed_stories:
        for slug, entry in completed_stories.items():
            line = f"- [x] {slug} (status: {entry.status})"
            if entry.started_at:
                line += f", started: {entry.started_at}"
            if entry.completed_at:
                line += f", completed: {entry.completed_at}"
            lines.append(line)
    else:
        lines.append("No stories completed before timeout.")
    lines.append("")

    # Stories Remaining
    lines.append("## Stories Remaining")
    lines.append("")
    if remaining_stories:
        for slug, entry in remaining_stories.items():
            lines.append(f"- [ ] {slug} (status: {entry.status})")
    else:
        lines.append("No stories remaining.")
    lines.append("")

    # Cost Summary
    budget = run_status.budget
    lines.append("## Cost Summary")
    lines.append("")
    lines.append(f"- **Invocations:** {_format_budget_field(budget.get('invocation_count', 0))}")
    lines.append(f"- **Total Tokens:** {_format_budget_field(budget.get('total_tokens', 0))}")
    lines.append(f"- **Estimated Cost:** {_format_budget_field(budget.get('estimated_cost', '0'))}")
    lines.append("")

    # Next Steps
    lines.append("## Next Steps")
    lines.append("")
    lines.append("The run timed out before all stories were completed. To resume, run:")
    lines.append("")
    lines.append("```")
    lines.append(f"arcwright-ai dispatch --epic {resume_epic_target} --resume")
    lines.append("```")
    lines.append("")

    content = "\n".join(lines)
    path = _summary_path(project_root, run_id)
    await asyncio.to_thread(path.parent.mkdir, parents=True, exist_ok=True)
    await write_text_async(path, content)
    return path
