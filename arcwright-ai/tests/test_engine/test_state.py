"""Tests for engine/state.py — StoryState and ProjectState Pydantic models."""

from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError as PydanticValidationError

from arcwright_ai.core.config import ApiConfig, RunConfig
from arcwright_ai.core.lifecycle import TaskState
from arcwright_ai.core.types import EpicId, RunId, StoryId
from arcwright_ai.engine.state import ProjectState, StoryState


def make_run_config() -> RunConfig:
    """Build a minimal RunConfig suitable for tests."""
    return RunConfig(api=ApiConfig(claude_api_key="test-key-not-real"))


def make_story_state(**kwargs: object) -> StoryState:
    """Build a minimal StoryState for tests, accepting field overrides."""
    defaults: dict[str, object] = {
        "story_id": StoryId("2-1-state-models"),
        "epic_id": EpicId("epic-2"),
        "run_id": RunId("20260302-143052-a7f3"),
        "story_path": Path("_spec/implementation-artifacts/2-1-state-models.md"),
        "project_root": Path("/project"),
        "config": make_run_config(),
    }
    defaults.update(kwargs)
    return StoryState(**defaults)  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# StoryState tests
# ---------------------------------------------------------------------------


def test_story_state_creation_with_required_fields() -> None:
    state = make_story_state()
    assert state.story_id == "2-1-state-models"
    assert state.epic_id == "epic-2"
    assert state.run_id == "20260302-143052-a7f3"
    assert state.status == TaskState.QUEUED
    assert state.context_bundle is None
    assert state.agent_output is None
    assert state.validation_result is None
    assert state.retry_count == 0


def test_story_state_is_mutable() -> None:
    state = make_story_state()
    state.status = TaskState.RUNNING
    assert state.status == TaskState.RUNNING


def test_story_state_forbids_extra_fields() -> None:
    with pytest.raises(PydanticValidationError):
        make_story_state(extra_field="x")  # type: ignore[call-arg]


def test_story_state_model_copy_updates() -> None:
    state = make_story_state()
    updated = state.model_copy(update={"status": TaskState.RUNNING})
    assert updated.status == TaskState.RUNNING
    assert state.status == TaskState.QUEUED  # original unchanged


def test_story_state_budget_default_factory() -> None:
    state = make_story_state()
    assert state.budget.invocation_count == 0
    # Ensure two instances get distinct BudgetState objects
    state2 = make_story_state()
    assert state.budget is not state2.budget


# ---------------------------------------------------------------------------
# ProjectState tests
# ---------------------------------------------------------------------------


def test_project_state_creation_with_required_fields() -> None:
    config = make_run_config()
    ps = ProjectState(
        epic_id=EpicId("epic-2"),
        run_id=RunId("20260302-143052-a7f3"),
        config=config,
    )
    assert ps.epic_id == "epic-2"
    assert ps.run_id == "20260302-143052-a7f3"
    assert ps.status == TaskState.QUEUED
    assert ps.completed_stories == 0
    assert ps.current_story_index == 0


def test_project_state_stories_default_empty_list() -> None:
    config = make_run_config()
    ps = ProjectState(
        epic_id=EpicId("epic-2"),
        run_id=RunId("20260302-143052-a7f3"),
        config=config,
    )
    assert ps.stories == []


def test_project_state_forbids_extra_fields() -> None:
    config = make_run_config()
    with pytest.raises(PydanticValidationError):
        ProjectState(  # type: ignore[call-arg]
            epic_id=EpicId("epic-2"),
            run_id=RunId("20260302-143052-a7f3"),
            config=config,
            unexpected="oops",
        )
