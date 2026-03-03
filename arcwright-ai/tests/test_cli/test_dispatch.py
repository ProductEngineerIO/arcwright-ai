"""Tests for CLI dispatch command — story/epic finder, run ID, JSONL handler, integration.

Uses typer.testing.CliRunner for command invocation.
All filesystem tests use tmp_path for full isolation.
"""

from __future__ import annotations

import json
import logging
import re
from decimal import Decimal
from typing import TYPE_CHECKING

import pytest
from typer.testing import CliRunner

from arcwright_ai.agent.invoker import InvocationResult
from arcwright_ai.cli.app import app
from arcwright_ai.cli.dispatch import (
    _find_epic_stories,
    _find_story_file,
    _generate_run_id,
    _JsonlFileHandler,
)
from arcwright_ai.core.config import ApiConfig, RunConfig
from arcwright_ai.core.types import EpicId, StoryId

if TYPE_CHECKING:
    from pathlib import Path

runner = CliRunner()

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_RUN_ID_PATTERN = re.compile(r"^\d{8}-\d{6}-[0-9a-f]{4}$")


def _make_test_project(tmp_path: Path, epic_num: str = "2", story_num: str = "1") -> Path:
    """Scaffold a minimal project with BMAD artifacts and one story.

    Returns:
        Path to the created story file.
    """
    planning = tmp_path / "_spec" / "planning-artifacts"
    planning.mkdir(parents=True)
    (planning / "prd.md").write_text("# PRD\n\n## FR1\nTest requirement", encoding="utf-8")
    (planning / "architecture.md").write_text("# Architecture\n\n### Decision 1\nTest decision", encoding="utf-8")

    impl = tmp_path / "_spec" / "implementation-artifacts"
    impl.mkdir(parents=True)
    story_file = impl / f"{epic_num}-{story_num}-story-slug.md"
    story_file.write_text(
        f"# Story {epic_num}.{story_num}\n\n## Dev Notes\n\nFR1, Decision 1\n",
        encoding="utf-8",
    )
    return story_file


# ---------------------------------------------------------------------------
# Task 7.1 — _find_story_file parses story spec formats
# ---------------------------------------------------------------------------


def test_dispatch_story_parses_dot_format(tmp_path: Path) -> None:
    """_find_story_file resolves '2.7' → epic_num=2, story_num=7."""
    impl = tmp_path / "_spec" / "implementation-artifacts"
    impl.mkdir(parents=True)
    story_file = impl / "2-7-agent-dispatch-node.md"
    story_file.write_text("# Story 2.7\n", encoding="utf-8")

    found_path, story_id, epic_id = _find_story_file("2.7", impl)
    assert found_path == story_file
    assert story_id == StoryId("2-7-agent-dispatch-node")
    assert epic_id == EpicId("epic-2")


def test_dispatch_story_parses_hyphen_format(tmp_path: Path) -> None:
    """_find_story_file resolves '2-7' → same result as '2.7'."""
    impl = tmp_path / "_spec" / "implementation-artifacts"
    impl.mkdir(parents=True)
    story_file = impl / "2-7-agent-dispatch-node.md"
    story_file.write_text("# Story 2.7\n", encoding="utf-8")

    found_path, story_id, epic_id = _find_story_file("2-7", impl)
    assert found_path == story_file
    assert story_id == StoryId("2-7-agent-dispatch-node")
    assert epic_id == EpicId("epic-2")


# ---------------------------------------------------------------------------
# Task 7.2 — _find_story_file raises on missing story
# ---------------------------------------------------------------------------


def test_dispatch_story_raises_on_missing_story(tmp_path: Path) -> None:
    """_find_story_file raises ProjectError when no matching file exists."""
    from arcwright_ai.core.exceptions import ProjectError

    impl = tmp_path / "_spec" / "implementation-artifacts"
    impl.mkdir(parents=True)

    with pytest.raises(ProjectError, match="No story file found"):
        _find_story_file("9.9", impl)


# ---------------------------------------------------------------------------
# Task 7.3 — _find_epic_stories returns sorted list
# ---------------------------------------------------------------------------


def test_find_epic_stories_returns_sorted_list(tmp_path: Path) -> None:
    """_find_epic_stories returns stories sorted by story number, no retrospectives."""
    impl = tmp_path / "_spec" / "implementation-artifacts"
    impl.mkdir(parents=True)
    (impl / "2-3-context-answerer.md").write_text("# Story 2.3\n", encoding="utf-8")
    (impl / "2-1-state-models.md").write_text("# Story 2.1\n", encoding="utf-8")
    (impl / "2-5-agent-invoker.md").write_text("# Story 2.5\n", encoding="utf-8")
    (impl / "epic-2-retrospective.md").write_text("# Retro\n", encoding="utf-8")

    stories = _find_epic_stories("2", impl)

    assert len(stories) == 3
    story_ids = [str(sid) for _, sid, _ in stories]
    assert story_ids == [
        "2-1-state-models",
        "2-3-context-answerer",
        "2-5-agent-invoker",
    ]


def test_find_epic_stories_accepts_epic_prefix_format(tmp_path: Path) -> None:
    """_find_epic_stories handles 'epic-2' as well as '2'."""
    impl = tmp_path / "_spec" / "implementation-artifacts"
    impl.mkdir(parents=True)
    (impl / "2-1-state-models.md").write_text("# Story 2.1\n", encoding="utf-8")

    stories_plain = _find_epic_stories("2", impl)
    stories_prefix = _find_epic_stories("epic-2", impl)

    assert [str(sid) for _, sid, _ in stories_plain] == [str(sid) for _, sid, _ in stories_prefix]


def test_find_epic_stories_raises_on_empty_epic(tmp_path: Path) -> None:
    """_find_epic_stories raises ProjectError when epic has no stories."""
    from arcwright_ai.core.exceptions import ProjectError

    impl = tmp_path / "_spec" / "implementation-artifacts"
    impl.mkdir(parents=True)

    with pytest.raises(ProjectError, match="No story files found"):
        _find_epic_stories("99", impl)


# ---------------------------------------------------------------------------
# Task 7.4 — _generate_run_id format
# ---------------------------------------------------------------------------


def test_generate_run_id_format() -> None:
    """_generate_run_id returns YYYYMMDD-HHMMSS-<4hex> format."""
    run_id = _generate_run_id()
    assert _RUN_ID_PATTERN.match(str(run_id)), f"Unexpected format: {run_id!r}"


def test_generate_run_id_is_unique() -> None:
    """Consecutive run IDs are different."""
    assert _generate_run_id() != _generate_run_id()


# ---------------------------------------------------------------------------
# Task 7.5 — _JsonlFileHandler writes correct JSON Lines format
# ---------------------------------------------------------------------------


def test_jsonl_handler_writes_correct_format(tmp_path: Path) -> None:
    """_JsonlFileHandler emits valid JSON Lines with D8 envelope fields."""
    log_file = tmp_path / "test.jsonl"
    handler = _JsonlFileHandler(log_file)
    handler.setLevel(logging.INFO)

    test_logger = logging.getLogger("arcwright_ai.test_jsonl")
    test_logger.addHandler(handler)
    test_logger.setLevel(logging.INFO)
    try:
        test_logger.info("test.event", extra={"data": {"key": "value"}})
    finally:
        test_logger.removeHandler(handler)
        handler.close()

    lines = log_file.read_text(encoding="utf-8").strip().split("\n")
    assert len(lines) == 1

    entry = json.loads(lines[0])
    assert entry["event"] == "test.event"
    assert entry["level"] == "info"
    assert entry["data"] == {"key": "value"}
    assert "ts" in entry


def test_jsonl_handler_handles_missing_data_field(tmp_path: Path) -> None:
    """_JsonlFileHandler writes empty dict for data when extra.data is absent."""
    log_file = tmp_path / "no_data.jsonl"
    handler = _JsonlFileHandler(log_file)
    handler.setLevel(logging.INFO)

    test_logger = logging.getLogger("arcwright_ai.test_no_data")
    test_logger.addHandler(handler)
    test_logger.setLevel(logging.INFO)
    try:
        test_logger.info("plain.event")
    finally:
        test_logger.removeHandler(handler)
        handler.close()

    entry = json.loads(log_file.read_text(encoding="utf-8").strip())
    assert entry["data"] == {}


# ---------------------------------------------------------------------------
# Task 7.6 — Integration test: full CLI → engine → agent pipeline
# ---------------------------------------------------------------------------


def test_dispatch_story_end_to_end_with_mock_sdk(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """CLI dispatch --story with MockSDK: exit 0, checkpoint written, JSONL events present."""
    # Set up project structure
    _make_test_project(tmp_path, epic_num="2", story_num="1")

    # Monkeypatch working directory so _discover_project_root finds the project
    monkeypatch.chdir(tmp_path)

    # Monkeypatch load_config to avoid real config file
    test_config = RunConfig(api=ApiConfig(claude_api_key="test-key-ci"))
    monkeypatch.setattr("arcwright_ai.cli.dispatch.load_config", lambda *args, **kwargs: test_config)

    # Monkeypatch invoke_agent in engine/nodes.py to avoid real SDK
    async def _mock_invoke(*args: object, **kwargs: object) -> InvocationResult:
        logging.getLogger("arcwright_ai").info(
            "agent.response",
            extra={
                "data": {
                    "tokens_input": 300,
                    "tokens_output": 150,
                    "cost_usd": "0.03",
                    "session_id": "integration-test-session",
                }
            },
        )
        return InvocationResult(
            output_text="Mock agent output for integration test",
            tokens_input=300,
            tokens_output=150,
            total_cost=Decimal("0.03"),
            duration_ms=500,
            session_id="integration-test-session",
            num_turns=2,
            is_error=False,
        )

    monkeypatch.setattr("arcwright_ai.engine.nodes.invoke_agent", _mock_invoke)

    result = runner.invoke(app, ["dispatch", "--story", "2.1"], catch_exceptions=False)

    # Verify exit code
    assert result.exit_code == 0, f"Unexpected exit code {result.exit_code}:\n{result.output}"

    # Verify agent output checkpoint written
    agent_outputs = list(tmp_path.glob(".arcwright-ai/runs/*/stories/*/agent-output.md"))
    assert len(agent_outputs) == 1, "Expected exactly one agent-output.md checkpoint"
    assert "Mock agent output for integration test" in agent_outputs[0].read_text(encoding="utf-8")

    # Verify JSONL log events written
    log_files = list(tmp_path.glob(".arcwright-ai/runs/*/log.jsonl"))
    assert len(log_files) == 1, "Expected exactly one log.jsonl"
    lines = [ln for ln in log_files[0].read_text(encoding="utf-8").strip().split("\n") if ln]
    entries = [json.loads(line) for line in lines]
    events_by_name = {entry["event"] for entry in entries}
    assert "run.start" in events_by_name
    assert "story.start" in events_by_name
    assert "context.resolve" in events_by_name
    assert "agent.dispatch" in events_by_name
    assert "agent.response" in events_by_name

    # Budget evidence from invocation response event
    response_entries = [entry for entry in entries if entry["event"] == "agent.response"]
    assert len(response_entries) >= 1
    response_data = response_entries[-1].get("data", {})
    assert int(response_data.get("tokens_input", 0)) > 0
    assert int(response_data.get("tokens_output", 0)) > 0


# ---------------------------------------------------------------------------
# Task 7.7 — Neither --story nor --epic provided → error
# ---------------------------------------------------------------------------


def test_dispatch_requires_story_or_epic_option() -> None:
    """dispatch without --story or --epic exits with code 1."""
    result = runner.invoke(app, ["dispatch"])
    assert result.exit_code == 1


# ---------------------------------------------------------------------------
# Task 7.8 — Both --story and --epic provided → error
# ---------------------------------------------------------------------------


def test_dispatch_rejects_both_story_and_epic() -> None:
    """dispatch with both --story and --epic exits with code 1."""
    result = runner.invoke(app, ["dispatch", "--story", "2.1", "--epic", "2"])
    assert result.exit_code == 1
