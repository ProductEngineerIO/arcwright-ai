"""Unit tests for arcwright_ai.output.decisions — LLM decision extraction."""

from __future__ import annotations

from typing import TYPE_CHECKING
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

if TYPE_CHECKING:
    from pathlib import Path

from arcwright_ai.output.decisions import (
    build_extraction_prompt,
    extract_agent_decisions,
    parse_extraction_response,
)

# ---------------------------------------------------------------------------
# 5.1 — Extraction prompt construction
# ---------------------------------------------------------------------------


def test_build_extraction_prompt_contains_diff() -> None:
    """build_extraction_prompt includes the git diff in the output."""
    diff = "diff --git a/foo.py b/foo.py\n+added line"
    prompt = build_extraction_prompt(diff, "agent did work")

    assert "```diff" in prompt
    assert diff in prompt


def test_build_extraction_prompt_contains_agent_output() -> None:
    """build_extraction_prompt includes the agent output text."""
    agent_output = "I implemented the Strategy pattern here."
    prompt = build_extraction_prompt("", agent_output)

    assert agent_output in prompt


def test_build_extraction_prompt_caps_diff_length() -> None:
    """build_extraction_prompt caps the diff at 50 000 characters."""
    long_diff = "x" * 60_000
    prompt = build_extraction_prompt(long_diff, "output")

    # Only the first 50 000 chars of the diff should appear
    assert "x" * 50_000 in prompt
    assert "x" * 60_000 not in prompt


def test_build_extraction_prompt_caps_agent_output_length() -> None:
    """build_extraction_prompt caps agent output at 20 000 characters."""
    long_output = "y" * 25_000
    prompt = build_extraction_prompt("diff", long_output)

    assert "y" * 20_000 in prompt
    assert "y" * 25_000 not in prompt


def test_build_extraction_prompt_instructs_no_tools() -> None:
    """build_extraction_prompt instructs the model not to use tools."""
    prompt = build_extraction_prompt("diff", "output")

    assert "Do NOT use any tools" in prompt
    assert "Do NOT write any files" in prompt


# ---------------------------------------------------------------------------
# 5.2 — Response parsing into ProvenanceEntry list
# ---------------------------------------------------------------------------


def test_parse_extraction_response_single_decision() -> None:
    """parse_extraction_response parses a single well-formed decision block."""
    raw = (
        "DECISION: Chose Strategy pattern for validation routing\n"
        "ALTERNATIVES: if/else chain, registry dict\n"
        "RATIONALE: Strategy pattern allows adding new types without modifying existing code.\n"
        "REFERENCES: AC-1, FR-9\n"
    )
    entries = parse_extraction_response(raw, timestamp="2026-01-01T00:00:00Z")

    assert len(entries) == 1
    e = entries[0]
    assert e.decision == "Chose Strategy pattern for validation routing"
    assert "if/else chain" in e.alternatives
    assert "registry dict" in e.alternatives
    assert "Strategy pattern" in e.rationale
    assert "AC-1" in e.ac_references
    assert "FR-9" in e.ac_references
    assert e.timestamp == "2026-01-01T00:00:00Z"


def test_parse_extraction_response_multiple_decisions() -> None:
    """parse_extraction_response parses multiple sequential decision blocks."""
    raw = (
        "DECISION: Added index on user_id\n"
        "ALTERNATIVES: No index, composite index\n"
        "RATIONALE: Sequential scans were O(n).\n"
        "REFERENCES: NFR-3\n\n"
        "DECISION: Extracted helper module\n"
        "ALTERNATIVES: Inline code\n"
        "RATIONALE: Separation of concerns.\n"
        "REFERENCES: None\n"
    )
    entries = parse_extraction_response(raw)

    assert len(entries) == 2
    assert entries[0].decision == "Added index on user_id"
    assert entries[1].decision == "Extracted helper module"
    assert entries[1].ac_references == []


def test_parse_extraction_response_none_alternatives() -> None:
    """parse_extraction_response handles 'None' alternatives as empty list."""
    raw = "DECISION: Simple fix\nALTERNATIVES: None\nRATIONALE: Only one approach was viable.\nREFERENCES: None\n"
    entries = parse_extraction_response(raw)

    assert len(entries) == 1
    assert entries[0].alternatives == []
    assert entries[0].ac_references == []


def test_parse_extraction_response_uses_provided_timestamp() -> None:
    """parse_extraction_response stamps each entry with the given timestamp."""
    raw = "DECISION: Something\nALTERNATIVES: None\nRATIONALE: Because.\nREFERENCES: None\n"
    entries = parse_extraction_response(raw, timestamp="2026-03-18T12:00:00Z")

    assert all(e.timestamp == "2026-03-18T12:00:00Z" for e in entries)


def test_parse_extraction_response_fallback_on_empty_input() -> None:
    """parse_extraction_response returns [] on empty/garbage input."""
    entries = parse_extraction_response("")

    assert entries == []


# ---------------------------------------------------------------------------
# 5.6 — Extraction failure does not break operation
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_extract_agent_decisions_returns_none_on_no_input(
    tmp_path: Path,
) -> None:
    """extract_agent_decisions returns None when both diff and agent output are empty."""
    worktree = tmp_path / "worktree"
    worktree.mkdir()
    checkpoint = tmp_path / "checkpoint"
    checkpoint.mkdir()
    provenance_path = tmp_path / "validation.md"

    # git is a local import inside extract_agent_decisions — patch at source
    mock_diff = AsyncMock(return_value=MagicMock(stdout=""))
    with (
        patch("arcwright_ai.scm.git.git", mock_diff),
        patch(
            "arcwright_ai.output.decisions.read_text_async",
            side_effect=FileNotFoundError,
        ),
    ):
        result = await extract_agent_decisions(
            worktree,
            checkpoint,
            "abc123",
            provenance_path,
            model="claude-test",
            api_key="test-key",
            story_slug="1-1-test",
            project_root=tmp_path,
        )

    assert result is None


@pytest.mark.asyncio
async def test_extract_agent_decisions_returns_none_on_invoke_error(
    tmp_path: Path,
) -> None:
    """extract_agent_decisions returns None when invoke_agent raises an exception."""
    worktree = tmp_path / "worktree"
    worktree.mkdir()
    checkpoint = tmp_path / "checkpoint"
    checkpoint.mkdir()
    agent_output_file = checkpoint / "agent-output.md"
    agent_output_file.write_text("agent output text")
    provenance_path = tmp_path / "validation.md"

    mock_diff = AsyncMock(return_value=MagicMock(stdout="diff line"))
    with (
        patch("arcwright_ai.scm.git.git", mock_diff),
        patch("arcwright_ai.agent.invoker.invoke_agent", side_effect=RuntimeError("SDK crash")),
    ):
        result = await extract_agent_decisions(
            worktree,
            checkpoint,
            "abc123",
            provenance_path,
            model="claude-test",
            api_key="test-key",
            story_slug="1-1-test",
            project_root=tmp_path,
        )

    assert result is None


@pytest.mark.asyncio
async def test_extract_agent_decisions_success(
    tmp_path: Path,
) -> None:
    """extract_agent_decisions writes entries to the provenance file on success."""
    from decimal import Decimal

    import arcwright_ai.agent.invoker as _invoker_mod

    InvocationResult = _invoker_mod.InvocationResult

    worktree = tmp_path / "worktree"
    worktree.mkdir()
    checkpoint = tmp_path / "checkpoint"
    checkpoint.mkdir()
    agent_output_file = checkpoint / "agent-output.md"
    agent_output_file.write_text("agent added Strategy pattern")
    provenance_path = tmp_path / "validation.md"

    fake_response = (
        "DECISION: Used Strategy pattern\nALTERNATIVES: if/else chain\nRATIONALE: Extensibility.\nREFERENCES: AC-1\n"
    )
    fake_result = InvocationResult(
        output_text=fake_response,
        tokens_input=100,
        tokens_output=50,
        total_cost=Decimal("0.001"),
        duration_ms=500,
        session_id="sess-1",
        num_turns=1,
        is_error=False,
    )

    mock_diff = AsyncMock(return_value=MagicMock(stdout="diff --git a/x.py"))
    with (
        patch("arcwright_ai.scm.git.git", mock_diff),
        patch("arcwright_ai.agent.invoker.invoke_agent", return_value=fake_result),
    ):
        result = await extract_agent_decisions(
            worktree,
            checkpoint,
            "abc123",
            provenance_path,
            model="claude-test",
            api_key="test-key",
            story_slug="1-1-test",
            project_root=tmp_path,
        )

    assert result is not None
    assert result.tokens_input == 100
    # Verify the decision was written to the provenance file
    content = provenance_path.read_text()
    assert "## Implementation Decisions" in content
    assert "Used Strategy pattern" in content


@pytest.mark.asyncio
async def test_extract_agent_decisions_returns_none_on_unparseable_response(
    tmp_path: Path,
) -> None:
    """extract_agent_decisions returns None and writes nothing when response is unparseable."""
    from decimal import Decimal

    import arcwright_ai.agent.invoker as _invoker_mod

    InvocationResult = _invoker_mod.InvocationResult

    worktree = tmp_path / "worktree"
    worktree.mkdir()
    checkpoint = tmp_path / "checkpoint"
    checkpoint.mkdir()
    (checkpoint / "agent-output.md").write_text("agent output")
    provenance_path = tmp_path / "validation.md"

    fake_result = InvocationResult(
        output_text="this is not parseable",
        tokens_input=100,
        tokens_output=50,
        total_cost=Decimal("0.001"),
        duration_ms=500,
        session_id="sess-1",
        num_turns=1,
        is_error=False,
    )

    mock_diff = AsyncMock(return_value=MagicMock(stdout="diff --git a/x.py"))
    with (
        patch("arcwright_ai.scm.git.git", mock_diff),
        patch("arcwright_ai.agent.invoker.invoke_agent", return_value=fake_result),
    ):
        result = await extract_agent_decisions(
            worktree,
            checkpoint,
            "abc123",
            provenance_path,
            model="claude-test",
            api_key="test-key",
            story_slug="1-1-test",
            project_root=tmp_path,
        )

    assert result is None
    assert not provenance_path.exists()


@pytest.mark.asyncio
async def test_extract_agent_decisions_includes_all_attempt_outputs_in_prompt(
    tmp_path: Path,
) -> None:
    """extract_agent_decisions includes attempt checkpoint outputs in extraction prompt."""
    from decimal import Decimal

    import arcwright_ai.agent.invoker as _invoker_mod

    InvocationResult = _invoker_mod.InvocationResult

    worktree = tmp_path / "worktree"
    worktree.mkdir()
    checkpoint = tmp_path / "checkpoint"
    checkpoint.mkdir()
    (checkpoint / "agent-output.attempt-1.md").write_text("attempt one output")
    (checkpoint / "agent-output.attempt-2.md").write_text("attempt two output")
    (checkpoint / "agent-output.md").write_text("attempt two output")
    provenance_path = tmp_path / "validation.md"

    fake_result = InvocationResult(
        output_text=(
            "DECISION: Combined retry reasoning\n"
            "ALTERNATIVES: None\n"
            "RATIONALE: Included both attempts.\n"
            "REFERENCES: None\n"
        ),
        tokens_input=100,
        tokens_output=50,
        total_cost=Decimal("0.001"),
        duration_ms=500,
        session_id="sess-1",
        num_turns=1,
        is_error=False,
    )

    mock_diff = AsyncMock(return_value=MagicMock(stdout="diff --git a/x.py"))
    mock_invoke = AsyncMock(return_value=fake_result)
    with (
        patch("arcwright_ai.scm.git.git", mock_diff),
        patch("arcwright_ai.agent.invoker.invoke_agent", mock_invoke),
    ):
        result = await extract_agent_decisions(
            worktree,
            checkpoint,
            "abc123",
            provenance_path,
            model="claude-test",
            api_key="test-key",
            story_slug="1-1-test",
            project_root=tmp_path,
        )

    assert result is not None
    await_call = mock_invoke.await_args
    assert await_call is not None
    prompt_arg = await_call.args[0]
    assert "attempt one output" in prompt_arg
    assert "attempt two output" in prompt_arg
