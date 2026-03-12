"""Output summary — Run summary and halt report generation.

This module is the single writer for ``summary.md`` inside a run directory.
It exposes three async public functions — one per run outcome — and must
NEVER import from ``engine/``, ``agent/``, ``validation/``, ``context/``,
``scm/``, or ``cli/`` packages.  Its full dependency surface is:
``core/constants``, ``core/exceptions``, ``core/io``, ``output/run_manager``.
"""

from __future__ import annotations

import asyncio
import logging
import re
from decimal import ROUND_HALF_UP, Decimal
from typing import TYPE_CHECKING, Any

from arcwright_ai.core.constants import DIR_ARCWRIGHT, DIR_RUNS, SUMMARY_FILENAME
from arcwright_ai.core.io import write_text_async
from arcwright_ai.output.run_manager import RunStatusValue, get_run_status

if TYPE_CHECKING:
    from pathlib import Path

__all__: list[str] = [
    "format_budget_remaining",
    "format_cost",
    "format_retry_overhead",
    "format_tokens",
    "write_halt_report",
    "write_success_summary",
    "write_timeout_summary",
]

_log = logging.getLogger(__name__)

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


def format_cost(value: Decimal | str | int | float | None) -> str:
    """Format a monetary cost value as a human-readable dollar string.

    All rounding uses ``Decimal.quantize`` to ``0.01`` with ``ROUND_HALF_UP``
    to avoid float imprecision.  String inputs are parsed to ``Decimal``
    before formatting so both ``Decimal`` and ``str`` budget dict values
    (from ``_serialize_budget``) are handled correctly.

    Args:
        value: Cost amount as ``Decimal``, ``str``, ``int``, ``float``, or
            ``None``.  ``None`` and all zero variants return ``"$0.00"``.

    Returns:
        Human-readable dollar string such as ``"$1.17"`` or ``"$0.00"``.

    Examples:
        >>> format_cost(Decimal("1.17"))
        '$1.17'
        >>> format_cost("0.005")
        '$0.01'
        >>> format_cost(None)
        '$0.00'
    """
    if value is None:
        return "$0.00"
    d = Decimal(str(value))
    quantized = d.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    return f"${quantized:,.2f}"


def format_tokens(value: int | str | None) -> str:
    """Format a token count as a comma-separated integer string.

    String inputs are parsed to ``int`` before formatting so both integer
    and string budget dict values are handled correctly.

    Args:
        value: Token count as ``int``, ``str``, or ``None``.  ``None``
            returns ``"0"``.

    Returns:
        Comma-separated integer string such as ``"12,450"`` or ``"0"``.

    Examples:
        >>> format_tokens(12450)
        '12,450'
        >>> format_tokens(0)
        '0'
        >>> format_tokens(None)
        '0'
        >>> format_tokens(1000000)
        '1,000,000'
    """
    if value is None:
        return "0"
    return f"{int(value):,}"


def format_budget_remaining(
    current: Decimal | str,
    ceiling: Decimal | str,
    max_invocations: int | str | None = None,
) -> str:
    """Format remaining budget as a percentage and absolute amount string.

    When *ceiling* is zero the budget is unlimited.  When *max_invocations*
    is provided and equals zero, budget is also treated as unlimited per
    story display requirements. When budget is not unlimited and *ceiling* > 0,
    calculates remaining = ceiling - current and returns
    ``"X% ($Y.YY of $Z.ZZ)"``.

    Args:
        current: Amount of budget already spent, as ``Decimal`` or ``str``.
        ceiling: Maximum budget ceiling, as ``Decimal`` or ``str``.
            Pass ``"0"`` or ``Decimal("0")`` for unlimited budgets.
        max_invocations: Optional invocation ceiling. When provided as
            ``0``/``"0"``, returns ``"unlimited"``.

    Returns:
        ``"unlimited"`` when *ceiling* is zero; otherwise a percentage
        and absolute string such as ``"73% ($7.30 of $10.00)"``.

    Examples:
        >>> format_budget_remaining("2.70", "10.00")
        '73% ($7.30 of $10.00)'
        >>> format_budget_remaining("0", "0")
        'unlimited'
        >>> format_budget_remaining("2.70", "10.00", 0)
        'unlimited'
        >>> format_budget_remaining("10.00", "10.00")
        '0% ($0.00 of $10.00)'
    """
    c_ceil = Decimal(str(ceiling))
    if c_ceil == Decimal("0"):
        return "unlimited"
    if max_invocations is not None and int(max_invocations) == 0:
        return "unlimited"
    c_curr = Decimal(str(current))
    remaining = c_ceil - c_curr
    pct = (remaining / c_ceil * 100).quantize(Decimal("1"), rounding=ROUND_HALF_UP)
    return f"{int(pct)}% ({format_cost(remaining)} of {format_cost(c_ceil)})"


def format_retry_overhead(per_story: dict[str, Any]) -> str:
    """Format retry overhead cost as a dollar amount and percentage string.

    Computes the first-pass cost (one invocation per story at the
    per-invocation rate) versus total cost.  The difference is the
    retry overhead.

    Args:
        per_story: Per-story cost dict from the budget, keyed by story slug.
            Each value must have ``"cost"`` (str or Decimal),
            ``"invocations"`` (int), and is typically sourced from
            ``_serialize_budget``.

    Returns:
        ``"$0.00 (no retries)"`` when no stories have more than one
        invocation, otherwise ``"$X.XX (Y% overhead)"`` where X.XX is the
        retry overhead cost and Y is the overhead percentage relative to
        first-pass cost.

    Examples:
        >>> format_retry_overhead({})
        '$0.00 (no retries)'
        >>> format_retry_overhead({"s": {"cost": "1.50", "invocations": 3}})
        '$1.00 (200% overhead)'
    """
    if not per_story:
        return "$0.00 (no retries)"
    first_pass_total = Decimal("0")
    total_cost = Decimal("0")
    has_retries = False
    for entry in per_story.values():
        cost = Decimal(str(entry.get("cost", "0")))
        invocations = int(entry.get("invocations", 1))
        cost_per_invocation = cost / invocations if invocations > 0 else cost
        first_pass_total += cost_per_invocation
        total_cost += cost
        if invocations > 1:
            has_retries = True
    if not has_retries:
        return "$0.00 (no retries)"
    retry_cost = total_cost - first_pass_total
    if first_pass_total > 0:
        pct = (retry_cost / first_pass_total * 100).quantize(Decimal("1"), rounding=ROUND_HALF_UP)
        return f"{format_cost(retry_cost)} ({int(pct)}% overhead)"
    return f"{format_cost(retry_cost)} (overhead)"


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


def _truncate_output_by_lines(text: str, max_lines: int = 500) -> tuple[str, bool]:
    """Truncate text to its last *max_lines* lines.

    Args:
        text: The text to truncate.
        max_lines: Maximum number of lines to keep from the end.

    Returns:
        A 2-tuple ``(truncated_text, was_truncated)`` where *was_truncated*
        is ``True`` when the original text exceeded *max_lines*.
    """
    lines = text.splitlines(keepends=True)
    if len(lines) <= max_lines:
        return text, False
    return "".join(lines[-max_lines:]), True


def _extract_failing_ac_ids(validation_history: list[dict[str, Any]]) -> list[str]:
    """Extract unique failing AC IDs from validation history entries.

    Parses AC ID references from the ``failures`` field in each entry.
    Supports formats like ``"V3: ACs 1, 3"`` and ``"V3: ACs AC1, AC2"``.

    Args:
        validation_history: List of validation dicts with ``failures`` keys.

    Returns:
        Sorted list of unique AC ID strings (e.g., ``["1", "3"]``).
    """
    ac_ids: set[str] = set()
    for entry in validation_history:
        failures = str(entry.get("failures", ""))
        for segment in re.findall(r"ACs?\s+([^\n.;]+)", failures, flags=re.IGNORECASE):
            for ac_id in re.findall(r"(?:AC[-\s]*)?#?(\d+)", segment, flags=re.IGNORECASE):
                ac_ids.add(ac_id)
    return sorted(ac_ids, key=int)


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


def _build_per_story_cost_lines(per_story: dict[str, Any]) -> list[str]:
    """Build per-story cost table lines for a summary section.

    When any story has ``cost_by_role`` data, renders a table with separate
    Gen and Review cost columns.  Falls back to the simple 5-column table
    when no role data is present (backward compatibility).

    Args:
        per_story: The ``per_story`` dict from a serialized ``BudgetState``.

    Returns:
        List of markdown table lines (header + data rows), or an empty list
        when *per_story* is empty.
    """
    if not per_story:
        return []
    has_roles = any(bool(e.get("cost_by_role") or {}) for e in per_story.values())
    lines: list[str] = []
    if has_roles:
        lines.append("| Story | Tokens In | Tokens Out | Gen Cost | Rev Cost | Total | Inv |")
        lines.append("| --- | --- | --- | --- | --- | --- | --- |")
        for _slug, _entry in per_story.items():
            _cbr = _entry.get("cost_by_role") or {}
            _gen = format_cost(str(_cbr.get("generate", "0")))
            _rev = format_cost(str(_cbr.get("review", "0")))
            _tok_in = format_tokens(_entry.get("tokens_input", 0))
            _tok_out = format_tokens(_entry.get("tokens_output", 0))
            _cost = format_cost(_entry.get("cost", "0"))
            _inv = _entry.get("invocations", 1)
            lines.append(f"| {_slug} | {_tok_in} | {_tok_out} | {_gen} | {_rev} | {_cost} | {_inv} |")
    else:
        lines.append("| Story | Tokens In | Tokens Out | Cost | Invocations |")
        lines.append("| --- | --- | --- | --- | --- |")
        for _slug, _entry in per_story.items():
            _tok_in = format_tokens(_entry.get("tokens_input", 0))
            _tok_out = format_tokens(_entry.get("tokens_output", 0))
            _cost = format_cost(_entry.get("cost", "0"))
            _inv = _entry.get("invocations", 1)
            lines.append(f"| {_slug} | {_tok_in} | {_tok_out} | {_cost} | {_inv} |")
    return lines


def _build_cost_by_role_section(
    per_story: dict[str, Any],
    config_snapshot: dict[str, Any] | None = None,
) -> list[str]:
    """Build a "Cost by Model Role" markdown subsection.

    Aggregates ``cost_by_role`` across all per-story entries.  Returns an
    empty list when no role data is present (backward compatibility — old
    ``run.yaml`` files without ``cost_by_role``).

    Args:
        per_story: The ``per_story`` dict from a serialized ``BudgetState``.
        config_snapshot: Optional config snapshot dict with ``model_version``
            and ``review_model_version`` keys.

    Returns:
        List of markdown lines for the subsection, or an empty list when no
        role cost data is available.
    """
    role_costs: dict[str, dict[str, Any]] = {}
    for _slug, entry in per_story.items():
        cost_by_role = entry.get("cost_by_role") or {}
        invocations_by_role = entry.get("invocations_by_role") or {}
        tokens_input_by_role = entry.get("tokens_input_by_role") or {}
        tokens_output_by_role = entry.get("tokens_output_by_role") or {}
        for role, cost_val in cost_by_role.items():
            if role not in role_costs:
                role_costs[role] = {
                    "cost": Decimal("0"),
                    "invocations": 0,
                    "tokens_input": 0,
                    "tokens_output": 0,
                }
            role_costs[role]["cost"] += Decimal(str(cost_val))
            explicit_role_invocations = int(invocations_by_role.get(role, 0) or 0)
            role_costs[role]["invocations"] += explicit_role_invocations if explicit_role_invocations > 0 else 1
            role_costs[role]["tokens_input"] += int(tokens_input_by_role.get(role, 0) or 0)
            role_costs[role]["tokens_output"] += int(tokens_output_by_role.get(role, 0) or 0)
    # Filter to non-zero roles
    role_costs = {r: d for r, d in role_costs.items() if d["cost"] > Decimal("0")}
    if not role_costs:
        return []

    snapshot = config_snapshot or {}
    role_model_map = {
        "generate": snapshot.get("model_version", "—"),
        "review": snapshot.get("review_model_version", "—"),
    }
    role_label_map = {"generate": "Generation", "review": "Review"}

    lines: list[str] = []
    lines.append("")
    lines.append("### Cost by Model Role")
    lines.append("")
    lines.append("| Role | Model Version | Invocations | Tokens (In/Out) | Cost |")
    lines.append("| --- | --- | --- | --- | --- |")
    for role, data in role_costs.items():
        label = role_label_map.get(role, role.capitalize())
        model_ver = role_model_map.get(role, "—")
        tokens_in_out = f"{format_tokens(data['tokens_input'])} / {format_tokens(data['tokens_output'])}"
        lines.append(
            f"| {label} | {model_ver} | {data['invocations']} | {tokens_in_out} | {format_cost(str(data['cost']))} |"
        )
    return lines


# ---------------------------------------------------------------------------
# Public async write functions
# ---------------------------------------------------------------------------


async def write_success_summary(
    project_root: Path,
    run_id: str,
    *,
    previous_run_id: str | None = None,
) -> Path:
    """Write a run success summary to ``summary.md``.

    Reads ``run.yaml`` via :func:`~arcwright_ai.output.run_manager.get_run_status`,
    builds a structured markdown document, and writes it to
    ``.arcwright-ai/runs/<run-id>/summary.md``.

    The function is idempotent — each call overwrites any previous
    ``summary.md`` at the target path.

    When *previous_run_id* is provided the previous run's ``summary.md`` is
    read and prepended under a ``## Previous Run Report`` section before the
    new run's content.  If the previous summary cannot be read (missing or
    corrupted) a warning is logged and the new summary is written without it.

    Args:
        project_root: Absolute path to the target project root.
        run_id: Run identifier string.
        previous_run_id: Optional run ID of a prior halted run whose summary
            should be included for chronological continuity.

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
    lines.append(f"- **Total Cost:** {format_cost(budget.get('estimated_cost', '0'))}")
    _tokens_in = int(budget.get("total_tokens_input", 0) or 0)
    _tokens_out = int(budget.get("total_tokens_output", 0) or 0)
    _total_tok = int(budget.get("total_tokens", 0) or 0) or (_tokens_in + _tokens_out)
    lines.append(
        f"- **Total Tokens:** {format_tokens(_total_tok)}"
        f" (input: {format_tokens(_tokens_in)} / output: {format_tokens(_tokens_out)})"
    )
    lines.append(f"- **Total Invocations:** {budget.get('invocation_count', 0) or 0}")
    _max_cost_ss = budget.get("max_cost", "0")
    lines.append(
        f"- **Budget Utilization:** "
        f"{format_budget_remaining(budget.get('estimated_cost', '0'), _max_cost_ss, budget.get('max_invocations'))}"
    )
    _per_story_ss: dict[str, Any] = budget.get("per_story", {}) or {}
    _per_story_lines_ss = _build_per_story_cost_lines(_per_story_ss)
    if _per_story_lines_ss:
        lines.append("")
        lines.extend(_per_story_lines_ss)
    else:
        lines.append("- No per-story data yet")
    lines.extend(_build_cost_by_role_section(_per_story_ss, run_status.config_snapshot))
    lines.append(f"- **Retry Overhead:** {format_retry_overhead(_per_story_ss)}")
    lines.append("")

    # Provenance References
    lines.append("## Provenance References")
    lines.append("")
    for slug in run_status.stories:
        lines.append(f"- .arcwright-ai/runs/{run_id}/stories/{slug}/")
    lines.append("")

    # Pull Request section (AC: #9 — only present when a PR URL was recorded)
    pr_entries: list[tuple[str, str]] = [
        (slug, entry.pr_url) for slug, entry in run_status.stories.items() if entry.pr_url
    ]
    if pr_entries:
        lines.append("## Pull Request")
        lines.append("")
        for slug, url in pr_entries:
            lines.append(f"- **{slug}**: {url}")
        lines.append("")

    # Next Steps
    lines.append("## Next Steps")
    lines.append("")
    lines.append("All stories completed successfully. Review provenance artifacts for decision audit trail.")
    lines.append("")

    content = "\n".join(lines)

    # Prepend previous run report when previous_run_id is provided (AC#4).
    if previous_run_id is not None:
        prev_path = _summary_path(project_root, previous_run_id)
        try:
            prev_content = await asyncio.to_thread(prev_path.read_text, encoding="utf-8")
            prev_lines: list[str] = [
                "## Previous Run Report",
                "",
                f"*From halted run: {previous_run_id}*",
                "",
                prev_content,
                "",
                "---",
                "",
            ]
            content = "\n".join(prev_lines) + content
        except Exception:
            _log.warning(
                "summary.previous_run_read_error",
                extra={"data": {"previous_run_id": previous_run_id}},
            )

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
    failing_ac_ids: list[str] | None = None,
    worktree_path: str | None = None,
    previous_run_id: str | None = None,
) -> Path:
    """Write a structured halt report to ``summary.md``.

    Builds a diagnostic markdown document containing the 4 required NFR18
    fields (halted story with failing AC IDs, validation failures, retry
    history, suggested fix) plus run context and last agent output.

    The function is idempotent — each call overwrites any previous
    ``summary.md`` at the target path.

    When *previous_run_id* is provided the previous run's ``summary.md`` is
    read and prepended under a ``## Previous Run Report`` section.  If the
    previous summary cannot be read a warning is logged and the new report is
    written without it.

    Args:
        project_root: Absolute path to the target project root.
        run_id: Run identifier string.
        halted_story: Slug of the story that caused the halt.
        halt_reason: Human-readable description of why execution halted.
        validation_history: List of validation attempt dicts, each with keys
            ``attempt`` (int), ``outcome`` (str), and ``failures`` (str).
        last_agent_output: Raw output from the last agent invocation.
        suggested_fix: Human-readable suggestion for resolving the failure.
        failing_ac_ids: Optional explicit list of failing AC ID strings to
            display in the "Halted Story" section.  When ``None`` the IDs are
            extracted from *validation_history* automatically.  When an empty
            list is passed, ``"N/A"`` is displayed.
        worktree_path: Optional path to the isolated worktree for the failing
            story.  When ``None``, renders a placeholder noting that worktree
            isolation is pending Story 6.2.
        previous_run_id: Optional run ID of a prior halted run whose summary
            should be prepended for chronological continuity.

    Returns:
        Path to the written ``summary.md`` file.

    Raises:
        RunError: If the run ID cannot be found (no ``run.yaml``).
    """
    run_status = await get_run_status(project_root, run_id)
    epic_num = _extract_epic_from_slug(halted_story)
    resume_epic_target = _format_resume_epic_target(epic_num)

    # Resolve failing AC IDs: use explicit list, or extract from validation history.
    resolved_ac_ids = _extract_failing_ac_ids(validation_history) if failing_ac_ids is None else failing_ac_ids

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
    if resolved_ac_ids:
        ac_display = ", ".join(f"#{ac}" for ac in resolved_ac_ids)
        lines.append(f"- **Failing ACs:** {ac_display}")
    else:
        lines.append("- **Failing ACs:** N/A")
    if worktree_path is not None:
        lines.append(f"- **Preserved Worktree:** {worktree_path}")
    else:
        lines.append("- **Preserved Worktree:** N/A (worktree isolation pending Story 6.2)")
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

    # Last Agent Output  — line-based truncation (NFR18 field 3)
    lines.append("## Last Agent Output")
    lines.append("")
    truncated_text, was_truncated = _truncate_output_by_lines(last_agent_output)
    total_lines = last_agent_output.count("\n") + 1 if last_agent_output else 0
    if was_truncated:
        lines.append(f"*... truncated ({total_lines} lines total, showing last 500) ...*")
        lines.append("")
        lines.append("<details>")
        lines.append("<summary>Last 500 lines of agent output</summary>")
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
    lines.append("")

    # Cost Summary
    budget = run_status.budget
    lines.append("## Cost Summary")
    lines.append("")
    lines.append(f"- **Total Cost:** {format_cost(budget.get('estimated_cost', '0'))}")
    _tokens_in_hr = int(budget.get("total_tokens_input", 0) or 0)
    _tokens_out_hr = int(budget.get("total_tokens_output", 0) or 0)
    _total_tok_hr = int(budget.get("total_tokens", 0) or 0) or (_tokens_in_hr + _tokens_out_hr)
    lines.append(
        f"- **Total Tokens:** {format_tokens(_total_tok_hr)}"
        f" (input: {format_tokens(_tokens_in_hr)} / output: {format_tokens(_tokens_out_hr)})"
    )
    lines.append(f"- **Total Invocations:** {budget.get('invocation_count', 0) or 0}")
    _max_cost_hr = budget.get("max_cost", "0")
    lines.append(
        f"- **Budget Utilization:** "
        f"{format_budget_remaining(budget.get('estimated_cost', '0'), _max_cost_hr, budget.get('max_invocations'))}"
    )
    _per_story_hr: dict[str, Any] = budget.get("per_story", {}) or {}
    _per_story_lines_hr = _build_per_story_cost_lines(_per_story_hr)
    if _per_story_lines_hr:
        lines.append("")
        lines.extend(_per_story_lines_hr)
    else:
        lines.append("- No per-story data yet")
    lines.extend(_build_cost_by_role_section(_per_story_hr, run_status.config_snapshot))
    lines.append(f"- **Retry Overhead:** {format_retry_overhead(_per_story_hr)}")
    lines.append("")

    content = "\n".join(lines)

    # Prepend previous run report when previous_run_id is provided (AC#4).
    if previous_run_id is not None:
        prev_path = _summary_path(project_root, previous_run_id)
        try:
            prev_content = await asyncio.to_thread(prev_path.read_text, encoding="utf-8")
            prev_lines: list[str] = [
                "## Previous Run Report",
                "",
                f"*From halted run: {previous_run_id}*",
                "",
                prev_content,
                "",
                "---",
                "",
            ]
            content = "\n".join(prev_lines) + content
        except Exception:
            _log.warning(
                "summary.previous_run_read_error",
                extra={"data": {"previous_run_id": previous_run_id}},
            )

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
    lines.append(f"- **Total Cost:** {format_cost(budget.get('estimated_cost', '0'))}")
    _tokens_in_to = int(budget.get("total_tokens_input", 0) or 0)
    _tokens_out_to = int(budget.get("total_tokens_output", 0) or 0)
    _total_tok_to = int(budget.get("total_tokens", 0) or 0) or (_tokens_in_to + _tokens_out_to)
    lines.append(
        f"- **Total Tokens:** {format_tokens(_total_tok_to)}"
        f" (input: {format_tokens(_tokens_in_to)} / output: {format_tokens(_tokens_out_to)})"
    )
    lines.append(f"- **Total Invocations:** {budget.get('invocation_count', 0) or 0}")
    _max_cost_to = budget.get("max_cost", "0")
    lines.append(
        f"- **Budget Utilization:** "
        f"{format_budget_remaining(budget.get('estimated_cost', '0'), _max_cost_to, budget.get('max_invocations'))}"
    )
    _per_story_to: dict[str, Any] = budget.get("per_story", {}) or {}
    _per_story_lines_to = _build_per_story_cost_lines(_per_story_to)
    if _per_story_lines_to:
        lines.append("")
        lines.extend(_per_story_lines_to)
    else:
        lines.append("- No per-story data yet")
    lines.extend(_build_cost_by_role_section(_per_story_to, run_status.config_snapshot))
    lines.append(f"- **Retry Overhead:** {format_retry_overhead(_per_story_to)}")
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
