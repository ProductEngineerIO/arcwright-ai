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
    """(9f) write_halt_report truncates last_agent_output to 2000 chars with notice."""
    long_output = "A" * 3000
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
    assert "3000" in content  # total length notice
    # Last 2000 chars of "A"*3000 == "A"*2000
    assert "A" * 2000 in content
    # The first 1000 'A's should not appear as a continuous block
    assert "A" * 2001 not in content


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
