"""Unit tests for the validation pipeline (Story 3.3)."""

from __future__ import annotations

from decimal import Decimal
from pathlib import Path
from typing import cast

import pytest

from arcwright_ai.core.exceptions import ValidationError
from arcwright_ai.validation.pipeline import (
    PipelineOutcome,
    PipelineResult,
    run_validation_pipeline,
)
from arcwright_ai.validation.quality_gate import (
    QualityFeedback,
    QualityGateResult,
    ToolResult,
)
from arcwright_ai.validation.v3_reflexion import (
    ACResult,
    ReflexionFeedback,
    V3ReflexionResult,
    ValidationResult,
)
from arcwright_ai.validation.v6_invariant import V6CheckResult, V6ValidationResult

# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------

STORY_PATH = Path("/project/stories/3-3-story.md")
PROJECT_ROOT = Path("/project")


@pytest.fixture
def mock_v6_pass(monkeypatch: pytest.MonkeyPatch) -> V6ValidationResult:
    """Monkeypatch run_v6_validation to return all-pass result."""
    result = V6ValidationResult(
        passed=True,
        results=[
            V6CheckResult(check_name="file_existence", passed=True),
            V6CheckResult(check_name="naming_conventions", passed=True),
            V6CheckResult(check_name="python_syntax", passed=True),
            V6CheckResult(check_name="yaml_validity", passed=True),
        ],
    )

    async def _mock_v6(agent_output: str, project_root: Path, story_path: Path) -> V6ValidationResult:
        return result

    monkeypatch.setattr("arcwright_ai.validation.pipeline.run_v6_validation", _mock_v6)
    return result


@pytest.fixture
def mock_v6_fail(monkeypatch: pytest.MonkeyPatch) -> V6ValidationResult:
    """Monkeypatch run_v6_validation to return failure result."""
    result = V6ValidationResult(
        passed=False,
        results=[
            V6CheckResult(
                check_name="file_existence",
                passed=False,
                failure_detail="Missing: src/foo.py",
            ),
            V6CheckResult(check_name="naming_conventions", passed=True),
        ],
    )

    async def _mock_v6(agent_output: str, project_root: Path, story_path: Path) -> V6ValidationResult:
        return result

    monkeypatch.setattr("arcwright_ai.validation.pipeline.run_v6_validation", _mock_v6)
    return result


@pytest.fixture
def mock_v3_pass(monkeypatch: pytest.MonkeyPatch) -> V3ReflexionResult:
    """Monkeypatch run_v3_reflexion to return all-pass result."""
    v3_result = V3ReflexionResult(
        validation_result=ValidationResult(
            passed=True,
            ac_results=[
                ACResult(ac_id="1", passed=True, rationale="Criterion met"),
            ],
            raw_response="AC-1: PASS\nRationale: Criterion met",
            attempt_number=1,
        ),
        feedback=ReflexionFeedback(passed=True, attempt_number=1),
        tokens_used=300,
        cost=Decimal("0.005"),
    )

    async def _mock_v3(
        agent_output: str,
        story_path: Path,
        project_root: Path,
        *,
        model: str,
        cwd: Path,
        sandbox: object,
        api_key: str,
        attempt_number: int = 1,
    ) -> V3ReflexionResult:
        return v3_result

    monkeypatch.setattr("arcwright_ai.validation.pipeline.run_v3_reflexion", _mock_v3)
    return v3_result


@pytest.fixture
def mock_v3_fail(monkeypatch: pytest.MonkeyPatch) -> V3ReflexionResult:
    """Monkeypatch run_v3_reflexion to return failure result."""
    v3_result = V3ReflexionResult(
        validation_result=ValidationResult(
            passed=False,
            ac_results=[
                ACResult(ac_id="1", passed=True, rationale="Met"),
                ACResult(ac_id="2", passed=False, rationale="Missing implementation"),
            ],
            raw_response="AC-1: PASS\nAC-2: FAIL",
            attempt_number=1,
        ),
        feedback=ReflexionFeedback(
            passed=False,
            unmet_criteria=["2"],
            feedback_per_criterion={"2": "Missing implementation. Suggested Fix: Add X"},
            attempt_number=1,
        ),
        tokens_used=350,
        cost=Decimal("0.006"),
    )

    async def _mock_v3(
        agent_output: str,
        story_path: Path,
        project_root: Path,
        *,
        model: str,
        cwd: Path,
        sandbox: object,
        api_key: str,
        attempt_number: int = 1,
    ) -> V3ReflexionResult:
        return v3_result

    monkeypatch.setattr("arcwright_ai.validation.pipeline.run_v3_reflexion", _mock_v3)
    return v3_result


# Shared dummy sandbox / model for all tests
_SANDBOX = object()
_MODEL = "claude-opus-4-5"
_CWD = Path("/project")


# ---------------------------------------------------------------------------
# Test 4.1 — V6 fail short-circuits V3
# ---------------------------------------------------------------------------


async def test_run_validation_pipeline_v6_fail_short_circuits_v3(
    mock_v6_fail: V6ValidationResult,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """V6 failure must short-circuit V3 — V3 is never called."""

    async def _v3_must_not_be_called(*args: object, **kwargs: object) -> None:
        raise AssertionError("V3 should not be called when V6 fails")

    monkeypatch.setattr("arcwright_ai.validation.pipeline.run_v3_reflexion", _v3_must_not_be_called)

    result = await run_validation_pipeline(
        "agent output",
        STORY_PATH,
        PROJECT_ROOT,
        model=_MODEL,
        cwd=_CWD,
        sandbox=_SANDBOX,  # type: ignore[arg-type]
        api_key="sk-test-not-real",
    )

    assert result.passed is False
    assert result.outcome == PipelineOutcome.FAIL_V6
    assert result.v3_result is None
    assert result.feedback is None
    assert result.tokens_used == 0
    assert result.cost == Decimal("0")


# ---------------------------------------------------------------------------
# Test 4.2 — V6 pass + V3 pass → PASS outcome
# ---------------------------------------------------------------------------


async def test_run_validation_pipeline_v6_pass_v3_pass(
    mock_v6_pass: V6ValidationResult,
    mock_v3_pass: V3ReflexionResult,
) -> None:
    """V6 + V3 both pass → outcome PASS, tokens reflect V3 usage."""
    result = await run_validation_pipeline(
        "agent output",
        STORY_PATH,
        PROJECT_ROOT,
        model=_MODEL,
        cwd=_CWD,
        sandbox=_SANDBOX,  # type: ignore[arg-type]
        api_key="sk-test-not-real",
    )

    assert result.passed is True
    assert result.outcome == PipelineOutcome.PASS
    assert result.v6_result is mock_v6_pass
    assert result.v3_result is mock_v3_pass
    assert result.tokens_used == mock_v3_pass.tokens_used
    assert result.cost == mock_v3_pass.cost
    assert result.feedback is None


# ---------------------------------------------------------------------------
# Test 4.3 — V6 pass + V3 fail → FAIL_V3 outcome
# ---------------------------------------------------------------------------


async def test_run_validation_pipeline_v6_pass_v3_fail(
    mock_v6_pass: V6ValidationResult,
    mock_v3_fail: V3ReflexionResult,
) -> None:
    """V6 passes but V3 fails → outcome FAIL_V3, feedback populated."""
    result = await run_validation_pipeline(
        "agent output",
        STORY_PATH,
        PROJECT_ROOT,
        model=_MODEL,
        cwd=_CWD,
        sandbox=_SANDBOX,  # type: ignore[arg-type]
        api_key="sk-test-not-real",
    )

    assert result.passed is False
    assert result.outcome == PipelineOutcome.FAIL_V3
    assert result.v6_result is mock_v6_pass
    assert result.v3_result is mock_v3_fail
    assert result.feedback is mock_v3_fail.feedback
    assert result.feedback is not None
    assert result.feedback.unmet_criteria == ["2"]
    assert result.tokens_used == mock_v3_fail.tokens_used
    assert result.cost == mock_v3_fail.cost


# ---------------------------------------------------------------------------
# Test 4.4 — PipelineResult contains correct sub-results
# ---------------------------------------------------------------------------


async def test_run_validation_pipeline_result_aggregation(
    mock_v6_pass: V6ValidationResult,
    mock_v3_pass: V3ReflexionResult,
) -> None:
    """PipelineResult exposes V6 and V3 sub-results via .v6_result and .v3_result."""
    result = await run_validation_pipeline(
        "agent output",
        STORY_PATH,
        PROJECT_ROOT,
        model=_MODEL,
        cwd=_CWD,
        sandbox=_SANDBOX,  # type: ignore[arg-type]
        api_key="sk-test-not-real",
    )

    assert result.v6_result is mock_v6_pass
    assert result.v3_result is mock_v3_pass
    assert result.v6_result.passed is True
    assert result.v3_result is not None
    assert result.v3_result.validation_result.passed is True


# ---------------------------------------------------------------------------
# Test 4.5 — PipelineResult serialization round-trip
# ---------------------------------------------------------------------------


async def test_pipeline_result_serialization_round_trip(
    mock_v6_pass: V6ValidationResult,
    mock_v3_pass: V3ReflexionResult,
    mock_v3_fail: V3ReflexionResult,
    mock_v6_fail: V6ValidationResult,
) -> None:
    """PipelineResult.model_dump() + model_validate() round-trip for all 3 outcomes."""

    # PASS
    pass_result = PipelineResult(
        passed=True,
        outcome=PipelineOutcome.PASS,
        v6_result=mock_v6_pass,
        v3_result=mock_v3_pass,
        tokens_used=300,
        cost=Decimal("0.005"),
    )
    restored_pass = PipelineResult.model_validate(pass_result.model_dump(round_trip=True))
    assert restored_pass.passed == pass_result.passed
    assert restored_pass.outcome == pass_result.outcome
    assert restored_pass.tokens_used == pass_result.tokens_used
    assert restored_pass.cost == pass_result.cost

    # FAIL_V6
    fail_v6_result = PipelineResult(
        passed=False,
        outcome=PipelineOutcome.FAIL_V6,
        v6_result=mock_v6_fail,
        tokens_used=0,
        cost=Decimal("0"),
    )
    restored_v6 = PipelineResult.model_validate(fail_v6_result.model_dump(round_trip=True))
    assert restored_v6.passed == fail_v6_result.passed
    assert restored_v6.outcome == fail_v6_result.outcome
    assert restored_v6.v3_result is None

    # FAIL_V3 — include v6_pass so v6_result is valid
    fail_v3_result = PipelineResult(
        passed=False,
        outcome=PipelineOutcome.FAIL_V3,
        v6_result=mock_v6_pass,
        v3_result=mock_v3_fail,
        feedback=mock_v3_fail.feedback,
        tokens_used=350,
        cost=Decimal("0.006"),
    )
    restored_v3 = PipelineResult.model_validate(fail_v3_result.model_dump(round_trip=True))
    assert restored_v3.passed == fail_v3_result.passed
    assert restored_v3.outcome == fail_v3_result.outcome
    assert restored_v3.feedback is not None
    assert restored_v3.feedback.unmet_criteria == ["2"]


# ---------------------------------------------------------------------------
# Test 4.6 — Structured log events emitted correctly
# ---------------------------------------------------------------------------


async def test_run_validation_pipeline_emits_structured_log_events(
    mock_v6_pass: V6ValidationResult,
    mock_v3_pass: V3ReflexionResult,
    mock_v6_fail: V6ValidationResult,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Structured log events are emitted for both V6-short-circuit and full V6+V3 paths."""
    import logging

    def _event_data(records: list[logging.LogRecord], event: str) -> list[dict[str, object]]:
        """Extract structured ``data`` payloads for a given event name."""
        payloads: list[dict[str, object]] = []
        for record in records:
            if record.message != event:
                continue
            data = getattr(record, "data", None)
            if isinstance(data, dict):
                payloads.append(cast("dict[str, object]", data))
        return payloads

    # --- Path 1: V6 short-circuit (mock_v6_fail is already patched into pipeline) ---
    async def _v3_noop(*args: object, **kwargs: object) -> None:
        raise AssertionError("V3 should not be called")

    monkeypatch.setattr("arcwright_ai.validation.pipeline.run_v3_reflexion", _v3_noop)

    with caplog.at_level(logging.INFO, logger="arcwright_ai.validation.pipeline"):
        await run_validation_pipeline(
            "agent output",
            STORY_PATH,
            PROJECT_ROOT,
            model=_MODEL,
            cwd=_CWD,
            sandbox=_SANDBOX,  # type: ignore[arg-type]
            api_key="sk-test-not-real",
        )

    log_messages_v6_short = [r.message for r in caplog.records]
    assert "validation.pipeline.start" in log_messages_v6_short
    assert "validation.pipeline.v6_complete" in log_messages_v6_short
    assert "validation.pipeline.v6_short_circuit" in log_messages_v6_short
    assert "validation.pipeline.complete" in log_messages_v6_short

    start_payload = _event_data(caplog.records, "validation.pipeline.start")[-1]
    assert start_payload["story"] == str(STORY_PATH)
    assert start_payload["attempt_number"] == 1

    v6_complete_payload = _event_data(caplog.records, "validation.pipeline.v6_complete")[-1]
    assert v6_complete_payload["passed"] is False
    assert v6_complete_payload["checks_run"] == len(mock_v6_fail.results)
    assert v6_complete_payload["failures"] == len(mock_v6_fail.failures)

    short_payload = _event_data(caplog.records, "validation.pipeline.v6_short_circuit")[-1]
    assert short_payload["story"] == str(STORY_PATH)
    assert short_payload["v6_failures"] == len(mock_v6_fail.failures)

    complete_short_payload = _event_data(caplog.records, "validation.pipeline.complete")[-1]
    assert complete_short_payload["outcome"] == "fail_v6"
    assert complete_short_payload["tokens_used"] == 0
    assert complete_short_payload["cost"] == "0"

    caplog.clear()

    # --- Path 2: Full V6+V3 pass path ---
    async def _v6_pass_fn(agent_output: str, project_root: Path, story_path: Path) -> V6ValidationResult:
        return mock_v6_pass

    async def _v3_pass_fn(
        agent_output: str,
        story_path: Path,
        project_root: Path,
        *,
        model: str,
        cwd: Path,
        sandbox: object,
        api_key: str,
        attempt_number: int = 1,
    ) -> V3ReflexionResult:
        return mock_v3_pass

    monkeypatch.setattr("arcwright_ai.validation.pipeline.run_v6_validation", _v6_pass_fn)
    monkeypatch.setattr("arcwright_ai.validation.pipeline.run_v3_reflexion", _v3_pass_fn)

    with caplog.at_level(logging.INFO, logger="arcwright_ai.validation.pipeline"):
        await run_validation_pipeline(
            "agent output",
            STORY_PATH,
            PROJECT_ROOT,
            model=_MODEL,
            cwd=_CWD,
            sandbox=_SANDBOX,  # type: ignore[arg-type]
            api_key="sk-test-not-real",
        )

    log_messages_full = [r.message for r in caplog.records]
    assert "validation.pipeline.start" in log_messages_full
    assert "validation.pipeline.v6_complete" in log_messages_full
    assert "validation.pipeline.v3_complete" in log_messages_full
    assert "validation.pipeline.complete" in log_messages_full
    # Short-circuit event must NOT be present on pass path
    assert "validation.pipeline.v6_short_circuit" not in log_messages_full

    start_full_payload = _event_data(caplog.records, "validation.pipeline.start")[-1]
    assert start_full_payload["story"] == str(STORY_PATH)
    assert start_full_payload["attempt_number"] == 1

    v6_full_payload = _event_data(caplog.records, "validation.pipeline.v6_complete")[-1]
    assert v6_full_payload["passed"] is True
    assert v6_full_payload["checks_run"] == len(mock_v6_pass.results)
    assert v6_full_payload["failures"] == 0

    v3_payload = _event_data(caplog.records, "validation.pipeline.v3_complete")[-1]
    assert v3_payload["passed"] is True
    assert v3_payload["acs_evaluated"] == len(mock_v3_pass.validation_result.ac_results)
    assert v3_payload["acs_failed"] == len(mock_v3_pass.feedback.unmet_criteria)
    assert v3_payload["tokens_used"] == mock_v3_pass.tokens_used

    complete_full_payload = _event_data(caplog.records, "validation.pipeline.complete")[-1]
    assert complete_full_payload["outcome"] == "pass"
    assert complete_full_payload["tokens_used"] == mock_v3_pass.tokens_used
    assert complete_full_payload["cost"] == str(mock_v3_pass.cost)


# ---------------------------------------------------------------------------
# Test 4.7 — ValidationError from V3 propagates uncaught
# ---------------------------------------------------------------------------


async def test_run_validation_pipeline_v3_validation_error_propagates(
    mock_v6_pass: V6ValidationResult,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """ValidationError raised by V3 must propagate uncaught through the pipeline."""

    async def _v3_raises(*args: object, **kwargs: object) -> None:
        raise ValidationError("SDK crash during reflexion")

    monkeypatch.setattr("arcwright_ai.validation.pipeline.run_v3_reflexion", _v3_raises)

    with pytest.raises(ValidationError, match="SDK crash during reflexion"):
        await run_validation_pipeline(
            "agent output",
            STORY_PATH,
            PROJECT_ROOT,
            model=_MODEL,
            cwd=_CWD,
            sandbox=_SANDBOX,  # type: ignore[arg-type]
            api_key="sk-test-not-real",
        )


# ---------------------------------------------------------------------------
# Test 4.8 — PipelineOutcome enum string values
# ---------------------------------------------------------------------------


def test_pipeline_outcome_enum_values() -> None:
    """PipelineOutcome enum values match expected strings for routing."""
    assert PipelineOutcome.PASS == "pass"
    assert PipelineOutcome.FAIL_V6 == "fail_v6"
    assert PipelineOutcome.FAIL_V3 == "fail_v3"


# ---------------------------------------------------------------------------
# Test 4.9 — feedback is None on V3 pass
# ---------------------------------------------------------------------------


async def test_run_validation_pipeline_feedback_is_none_on_v3_pass(
    mock_v6_pass: V6ValidationResult,
    mock_v3_pass: V3ReflexionResult,
) -> None:
    """When V3 passes, PipelineResult.feedback is None (not empty ReflexionFeedback)."""
    result = await run_validation_pipeline(
        "agent output",
        STORY_PATH,
        PROJECT_ROOT,
        model=_MODEL,
        cwd=_CWD,
        sandbox=_SANDBOX,  # type: ignore[arg-type]
        api_key="sk-test-not-real",
    )

    assert result.passed is True
    assert result.feedback is None


# ---------------------------------------------------------------------------
# Test 4.10 — cost and tokens_used are zero on V6 short-circuit
# ---------------------------------------------------------------------------


async def test_run_validation_pipeline_cost_is_zero_on_v6_short_circuit(
    mock_v6_fail: V6ValidationResult,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """cost is Decimal('0') and tokens_used is 0 when V6 fails and V3 is not invoked."""

    async def _v3_must_not_be_called(*args: object, **kwargs: object) -> None:
        raise AssertionError("V3 must not be called")

    monkeypatch.setattr("arcwright_ai.validation.pipeline.run_v3_reflexion", _v3_must_not_be_called)

    result = await run_validation_pipeline(
        "agent output",
        STORY_PATH,
        PROJECT_ROOT,
        model=_MODEL,
        cwd=_CWD,
        sandbox=_SANDBOX,  # type: ignore[arg-type]
        api_key="sk-test-not-real",
    )

    assert result.tokens_used == 0
    assert result.cost == Decimal("0")


# ---------------------------------------------------------------------------
# Test 6.6/6.7 — Quality Gate integration with the pipeline
# ---------------------------------------------------------------------------

WORKTREE_PATH = Path("/project/.arcwright-ai/worktrees/10-12-story")


@pytest.fixture
def mock_quality_gate_pass(monkeypatch: pytest.MonkeyPatch) -> QualityGateResult:
    """Monkeypatch run_quality_gate to return a passing result."""
    feedback = QualityFeedback(
        passed=True,
        auto_fix_summary=[],
        tool_results=[
            ToolResult(tool_name="ruff check", passed=True, exit_code=0),
            ToolResult(tool_name="mypy --strict", passed=True, exit_code=0),
            ToolResult(tool_name="pytest", passed=True, exit_code=0),
        ],
    )
    qg_result = QualityGateResult(passed=True, feedback=feedback)

    async def _mock_qg(project_root: Path, worktree_path: Path, *, timeout: int = 300) -> QualityGateResult:
        return qg_result

    monkeypatch.setattr("arcwright_ai.validation.pipeline.run_quality_gate", _mock_qg)
    return qg_result


@pytest.fixture
def mock_quality_gate_fail(monkeypatch: pytest.MonkeyPatch) -> QualityGateResult:
    """Monkeypatch run_quality_gate to return a failing result."""
    feedback = QualityFeedback(
        passed=False,
        auto_fix_summary=[],
        tool_results=[
            ToolResult(tool_name="ruff check", passed=True, exit_code=0),
            ToolResult(
                tool_name="mypy --strict",
                passed=False,
                exit_code=1,
                stderr="error: Missing return statement  [return]",
            ),
            ToolResult(tool_name="pytest", passed=True, exit_code=0),
        ],
    )
    qg_result = QualityGateResult(passed=False, feedback=feedback)

    async def _mock_qg(project_root: Path, worktree_path: Path, *, timeout: int = 300) -> QualityGateResult:
        return qg_result

    monkeypatch.setattr("arcwright_ai.validation.pipeline.run_quality_gate", _mock_qg)
    return qg_result


async def test_pipeline_quality_gate_pass_returns_pass(
    mock_v6_pass: V6ValidationResult,
    mock_v3_pass: V3ReflexionResult,
    mock_quality_gate_pass: QualityGateResult,
) -> None:
    """V6 pass → V3 pass → QG pass ⟹ PipelineOutcome.PASS with quality_feedback populated."""
    result = await run_validation_pipeline(
        "agent output",
        STORY_PATH,
        PROJECT_ROOT,
        model=_MODEL,
        cwd=_CWD,
        sandbox=_SANDBOX,  # type: ignore[arg-type]
        api_key="sk-test-not-real",
        worktree_path=WORKTREE_PATH,
    )

    assert result.outcome == PipelineOutcome.PASS
    assert result.quality_feedback is not None
    assert result.quality_feedback.passed is True
    assert len(result.quality_feedback.tool_results) == 3
    assert all(r.passed for r in result.quality_feedback.tool_results)


async def test_pipeline_quality_gate_fail_returns_fail_quality(
    mock_v6_pass: V6ValidationResult,
    mock_v3_pass: V3ReflexionResult,
    mock_quality_gate_fail: QualityGateResult,
) -> None:
    """V6 pass → V3 pass → QG fail ⟹ PipelineOutcome.FAIL_QUALITY with quality_feedback."""
    result = await run_validation_pipeline(
        "agent output",
        STORY_PATH,
        PROJECT_ROOT,
        model=_MODEL,
        cwd=_CWD,
        sandbox=_SANDBOX,  # type: ignore[arg-type]
        api_key="sk-test-not-real",
        worktree_path=WORKTREE_PATH,
    )

    assert result.outcome == PipelineOutcome.FAIL_QUALITY
    assert result.quality_feedback is not None
    assert result.quality_feedback.passed is False
    failing = [r for r in result.quality_feedback.tool_results if not r.passed]
    assert len(failing) == 1
    assert failing[0].tool_name == "mypy --strict"


async def test_pipeline_no_worktree_path_skips_quality_gate(
    mock_v6_pass: V6ValidationResult,
    mock_v3_pass: V3ReflexionResult,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """When worktree_path is None, quality gate is not invoked and result is PASS."""

    async def _qg_must_not_be_called(*args: object, **kwargs: object) -> None:
        raise AssertionError("Quality gate must not be called when worktree_path is None")

    monkeypatch.setattr("arcwright_ai.validation.pipeline.run_quality_gate", _qg_must_not_be_called)

    result = await run_validation_pipeline(
        "agent output",
        STORY_PATH,
        PROJECT_ROOT,
        model=_MODEL,
        cwd=_CWD,
        sandbox=_SANDBOX,  # type: ignore[arg-type]
        api_key="sk-test-not-real",
        worktree_path=None,
    )

    assert result.outcome == PipelineOutcome.PASS
    assert result.quality_feedback is None
