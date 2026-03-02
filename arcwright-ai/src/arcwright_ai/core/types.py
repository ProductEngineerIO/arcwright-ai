"""Core types — Shared Pydantic models and type definitions."""

from __future__ import annotations

from datetime import datetime  # noqa: F401  # re-exported for downstream use
from decimal import Decimal
from typing import NewType

from pydantic import BaseModel, ConfigDict, Field

__all__: list[str] = [
    "ArcwrightModel",
    "ArtifactRef",
    "BudgetState",
    "ContextBundle",
    "EpicId",
    "ProvenanceEntry",
    "RunId",
    "StoryId",
]

# ---------------------------------------------------------------------------
# Typed ID wrappers
# ---------------------------------------------------------------------------

StoryId = NewType("StoryId", str)
"""Typed wrapper for a story identifier, e.g. '1-2-user-auth'."""

EpicId = NewType("EpicId", str)
"""Typed wrapper for an epic identifier, e.g. 'epic-1'."""

RunId = NewType("RunId", str)
"""Typed wrapper for a run identifier, e.g. '20260302-143052-a7f3'."""


# ---------------------------------------------------------------------------
# Base model
# ---------------------------------------------------------------------------


class ArcwrightModel(BaseModel):
    """Base class for all Arcwright AI Pydantic models.

    Configured with frozen=True (immutable after construction),
    extra="forbid" (reject unknown fields), and str_strip_whitespace=True
    (strip leading/trailing whitespace from string fields).
    """

    model_config = ConfigDict(
        frozen=True,
        extra="forbid",
        str_strip_whitespace=True,
    )


# ---------------------------------------------------------------------------
# Domain models
# ---------------------------------------------------------------------------


class ArtifactRef(ArcwrightModel):
    """Reference to a BMAD planning artifact.

    Core fields implement dependency layers 1-2 (phase ordering + existence
    checks).  Optional extension fields prepare for layers 3-5 (Growth phase).

    Attributes:
        story_id: The story this artifact belongs to.
        epic_id: The epic this artifact belongs to.
        path: Relative path to the artifact file.
        status_gate: Optional layer-3 status gate value (Growth phase).
        assignee_lock: Optional layer-4 assignee lock identifier (Growth phase).
        content_hash: Optional layer-5 hash for staleness detection (Growth phase).
    """

    story_id: StoryId
    epic_id: EpicId
    path: str  # relative path, not Path — Pydantic serialisation
    # Layer 3-5 extension fields — None in MVP, reserved for Growth
    status_gate: str | None = None
    assignee_lock: str | None = None
    content_hash: str | None = None


class ContextBundle(ArcwrightModel):
    """Assembled context payload for agent invocation.

    Attributes:
        story_content: Full markdown content of the story file.
        architecture_sections: Relevant architecture doc sections.
        domain_requirements: Matching FR/NFR requirements.
        answerer_rules: Static BMAD rules resolved by the answerer.
    """

    story_content: str
    architecture_sections: str = ""
    domain_requirements: str = ""
    answerer_rules: str = ""


class BudgetState(ArcwrightModel):
    """Tracks token and cost consumption for a story execution.

    Note: BudgetState is frozen per ArcwrightModel convention.  When budget
    values need updating, create a new instance via model_copy(update={...}).
    Uses ``Decimal`` for cost fields to ensure exact decimal arithmetic and
    avoid IEEE 754 floating-point rounding errors in financial calculations.

    Attributes:
        invocation_count: Number of SDK invocations made.
        total_tokens: Cumulative tokens consumed (input + output).
        estimated_cost: Running cost estimate in USD (exact Decimal).
        max_invocations: Maximum SDK invocations allowed (0 = unlimited).
        max_cost: Maximum cost allowed in USD (Decimal; 0 = unlimited).
    """

    invocation_count: int = 0
    total_tokens: int = 0
    estimated_cost: Decimal = Decimal("0")
    max_invocations: int = 0
    max_cost: Decimal = Decimal("0")


class ProvenanceEntry(ArcwrightModel):
    """A single logged implementation decision during story execution.

    Attributes:
        decision: Description of the decision made.
        alternatives: List of alternatives that were considered.
        rationale: Why this decision was made.
        ac_references: AC IDs or architecture refs informing the decision.
        timestamp: ISO 8601 timestamp when the decision was logged.
    """

    decision: str
    alternatives: list[str] = Field(default_factory=list)
    rationale: str
    ac_references: list[str] = Field(default_factory=list)
    timestamp: str  # ISO 8601 format — avoid datetime for frozen Pydantic serialisation
