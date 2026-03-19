"""Output decisions — LLM-based extraction of agent implementation decisions."""

from __future__ import annotations

import asyncio
import logging
import re
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from arcwright_ai.core.io import read_text_async
from arcwright_ai.output.provenance import append_entry_to_section

if TYPE_CHECKING:
    from pathlib import Path

    from arcwright_ai.agent.invoker import InvocationResult
    from arcwright_ai.core.types import ProvenanceEntry

__all__: list[str] = ["build_extraction_prompt", "extract_agent_decisions", "parse_extraction_response"]

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Extraction prompt
# ---------------------------------------------------------------------------

_EXTRACTION_PROMPT_TEMPLATE = (
    "## Implementation Decision Extraction Task\n\n"
    "You are analysing a code diff and agent implementation output to extract "
    "the key **implementation decisions** made by the agent.\n\n"
    "An implementation decision is a concrete choice the agent made during "
    "coding, such as:\n"
    "- Choosing a design pattern (Strategy, Factory, etc.)\n"
    "- Selecting a data structure or algorithm\n"
    "- Deciding to split or merge modules/classes\n"
    "- Adding or skipping an abstraction layer\n"
    "- Picking one API/library over another\n\n"
    "Do NOT include pipeline execution metadata (e.g. 'agent invoked', "
    "'validation passed'). Focus only on code-level design decisions.\n\n"
    "### Format Requirements\n\n"
    "For each decision, respond with EXACTLY this format:\n\n"
    "DECISION: {{short title describing the choice, max 80 chars}}\n"
    "ALTERNATIVES: {{comma-separated list of alternatives considered, or 'None'}}\n"
    "RATIONALE: {{one to three sentences explaining why this choice was made}}\n"
    "REFERENCES: {{comma-separated AC/architecture IDs like AC-1, FR-9, or 'None'}}\n\n"
    "Extract between 1 and 5 decisions. If there are fewer than 1 meaningful "
    "decision, output exactly:\n\n"
    "DECISION: No significant implementation decisions detected\n"
    "ALTERNATIVES: None\n"
    "RATIONALE: The changes did not involve explicit design trade-offs.\n"
    "REFERENCES: None\n\n"
    "Do NOT use any tools. Do NOT write any files. Output ONLY the decision "
    "blocks in the specified format, with no preamble or postamble.\n\n"
    "### Git Diff\n\n"
    "```diff\n"
    "{diff}\n"
    "```\n\n"
    "### Agent Implementation Output\n\n"
    "{agent_output}\n"
)

# Patterns to parse the extraction response
_DECISION_SPLIT: re.Pattern[str] = re.compile(r"(?=^DECISION:)", re.MULTILINE)
_FIELD: re.Pattern[str] = re.compile(
    r"^(DECISION|ALTERNATIVES|RATIONALE|REFERENCES):\s*(.+?)(?=\n(?:DECISION|ALTERNATIVES|RATIONALE|REFERENCES):|\Z)",
    re.MULTILINE | re.DOTALL,
)
_ATTEMPT_OUTPUT_FILENAME_RE: re.Pattern[str] = re.compile(r"agent-output\.attempt-(\d+)\.md$")


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def build_extraction_prompt(diff_text: str, agent_output: str) -> str:
    """Build the review-model extraction prompt.

    Args:
        diff_text: Git diff output (``git diff <base>..HEAD``).
        agent_output: Contents of ``agent-output.md`` from the run checkpoint.

    Returns:
        Fully-assembled prompt string ready to pass to ``invoke_agent()``.
    """
    return _EXTRACTION_PROMPT_TEMPLATE.format(
        diff=diff_text[:50_000],  # cap to avoid excessive token usage
        agent_output=agent_output[:20_000],
    )


def parse_extraction_response(raw_response: str, *, timestamp: str | None = None) -> list[ProvenanceEntry]:
    """Parse the review model's extraction output into ``ProvenanceEntry`` objects.

    Args:
        raw_response: Full text output from the extraction invocation.
        timestamp: ISO 8601 timestamp to stamp each entry. Defaults to now (UTC).

    Returns:
        List of ``ProvenanceEntry`` objects. Returns an empty list when the
        response cannot be parsed.
    """
    from arcwright_ai.core.types import ProvenanceEntry

    ts = timestamp or datetime.now(tz=UTC).isoformat()

    blocks = _DECISION_SPLIT.split(raw_response.strip())
    entries: list[ProvenanceEntry] = []

    for block in blocks:
        block = block.strip()
        if not block:
            continue

        fields: dict[str, str] = {}
        for m in _FIELD.finditer(block):
            fields[m.group(1)] = m.group(2).strip()

        decision = fields.get("DECISION", "").strip()
        if not decision:
            continue

        alternatives_raw = fields.get("ALTERNATIVES", "None")
        if alternatives_raw.lower() == "none":
            alternatives: list[str] = []
        else:
            alternatives = [a.strip() for a in alternatives_raw.split(",") if a.strip()]

        rationale = fields.get("RATIONALE", "").strip() or "No rationale provided."

        references_raw = fields.get("REFERENCES", "None")
        if references_raw.lower() == "none":
            ac_references: list[str] = []
        else:
            ac_references = [r.strip() for r in references_raw.split(",") if r.strip()]

        entries.append(
            ProvenanceEntry(
                decision=decision,
                alternatives=alternatives,
                rationale=rationale,
                ac_references=ac_references,
                timestamp=ts,
            )
        )

    return entries


async def _load_agent_output_text(checkpoint_dir: Path) -> str:
    """Load and concatenate agent outputs across retries for extraction input.

    Includes attempt-specific checkpoint files when present, falling back to
    ``agent-output.md`` for backward compatibility.
    """
    from arcwright_ai.core.constants import AGENT_OUTPUT_FILENAME

    canonical_path = checkpoint_dir / AGENT_OUTPUT_FILENAME
    attempt_paths = await asyncio.to_thread(lambda: list(checkpoint_dir.glob("agent-output.attempt-*.md")))

    def _attempt_sort_key(path: Path) -> tuple[int, str]:
        m = _ATTEMPT_OUTPUT_FILENAME_RE.search(path.name)
        if m is None:
            return (0, path.name)
        return (int(m.group(1)), path.name)

    sorted_attempt_paths = sorted(attempt_paths, key=_attempt_sort_key)
    chunks: list[str] = []

    for attempt_path in sorted_attempt_paths:
        try:
            attempt_text = (await read_text_async(attempt_path)).strip()
        except FileNotFoundError:
            continue
        if not attempt_text:
            continue
        m = _ATTEMPT_OUTPUT_FILENAME_RE.search(attempt_path.name)
        attempt_no = m.group(1) if m is not None else "?"
        chunks.append(f"## Attempt {attempt_no}\n\n{attempt_text}")

    try:
        canonical_text = (await read_text_async(canonical_path)).strip()
    except FileNotFoundError:
        canonical_text = ""

    if canonical_text and (not chunks or canonical_text not in chunks[-1]):
        # Avoid duplicating content when the canonical file mirrors the final attempt.
        chunks.append(f"## Final Agent Output\n\n{canonical_text}")

    return "\n\n".join(chunks)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


async def extract_agent_decisions(
    worktree_path: Path,
    checkpoint_dir: Path,
    base_ref: str,
    provenance_path: Path,
    *,
    model: str,
    api_key: str,
    story_slug: str,
    project_root: Path,
) -> InvocationResult | None:
    """Extract implementation decisions from git diff and agent output.

    Reads the git diff between the worktree HEAD and *base_ref*, loads
    ``agent-output.md`` from *checkpoint_dir*, prompts the review model for
    structured implementation decisions, parses the response, and appends
    each decision to the ``## Implementation Decisions`` section of the
    provenance file.

    This function is **best-effort**: all internal errors are caught, logged
    as warnings, and ``None`` is returned so the calling ``commit_node`` can
    continue regardless.

    Args:
        worktree_path: Absolute path to the story git worktree.
        checkpoint_dir: Run checkpoint directory containing ``agent-output.md``.
        base_ref: Git ref (SHA or branch) to diff against.
        provenance_path: Path to the provenance ``validation.md`` file.
        model: Claude model identifier for the review role.
        api_key: Anthropic API key (secret value already extracted).
        story_slug: Story slug for log context.
        project_root: Project root path (used as sandbox cwd for extraction).

    Returns:
        ``InvocationResult`` on success (caller may use for budget tracking),
        or ``None`` if extraction failed.
    """
    from arcwright_ai.agent.invoker import invoke_agent
    from arcwright_ai.agent.sandbox import validate_path
    from arcwright_ai.scm.git import git

    # Read git diff
    try:
        diff_result = await git("diff", f"{base_ref}..HEAD", cwd=worktree_path)
        diff_text = diff_result.stdout.strip()
    except Exception as exc:
        logger.warning(
            "decisions.git_diff_error",
            extra={"data": {"story": story_slug, "error": str(exc)}},
        )
        diff_text = ""

    # Read agent output (all attempts when available)
    try:
        agent_output = await _load_agent_output_text(checkpoint_dir)
    except Exception as exc:
        logger.warning(
            "decisions.agent_output_read_error",
            extra={"data": {"story": story_slug, "error": str(exc)}},
        )
        agent_output = ""

    if not diff_text and not agent_output:
        logger.warning(
            "decisions.no_input",
            extra={"data": {"story": story_slug}},
        )
        return None

    prompt = build_extraction_prompt(diff_text, agent_output)

    try:
        result = await invoke_agent(
            prompt,
            model=model,
            cwd=project_root,
            sandbox=validate_path,
            api_key=api_key,
            max_turns=1,
        )
    except Exception as exc:
        logger.warning(
            "decisions.extraction_error",
            extra={"data": {"story": story_slug, "error": str(exc)}},
        )
        return None

    ts = datetime.now(tz=UTC).isoformat()
    entries = parse_extraction_response(result.output_text, timestamp=ts)
    if not entries:
        logger.warning(
            "decisions.extraction_unparseable",
            extra={"data": {"story": story_slug}},
        )
        return None

    for entry in entries:
        try:
            await append_entry_to_section(provenance_path, entry, section="implementation")
        except Exception as exc:
            logger.warning(
                "decisions.provenance_write_error",
                extra={"data": {"story": story_slug, "error": str(exc)}},
            )

    logger.info(
        "decisions.extracted",
        extra={"data": {"story": story_slug, "count": len(entries)}},
    )
    return result
