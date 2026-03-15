"""Tests for core/types.py — Pydantic models and typed str wrappers."""

from __future__ import annotations

from decimal import Decimal

import pytest
from pydantic import ValidationError as PydanticValidationError

from arcwright_ai.core.types import (
    ArcwrightModel,
    ArtifactRef,
    BudgetState,
    ContextBundle,
    EpicId,
    ProvenanceEntry,
    RunId,
    StoryCost,
    StoryId,
    calculate_invocation_cost,
)

# ---------------------------------------------------------------------------
# ArcwrightModel configuration
# ---------------------------------------------------------------------------


class _SampleModel(ArcwrightModel):
    name: str
    value: int = 0


def test_arcwright_model_config_frozen() -> None:
    model = _SampleModel(name="test")
    with pytest.raises(PydanticValidationError):
        model.name = "changed"  # type: ignore[misc]


def test_arcwright_model_config_extra_forbid() -> None:
    with pytest.raises(PydanticValidationError):
        _SampleModel(name="test", unknown_field="oops")  # type: ignore[call-arg]


def test_arcwright_model_config_str_strip_whitespace() -> None:
    model = _SampleModel(name="  hello  ")
    assert model.name == "hello"


# ---------------------------------------------------------------------------
# NewType wrappers
# ---------------------------------------------------------------------------


def test_story_id_is_str_wrapper() -> None:
    sid = StoryId("1-2-user-auth")
    assert isinstance(sid, str)
    assert sid == "1-2-user-auth"


def test_epic_id_is_str_wrapper() -> None:
    eid = EpicId("epic-1")
    assert isinstance(eid, str)
    assert eid == "epic-1"


def test_run_id_is_str_wrapper() -> None:
    rid = RunId("20260302-143052-a7f3")
    assert isinstance(rid, str)
    assert rid == "20260302-143052-a7f3"


# ---------------------------------------------------------------------------
# ArtifactRef
# ---------------------------------------------------------------------------


def test_artifact_ref_core_fields() -> None:
    ref = ArtifactRef(
        story_id=StoryId("1-2"),
        epic_id=EpicId("epic-1"),
        path="docs/arch.md",
    )
    assert ref.story_id == "1-2"
    assert ref.epic_id == "epic-1"
    assert ref.path == "docs/arch.md"


def test_artifact_ref_extension_fields_default_none() -> None:
    ref = ArtifactRef(
        story_id=StoryId("1-2"),
        epic_id=EpicId("epic-1"),
        path="docs/arch.md",
    )
    assert ref.status_gate is None
    assert ref.assignee_lock is None
    assert ref.content_hash is None


def test_artifact_ref_extension_fields_can_be_set() -> None:
    ref = ArtifactRef(
        story_id=StoryId("1-2"),
        epic_id=EpicId("epic-1"),
        path="docs/arch.md",
        status_gate="approved",
        assignee_lock="alice",
        content_hash="abc123",
    )
    assert ref.status_gate == "approved"
    assert ref.assignee_lock == "alice"
    assert ref.content_hash == "abc123"


# ---------------------------------------------------------------------------
# ContextBundle
# ---------------------------------------------------------------------------


def test_context_bundle_required_field() -> None:
    bundle = ContextBundle(story_content="## Story\n")
    assert bundle.story_content == "## Story"


def test_context_bundle_optional_fields_default_empty_string() -> None:
    bundle = ContextBundle(story_content="x")
    assert bundle.architecture_sections == ""
    assert bundle.domain_requirements == ""
    assert bundle.answerer_rules == ""


def test_context_bundle_all_fields() -> None:
    bundle = ContextBundle(
        story_content="story",
        architecture_sections="arch",
        domain_requirements="req",
        answerer_rules="rules",
    )
    assert bundle.architecture_sections == "arch"
    assert bundle.domain_requirements == "req"
    assert bundle.answerer_rules == "rules"


# ---------------------------------------------------------------------------
# BudgetState
# ---------------------------------------------------------------------------


def test_budget_state_default_values() -> None:
    budget = BudgetState()
    assert budget.invocation_count == 0
    assert budget.total_tokens == 0
    assert budget.estimated_cost == Decimal("0")
    assert budget.max_invocations == 0
    assert budget.max_cost == Decimal("0")


def test_budget_state_custom_values() -> None:
    budget = BudgetState(
        invocation_count=3,
        total_tokens=10000,
        estimated_cost=Decimal("0.05"),
        max_invocations=10,
        max_cost=Decimal("1.00"),
    )
    assert budget.invocation_count == 3
    assert budget.total_tokens == 10000
    assert budget.estimated_cost == Decimal("0.05")
    assert budget.max_invocations == 10
    assert budget.max_cost == Decimal("1.00")


def test_budget_state_is_frozen() -> None:
    budget = BudgetState()
    with pytest.raises(PydanticValidationError):
        budget.invocation_count = 5  # type: ignore[misc]


def test_budget_state_new_fields_default_values() -> None:
    budget = BudgetState()
    assert budget.total_tokens_input == 0
    assert budget.total_tokens_output == 0
    assert budget.per_story == {}


def test_budget_state_with_per_story() -> None:
    sc = StoryCost(tokens_input=100, tokens_output=50, cost=Decimal("0.01"), invocations=1)
    budget = BudgetState(per_story={"2-1-state-models": sc})
    assert "2-1-state-models" in budget.per_story
    assert budget.per_story["2-1-state-models"].tokens_input == 100


def test_budget_state_model_copy_with_per_story() -> None:
    """BudgetState.per_story can be updated via model_copy (frozen model pattern)."""
    sc1 = StoryCost(tokens_input=100, tokens_output=50, cost=Decimal("0.01"), invocations=1)
    budget = BudgetState(per_story={"s1": sc1})
    sc2 = StoryCost(tokens_input=200, tokens_output=100, cost=Decimal("0.02"), invocations=1)
    new_budget = budget.model_copy(update={"per_story": {**budget.per_story, "s2": sc2}})
    assert "s1" in new_budget.per_story
    assert "s2" in new_budget.per_story
    assert new_budget.per_story["s2"].tokens_input == 200


# ---------------------------------------------------------------------------
# StoryCost
# ---------------------------------------------------------------------------


def test_story_cost_default_values() -> None:
    sc = StoryCost()
    assert sc.tokens_input == 0
    assert sc.tokens_output == 0
    assert sc.cost == Decimal("0")
    assert sc.invocations == 0


def test_story_cost_custom_values() -> None:
    sc = StoryCost(tokens_input=500, tokens_output=200, cost=Decimal("0.05"), invocations=2)
    assert sc.tokens_input == 500
    assert sc.tokens_output == 200
    assert sc.cost == Decimal("0.05")
    assert sc.invocations == 2


def test_story_cost_is_frozen() -> None:
    sc = StoryCost()
    with pytest.raises(PydanticValidationError):
        sc.tokens_input = 99  # type: ignore[misc]


def test_story_cost_cost_by_role_default_empty() -> None:
    """StoryCost() initialises with an empty cost_by_role dict."""
    sc = StoryCost()
    assert sc.cost_by_role == {}
    assert sc.invocations_by_role == {}
    assert sc.tokens_input_by_role == {}
    assert sc.tokens_output_by_role == {}


def test_story_cost_cost_by_role_with_values() -> None:
    """StoryCost accepts cost_by_role with Decimal values."""
    sc = StoryCost(
        cost_by_role={"generate": Decimal("1.50"), "review": Decimal("0.75")},
        invocations_by_role={"generate": 2, "review": 1},
        tokens_input_by_role={"generate": 1200, "review": 400},
        tokens_output_by_role={"generate": 300, "review": 150},
    )
    assert sc.cost_by_role["generate"] == Decimal("1.50")
    assert sc.cost_by_role["review"] == Decimal("0.75")
    assert sc.invocations_by_role["generate"] == 2
    assert sc.tokens_input_by_role["review"] == 400
    assert sc.tokens_output_by_role["generate"] == 300


def test_story_cost_cost_by_role_backward_compat() -> None:
    """All existing StoryCost() constructions work without cost_by_role."""
    sc = StoryCost(tokens_input=100, tokens_output=50, cost=Decimal("0.01"), invocations=1)
    assert sc.cost_by_role == {}


def test_story_cost_model_copy_updates_cost_by_role() -> None:
    """model_copy(update={...}) correctly updates cost_by_role on frozen StoryCost."""
    sc = StoryCost(cost_by_role={"generate": Decimal("1.00")})
    new_sc = sc.model_copy(update={"cost_by_role": {"generate": Decimal("1.00"), "review": Decimal("0.50")}})
    assert new_sc.cost_by_role["review"] == Decimal("0.50")
    # Original unchanged (frozen)
    assert "review" not in sc.cost_by_role


# ---------------------------------------------------------------------------
# calculate_invocation_cost
# ---------------------------------------------------------------------------


def test_calculate_invocation_cost_basic() -> None:
    from arcwright_ai.core.config import ModelPricing

    pricing = ModelPricing(input_rate=Decimal("15.00"), output_rate=Decimal("75.00"))
    cost = calculate_invocation_cost(1_000_000, 1_000_000, pricing)
    assert cost == Decimal("90.00")


def test_calculate_invocation_cost_small_tokens() -> None:
    from arcwright_ai.core.config import ModelPricing

    pricing = ModelPricing(input_rate=Decimal("15.00"), output_rate=Decimal("75.00"))
    # 500 input, 200 output — matches mock_invoke_result in nodes tests
    cost = calculate_invocation_cost(500, 200, pricing)
    expected = Decimal("500") / Decimal("1000000") * Decimal("15.00") + Decimal("200") / Decimal("1000000") * Decimal(
        "75.00"
    )
    assert cost == expected


def test_calculate_invocation_cost_zero_tokens() -> None:
    from arcwright_ai.core.config import ModelPricing

    pricing = ModelPricing(input_rate=Decimal("15.00"), output_rate=Decimal("75.00"))
    cost = calculate_invocation_cost(0, 0, pricing)
    assert cost == Decimal("0")


def test_calculate_invocation_cost_custom_rates() -> None:
    from arcwright_ai.core.config import ModelPricing

    pricing = ModelPricing(input_rate=Decimal("3.00"), output_rate=Decimal("15.00"))
    cost = calculate_invocation_cost(1_000_000, 500_000, pricing)
    expected = Decimal("3.00") + Decimal("500000") / Decimal("1000000") * Decimal("15.00")
    assert cost == expected


# ---------------------------------------------------------------------------
# ProvenanceEntry
# ---------------------------------------------------------------------------


def test_provenance_entry_required_fields() -> None:
    entry = ProvenanceEntry(
        decision="Use Pydantic",
        rationale="Strong validation and serialization",
        timestamp="2026-03-02T14:30:52Z",
    )
    assert entry.decision == "Use Pydantic"
    assert entry.rationale == "Strong validation and serialization"
    assert entry.timestamp == "2026-03-02T14:30:52Z"


def test_provenance_entry_optional_list_fields_default_empty() -> None:
    entry = ProvenanceEntry(
        decision="Use Pydantic",
        rationale="Strong validation",
        timestamp="2026-03-02T00:00:00Z",
    )
    assert entry.alternatives == []
    assert entry.ac_references == []


def test_provenance_entry_with_list_fields() -> None:
    entry = ProvenanceEntry(
        decision="Use StrEnum",
        alternatives=["IntEnum", "plain string constants"],
        rationale="Direct string comparison",
        ac_references=["AC-2", "AC-3"],
        timestamp="2026-03-02T00:00:00Z",
    )
    assert entry.alternatives == ["IntEnum", "plain string constants"]
    assert entry.ac_references == ["AC-2", "AC-3"]


# ---------------------------------------------------------------------------
# __all__ completeness
# ---------------------------------------------------------------------------


def test_all_symbols_exported() -> None:
    import arcwright_ai.core.types as mod

    expected = {
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
    }
    assert set(mod.__all__) == expected
