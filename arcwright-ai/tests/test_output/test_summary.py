"""Unit tests for arcwright_ai.output.summary — Run summary and halt report generation."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import pytest

from arcwright_ai.core.config import ApiConfig, RunConfig
from arcwright_ai.core.constants import DIR_ARCWRIGHT, DIR_RUNS, SUMMARY_FILENAME
from arcwright_ai.core.exceptions import RunError
from arcwright_ai.core.types import RunId
from arcwright_ai.output.run_manager import (
    create_run,
    update_story_status,
)
from arcwright_ai.output.summary import (
    _extract_epic_from_slug,
    _extract_failing_ac_ids,
    _truncate_output_by_lines,
    write_halt_report,
    write_success_summary,
    write_timeout_summary,
)

if TYPE_CHECKING:
    from pathlib import Path

# ---------------------------------------------------------------------------
# Helpers / Fixtures
# ---------------------------------------------------------------------------


def _make_config() -> RunConfig:
    """Return a minimal RunConfig suitable for tests.

    Returns:
        RunConfig with a known API key and default values for all other fields.
    """
    return RunConfig(api=ApiConfig(claude_api_key="test-key-123"))


def _make_run_id() -> RunId:
    """Return a stable run ID for tests.

    Returns:
        RunId string.
    """
    return RunId("20260304-120000-abc123")


STORY_SLUGS_SINGLE = ["4-3-run-summary"]
STORY_SLUGS_MULTI = ["4-1-provenance", "4-2-run-manager", "4-3-run-summary"]


def _summary_md_path(tmp_path: Path, run_id: str) -> Path:
    """Return expected path for summary.md.

    Args:
        tmp_path: Test temp directory.
        run_id: Run identifier.

    Returns:
        Expected Path to summary.md.
    """
    return tmp_path / DIR_ARCWRIGHT / DIR_RUNS / run_id / SUMMARY_FILENAME


def _make_validation_history(count: int = 2) -> list[dict[str, Any]]:
    """Return a list of validation history entries.

    Args:
        count: Number of entries to generate.

    Returns:
        List of validation attempt dicts.
    """
    entries: list[dict[str, Any]] = []
    for i in range(1, count + 1):
        entry: dict[str, Any] = {
            "attempt": i,
            "outcome": "failed",
            "failures": f"AC{i} not satisfied: missing implementation detail number {i}",
        }
        entries.append(entry)
    return entries


@pytest.fixture
async def run_dir(tmp_path: Path) -> str:
    """Create a run directory with a single story and return the run ID.

    Args:
        tmp_path: Pytest temporary directory fixture.

    Returns:
        Run ID string.
    """
    run_id = _make_run_id()
    config = _make_config()
    await create_run(tmp_path, run_id, config, STORY_SLUGS_SINGLE)
    return run_id


@pytest.fixture
async def multi_story_run_dir(tmp_path: Path) -> str:
    """Create a run directory with multiple stories and return the run ID.

    Args:
        tmp_path: Pytest temporary directory fixture.

    Returns:
        Run ID string.
    """
    run_id = _make_run_id()
    config = _make_config()
    await create_run(tmp_path, run_id, config, STORY_SLUGS_MULTI)
    return run_id


# ---------------------------------------------------------------------------
# Tests for _extract_epic_from_slug (AC: #9m, #9n)
# ---------------------------------------------------------------------------


def test_extract_epic_from_slug_standard() -> None:
    """(9m) _extract_epic_from_slug parses the leading digit from X-N-name slugs."""
    assert _extract_epic_from_slug("4-3-run-summary") == "4"
    assert _extract_epic_from_slug("1-1-project-scaffold") == "1"
    assert _extract_epic_from_slug("10-2-some-story") == "10"


def test_extract_epic_from_slug_single_digit() -> None:
    """(9m) _extract_epic_from_slug handles single-digit epics."""
    assert _extract_epic_from_slug("2-7-agent-dispatch") == "2"
    assert _extract_epic_from_slug("5-1-epic-dispatch") == "5"


def test_extract_epic_from_slug_unparseable_returns_placeholder() -> None:
    """(9n) _extract_epic_from_slug returns '<EPIC>' for unrecognised formats."""
    assert _extract_epic_from_slug("not-matching") == "<EPIC>"
    assert _extract_epic_from_slug("") == "<EPIC>"
    assert _extract_epic_from_slug("epic-4") == "<EPIC>"


# ---------------------------------------------------------------------------
# Tests for write_success_summary (AC: #9a, #9b, #9c, #9k, #9l, #9p)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_write_success_summary_required_sections(tmp_path: Path, run_dir: str) -> None:
    """(9a) write_success_summary generates all required sections."""
    path = await write_success_summary(tmp_path, run_dir)

    content = path.read_text(encoding="utf-8")
    assert f"# Run Summary: {run_dir}" in content
    assert "## Overview" in content
    assert "## Stories Completed" in content
    assert "## Cost Summary" in content
    assert "## Provenance References" in content
    assert "## Next Steps" in content


@pytest.mark.asyncio
async def test_write_success_summary_returns_correct_path(tmp_path: Path, run_dir: str) -> None:
    """(9a) write_success_summary returns path to the summary.md."""
    path = await write_success_summary(tmp_path, run_dir)
    expected = _summary_md_path(tmp_path, run_dir)
    assert path == expected
    assert path.exists()


@pytest.mark.asyncio
async def test_write_success_summary_stories_with_status(tmp_path: Path, run_dir: str) -> None:
    """(9b) write_success_summary lists stories with correct status."""
    # Update story status so it shows completed
    await update_story_status(
        tmp_path,
        run_dir,
        STORY_SLUGS_SINGLE[0],
        status="completed",
        started_at="2026-03-04T12:00:00",
        completed_at="2026-03-04T12:05:00",
    )
    path = await write_success_summary(tmp_path, run_dir)
    content = path.read_text(encoding="utf-8")

    assert "4-3-run-summary" in content
    assert "status: completed" in content
    assert "started: 2026-03-04T12:00:00" in content
    assert "completed: 2026-03-04T12:05:00" in content


@pytest.mark.asyncio
async def test_write_success_summary_zero_budget_shows_na(tmp_path: Path, run_dir: str) -> None:
    """(9c) write_success_summary shows N/A for zero budget fields."""
    path = await write_success_summary(tmp_path, run_dir)
    content = path.read_text(encoding="utf-8")

    # Fresh run has 0/empty budget fields
    assert "N/A" in content


@pytest.mark.asyncio
async def test_write_success_summary_idempotent(tmp_path: Path, run_dir: str) -> None:
    """(9k) write_success_summary overwrites existing summary.md (idempotent)."""
    path1 = await write_success_summary(tmp_path, run_dir)
    first_content = path1.read_text(encoding="utf-8")

    path2 = await write_success_summary(tmp_path, run_dir)
    second_content = path2.read_text(encoding="utf-8")

    assert path1 == path2
    assert first_content == second_content


@pytest.mark.asyncio
async def test_write_success_summary_run_not_found_raises(tmp_path: Path) -> None:
    """(9l) write_success_summary raises RunError when run ID not found."""
    with pytest.raises(RunError):
        await write_success_summary(tmp_path, "nonexistent-run-id")


@pytest.mark.asyncio
async def test_write_success_summary_multiple_stories(tmp_path: Path, multi_story_run_dir: str) -> None:
    """(9p) write_success_summary lists all stories for multi-story runs."""
    path = await write_success_summary(tmp_path, multi_story_run_dir)
    content = path.read_text(encoding="utf-8")

    for slug in STORY_SLUGS_MULTI:
        assert slug in content


@pytest.mark.asyncio
async def test_write_success_summary_provenance_references(tmp_path: Path, multi_story_run_dir: str) -> None:
    """(9a) Provenance references section includes all story artifact directories."""
    path = await write_success_summary(tmp_path, multi_story_run_dir)
    content = path.read_text(encoding="utf-8")

    for slug in STORY_SLUGS_MULTI:
        assert f".arcwright-ai/runs/{multi_story_run_dir}/stories/{slug}/" in content


# ---------------------------------------------------------------------------
# Tests for write_halt_report (AC: #9d, #9e, #9f, #9g, #9h, #9k, #9l, #9q)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_write_halt_report_nfr18_fields_present(tmp_path: Path, run_dir: str) -> None:
    """(9d) write_halt_report includes all 4 NFR18 diagnostic fields."""
    validation_history = _make_validation_history(2)
    path = await write_halt_report(
        tmp_path,
        run_dir,
        halted_story="4-3-run-summary",
        halt_reason="max retries exceeded",
        validation_history=validation_history,
        last_agent_output="Agent output here",
        suggested_fix="Check the implementation of write_success_summary.",
    )
    content = path.read_text(encoding="utf-8")

    # Field 1: Which story failed
    assert "## Halted Story" in content
    assert "4-3-run-summary" in content

    # Field 2: What validation criteria failed
    assert "## Validation Failures" in content

    # Field 3: Retry history
    assert "## Retry History" in content
    assert "| Attempt | Outcome | Feedback |" in content

    # Field 4: Suggested manual fix
    assert "## Suggested Fix" in content
    assert "Check the implementation of write_success_summary." in content


@pytest.mark.asyncio
async def test_write_halt_report_retry_history_table_truncation(tmp_path: Path, run_dir: str) -> None:
    """(9e) write_halt_report truncates feedback longer than 200 chars in retry table."""
    long_feedback = "X" * 250
    validation_history: list[dict[str, Any]] = [
        {"attempt": 1, "outcome": "failed", "failures": long_feedback},
    ]
    path = await write_halt_report(
        tmp_path,
        run_dir,
        halted_story="4-3-run-summary",
        halt_reason="test",
        validation_history=validation_history,
        last_agent_output="short output",
        suggested_fix="fix",
    )
    content = path.read_text(encoding="utf-8")

    # The table row should contain truncated feedback (200 chars + "...")
    assert "X" * 200 + "..." in content
    # The original 250-char version should NOT appear in the table row
    # (it might appear in Validation Failures section, but not in the table)
    table_section = content.split("## Retry History")[1].split("##")[0]
    assert len("X" * 250) > 200  # sanity check
    # Table rows end at newline; any row with 250 Xs would be > 200
    for line in table_section.splitlines():
        if "X" in line and "|" in line:
            assert "X" * 251 not in line


@pytest.mark.asyncio
async def test_write_halt_report_long_agent_output_truncation(tmp_path: Path, run_dir: str) -> None:
    """(9f) write_halt_report truncates last_agent_output to 500 lines with notice."""
    # Build a 600-line output so truncation triggers
    long_output = "\n".join(f"line {i}" for i in range(600))
    path = await write_halt_report(
        tmp_path,
        run_dir,
        halted_story="4-3-run-summary",
        halt_reason="test",
        validation_history=[],
        last_agent_output=long_output,
        suggested_fix="fix",
    )
    content = path.read_text(encoding="utf-8")

    assert "truncated" in content.lower()
    assert "600" in content  # total line count notice
    # Last 500 lines start at line 100 (lines 100-599 of a 0-indexed 600-line output)
    assert "line 599" in content
    # The first line should not appear (it was truncated off)
    assert "line 0\n" not in content


@pytest.mark.asyncio
async def test_write_halt_report_short_agent_output_no_truncation(tmp_path: Path, run_dir: str) -> None:
    """(9g) write_halt_report renders short agent output without truncation."""
    short_output = "Short output text."
    path = await write_halt_report(
        tmp_path,
        run_dir,
        halted_story="4-3-run-summary",
        halt_reason="test",
        validation_history=[],
        last_agent_output=short_output,
        suggested_fix="fix",
    )
    content = path.read_text(encoding="utf-8")

    assert short_output in content
    # No truncation notice should be present
    assert "truncated" not in content.lower()


@pytest.mark.asyncio
async def test_write_halt_report_resume_command_contains_epic(tmp_path: Path, run_dir: str) -> None:
    """(9h) write_halt_report resume command contains correct epic number."""
    path = await write_halt_report(
        tmp_path,
        run_dir,
        halted_story="4-3-run-summary",
        halt_reason="test",
        validation_history=[],
        last_agent_output="output",
        suggested_fix="fix",
    )
    content = path.read_text(encoding="utf-8")

    assert "arcwright-ai dispatch --epic EPIC-4 --resume" in content


@pytest.mark.asyncio
async def test_write_halt_report_resume_command_uses_placeholder_for_unparseable_slug(
    tmp_path: Path,
    run_dir: str,
) -> None:
    """(9n) unparseable slugs use '<EPIC>' placeholder without extra prefix."""
    path = await write_halt_report(
        tmp_path,
        run_dir,
        halted_story="not-a-story-slug",
        halt_reason="test",
        validation_history=[],
        last_agent_output="output",
        suggested_fix="fix",
    )
    content = path.read_text(encoding="utf-8")

    assert "arcwright-ai dispatch --epic <EPIC> --resume" in content
    assert "arcwright-ai dispatch --epic EPIC-<EPIC> --resume" not in content


@pytest.mark.asyncio
async def test_write_halt_report_retry_history_escapes_markdown_cells(tmp_path: Path, run_dir: str) -> None:
    """Retry-history table escapes pipes and newlines in feedback text."""
    validation_history: list[dict[str, Any]] = [
        {
            "attempt": 1,
            "outcome": "failed|partial",
            "failures": "line1\nline2|detail",
        }
    ]
    path = await write_halt_report(
        tmp_path,
        run_dir,
        halted_story="4-3-run-summary",
        halt_reason="test",
        validation_history=validation_history,
        last_agent_output="output",
        suggested_fix="fix",
    )
    content = path.read_text(encoding="utf-8")

    assert "| 1 | failed\\|partial | line1<br>line2\\|detail |" in content


@pytest.mark.asyncio
async def test_write_halt_report_idempotent(tmp_path: Path, run_dir: str) -> None:
    """(9k) write_halt_report overwrites existing summary.md (idempotent)."""
    kwargs: dict[str, Any] = dict(
        halted_story="4-3-run-summary",
        halt_reason="test",
        validation_history=[],
        last_agent_output="output",
        suggested_fix="fix",
    )
    path1 = await write_halt_report(tmp_path, run_dir, **kwargs)
    first_content = path1.read_text(encoding="utf-8")

    path2 = await write_halt_report(tmp_path, run_dir, **kwargs)
    second_content = path2.read_text(encoding="utf-8")

    assert path1 == path2
    assert first_content == second_content


@pytest.mark.asyncio
async def test_write_halt_report_run_not_found_raises(tmp_path: Path) -> None:
    """(9l) write_halt_report raises RunError when run ID not found."""
    with pytest.raises(RunError):
        await write_halt_report(
            tmp_path,
            "nonexistent-run-id",
            halted_story="4-3-run-summary",
            halt_reason="test",
            validation_history=[],
            last_agent_output="output",
            suggested_fix="fix",
        )


@pytest.mark.asyncio
async def test_write_halt_report_empty_validation_history_has_table_header(tmp_path: Path, run_dir: str) -> None:
    """(9q) write_halt_report with empty validation_history still shows table header."""
    path = await write_halt_report(
        tmp_path,
        run_dir,
        halted_story="4-3-run-summary",
        halt_reason="test",
        validation_history=[],
        last_agent_output="output",
        suggested_fix="fix",
    )
    content = path.read_text(encoding="utf-8")

    assert "| Attempt | Outcome | Feedback |" in content
    # Should show empty row placeholder
    assert "| — | — | — |" in content


# ---------------------------------------------------------------------------
# Tests for write_timeout_summary (AC: #9i, #9j, #9k, #9l)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_write_timeout_summary_completed_and_remaining(tmp_path: Path, multi_story_run_dir: str) -> None:
    """(9i) write_timeout_summary lists stories completed and remaining."""
    # Mark first story as completed
    await update_story_status(
        tmp_path,
        multi_story_run_dir,
        STORY_SLUGS_MULTI[0],
        status="completed",
    )
    path = await write_timeout_summary(tmp_path, multi_story_run_dir)
    content = path.read_text(encoding="utf-8")

    assert "## Stories Completed" in content
    assert "## Stories Remaining" in content
    assert STORY_SLUGS_MULTI[0] in content
    assert STORY_SLUGS_MULTI[1] in content


@pytest.mark.asyncio
async def test_write_timeout_summary_resume_command_present(tmp_path: Path, multi_story_run_dir: str) -> None:
    """(9j) write_timeout_summary includes resume command in Next Steps."""
    path = await write_timeout_summary(tmp_path, multi_story_run_dir)
    content = path.read_text(encoding="utf-8")

    assert "## Next Steps" in content
    assert "arcwright-ai dispatch --epic EPIC-" in content
    assert "--resume" in content


@pytest.mark.asyncio
async def test_write_timeout_summary_resume_command_uses_placeholder_for_unparseable_slug(tmp_path: Path) -> None:
    """Unparseable remaining story slug produces '<EPIC>' resume placeholder."""
    run_id = _make_run_id()
    config = _make_config()
    await create_run(tmp_path, run_id, config, ["story-without-epic-prefix"])

    path = await write_timeout_summary(tmp_path, run_id)
    content = path.read_text(encoding="utf-8")

    assert "arcwright-ai dispatch --epic <EPIC> --resume" in content
    assert "arcwright-ai dispatch --epic EPIC-<EPIC> --resume" not in content


@pytest.mark.asyncio
async def test_write_timeout_summary_idempotent(tmp_path: Path, run_dir: str) -> None:
    """(9k) write_timeout_summary overwrites existing summary.md (idempotent)."""
    path1 = await write_timeout_summary(tmp_path, run_dir)
    first_content = path1.read_text(encoding="utf-8")

    path2 = await write_timeout_summary(tmp_path, run_dir)
    second_content = path2.read_text(encoding="utf-8")

    assert path1 == path2
    assert first_content == second_content


@pytest.mark.asyncio
async def test_write_timeout_summary_run_not_found_raises(tmp_path: Path) -> None:
    """(9l) write_timeout_summary raises RunError when run ID not found."""
    with pytest.raises(RunError):
        await write_timeout_summary(tmp_path, "nonexistent-run-id")


@pytest.mark.asyncio
async def test_write_timeout_summary_returns_correct_path(tmp_path: Path, run_dir: str) -> None:
    """write_timeout_summary returns path to the written summary.md file."""
    path = await write_timeout_summary(tmp_path, run_dir)
    expected = _summary_md_path(tmp_path, run_dir)
    assert path == expected
    assert path.exists()


# ---------------------------------------------------------------------------
# Cross-function tests: directory creation (AC: #9o)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_write_success_summary_creates_parent_dirs(tmp_path: Path) -> None:
    """(9o) write_success_summary creates parent directories if needed."""
    run_id = _make_run_id()
    config = _make_config()
    # Create run to have a valid run.yaml
    await create_run(tmp_path, run_id, config, STORY_SLUGS_SINGLE)
    # Verify summary path parent exists after call
    path = await write_success_summary(tmp_path, run_id)
    assert path.parent.exists()


@pytest.mark.asyncio
async def test_write_halt_report_creates_parent_dirs(tmp_path: Path) -> None:
    """(9o) write_halt_report creates parent directories if needed."""
    run_id = _make_run_id()
    config = _make_config()
    await create_run(tmp_path, run_id, config, STORY_SLUGS_SINGLE)
    path = await write_halt_report(
        tmp_path,
        run_id,
        halted_story="4-3-run-summary",
        halt_reason="test",
        validation_history=[],
        last_agent_output="output",
        suggested_fix="fix",
    )
    assert path.parent.exists()


@pytest.mark.asyncio
async def test_write_timeout_summary_creates_parent_dirs(tmp_path: Path) -> None:
    """(9o) write_timeout_summary creates parent directories if needed."""
    run_id = _make_run_id()
    config = _make_config()
    await create_run(tmp_path, run_id, config, STORY_SLUGS_SINGLE)
    path = await write_timeout_summary(tmp_path, run_id)
    assert path.parent.exists()


# ---------------------------------------------------------------------------
# Task 6.1-6.2 — _truncate_output_by_lines (AC: #1, #13b)
# ---------------------------------------------------------------------------


def test_truncate_output_by_lines_under_limit() -> None:
    """(6.1) _truncate_output_by_lines — text under 500 lines → no truncation."""
    text = "\n".join(f"line {i}" for i in range(100))
    result, was_truncated = _truncate_output_by_lines(text)
    assert not was_truncated
    assert result == text


def test_truncate_output_by_lines_exactly_at_limit() -> None:
    """(6.1) _truncate_output_by_lines — exactly 500 lines → no truncation."""
    text = "\n".join(f"line {i}" for i in range(500))
    result, was_truncated = _truncate_output_by_lines(text)
    assert not was_truncated
    assert result == text


def test_truncate_output_by_lines_over_limit() -> None:
    """(6.2) _truncate_output_by_lines — over 500 lines → truncates, was_truncated=True."""
    text = "\n".join(f"line {i}" for i in range(600))
    result, was_truncated = _truncate_output_by_lines(text)
    assert was_truncated
    # Should keep last 500 lines (lines 100-599)
    assert "line 599" in result
    assert "line 0\n" not in result


def test_truncate_output_by_lines_custom_max() -> None:
    """(6.2) _truncate_output_by_lines — custom max_lines parameter is respected."""
    text = "\n".join(f"line {i}" for i in range(20))
    result, was_truncated = _truncate_output_by_lines(text, max_lines=10)
    assert was_truncated
    assert "line 19" in result
    assert "line 0\n" not in result


def test_truncate_output_by_lines_empty_text() -> None:
    """(6.1) _truncate_output_by_lines — empty text → (empty, False)."""
    result, was_truncated = _truncate_output_by_lines("")
    assert not was_truncated
    assert result == ""


# ---------------------------------------------------------------------------
# Task 6.3-6.6 — write_halt_report new params (AC: #1, #3, #13a-d)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_write_halt_report_failing_ac_ids_displayed(tmp_path: Path, run_dir: str) -> None:
    """(6.3) write_halt_report — failing_ac_ids=['1','3'] → 'Failing ACs: #1, #3'."""
    path = await write_halt_report(
        tmp_path,
        run_dir,
        halted_story="5-4-halt-resume",
        halt_reason="validation exhaustion",
        validation_history=[],
        last_agent_output="",
        suggested_fix="fix this",
        failing_ac_ids=["1", "3"],
    )
    content = path.read_text(encoding="utf-8")
    assert "**Failing ACs:** #1, #3" in content


@pytest.mark.asyncio
async def test_write_halt_report_failing_ac_ids_none_shows_na(tmp_path: Path, run_dir: str) -> None:
    """(6.4) write_halt_report — failing_ac_ids=None → 'Failing ACs: N/A'."""
    path = await write_halt_report(
        tmp_path,
        run_dir,
        halted_story="5-4-halt-resume",
        halt_reason="budget exceeded",
        validation_history=[],
        last_agent_output="",
        suggested_fix="fix",
        failing_ac_ids=None,
    )
    content = path.read_text(encoding="utf-8")
    assert "**Failing ACs:** N/A" in content


@pytest.mark.asyncio
async def test_write_halt_report_worktree_path_none_shows_placeholder(tmp_path: Path, run_dir: str) -> None:
    """(6.5) write_halt_report — worktree_path=None → renders N/A placeholder."""
    path = await write_halt_report(
        tmp_path,
        run_dir,
        halted_story="5-4-halt-resume",
        halt_reason="test",
        validation_history=[],
        last_agent_output="",
        suggested_fix="fix",
        worktree_path=None,
    )
    content = path.read_text(encoding="utf-8")
    assert "N/A (worktree isolation pending Story 6.2)" in content


@pytest.mark.asyncio
async def test_write_halt_report_worktree_path_renders_actual_path(tmp_path: Path, run_dir: str) -> None:
    """(6.6) write_halt_report — worktree_path='/some/path' → renders actual path."""
    path = await write_halt_report(
        tmp_path,
        run_dir,
        halted_story="5-4-halt-resume",
        halt_reason="test",
        validation_history=[],
        last_agent_output="",
        suggested_fix="fix",
        worktree_path="/worktrees/5-4-branch",
    )
    content = path.read_text(encoding="utf-8")
    assert "/worktrees/5-4-branch" in content


# ---------------------------------------------------------------------------
# Task 6.7-6.8 — write_halt_report previous_run_id (AC: #4, #13e-f)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_write_halt_report_previous_run_combined_summary(tmp_path: Path) -> None:
    """(6.7) write_halt_report — previous_run_id provided → combined summary contains
    'Previous Run Report' section and previous run content."""
    from arcwright_ai.core.constants import DIR_ARCWRIGHT, DIR_RUNS

    config = _make_config()
    prev_run_id = "20260301-100000-prev11"
    curr_run_id = "20260306-120000-curr22"

    # Create previous run and write a synthetic summary.md to it
    await create_run(tmp_path, prev_run_id, config, ["5-3-resume-controller"])
    prev_summary_dir = tmp_path / DIR_ARCWRIGHT / DIR_RUNS / prev_run_id
    prev_summary_dir.mkdir(parents=True, exist_ok=True)
    (prev_summary_dir / "summary.md").write_text("# Previous halt report content", encoding="utf-8")

    # Create current run
    await create_run(tmp_path, curr_run_id, config, ["5-4-halt-resume"])

    path = await write_halt_report(
        tmp_path,
        curr_run_id,
        halted_story="5-4-halt-resume",
        halt_reason="validation exhaustion",
        validation_history=[],
        last_agent_output="",
        suggested_fix="fix",
        previous_run_id=prev_run_id,
    )
    content = path.read_text(encoding="utf-8")
    assert "Previous Run Report" in content
    assert "Previous halt report content" in content
    assert prev_run_id in content


@pytest.mark.asyncio
async def test_write_halt_report_previous_run_missing_logs_warning_proceeds(
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """(6.8) write_halt_report — previous_run_id provided but summary missing →
    warning logged, new summary still written."""
    import logging

    config = _make_config()
    curr_run_id = "20260306-120000-curr22"
    await create_run(tmp_path, curr_run_id, config, ["5-4-halt-resume"])

    with caplog.at_level(logging.WARNING, logger="arcwright_ai.output.summary"):
        path = await write_halt_report(
            tmp_path,
            curr_run_id,
            halted_story="5-4-halt-resume",
            halt_reason="validation exhaustion",
            validation_history=[],
            last_agent_output="",
            suggested_fix="fix",
            previous_run_id="nonexistent-run-id",
        )

    # New summary was written despite missing previous
    assert path.exists()
    content = path.read_text(encoding="utf-8")
    assert "# Run Summary:" in content
    # Warning was logged
    assert any("previous_run_read_error" in r.message for r in caplog.records)


# ---------------------------------------------------------------------------
# Task 6.9-6.10 — write_success_summary previous_run_id (AC: #4, #13g-h)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_write_success_summary_previous_run_combined(tmp_path: Path) -> None:
    """(6.9) write_success_summary — previous_run_id provided → combined summary
    contains 'Previous Run Report' section."""
    from arcwright_ai.core.constants import DIR_ARCWRIGHT, DIR_RUNS

    config = _make_config()
    prev_run_id = "20260301-100000-prev33"
    curr_run_id = "20260306-120000-curr44"

    # Create previous run and write a synthetic summary.md
    await create_run(tmp_path, prev_run_id, config, ["5-3-resume-controller"])
    prev_summary_dir = tmp_path / DIR_ARCWRIGHT / DIR_RUNS / prev_run_id
    prev_summary_dir.mkdir(parents=True, exist_ok=True)
    (prev_summary_dir / "summary.md").write_text("# Halt report from previous run", encoding="utf-8")

    # Create current run
    await create_run(tmp_path, curr_run_id, config, ["5-4-halt-resume"])

    path = await write_success_summary(
        tmp_path,
        curr_run_id,
        previous_run_id=prev_run_id,
    )
    content = path.read_text(encoding="utf-8")
    assert "Previous Run Report" in content
    assert "Halt report from previous run" in content
    assert prev_run_id in content


@pytest.mark.asyncio
async def test_write_success_summary_no_previous_run_id_unchanged(tmp_path: Path, run_dir: str) -> None:
    """(6.10) write_success_summary — previous_run_id=None → behavior unchanged."""
    path = await write_success_summary(tmp_path, run_dir)
    content = path.read_text(encoding="utf-8")
    # Normal summary structure present; no previous run section
    assert "# Run Summary:" in content
    assert "Previous Run Report" not in content


# ---------------------------------------------------------------------------
# Task 6.11-6.12 — _extract_failing_ac_ids (AC: #8, #13a)
# ---------------------------------------------------------------------------


def test_extract_failing_ac_ids_parses_v3_format() -> None:
    """(6.11) _extract_failing_ac_ids — 'V3: ACs 1, 3' → ['1', '3']."""
    history: list[dict[str, Any]] = [
        {"attempt": 1, "outcome": "fail_v3", "failures": "V3: ACs 1, 3"},
    ]
    result = _extract_failing_ac_ids(history)
    assert result == ["1", "3"]


def test_extract_failing_ac_ids_empty_history() -> None:
    """(6.12) _extract_failing_ac_ids — empty history → []."""
    result = _extract_failing_ac_ids([])
    assert result == []


def test_extract_failing_ac_ids_deduplicates() -> None:
    """_extract_failing_ac_ids — same AC across multiple attempts → deduplicated."""
    history: list[dict[str, Any]] = [
        {"attempt": 1, "outcome": "fail_v3", "failures": "V3: ACs 1, 3"},
        {"attempt": 2, "outcome": "fail_v3", "failures": "V3: ACs 1, 5"},
    ]
    result = _extract_failing_ac_ids(history)
    assert result == ["1", "3", "5"]


def test_extract_failing_ac_ids_parses_mixed_token_formats() -> None:
    """_extract_failing_ac_ids parses AC IDs from '#N', 'AC-N', and 'ACN' forms."""
    history: list[dict[str, Any]] = [
        {"attempt": 1, "outcome": "fail_v3", "failures": "V3: ACs #2, AC-4, AC7"},
    ]
    result = _extract_failing_ac_ids(history)
    assert result == ["2", "4", "7"]


def test_extract_failing_ac_ids_no_matches_returns_empty() -> None:
    """_extract_failing_ac_ids — no AC pattern in failures → []."""
    history: list[dict[str, Any]] = [
        {"attempt": 1, "outcome": "fail_v6", "failures": "V6: 2 checks failed"},
    ]
    result = _extract_failing_ac_ids(history)
    assert result == []


@pytest.mark.asyncio
async def test_write_halt_report_ac_ids_extracted_from_history(tmp_path: Path, run_dir: str) -> None:
    """write_halt_report — when failing_ac_ids omitted, ACs extracted from validation_history."""
    history: list[dict[str, Any]] = [
        {"attempt": 1, "outcome": "fail_v3", "failures": "V3: ACs 2, 4"},
    ]
    path = await write_halt_report(
        tmp_path,
        run_dir,
        halted_story="5-4-halt-resume",
        halt_reason="validation exhaustion",
        validation_history=history,
        last_agent_output="",
        suggested_fix="fix",
    )
    content = path.read_text(encoding="utf-8")
    assert "**Failing ACs:** #2, #4" in content


# ---------------------------------------------------------------------------
# Story 6.7 — PR URL in run summary (Task 5.5 / AC: #9)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_write_success_summary_includes_pull_request_section_when_pr_url_set(
    tmp_path: Path,
    run_dir: str,
) -> None:
    """write_success_summary emits '## Pull Request' section when story has pr_url."""
    pr_url = "https://github.com/owner/repo/pull/42"
    await update_story_status(
        tmp_path,
        run_dir,
        STORY_SLUGS_SINGLE[0],
        status="success",
        pr_url=pr_url,
    )

    path = await write_success_summary(tmp_path, run_dir)
    content = path.read_text(encoding="utf-8")

    assert "## Pull Request" in content
    assert pr_url in content


@pytest.mark.asyncio
async def test_write_success_summary_omits_pull_request_section_when_no_pr_url(
    tmp_path: Path,
    run_dir: str,
) -> None:
    """write_success_summary omits '## Pull Request' section when no pr_url is set."""
    path = await write_success_summary(tmp_path, run_dir)
    content = path.read_text(encoding="utf-8")

    assert "## Pull Request" not in content
