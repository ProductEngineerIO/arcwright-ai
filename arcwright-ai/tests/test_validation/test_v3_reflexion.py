"""Unit tests for arcwright_ai.validation.v3_reflexion — V3 LLM self-evaluation."""

from __future__ import annotations

import logging
from decimal import Decimal
from typing import TYPE_CHECKING

import pytest
from pydantic import ValidationError as PydanticValidationError

from arcwright_ai.core.exceptions import AgentError, ValidationError
from arcwright_ai.validation.v3_reflexion import (
    ACResult,
    ReflexionFeedback,
    ValidationResult,
    _build_reflexion_prompt,
    _extract_acceptance_criteria,
    _parse_reflexion_response,
    run_v3_reflexion,
)

if TYPE_CHECKING:
    from pathlib import Path


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_ALL_PASS_RESPONSE = (
    "AC-1: PASS\n"
    "Rationale: The module was created correctly with all required fields.\n\n"
    "AC-2: PASS\n"
    "Rationale: The invocation uses the correct parameters.\n"
)

_SINGLE_FAIL_RESPONSE = (
    "AC-1: PASS\n"
    "Rationale: Criterion one is satisfied.\n\n"
    "AC-2: FAIL\n"
    "Rationale: Missing the output field.\n"
    "Suggested Fix: Add output field to the model.\n"
)

_MULTI_FAIL_RESPONSE = (
    "AC-1: FAIL\n"
    "Rationale: Module not found.\n"
    "Suggested Fix: Create the module.\n\n"
    "AC-2: FAIL\n"
    "Rationale: Wrong return type.\n"
    "Suggested Fix: Update return annotation.\n"
)

_GIBBERISH_RESPONSE = "This is not a valid reflexion response at all. No verdicts here."


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def story_with_bdd_acs(tmp_path: Path) -> Path:
    """Create a story file with BDD-style acceptance criteria.

    Args:
        tmp_path: Pytest-provided temporary directory.

    Returns:
        Path to the created story markdown file.
    """
    story = tmp_path / "story.md"
    story.write_text(
        "# Story 3.2: Test Story\n\n"
        "## Acceptance Criteria (BDD)\n\n"
        "1. **Given** a project directory **When** init runs **Then** .arcwright-ai/ is created.\n\n"
        "2. **Given** an initialized project **When** validate-setup runs **Then** all checks pass.\n\n"
        "## Tasks / Subtasks\n\n"
        "- [ ] Task 1\n",
        encoding="utf-8",
    )
    return story


@pytest.fixture
def story_with_numbered_acs(tmp_path: Path) -> Path:
    """Create a story file with simple numbered acceptance criteria.

    Args:
        tmp_path: Pytest-provided temporary directory.

    Returns:
        Path to the created story markdown file.
    """
    story = tmp_path / "story.md"
    story.write_text(
        "# Story 1.1: Setup\n\n"
        "## Acceptance Criteria\n\n"
        "1. The module exports all required symbols.\n\n"
        "2. All tests pass with zero violations.\n\n"
        "## Tasks\n\n"
        "- [ ] Task 1\n",
        encoding="utf-8",
    )
    return story


@pytest.fixture
def story_without_acs(tmp_path: Path) -> Path:
    """Create a story file with no acceptance criteria section.

    Args:
        tmp_path: Pytest-provided temporary directory.

    Returns:
        Path to the created story file.
    """
    story = tmp_path / "story.md"
    story.write_text(
        "# Story X.X: No ACs\n\n## Story\n\nAs a developer I want X.\n\n## Tasks\n\n- [ ] Task 1\n",
        encoding="utf-8",
    )
    return story


@pytest.fixture
def mock_sandbox() -> object:
    """Provide a no-op sandbox validator for testing.

    Returns:
        A callable sandbox that allows all paths.
    """

    def _sandbox(path: object, cwd: object, tool_name: object) -> None:
        pass  # Allow all paths in tests

    return _sandbox


@pytest.fixture
def mock_reflexion_sdk_all_pass(monkeypatch: pytest.MonkeyPatch) -> None:
    """Monkeypatch the SDK to return an all-PASS reflexion response.

    Args:
        monkeypatch: Pytest monkeypatch fixture.
    """
    from tests.fixtures.mock_sdk import MockSDKClient

    mock = MockSDKClient(
        output_text=_ALL_PASS_RESPONSE,
        tokens_input=200,
        tokens_output=100,
        total_cost_usd=0.005,
    )
    monkeypatch.setattr("claude_code_sdk.query", mock.query)


@pytest.fixture
def mock_reflexion_sdk_single_fail(monkeypatch: pytest.MonkeyPatch) -> None:
    """Monkeypatch the SDK to return a single-AC-fail reflexion response.

    Args:
        monkeypatch: Pytest monkeypatch fixture.
    """
    from tests.fixtures.mock_sdk import MockSDKClient

    mock = MockSDKClient(
        output_text=_SINGLE_FAIL_RESPONSE,
        tokens_input=180,
        tokens_output=90,
        total_cost_usd=0.004,
    )
    monkeypatch.setattr("claude_code_sdk.query", mock.query)


@pytest.fixture
def mock_reflexion_sdk_multi_fail(monkeypatch: pytest.MonkeyPatch) -> None:
    """Monkeypatch the SDK to return multiple-AC-fail reflexion response.

    Args:
        monkeypatch: Pytest monkeypatch fixture.
    """
    from tests.fixtures.mock_sdk import MockSDKClient

    mock = MockSDKClient(
        output_text=_MULTI_FAIL_RESPONSE,
        tokens_input=160,
        tokens_output=80,
        total_cost_usd=0.003,
    )
    monkeypatch.setattr("claude_code_sdk.query", mock.query)


@pytest.fixture
def mock_reflexion_sdk_gibberish(monkeypatch: pytest.MonkeyPatch) -> None:
    """Monkeypatch the SDK to return an unparseable gibberish response.

    Args:
        monkeypatch: Pytest monkeypatch fixture.
    """
    from tests.fixtures.mock_sdk import MockSDKClient

    mock = MockSDKClient(
        output_text=_GIBBERISH_RESPONSE,
        tokens_input=100,
        tokens_output=50,
        total_cost_usd=0.002,
    )
    monkeypatch.setattr("claude_code_sdk.query", mock.query)


@pytest.fixture
def mock_reflexion_sdk_error(monkeypatch: pytest.MonkeyPatch) -> None:
    """Monkeypatch the SDK to raise AgentError.

    Args:
        monkeypatch: Pytest monkeypatch fixture.
    """
    from tests.fixtures.mock_sdk import MockSDKClient

    mock = MockSDKClient(
        output_text="",
        error=AgentError,
        error_message="Simulated SDK crash",
    )
    monkeypatch.setattr("claude_code_sdk.query", mock.query)


@pytest.fixture
def mock_reflexion_sdk_token_tracking(monkeypatch: pytest.MonkeyPatch) -> None:
    """Monkeypatch the SDK with known token/cost values for tracking tests.

    Args:
        monkeypatch: Pytest monkeypatch fixture.
    """
    from tests.fixtures.mock_sdk import MockSDKClient

    mock = MockSDKClient(
        output_text=_ALL_PASS_RESPONSE,
        tokens_input=300,
        tokens_output=150,
        total_cost_usd=0.0075,
    )
    monkeypatch.setattr("claude_code_sdk.query", mock.query)


# ---------------------------------------------------------------------------
# Tests: run_v3_reflexion — integration scenarios
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_run_v3_reflexion_all_pass(
    story_with_bdd_acs: Path,
    mock_reflexion_sdk_all_pass: None,
    mock_sandbox: object,
    tmp_path: Path,
) -> None:
    """Given mock SDK returns all-PASS, run_v3_reflexion reports fully passing result.

    Args:
        story_with_bdd_acs: Story file fixture with two BDD criteria.
        mock_reflexion_sdk_all_pass: Monkeypatch for all-pass SDK response.
        mock_sandbox: No-op sandbox validator.
        tmp_path: Temporary directory for cwd.
    """
    result = await run_v3_reflexion(
        agent_output="Full implementation output here.",
        story_path=story_with_bdd_acs,
        project_root=tmp_path,
        model="claude-test",
        cwd=tmp_path,
        sandbox=mock_sandbox,  # type: ignore[arg-type]
    )

    assert result.validation_result.passed is True
    assert result.feedback.passed is True
    assert result.feedback.unmet_criteria == []
    assert len(result.validation_result.ac_results) == 2
    assert all(r.passed for r in result.validation_result.ac_results)


@pytest.mark.asyncio
async def test_run_v3_reflexion_single_ac_fail(
    story_with_bdd_acs: Path,
    mock_reflexion_sdk_single_fail: None,
    mock_sandbox: object,
    tmp_path: Path,
) -> None:
    """Given mock SDK returns one AC fail, result reports single failure correctly.

    Args:
        story_with_bdd_acs: Story file fixture with two BDD criteria.
        mock_reflexion_sdk_single_fail: Monkeypatch for single-fail SDK response.
        mock_sandbox: No-op sandbox validator.
        tmp_path: Temporary directory for cwd.
    """
    result = await run_v3_reflexion(
        agent_output="Partial implementation.",
        story_path=story_with_bdd_acs,
        project_root=tmp_path,
        model="claude-test",
        cwd=tmp_path,
        sandbox=mock_sandbox,  # type: ignore[arg-type]
    )

    assert result.validation_result.passed is False
    assert result.feedback.passed is False
    assert "2" in result.feedback.unmet_criteria
    assert "2" in result.feedback.feedback_per_criterion
    assert "1" not in result.feedback.unmet_criteria


@pytest.mark.asyncio
async def test_run_v3_reflexion_multiple_ac_fail(
    story_with_bdd_acs: Path,
    mock_reflexion_sdk_multi_fail: None,
    mock_sandbox: object,
    tmp_path: Path,
) -> None:
    """Given mock SDK returns multiple AC fails, all failing ACs are reported.

    Args:
        story_with_bdd_acs: Story file fixture with two BDD criteria.
        mock_reflexion_sdk_multi_fail: Monkeypatch for multi-fail SDK response.
        mock_sandbox: No-op sandbox validator.
        tmp_path: Temporary directory for cwd.
    """
    result = await run_v3_reflexion(
        agent_output="Incomplete implementation.",
        story_path=story_with_bdd_acs,
        project_root=tmp_path,
        model="claude-test",
        cwd=tmp_path,
        sandbox=mock_sandbox,  # type: ignore[arg-type]
    )

    assert result.validation_result.passed is False
    assert set(result.feedback.unmet_criteria) == {"1", "2"}
    assert "1" in result.feedback.feedback_per_criterion
    assert "2" in result.feedback.feedback_per_criterion


@pytest.mark.asyncio
async def test_run_v3_reflexion_malformed_response(
    story_with_bdd_acs: Path,
    mock_reflexion_sdk_gibberish: None,
    mock_sandbox: object,
    tmp_path: Path,
) -> None:
    """Given mock SDK returns unparseable gibberish, all ACs treated as FAIL.

    Args:
        story_with_bdd_acs: Story file fixture with two BDD criteria.
        mock_reflexion_sdk_gibberish: Monkeypatch for gibberish SDK response.
        mock_sandbox: No-op sandbox validator.
        tmp_path: Temporary directory for cwd.
    """
    result = await run_v3_reflexion(
        agent_output="Some output.",
        story_path=story_with_bdd_acs,
        project_root=tmp_path,
        model="claude-test",
        cwd=tmp_path,
        sandbox=mock_sandbox,  # type: ignore[arg-type]
    )

    assert result.validation_result.passed is False
    assert len(result.validation_result.ac_results) == 2
    assert all(not r.passed for r in result.validation_result.ac_results)
    assert all(r.rationale == "Reflexion did not evaluate this criterion" for r in result.validation_result.ac_results)


@pytest.mark.asyncio
async def test_run_v3_reflexion_sdk_error(
    story_with_bdd_acs: Path,
    mock_reflexion_sdk_error: None,
    mock_sandbox: object,
    tmp_path: Path,
) -> None:
    """Given mock SDK raises AgentError, run_v3_reflexion wraps it as ValidationError.

    Args:
        story_with_bdd_acs: Story file fixture.
        mock_reflexion_sdk_error: Monkeypatch for SDK error.
        mock_sandbox: No-op sandbox validator.
        tmp_path: Temporary directory for cwd.
    """
    with pytest.raises(ValidationError) as exc_info:
        await run_v3_reflexion(
            agent_output="Some output.",
            story_path=story_with_bdd_acs,
            project_root=tmp_path,
            model="claude-test",
            cwd=tmp_path,
            sandbox=mock_sandbox,  # type: ignore[arg-type]
        )

    assert "Simulated SDK crash" in str(exc_info.value)
    assert exc_info.value.details is not None
    assert "original_error" in exc_info.value.details


@pytest.mark.asyncio
async def test_run_v3_reflexion_tracks_tokens_and_cost(
    story_with_bdd_acs: Path,
    mock_reflexion_sdk_token_tracking: None,
    mock_sandbox: object,
    tmp_path: Path,
) -> None:
    """Given mock SDK with known token/cost values, V3ReflexionResult captures them.

    Args:
        story_with_bdd_acs: Story file fixture.
        mock_reflexion_sdk_token_tracking: Monkeypatch for token tracking.
        mock_sandbox: No-op sandbox validator.
        tmp_path: Temporary directory for cwd.
    """
    result = await run_v3_reflexion(
        agent_output="Implementation output.",
        story_path=story_with_bdd_acs,
        project_root=tmp_path,
        model="claude-test",
        cwd=tmp_path,
        sandbox=mock_sandbox,  # type: ignore[arg-type]
    )

    # tokens_input=300, tokens_output=150 → tokens_used=450
    assert result.tokens_used == 450
    # total_cost_usd=0.0075
    assert result.cost == Decimal("0.0075")


@pytest.mark.asyncio
async def test_run_v3_reflexion_no_acceptance_criteria(
    story_without_acs: Path,
    mock_sandbox: object,
    tmp_path: Path,
) -> None:
    """Given story file has no AC section, run_v3_reflexion returns passing result.

    Args:
        story_without_acs: Story file fixture with no AC section.
        mock_sandbox: No-op sandbox validator.
        tmp_path: Temporary directory for cwd.
    """
    result = await run_v3_reflexion(
        agent_output="Some output.",
        story_path=story_without_acs,
        project_root=tmp_path,
        model="claude-test",
        cwd=tmp_path,
        sandbox=mock_sandbox,  # type: ignore[arg-type]
    )

    assert result.validation_result.passed is True
    assert result.validation_result.ac_results == []
    assert result.feedback.passed is True
    assert result.feedback.unmet_criteria == []
    assert result.tokens_used == 0
    assert result.cost == Decimal("0")


# ---------------------------------------------------------------------------
# Tests: _extract_acceptance_criteria
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_extract_acceptance_criteria_bdd_format(
    story_with_bdd_acs: Path,
) -> None:
    """BDD format story correctly extracts all criteria with proper IDs.

    Args:
        story_with_bdd_acs: Story file with two BDD-formatted criteria.
    """
    criteria = await _extract_acceptance_criteria(story_with_bdd_acs)

    assert len(criteria) == 2
    assert criteria[0][0] == "1"
    assert "Given" in criteria[0][1]
    assert criteria[1][0] == "2"
    assert "validate-setup" in criteria[1][1]


@pytest.mark.asyncio
async def test_extract_acceptance_criteria_numbered_format(
    story_with_numbered_acs: Path,
) -> None:
    """Simple numbered list story correctly extracts all criteria.

    Args:
        story_with_numbered_acs: Story file with simple numbered criteria.
    """
    criteria = await _extract_acceptance_criteria(story_with_numbered_acs)

    assert len(criteria) == 2
    assert criteria[0][0] == "1"
    assert "module exports" in criteria[0][1]
    assert criteria[1][0] == "2"
    assert "zero violations" in criteria[1][1]


# ---------------------------------------------------------------------------
# Tests: _parse_reflexion_response
# ---------------------------------------------------------------------------


def test_parse_reflexion_response_complete() -> None:
    """Full PASS/FAIL response with rationale and suggested fix parses correctly.

    Verifies that all fields are extracted: verdict, rationale, and fix.
    """
    response = (
        "AC-1: PASS\n"
        "Rationale: All requirements met.\n\n"
        "AC-2: FAIL\n"
        "Rationale: Output field missing.\n"
        "Suggested Fix: Add `output: str` field.\n"
    )
    ac_results, feedback = _parse_reflexion_response(response, ["1", "2"])

    assert len(ac_results) == 2
    assert ac_results[0].ac_id == "1"
    assert ac_results[0].passed is True
    assert "requirements met" in ac_results[0].rationale

    assert ac_results[1].ac_id == "2"
    assert ac_results[1].passed is False
    assert "Output field missing" in ac_results[1].rationale

    assert "2" in feedback
    assert "Add" in feedback["2"]


def test_parse_reflexion_response_partial_match() -> None:
    """Response with some ACs missing marks missing ones as FAIL with default rationale.

    Verifies that ACs not present in the response get the default failure rationale.
    """
    response = "AC-1: PASS\nRationale: Good.\n"

    ac_results, feedback = _parse_reflexion_response(response, ["1", "2", "3"])

    assert len(ac_results) == 3
    assert ac_results[0].passed is True

    missing = [r for r in ac_results if r.ac_id in ("2", "3")]
    assert all(not r.passed for r in missing)
    assert all(r.rationale == "Reflexion did not evaluate this criterion" for r in missing)
    assert "2" in feedback
    assert "3" in feedback


def test_parse_reflexion_response_missing_rationale_uses_default() -> None:
    """If an AC verdict is present but rationale is missing, parser applies default rationale."""
    response = "AC-1: FAIL\nSuggested Fix: Add missing validation.\n"

    ac_results, feedback = _parse_reflexion_response(response, ["1"])

    assert len(ac_results) == 1
    assert ac_results[0].passed is False
    assert ac_results[0].rationale == "Reflexion did not provide rationale for this criterion"
    assert "1" in feedback


# ---------------------------------------------------------------------------
# Tests: _build_reflexion_prompt
# ---------------------------------------------------------------------------


def test_build_reflexion_prompt_includes_all_acs() -> None:
    """Prompt includes all provided ACs and agent output in expected structure.

    Verifies that every AC appears in the prompt and the agent output is included.
    """
    criteria = [("1", "Given X When Y Then Z."), ("2", "Given A When B Then C.")]
    agent_output = "def my_function(): pass"

    prompt = _build_reflexion_prompt(criteria, agent_output)

    assert "1. Given X When Y Then Z." in prompt
    assert "2. Given A When B Then C." in prompt
    assert agent_output in prompt
    assert "AC-{id}: PASS" in prompt
    assert "AC-{id}: FAIL" in prompt
    assert "Rationale:" in prompt
    assert "Suggested Fix:" in prompt


# ---------------------------------------------------------------------------
# Tests: Data model contract and serialization
# ---------------------------------------------------------------------------


def test_validation_result_is_serializable() -> None:
    """model_dump() + model_validate() round-trip works for all V3 models.

    Verifies that V3 models support full Pydantic serialization round-trips.
    """
    ac = ACResult(ac_id="1", passed=True, rationale="Met.")
    vr = ValidationResult(
        passed=True,
        ac_results=[ac],
        raw_response="raw",
        attempt_number=1,
    )

    dumped = vr.model_dump()
    restored = ValidationResult.model_validate(dumped)

    assert restored.passed is True
    assert len(restored.ac_results) == 1
    assert restored.ac_results[0].ac_id == "1"
    assert restored.raw_response == "raw"


def test_reflexion_feedback_contract() -> None:
    """ReflexionFeedback has exactly the fields Story 3.4 expects.

    Verifies the contract: passed, unmet_criteria, feedback_per_criterion,
    attempt_number are all present and correctly typed.
    """
    feedback = ReflexionFeedback(
        passed=False,
        unmet_criteria=["2", "3"],
        feedback_per_criterion={"2": "Missing field.", "3": "Wrong type."},
        attempt_number=2,
    )

    assert feedback.passed is False
    assert feedback.unmet_criteria == ["2", "3"]
    assert feedback.feedback_per_criterion["2"] == "Missing field."
    assert feedback.attempt_number == 2

    # Ensure it's frozen (immutable)
    with pytest.raises(PydanticValidationError):
        feedback.passed = True  # type: ignore[misc]


# ---------------------------------------------------------------------------
# Tests: Structured log events
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_run_v3_reflexion_emits_structured_log_events(
    story_with_bdd_acs: Path,
    mock_reflexion_sdk_all_pass: None,
    mock_sandbox: object,
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """run_v3_reflexion emits validation.v3.start and validation.v3.complete log events.

    Args:
        story_with_bdd_acs: Story file fixture.
        mock_reflexion_sdk_all_pass: Monkeypatch for all-pass SDK response.
        mock_sandbox: No-op sandbox validator.
        tmp_path: Temporary directory for cwd.
        caplog: Pytest log capture fixture.
    """
    with caplog.at_level(logging.INFO, logger="arcwright_ai.validation.v3_reflexion"):
        await run_v3_reflexion(
            agent_output="Output here.",
            story_path=story_with_bdd_acs,
            project_root=tmp_path,
            model="claude-test",
            cwd=tmp_path,
            sandbox=mock_sandbox,  # type: ignore[arg-type]
        )

    messages = [r.message for r in caplog.records]
    assert any("validation.v3.start" in m for m in messages)
    assert any("validation.v3.complete" in m for m in messages)

    start_events = [r for r in caplog.records if r.message == "validation.v3.start"]
    assert start_events
    start_data = getattr(start_events[0], "data", {})
    assert start_data.get("acs_count") == 2
