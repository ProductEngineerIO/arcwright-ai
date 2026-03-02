"""Tests for engine/graph.py — LangGraph StateGraph construction and invocation."""

from __future__ import annotations

from pathlib import Path

import pytest
from langgraph.graph.state import CompiledStateGraph

from arcwright_ai.core.config import ApiConfig, RunConfig
from arcwright_ai.core.lifecycle import TaskState
from arcwright_ai.core.types import EpicId, RunId, StoryId
from arcwright_ai.engine.graph import build_story_graph
from arcwright_ai.engine.state import StoryState


def make_run_config() -> RunConfig:
    """Build a minimal RunConfig suitable for tests."""
    return RunConfig(api=ApiConfig(claude_api_key="test-key-not-real"))


def make_initial_state() -> StoryState:
    """Build a minimal initial StoryState with QUEUED status."""
    return StoryState(
        story_id=StoryId("2-1-state-models"),
        epic_id=EpicId("epic-2"),
        run_id=RunId("20260302-143052-a7f3"),
        story_path=Path("_spec/2-1.md"),
        project_root=Path("/project"),
        config=make_run_config(),
    )


# ---------------------------------------------------------------------------
# Graph construction tests
# ---------------------------------------------------------------------------


def test_build_story_graph_returns_compiled_graph() -> None:
    graph = build_story_graph()
    assert isinstance(graph, CompiledStateGraph)


def test_graph_contains_all_expected_nodes() -> None:
    graph = build_story_graph()
    node_names = set(graph.nodes.keys())
    expected = {"preflight", "budget_check", "agent_dispatch", "validate", "commit"}
    assert expected.issubset(node_names)


# ---------------------------------------------------------------------------
# Graph invocation tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_graph_success_path_end_to_end() -> None:
    graph = build_story_graph()
    initial_state = make_initial_state()
    result = await graph.ainvoke(initial_state)
    # LangGraph may return a dict or a state object depending on config
    final_status = result.get("status") if isinstance(result, dict) else result.status
    assert final_status == TaskState.SUCCESS


@pytest.mark.asyncio
async def test_graph_invocation_no_errors() -> None:
    graph = build_story_graph()
    initial_state = make_initial_state()
    # Should not raise
    await graph.ainvoke(initial_state)
