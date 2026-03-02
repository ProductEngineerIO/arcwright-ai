"""Engine state — Pydantic state models for LangGraph orchestration."""

from __future__ import annotations

from pathlib import Path  # noqa: TC003
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from arcwright_ai.core.config import RunConfig  # noqa: TC001
from arcwright_ai.core.lifecycle import TaskState
from arcwright_ai.core.types import BudgetState, ContextBundle, EpicId, RunId, StoryId

__all__: list[str] = [
    "ProjectState",
    "StoryState",
]


class StoryState(BaseModel):
    """Mutable state for a single story execution in the LangGraph StateGraph.

    This is the primary state object threaded through all graph nodes.
    Mutable (frozen=False) because LangGraph updates state during traversal.

    Attributes:
        story_id: Identifier for this story (e.g., '2-1-state-models').
        epic_id: Parent epic identifier (e.g., 'epic-2').
        run_id: Unique run identifier (e.g., '20260302-143052-a7f3').
        story_path: Path to the story markdown file.
        project_root: Root directory of the project.
        status: Current lifecycle state (queued → ... → success/escalated).
        context_bundle: Assembled context from preflight (None until preflight runs).
        agent_output: Raw agent response text (None until agent runs).
        validation_result: Validation results (None until validation runs; typed as
            dict for now — will become ValidationResult model in Epic 3).
        retry_count: Number of retry attempts so far.
        budget: Token/cost consumption tracker.
        config: Run-level configuration reference.
    """

    model_config = ConfigDict(frozen=False, extra="forbid")

    story_id: StoryId
    epic_id: EpicId
    run_id: RunId
    story_path: Path
    project_root: Path
    status: TaskState = TaskState.QUEUED
    context_bundle: ContextBundle | None = None
    agent_output: str | None = None
    validation_result: dict[str, Any] | None = None
    retry_count: int = 0
    budget: BudgetState = Field(default_factory=BudgetState)
    config: RunConfig


class ProjectState(BaseModel):
    """Mutable state for an epic-level execution containing multiple stories.

    Attributes:
        epic_id: Epic being dispatched (e.g., 'epic-2').
        run_id: Unique run identifier.
        stories: Ordered list of StoryState objects in this epic.
        config: Shared run configuration.
        status: Overall epic execution status.
        completed_stories: Count of stories that reached SUCCESS.
        current_story_index: Zero-based index of the story currently executing.
    """

    model_config = ConfigDict(frozen=False, extra="forbid")

    epic_id: EpicId
    run_id: RunId
    stories: list[StoryState] = Field(default_factory=list)
    config: RunConfig
    status: TaskState = TaskState.QUEUED
    completed_stories: int = 0
    current_story_index: int = 0
