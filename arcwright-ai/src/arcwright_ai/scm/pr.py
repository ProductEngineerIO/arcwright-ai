"""SCM PR — Pull request body generation with provenance embedding."""

from __future__ import annotations

import asyncio
import json
import logging
import re
import shutil
from enum import StrEnum
from typing import TYPE_CHECKING, NamedTuple

from arcwright_ai.core.constants import (
    DIR_ARCWRIGHT,
    DIR_RUNS,
    DIR_STORIES,
    STORY_COPY_FILENAME,
    VALIDATION_FILENAME,
)
from arcwright_ai.core.exceptions import ScmError
from arcwright_ai.core.io import read_text_async
from arcwright_ai.scm.git import git

if TYPE_CHECKING:
    from pathlib import Path

__all__: list[str] = [
    "MergeOutcome",
    "generate_pr_body",
    "get_pull_request_merge_sha",
    "merge_pull_request",
    "open_pull_request",
]

logger = logging.getLogger(__name__)


class MergeOutcome(StrEnum):
    """Structured outcome of a pull-request merge attempt."""

    MERGED = "merged"
    SKIPPED = "skipped"
    CI_FAILED = "ci_failed"
    TIMEOUT = "timeout"
    ERROR = "error"


_GITHUB_REMOTE_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"^https://github\.com/(?P<owner>[^/]+)/(?P<repo>[^/]+?)(?:\.git)?$"),
    re.compile(r"^git@github\.com:(?P<owner>[^/]+)/(?P<repo>[^/]+?)(?:\.git)?$"),
    re.compile(r"^ssh://git@github\.com/(?P<owner>[^/]+)/(?P<repo>[^/]+?)(?:\.git)?$"),
)

# ---------------------------------------------------------------------------
# Collapse thresholds (AC: #3)
# ---------------------------------------------------------------------------

_RATIONALE_COLLAPSE_THRESHOLD: int = 500

# ---------------------------------------------------------------------------
# Merge strategy flag mapping (Story 9.3)
# ---------------------------------------------------------------------------

_MERGE_STRATEGY_FLAGS: dict[str, str] = {
    "squash": "--squash",
    "merge": "--merge",
    "rebase": "--rebase",
}
_ALTERNATIVES_COLLAPSE_THRESHOLD: int = 5
_LARGE_BLOCK_LINE_THRESHOLD: int = 50

# ---------------------------------------------------------------------------
# Internal data model
# ---------------------------------------------------------------------------


class _Decision(NamedTuple):
    """Parsed agent decision from a provenance file.

    Attributes:
        title: Decision description extracted from ``### Decision: <title>``.
        timestamp: ISO-format timestamp string.
        alternatives: List of alternative options considered.
        rationale: Rationale text (may contain pre-existing ``<details>`` HTML).
        references: List of AC/architecture reference IDs (e.g. ``"AC-2"``, ``"D7"``).
    """

    title: str
    timestamp: str
    alternatives: list[str]
    rationale: str
    references: list[str]


# ---------------------------------------------------------------------------
# Private file readers (Tasks 1 & 2)
# ---------------------------------------------------------------------------


async def _read_provenance(run_id: str, story_slug: str, *, project_root: Path) -> str:
    """Read the provenance file from the D3↔D5 contract path.

    Args:
        run_id: Run identifier.
        story_slug: Story slug matching the run directory entry.
        project_root: Absolute path to the repository root.

    Returns:
        Raw provenance file content as a string.

    Raises:
        ScmError: If the provenance file does not exist.
    """
    path = project_root / DIR_ARCWRIGHT / DIR_RUNS / run_id / DIR_STORIES / story_slug / VALIDATION_FILENAME
    try:
        return await read_text_async(path)
    except FileNotFoundError as exc:
        logger.error(
            "scm.pr.provenance_missing",
            extra={"data": {"run_id": run_id, "story_slug": story_slug, "path": str(path)}},
        )
        raise ScmError(
            f"Provenance file not found: {path}",
            details={"run_id": run_id, "story_slug": story_slug, "path": str(path)},
        ) from exc


async def _read_story_copy(run_id: str, story_slug: str, *, project_root: Path) -> str | None:
    """Read the story copy file, returning ``None`` on missing file.

    Args:
        run_id: Run identifier.
        story_slug: Story slug matching the run directory entry.
        project_root: Absolute path to the repository root.

    Returns:
        Story file content as a string, or ``None`` if the file is absent.
    """
    path = project_root / DIR_ARCWRIGHT / DIR_RUNS / run_id / DIR_STORIES / story_slug / STORY_COPY_FILENAME
    try:
        return await read_text_async(path)
    except FileNotFoundError:
        logger.warning(
            "scm.pr.story_copy_missing",
            extra={"data": {"run_id": run_id, "story_slug": story_slug, "path": str(path)}},
        )
        return None


# ---------------------------------------------------------------------------
# Private parsers (Tasks 2 & 3)
# ---------------------------------------------------------------------------


def _extract_acceptance_criteria(story_content: str) -> list[str]:
    """Parse numbered acceptance criteria from a BMAD story file.

    Matches numbered items and unnumbered BDD lines (``**Given** ...``)
    under ``## Acceptance Criteria`` (or ``## Acceptance Criteria (BDD)``).
    Stops at the next ``## `` heading.

    Args:
        story_content: Raw story file text.

    Returns:
        List of AC strings, each suitable for rendering as a checkbox item.
    """
    lines = story_content.splitlines()
    in_ac_section = False
    ac_items: list[str] = []
    for line in lines:
        if re.match(r"^## Acceptance Criteria", line):
            in_ac_section = True
            continue
        if in_ac_section and line.startswith("## "):
            break
        if in_ac_section:
            m = re.match(r"^\d+\.\s+(.*)", line)
            if m:
                ac_items.append(m.group(1).strip())
                continue

            stripped = line.strip()
            if re.match(r"^(?:-\s*)?\*\*Given\*\*\s+.+", stripped):
                ac_items.append(re.sub(r"^-\s*", "", stripped))
    return ac_items


def _extract_story_title(provenance_content: str, *, story_content: str | None = None) -> str:
    """Extract the story slug/title from the provenance file header.

    Args:
        provenance_content: Raw provenance markdown text.
        story_content: Optional story copy markdown text used as fallback.

    Returns:
        The story slug from ``# Provenance: <slug>``. If absent, falls back
        to ``# Story ...`` from story copy content when available; otherwise
        returns ``"Unknown Story"``.
    """
    m = re.search(r"^# Provenance:\s*(.+)$", provenance_content, re.MULTILINE)
    if m:
        return m.group(1).strip()

    if story_content is not None:
        story_match = re.search(r"^#\s*Story\s+(.+)$", story_content, re.MULTILINE)
        if story_match:
            return story_match.group(1).strip()

    return "Unknown Story"


def _extract_validation_table(provenance_content: str) -> str:
    """Extract the ``## Validation History`` table from the provenance file.

    Args:
        provenance_content: Raw provenance markdown text.

    Returns:
        The validation table markdown string (excluding the section header),
        or an empty string if the section is absent.
    """
    marker = "## Validation History"
    next_section = "## Context Provided"
    start = provenance_content.find(marker)
    if start == -1:
        return ""
    end = provenance_content.find(next_section, start)
    section = provenance_content[start:end].strip() if end != -1 else provenance_content[start:].strip()
    # Remove the section header line
    lines = section.splitlines()
    table_lines: list[str] = []
    past_header = False
    for line in lines:
        if not past_header:
            if line.strip() == marker.strip():
                past_header = True
            continue
        table_lines.append(line)
    return "\n".join(table_lines).strip()


def _parse_field(content: str, field_name: str) -> str:
    """Extract the value of a bullet field from a decision section.

    Handles single-line and multi-line (``<details>`` block) values.

    Args:
        content: Markdown content of one decision subsection.
        field_name: Field label to search for (e.g. ``"Timestamp"``).

    Returns:
        Trimmed field value string, or ``""`` if the field is absent.
    """
    pattern = re.compile(
        rf"^- \*\*{re.escape(field_name)}\*\*:\s*(.*?)(?=\n- \*\*|\Z)",
        re.MULTILINE | re.DOTALL,
    )
    m = pattern.search(content)
    if m:
        return m.group(1).strip()
    return ""


def _extract_decisions(provenance_content: str) -> list[_Decision]:
    """Parse all ``### Decision: <title>`` subsections from the ``## Agent Decisions`` section.

    Handles both plain text and pre-existing ``<details>`` block values
    produced by ``output/provenance.py``.

    Args:
        provenance_content: Raw provenance markdown text.

    Returns:
        Ordered list of :class:`_Decision` named tuples from the
        ``## Agent Decisions`` section only.
    """
    return _parse_decisions_from_section(
        provenance_content,
        section_header="## Agent Decisions",
        end_headers=("## Implementation Decisions", "## Validation History"),
    )


def _extract_implementation_decisions(provenance_content: str) -> list[_Decision]:
    """Parse ``### Decision: <title>`` subsections from ``## Implementation Decisions``.

    Args:
        provenance_content: Raw provenance markdown text.

    Returns:
        Ordered list of :class:`_Decision` named tuples from the
        ``## Implementation Decisions`` section.  Empty list when the
        section is absent.
    """
    return _parse_decisions_from_section(
        provenance_content,
        section_header="## Implementation Decisions",
        end_headers=("## Validation History", "## Context Provided"),
    )


def _parse_decisions_from_section(
    provenance_content: str,
    section_header: str,
    end_headers: tuple[str, ...],
) -> list[_Decision]:
    """Parse ``### Decision:`` subsections from a named provenance section.

    Args:
        provenance_content: Raw provenance markdown text.
        section_header: The ``## …`` header that starts the section to parse.
        end_headers: Tuple of ``## …`` headers that terminate the section.

    Returns:
        Ordered list of :class:`_Decision` named tuples.
    """
    decisions: list[_Decision] = []

    section_start = provenance_content.find(section_header)
    if section_start == -1:
        return decisions

    end = len(provenance_content)
    for header in end_headers:
        idx = provenance_content.find(header, section_start + len(section_header))
        if idx != -1 and idx < end:
            end = idx

    section = provenance_content[section_start:end]

    decision_pattern = re.compile(r"^### Decision:\s*(.+)$", re.MULTILINE)
    matches = list(decision_pattern.finditer(section))

    for i, match in enumerate(matches):
        title = match.group(1).strip()
        section_start_inner = match.end()
        section_end = matches[i + 1].start() if i + 1 < len(matches) else len(section)
        section_content = section[section_start_inner:section_end]

        timestamp = _parse_field(section_content, "Timestamp")
        alternatives_raw = _parse_field(section_content, "Alternatives")
        rationale_raw = _parse_field(section_content, "Rationale")
        references_raw = _parse_field(section_content, "References")

        # Parse alternatives — may already be a <details> block
        alternatives: list[str] = []
        if alternatives_raw and alternatives_raw not in ("None considered", "None"):
            if "<details>" in alternatives_raw:
                alternatives = [alternatives_raw]
            else:
                alternatives = [a.strip() for a in alternatives_raw.split(",") if a.strip()]

        # Parse references
        references: list[str] = []
        if references_raw and references_raw != "None":
            if "<details>" not in references_raw:
                references = [r.strip() for r in references_raw.split(",") if r.strip()]
            else:
                references = [references_raw]

        decisions.append(
            _Decision(
                title=title,
                timestamp=timestamp,
                alternatives=alternatives,
                rationale=rationale_raw,
                references=references,
            )
        )

    return decisions


def _collapse_large_fenced_blocks(markdown: str) -> str:
    """Wrap large fenced code/diff blocks in ``<details>`` for readability.

    Args:
        markdown: Rendered markdown content.

    Returns:
        Markdown with fenced blocks over the line threshold wrapped in a
        collapsible details block.
    """

    def _repl(match: re.Match[str]) -> str:
        language = (match.group("lang") or "").strip()
        body = match.group("body")
        line_count = len(body.splitlines())

        if line_count <= _LARGE_BLOCK_LINE_THRESHOLD:
            return match.group(0)

        if language == "diff":
            label = f"Diff ({line_count} lines)"
        elif language:
            label = f"{language} block ({line_count} lines)"
        else:
            label = f"Code block ({line_count} lines)"

        fenced = f"```{language}\n{body}\n```" if language else f"```\n{body}\n```"
        return f"<details><summary>{label}</summary>\n\n{fenced}\n\n</details>"

    pattern = re.compile(r"```(?P<lang>[^\n`]*)\n(?P<body>.*?)\n```", re.DOTALL)
    return pattern.sub(_repl, markdown)


def _render_decision_subsections(decisions: list[_Decision]) -> list[str]:
    """Render a list of decisions into PR body lines.

    Args:
        decisions: Parsed decisions to render.

    Returns:
        Lines suitable for inclusion in the PR body.
    """
    parts: list[str] = []
    for decision in decisions:
        parts.append(f"#### {decision.title}")
        parts.append("")
        parts.append(f"- **Timestamp**: {decision.timestamp}")

        # Alternatives
        if not decision.alternatives:
            parts.append("- **Alternatives**: None considered")
        elif len(decision.alternatives) == 1 and "<details>" in decision.alternatives[0]:
            parts.append(f"- **Alternatives**: {decision.alternatives[0]}")
        elif len(decision.alternatives) > _ALTERNATIVES_COLLAPSE_THRESHOLD:
            alts_inner = ", ".join(decision.alternatives)
            parts.append(
                "- **Alternatives**: "
                "<details><summary>Alternatives (click to expand)</summary>"
                f"\n\n{alts_inner}\n\n</details>"
            )
        else:
            parts.append(f"- **Alternatives**: {', '.join(decision.alternatives)}")

        # Rationale
        if decision.rationale and "<details>" in decision.rationale:
            parts.append(f"- **Rationale**: {decision.rationale}")
        elif decision.rationale and len(decision.rationale) > _RATIONALE_COLLAPSE_THRESHOLD:
            parts.append(
                "- **Rationale**: "
                "<details><summary>Rationale (click to expand)</summary>"
                f"\n\n{decision.rationale}\n\n</details>"
            )
        else:
            parts.append(f"- **Rationale**: {decision.rationale}")

        # References
        if decision.references:
            refs_str = ", ".join(decision.references)
            parts.append(f"- **References**: {refs_str}")
        else:
            parts.append("- **References**: None")

        parts.append("")
    return parts


def _render_pr_body(
    title: str,
    ac_items: list[str] | None,
    validation_table: str,
    decisions: list[_Decision],
    impl_decisions: list[_Decision] | None = None,
) -> str:
    """Assemble the final PR body markdown string.

    Applies ``<details>`` wrapping for rationale >500 characters and
    alternatives >5 items.  Pre-existing ``<details>`` blocks are passed
    through unchanged.

    Args:
        title: Story title/slug from the provenance header.
        ac_items: Acceptance criteria lines, or ``None`` to omit the section.
        validation_table: Pre-parsed validation history table markdown.
        decisions: List of parsed pipeline-activity decisions (from
            ``## Agent Decisions`` in the provenance file).
        impl_decisions: List of LLM-extracted implementation decisions (from
            ``## Implementation Decisions``), or ``None`` to omit.

    Returns:
        GitHub-flavoured markdown PR description string.
    """
    parts: list[str] = []

    # Header
    parts.append(f"## Story: {title}")
    parts.append("")
    parts.append("---")
    parts.append("")

    # Acceptance Criteria section (omitted when ac_items is None)
    if ac_items is not None and ac_items:
        parts.append("### Acceptance Criteria")
        parts.append("")
        for ac in ac_items:
            parts.append(f"- [ ] {ac}")
        parts.append("")

    # Validation Results
    parts.append("### Validation Results")
    parts.append("")
    if validation_table:
        parts.append(validation_table)
    parts.append("")

    # Agent Decisions (LLM-extracted implementation decisions)
    parts.append("### Agent Decisions")
    parts.append("")
    if impl_decisions is None or not impl_decisions:
        parts.append("Decision extraction unavailable")
        parts.append("")
    else:
        parts.extend(_render_decision_subsections(impl_decisions))

    # Pipeline Activity (renamed from Decision Provenance)
    parts.append("### Pipeline Activity")
    parts.append("")

    if not decisions:
        parts.append("No pipeline activity recorded")
        parts.append("")
    else:
        parts.extend(_render_decision_subsections(decisions))

    return _collapse_large_fenced_blocks("\n".join(parts))


# ---------------------------------------------------------------------------
# Public API (Task 5)
# ---------------------------------------------------------------------------


async def generate_pr_body(run_id: str, story_slug: str, *, project_root: Path) -> str:
    """Generate a pull request body with embedded decision provenance.

    Reads the provenance file and optional story copy from the D3↔D5 contract
    path, then assembles a GitHub-flavoured markdown PR description containing
    the story title, acceptance criteria (if available), validation history
    table, and agent decision provenance subsections.

    Args:
        run_id: The run identifier (e.g. ``"20260101-120000-abc123"``).
        story_slug: The story slug matching the run directory entry
            (e.g. ``"6-4-pr-body-generator"``).
        project_root: Absolute path to the repository root.

    Returns:
        A GitHub-flavoured markdown string ready for use as a PR description.

    Raises:
        ScmError: If the provenance file does not exist at the expected path.
    """
    provenance_content = await _read_provenance(run_id, story_slug, project_root=project_root)
    story_content = await _read_story_copy(run_id, story_slug, project_root=project_root)

    title = _extract_story_title(provenance_content, story_content=story_content)
    ac_items: list[str] | None = _extract_acceptance_criteria(story_content) if story_content is not None else None
    validation_table = _extract_validation_table(provenance_content)
    decisions = _extract_decisions(provenance_content)
    impl_decisions = _extract_implementation_decisions(provenance_content)

    body = _render_pr_body(title, ac_items, validation_table, decisions, impl_decisions=impl_decisions or None)

    decision_count = len(decisions)
    impl_decision_count = len(impl_decisions)
    ac_count = len(ac_items) if ac_items is not None else 0

    logger.info(
        "scm.pr.generate",
        extra={
            "data": {
                "run_id": run_id,
                "story_slug": story_slug,
                "decision_count": decision_count,
                "impl_decision_count": impl_decision_count,
                "ac_count": ac_count,
            }
        },
    )

    return body


# ---------------------------------------------------------------------------
# Default branch detection helper
# ---------------------------------------------------------------------------


async def _detect_default_branch(
    project_root: Path,
    story_slug: str,
    *,
    default_branch_override: str = "",
) -> str:
    """Detect the repository default branch, fallback to ``main``.

    When *default_branch_override* is a non-empty string the value is returned
    immediately, bypassing all git/gh detection.

    Args:
        project_root: Absolute path to the repository root.
        story_slug: Story slug used in log events.
        default_branch_override: Config-supplied branch name.  Empty string
            (the default) means run the auto-detect cascade.

    Returns:
        Default branch name (e.g. ``"main"`` or ``"master"``).  Falls back to
        ``"main"`` if detection fails.
    """
    if stripped_override := default_branch_override.strip():
        logger.debug(
            "scm.pr.default_branch_config",
            extra={"data": {"story_slug": story_slug, "branch": stripped_override}},
        )
        return stripped_override

    try:
        result = await git("remote", "show", "origin", cwd=project_root)
        match = re.search(r"HEAD branch:\s*(?P<branch>\S+)", result.stdout)
        if match is not None:
            return match.group("branch")
    except Exception:
        pass

    if shutil.which("gh") is not None:
        try:
            proc = await asyncio.create_subprocess_exec(
                "gh",
                "repo",
                "view",
                "--json",
                "defaultBranchRef",
                cwd=str(project_root),
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout_bytes, _ = await proc.communicate()
            if proc.returncode == 0:
                parsed = json.loads(stdout_bytes.decode("utf-8", errors="replace"))
                branch = parsed.get("defaultBranchRef", {}).get("name")
                if isinstance(branch, str) and branch:
                    return branch
        except Exception:
            pass

    try:
        result = await git("rev-parse", "--abbrev-ref", "origin/HEAD", cwd=project_root)
        branch = result.stdout.strip()
        if branch.startswith("origin/"):
            return branch[len("origin/") :]
        if branch:
            return branch
    except Exception:
        pass

    logger.warning(
        "scm.pr.default_branch_fallback",
        extra={"data": {"story_slug": story_slug, "fallback": "main"}},
    )
    return "main"


def _parse_github_owner_repo(remote_url: str) -> tuple[str, str] | None:
    """Parse owner/repo from common GitHub remote URL formats."""
    for pattern in _GITHUB_REMOTE_PATTERNS:
        match = pattern.match(remote_url.strip())
        if match is None:
            continue
        owner = match.group("owner")
        repo = match.group("repo")
        if owner and repo:
            return owner, repo
    return None


async def _build_manual_pr_url(project_root: Path, branch_name: str) -> str:
    """Build manual PR URL including owner/repo when it can be resolved."""
    try:
        result = await git("remote", "get-url", "origin", cwd=project_root)
        parsed = _parse_github_owner_repo(result.stdout.strip())
        if parsed is not None:
            owner, repo = parsed
            return f"https://github.com/{owner}/{repo}/pull/new/{branch_name}"
    except Exception:
        pass
    return f"https://github.com/<owner>/<repo>/pull/new/{branch_name}"


# ---------------------------------------------------------------------------
# Public API — open_pull_request
# ---------------------------------------------------------------------------


async def open_pull_request(
    branch_name: str,
    story_slug: str,
    pr_body: str,
    *,
    project_root: Path,
    default_branch: str = "",
) -> str | None:
    """Open a GitHub pull request for the story branch (best-effort).

    Detects the repository default branch, checks ``gh`` CLI availability, then
    calls ``gh pr create``.  Any failure (gh missing, not authenticated, PR
    already exists) is logged as a warning and ``None`` is returned.  The
    caller's story status is never affected by failures (AC: #5).

    Args:
        branch_name: Full branch name (e.g. ``arcwright-ai/my-story``).
        story_slug: Story slug used for the PR title and log events.
        pr_body: Markdown PR description from :func:`generate_pr_body`.
        project_root: Absolute path to the repository root.
        default_branch: Config-supplied default branch override.  Empty string
            (the default) triggers auto-detection via ``_detect_default_branch``.

    Returns:
        PR URL string on success, or ``None`` on any failure.
    """
    manual_pr_url = await _build_manual_pr_url(project_root, branch_name)

    # Check gh CLI availability (AC: #5)
    if shutil.which("gh") is None:
        logger.warning(
            "scm.pr.create.skipped",
            extra={
                "data": {
                    "story_slug": story_slug,
                    "reason": "gh_not_found",
                    "manual_pr_url": manual_pr_url,
                }
            },
        )
        return None

    # Detect default branch (AC: #6)
    resolved_default_branch = await _detect_default_branch(
        project_root, story_slug, default_branch_override=default_branch
    )

    # Derive PR title from story slug (AC: #7)
    parts = story_slug.split("-", 2)
    title_part = parts[2] if len(parts) > 2 else story_slug
    pr_title = f"[arcwright-ai] {title_part.replace('-', ' ').title()}"

    # Open PR with gh CLI (AC: #4)
    try:
        proc = await asyncio.create_subprocess_exec(
            "gh",
            "pr",
            "create",
            "--base",
            resolved_default_branch,
            "--head",
            branch_name,
            "--title",
            pr_title,
            "--body",
            pr_body,
            cwd=str(project_root),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout_bytes, stderr_bytes = await proc.communicate()
        stdout = stdout_bytes.decode("utf-8", errors="replace").strip()
        stderr = stderr_bytes.decode("utf-8", errors="replace").strip()

        if proc.returncode != 0:
            # PR already exists is not a true error — just skip (AC: #10)
            if "already exists" in stderr.lower() or "already exists" in stdout.lower():
                logger.warning(
                    "scm.pr.create.skipped",
                    extra={
                        "data": {
                            "story_slug": story_slug,
                            "reason": "pr_already_exists",
                        }
                    },
                )
            else:
                logger.warning(
                    "scm.pr.create.skipped",
                    extra={
                        "data": {
                            "story_slug": story_slug,
                            "reason": "gh_error",
                            "stderr": stderr,
                            "returncode": proc.returncode,
                            "manual_pr_url": manual_pr_url,
                        }
                    },
                )
            return None

        pr_url = stdout
        logger.info(
            "scm.pr.create",
            extra={
                "data": {
                    "story_slug": story_slug,
                    "branch": branch_name,
                    "pr_url": pr_url,
                    "base": resolved_default_branch,
                }
            },
        )
        return pr_url

    except Exception as exc:
        logger.warning(
            "scm.pr.create.skipped",
            extra={
                "data": {
                    "story_slug": story_slug,
                    "reason": "subprocess_error",
                    "error": str(exc),
                    "manual_pr_url": manual_pr_url,
                }
            },
        )
        return None


async def merge_pull_request(
    pr_url: str,
    strategy: str = "squash",
    *,
    project_root: Path,
    wait_timeout: int = 0,
) -> MergeOutcome:
    """Merge a GitHub pull request after creation.

    When *wait_timeout* is ``0`` (default) the function performs an immediate
    merge identical to the original Story 9.3 behaviour.  When *wait_timeout*
    is positive the function queues auto-merge via ``--auto``, waits for CI
    checks to complete (up to *wait_timeout* seconds), and verifies the PR
    actually merged before returning.

    Args:
        pr_url: PR URL as returned by :func:`open_pull_request`, e.g.
            ``"https://github.com/owner/repo/pull/42"``.
        strategy: Merge strategy — ``"squash"`` (default), ``"merge"``, or
            ``"rebase"``.
        project_root: Absolute path to the repository root.
        wait_timeout: Maximum seconds to wait for CI checks.  ``0`` means
            fire-and-forget (immediate merge, no CI wait).

    Returns:
        A :class:`MergeOutcome` indicating the result of the merge attempt.
    """
    # Guard: gh CLI must be available
    if shutil.which("gh") is None:
        logger.warning(
            "scm.pr.merge.skipped",
            extra={"data": {"pr_url": pr_url, "reason": "gh_not_found", "merge_outcome": MergeOutcome.ERROR.value}},
        )
        return MergeOutcome.ERROR

    # Extract PR number from URL
    pr_number = _extract_pr_number(pr_url)
    if pr_number is None:
        logger.warning(
            "scm.pr.merge.skipped",
            extra={"data": {"pr_url": pr_url, "reason": "invalid_pr_url", "merge_outcome": MergeOutcome.ERROR.value}},
        )
        return MergeOutcome.ERROR

    # Map strategy to gh flag
    strategy_flag = _MERGE_STRATEGY_FLAGS.get(strategy, "--squash")

    if wait_timeout > 0:
        return await _merge_with_ci_wait(
            pr_number=pr_number,
            pr_url=pr_url,
            strategy_flag=strategy_flag,
            project_root=project_root,
            wait_timeout=wait_timeout,
        )

    # Fire-and-forget path (wait_timeout == 0, original behaviour)
    return await _merge_immediate(
        pr_number=pr_number,
        pr_url=pr_url,
        strategy=strategy,
        strategy_flag=strategy_flag,
        project_root=project_root,
    )


async def _merge_immediate(
    *,
    pr_number: str,
    pr_url: str,
    strategy: str,
    strategy_flag: str,
    project_root: Path,
) -> MergeOutcome:
    """Fire-and-forget merge (wait_timeout == 0)."""
    try:
        proc = await asyncio.create_subprocess_exec(
            "gh",
            "pr",
            "merge",
            pr_number,
            strategy_flag,
            "--delete-branch",
            cwd=str(project_root),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout_bytes, stderr_bytes = await proc.communicate()
        stdout = stdout_bytes.decode("utf-8", errors="replace").strip()
        stderr = stderr_bytes.decode("utf-8", errors="replace").strip()

        if proc.returncode != 0:
            # The remote PR merge may have succeeded even though gh exited non-zero.
            # This happens when --delete-branch cannot delete the local branch because
            # it is still checked out by a git worktree.  Verify actual PR state before
            # recording an error (AC: #1, #2).
            pr_merged = await _check_pr_state(pr_number, project_root)
            if pr_merged:
                logger.warning(
                    "scm.pr.post_merge_cleanup.failed",
                    extra={
                        "data": {
                            "pr_url": pr_url,
                            "pr_number": pr_number,
                            "returncode": proc.returncode,
                            "stderr": stderr,
                            "note": "pr_merged_but_local_cleanup_failed",
                        }
                    },
                )
                sha_match = re.search(r"[0-9a-f]{7,40}", stdout)
                merge_sha = sha_match.group(0) if sha_match else "unknown"
                logger.info(
                    "scm.pr.merge",
                    extra={
                        "data": {
                            "pr_url": pr_url,
                            "pr_number": pr_number,
                            "strategy": strategy,
                            "merge_sha": merge_sha,
                            "merge_outcome": MergeOutcome.MERGED.value,
                        }
                    },
                )
                return MergeOutcome.MERGED

            logger.warning(
                "scm.pr.merge.failed",
                extra={
                    "data": {
                        "pr_url": pr_url,
                        "pr_number": pr_number,
                        "stderr": stderr,
                        "returncode": proc.returncode,
                        "merge_outcome": MergeOutcome.ERROR.value,
                    }
                },
            )
            return MergeOutcome.ERROR

        sha_match = re.search(r"[0-9a-f]{7,40}", stdout)
        merge_sha = sha_match.group(0) if sha_match else "unknown"

        logger.info(
            "scm.pr.merge",
            extra={
                "data": {
                    "pr_url": pr_url,
                    "pr_number": pr_number,
                    "strategy": strategy,
                    "merge_sha": merge_sha,
                    "merge_outcome": MergeOutcome.MERGED.value,
                }
            },
        )
        return MergeOutcome.MERGED

    except Exception as exc:
        logger.warning(
            "scm.pr.merge.failed",
            extra={
                "data": {
                    "pr_url": pr_url,
                    "pr_number": pr_number,
                    "reason": "subprocess_error",
                    "error": str(exc),
                    "merge_outcome": MergeOutcome.ERROR.value,
                }
            },
        )
        return MergeOutcome.ERROR


async def _merge_with_ci_wait(
    *,
    pr_number: str,
    pr_url: str,
    strategy_flag: str,
    project_root: Path,
    wait_timeout: int,
) -> MergeOutcome:
    """Queue auto-merge, wait for CI, and verify the PR actually merged."""
    try:
        # Step A: Queue auto-merge with --auto flag
        outcome = await _step_a_queue_auto_merge(
            pr_number=pr_number,
            pr_url=pr_url,
            strategy_flag=strategy_flag,
            project_root=project_root,
        )
        if outcome is not None:
            return outcome

        # Step B: Wait for CI checks
        outcome = await _step_b_wait_for_ci(
            pr_number=pr_number,
            pr_url=pr_url,
            project_root=project_root,
            wait_timeout=wait_timeout,
        )
        if outcome is not None:
            return outcome

        # Step C: Verify merge completed
        return await _step_c_verify_merge(
            pr_number=pr_number,
            pr_url=pr_url,
            project_root=project_root,
            wait_timeout=wait_timeout,
        )

    except Exception as exc:
        logger.warning(
            "scm.pr.merge.failed",
            extra={
                "data": {
                    "pr_url": pr_url,
                    "pr_number": pr_number,
                    "reason": "subprocess_error",
                    "error": str(exc),
                    "merge_outcome": MergeOutcome.ERROR.value,
                    "wait_timeout": wait_timeout,
                }
            },
        )
        return MergeOutcome.ERROR


async def _step_a_queue_auto_merge(
    *,
    pr_number: str,
    pr_url: str,
    strategy_flag: str,
    project_root: Path,
) -> MergeOutcome | None:
    """Run ``gh pr merge --auto``.  Returns ``MergeOutcome.ERROR`` on failure, ``None`` on success."""
    proc = await asyncio.create_subprocess_exec(
        "gh",
        "pr",
        "merge",
        pr_number,
        strategy_flag,
        "--delete-branch",
        "--auto",
        cwd=str(project_root),
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    _stdout_bytes, stderr_bytes = await proc.communicate()
    stderr = stderr_bytes.decode("utf-8", errors="replace").strip()

    if "auto-merge is not allowed" in stderr:
        logger.warning(
            "scm.pr.merge.failed",
            extra={
                "data": {
                    "pr_url": pr_url,
                    "pr_number": pr_number,
                    "reason": "auto_merge_not_allowed",
                    "merge_outcome": MergeOutcome.ERROR.value,
                    "hint": "Auto-merge is not enabled for this repository. "
                    "Enable it in Settings → General → Allow auto-merge.",
                }
            },
        )
        return MergeOutcome.ERROR

    if proc.returncode != 0:
        # Local branch deletion via --delete-branch may fail when the branch is
        # still checked out in a worktree, even though GitHub queued auto-merge
        # successfully.  Treat this as a non-blocking cleanup warning (AC: #1, #2).
        if _is_branch_cleanup_error(stderr):
            logger.warning(
                "scm.pr.post_merge_cleanup.failed",
                extra={
                    "data": {
                        "pr_url": pr_url,
                        "pr_number": pr_number,
                        "returncode": proc.returncode,
                        "stderr": stderr,
                        "note": "auto_merge_queued_but_local_cleanup_failed",
                    }
                },
            )
            # Auto-merge was queued on GitHub; continue to CI-wait step.
        else:
            logger.warning(
                "scm.pr.merge.failed",
                extra={
                    "data": {
                        "pr_url": pr_url,
                        "pr_number": pr_number,
                        "stderr": stderr,
                        "returncode": proc.returncode,
                        "merge_outcome": MergeOutcome.ERROR.value,
                    }
                },
            )
            return MergeOutcome.ERROR

    logger.info(
        "scm.merge.auto_queued",
        extra={"data": {"pr_url": pr_url, "pr_number": pr_number}},
    )
    return None  # success — continue to Step B


async def _step_b_wait_for_ci(
    *,
    pr_number: str,
    pr_url: str,
    project_root: Path,
    wait_timeout: int,
) -> MergeOutcome | None:
    """Run ``gh pr checks --watch --fail-fast`` with timeout.

    Returns ``None`` when CI passes (caller should verify merge), or a
    terminal ``MergeOutcome`` on CI failure / timeout.
    """
    proc = await asyncio.create_subprocess_exec(
        "gh",
        "pr",
        "checks",
        pr_number,
        "--watch",
        "--fail-fast",
        cwd=str(project_root),
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    try:
        _stdout_bytes, stderr_bytes = await asyncio.wait_for(proc.communicate(), timeout=wait_timeout)
    except TimeoutError:
        # Graceful subprocess termination
        proc.terminate()
        try:
            await asyncio.wait_for(proc.wait(), timeout=5)
        except TimeoutError:
            proc.kill()
            await proc.wait()

        # Race-window check: PR may have merged moments before timeout
        merged = await _check_pr_state(pr_number, project_root)
        if merged:
            logger.info(
                "scm.merge.outcome",
                extra={
                    "data": {
                        "pr_url": pr_url,
                        "pr_number": pr_number,
                        "merge_outcome": MergeOutcome.MERGED.value,
                        "wait_timeout": wait_timeout,
                        "note": "merged_during_timeout_window",
                    }
                },
            )
            return MergeOutcome.MERGED

        logger.warning(
            "scm.merge.outcome",
            extra={
                "data": {
                    "pr_url": pr_url,
                    "pr_number": pr_number,
                    "merge_outcome": MergeOutcome.TIMEOUT.value,
                    "wait_timeout": wait_timeout,
                }
            },
        )
        return MergeOutcome.TIMEOUT

    if proc.returncode != 0:
        stderr = stderr_bytes.decode("utf-8", errors="replace").strip()
        outcome = MergeOutcome.CI_FAILED if proc.returncode == 1 else MergeOutcome.ERROR
        logger.warning(
            "scm.merge.outcome",
            extra={
                "data": {
                    "pr_url": pr_url,
                    "pr_number": pr_number,
                    "merge_outcome": outcome.value,
                    "wait_timeout": wait_timeout,
                    "ci_exit_code": proc.returncode,
                    "stderr": stderr,
                }
            },
        )
        return outcome

    return None  # CI passed — continue to Step C


async def _step_c_verify_merge(
    *,
    pr_number: str,
    pr_url: str,
    project_root: Path,
    wait_timeout: int,
) -> MergeOutcome:
    """Verify the PR actually merged (retry up to 3 times with 5s sleep)."""
    for attempt in range(3):
        if await _check_pr_state(pr_number, project_root):
            logger.info(
                "scm.merge.outcome",
                extra={
                    "data": {
                        "pr_url": pr_url,
                        "pr_number": pr_number,
                        "merge_outcome": MergeOutcome.MERGED.value,
                        "wait_timeout": wait_timeout,
                        "verify_attempt": attempt + 1,
                    }
                },
            )
            return MergeOutcome.MERGED
        await asyncio.sleep(5)

    logger.warning(
        "scm.merge.outcome",
        extra={
            "data": {
                "pr_url": pr_url,
                "pr_number": pr_number,
                "merge_outcome": MergeOutcome.ERROR.value,
                "wait_timeout": wait_timeout,
                "reason": "not_merged_after_retries",
            }
        },
    )
    return MergeOutcome.ERROR


async def _check_pr_state(pr_number: str, project_root: Path) -> bool:
    """Return ``True`` if the PR state is ``MERGED``."""
    proc = await asyncio.create_subprocess_exec(
        "gh",
        "pr",
        "view",
        pr_number,
        "--json",
        "state",
        "--jq",
        ".state",
        cwd=str(project_root),
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout_bytes, _ = await proc.communicate()
    return stdout_bytes.decode("utf-8", errors="replace").strip() == "MERGED"


def _extract_pr_number(pr_url: str) -> str | None:
    """Extract pull-request number from a GitHub PR URL.

    Args:
        pr_url: GitHub PR URL (for example,
            ``"https://github.com/owner/repo/pull/42"``).

    Returns:
        The PR number as a string, or ``None`` when the URL does not match the
        expected ``.../pull/<number>`` suffix.
    """
    clean_url = pr_url.rstrip("/")
    match = re.search(r"/pull/(\d+)$", clean_url)
    if match is None:
        return None
    return match.group(1)


def _is_branch_cleanup_error(stderr: str) -> bool:
    """Return ``True`` when stderr indicates only a local branch deletion failure.

    This occurs when the branch is still checked out by a git worktree and
    cannot be deleted via ``git branch -D`` until the worktree is removed.
    The remote PR merge may have already succeeded at this point.

    Args:
        stderr: Standard error output from the ``gh pr merge`` subprocess.

    Returns:
        ``True`` when the error pattern matches a local-branch deletion failure.
    """
    stderr_lower = stderr.lower()
    return "checked out at" in stderr_lower or "cannot delete branch" in stderr_lower


async def get_pull_request_merge_sha(pr_url: str, *, project_root: Path) -> str | None:
    """Resolve merge commit SHA for a pull request via ``gh pr view``.

    Args:
        pr_url: PR URL returned by :func:`open_pull_request`.
        project_root: Absolute path to the repository root.

    Returns:
        Merge commit SHA string when available, otherwise ``None``.
    """
    if shutil.which("gh") is None:
        logger.warning(
            "scm.pr.merge.sha.skipped",
            extra={"data": {"pr_url": pr_url, "reason": "gh_not_found"}},
        )
        return None

    pr_number = _extract_pr_number(pr_url)
    if pr_number is None:
        logger.warning(
            "scm.pr.merge.sha.skipped",
            extra={"data": {"pr_url": pr_url, "reason": "invalid_pr_url"}},
        )
        return None

    try:
        proc = await asyncio.create_subprocess_exec(
            "gh",
            "pr",
            "view",
            pr_number,
            "--json",
            "mergeCommit",
            "--jq",
            ".mergeCommit.oid",
            cwd=str(project_root),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout_bytes, stderr_bytes = await proc.communicate()
        stdout = stdout_bytes.decode("utf-8", errors="replace").strip()
        stderr = stderr_bytes.decode("utf-8", errors="replace").strip()

        if proc.returncode != 0:
            logger.warning(
                "scm.pr.merge.sha.skipped",
                extra={
                    "data": {
                        "pr_url": pr_url,
                        "pr_number": pr_number,
                        "reason": "gh_error",
                        "stderr": stderr,
                        "returncode": proc.returncode,
                    }
                },
            )
            return None

        sha_match = re.search(r"[0-9a-f]{7,40}", stdout)
        return sha_match.group(0) if sha_match else None

    except Exception as exc:
        logger.warning(
            "scm.pr.merge.sha.skipped",
            extra={
                "data": {
                    "pr_url": pr_url,
                    "pr_number": pr_number,
                    "reason": "subprocess_error",
                    "error": str(exc),
                }
            },
        )
        return None
