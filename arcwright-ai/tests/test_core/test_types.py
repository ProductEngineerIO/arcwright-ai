"""Tests for core/types.py — Pydantic models and typed str wrappers."""

from __future__ import annotations

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
    StoryId,
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
    assert budget.estimated_cost_usd == 0.0
    assert budget.token_ceiling == 0
    assert budget.cost_ceiling_usd == 0.0


def test_budget_state_custom_values() -> None:
    budget = BudgetState(
        invocation_count=3,
        total_tokens=10000,
        estimated_cost_usd=0.05,
        token_ceiling=50000,
        cost_ceiling_usd=1.00,
    )
    assert budget.invocation_count == 3
    assert budget.total_tokens == 10000
    assert budget.estimated_cost_usd == pytest.approx(0.05)
    assert budget.token_ceiling == 50000
    assert budget.cost_ceiling_usd == pytest.approx(1.00)


def test_budget_state_is_frozen() -> None:
    budget = BudgetState()
    with pytest.raises(PydanticValidationError):
        budget.invocation_count = 5  # type: ignore[misc]


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
        "StoryId",
    }
    assert set(mod.__all__) == expected
