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
    "StoryCost",
    "StoryId",
    "calculate_invocation_cost",
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


class StoryCost(ArcwrightModel):
    """Per-story cost breakdown for a single story within a run.

    Tracks token consumption and cost for all invocations (first-pass +
    retries) of a single story.  Frozen per ``ArcwrightModel`` convention;
    accumulate via ``model_copy(update={...})``.

    Attributes:
        tokens_input: Total input tokens consumed for this story.
        tokens_output: Total output tokens consumed for this story.
        cost: Estimated cost in USD (exact Decimal).
        invocations: Number of SDK invocations for this story.
    """

    tokens_input: int = 0
    tokens_output: int = 0
    cost: Decimal = Decimal("0")
    invocations: int = 0


class BudgetState(ArcwrightModel):
    """Tracks token and cost consumption for a run.

    Note: BudgetState is frozen per ArcwrightModel convention.  When budget
    values need updating, create a new instance via model_copy(update={...}).
    Uses ``Decimal`` for cost fields to ensure exact decimal arithmetic and
    avoid IEEE 754 floating-point rounding errors in financial calculations.

    Attributes:
        invocation_count: Total number of SDK invocations across all stories.
        total_tokens: Cumulative tokens consumed (input + output).
        total_tokens_input: Cumulative input tokens consumed.
        total_tokens_output: Cumulative output tokens consumed.
        estimated_cost: Running cost estimate in USD (exact Decimal).
        max_invocations: Maximum SDK invocations allowed (0 = unlimited).
        max_cost: Maximum cost allowed in USD (Decimal; 0 = unlimited).
        per_story: Per-story cost breakdown mapping story slug to StoryCost.
    """

    invocation_count: int = 0
    total_tokens: int = 0
    total_tokens_input: int = 0
    total_tokens_output: int = 0
    estimated_cost: Decimal = Decimal("0")
    max_invocations: int = 0
    max_cost: Decimal = Decimal("0")
    per_story: dict[str, StoryCost] = Field(default_factory=dict)


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


# ---------------------------------------------------------------------------
# Cost calculation
# ---------------------------------------------------------------------------

# TYPE_CHECKING import to avoid circular dependency at runtime.
# ModelPricing is only needed for the type signature; at runtime,
# duck-typing on .input_rate / .output_rate is sufficient.
from typing import TYPE_CHECKING  # noqa: E402

if TYPE_CHECKING:
    from arcwright_ai.core.config import ModelPricing


def calculate_invocation_cost(
    tokens_input: int,
    tokens_output: int,
    pricing: ModelPricing,
) -> Decimal:
    """Calculate the cost of a single SDK invocation using per-model pricing.

    Uses exact ``Decimal`` arithmetic to avoid IEEE 754 rounding errors.
    Pricing rates are expressed as USD per 1 million tokens.

    Args:
        tokens_input: Number of input tokens consumed.
        tokens_output: Number of output tokens consumed.
        pricing: ``ModelPricing`` instance with ``input_rate`` and
            ``output_rate`` (cost per 1M tokens).

    Returns:
        Estimated cost in USD as a ``Decimal``.
    """
    million = Decimal("1000000")
    return Decimal(tokens_input) / million * pricing.input_rate + Decimal(tokens_output) / million * pricing.output_rate
