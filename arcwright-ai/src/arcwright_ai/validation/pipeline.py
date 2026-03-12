"""Validation pipeline — Artifact-specific routing for validation strategies."""

from __future__ import annotations

import logging
from decimal import Decimal
from enum import StrEnum
from typing import TYPE_CHECKING

from arcwright_ai.core.types import ArcwrightModel
from arcwright_ai.validation.v3_reflexion import (
    ReflexionFeedback,
    V3ReflexionResult,
    run_v3_reflexion,
)
from arcwright_ai.validation.v6_invariant import (
    V6ValidationResult,
    run_v6_validation,
)

if TYPE_CHECKING:
    from pathlib import Path

    from arcwright_ai.agent.sandbox import PathValidator

__all__: list[str] = [
    "PipelineOutcome",
    "PipelineResult",
    "run_validation_pipeline",
]

logger = logging.getLogger(__name__)


class PipelineOutcome(StrEnum):
    """Outcome of the validation pipeline routing.

    Used by Story 3.4's validate node to determine the routing
    decision: PASS → success, FAIL_V3 → retry, FAIL_V6 → escalated.

    Attributes:
        PASS: Both V6 and V3 validation passed.
        FAIL_V6: V6 invariant checks failed (immediate, no retry per D2).
        FAIL_V3: V3 reflexion failed (retryable per D2).
    """

    PASS = "pass"
    FAIL_V6 = "fail_v6"
    FAIL_V3 = "fail_v3"


class PipelineResult(ArcwrightModel):
    """Comprehensive result from the validation pipeline.

    Wraps both V6 invariant and V3 reflexion results into a single
    model with a routing outcome signal. Consumed by Story 3.4's
    validate node.

    Attributes:
        passed: True only if both V6 and V3 pass.
        outcome: Pipeline routing signal (PASS, FAIL_V6, FAIL_V3).
        v6_result: V6 invariant validation result (always present).
        v3_result: V3 reflexion result (None if V6 short-circuited).
        feedback: V3 reflexion feedback for retry prompt injection
            (None if V6 short-circuited or V3 passed).
        tokens_used: Total tokens consumed across all validation steps.
        tokens_input: Total input tokens consumed across validation steps.
        tokens_output: Total output tokens consumed across validation steps.
        cost: Total estimated cost across all validation steps.
    """

    passed: bool
    outcome: PipelineOutcome
    v6_result: V6ValidationResult
    v3_result: V3ReflexionResult | None = None
    feedback: ReflexionFeedback | None = None
    tokens_used: int = 0
    tokens_input: int = 0
    tokens_output: int = 0
    cost: Decimal = Decimal("0")


async def run_validation_pipeline(
    agent_output: str,
    story_path: Path,
    project_root: Path,
    *,
    model: str,
    cwd: Path,
    sandbox: PathValidator,
    attempt_number: int = 1,
) -> PipelineResult:
    """Run the full validation pipeline (V6 → V3) for a story's agent output.

    V6 invariant checks run first (cheap, deterministic, zero tokens).
    If V6 fails, V3 is short-circuited and the pipeline returns immediately
    with ``PipelineOutcome.FAIL_V6``. If V6 passes, V3 reflexion validation
    runs and the outcome is determined by V3's result.

    Args:
        agent_output: The raw text output produced by the agent to validate.
        story_path: Absolute path to the story file being validated.
        project_root: Absolute path to the project root directory.
        model: Claude model version string for V3 reflexion (e.g. "claude-opus-4-5").
        cwd: Working directory for the V3 reflexion SDK invocation.
        sandbox: Path validation protocol instance used by V3 reflexion.
        attempt_number: Current attempt/retry number (1-based, default 1).

    Returns:
        A ``PipelineResult`` encoding the routing outcome, sub-results,
        aggregated token usage, and aggregated cost.

    Raises:
        ValidationError: If V6 or V3 raises an unexpected internal error
            (e.g. filesystem crash, SDK crash). Not caught — propagates to caller.
    """
    logger.info(
        "validation.pipeline.start",
        extra={"data": {"story": str(story_path), "attempt_number": attempt_number}},
    )

    # Step 1: Run V6 invariant checks (cheap, deterministic, zero tokens)
    v6_result: V6ValidationResult = await run_v6_validation(agent_output, project_root, story_path)

    logger.info(
        "validation.pipeline.v6_complete",
        extra={
            "data": {
                "passed": v6_result.passed,
                "checks_run": len(v6_result.results),
                "failures": len(v6_result.failures),
            }
        },
    )

    # Step 2: Short-circuit if V6 failed
    if not v6_result.passed:
        logger.info(
            "validation.pipeline.v6_short_circuit",
            extra={
                "data": {
                    "story": str(story_path),
                    "v6_failures": len(v6_result.failures),
                }
            },
        )
        logger.info(
            "validation.pipeline.complete",
            extra={"data": {"outcome": "fail_v6", "tokens_used": 0, "cost": "0"}},
        )
        return PipelineResult(
            passed=False,
            outcome=PipelineOutcome.FAIL_V6,
            v6_result=v6_result,
            v3_result=None,
            feedback=None,
            tokens_used=0,
            tokens_input=0,
            tokens_output=0,
            cost=Decimal("0"),
        )

    # Step 3: Run V3 reflexion (V6 passed — expensive, uses SDK)
    v3_result: V3ReflexionResult = await run_v3_reflexion(
        agent_output,
        story_path,
        project_root,
        model=model,
        cwd=cwd,
        sandbox=sandbox,
        attempt_number=attempt_number,
    )

    logger.info(
        "validation.pipeline.v3_complete",
        extra={
            "data": {
                "passed": v3_result.validation_result.passed,
                "acs_evaluated": len(v3_result.validation_result.ac_results),
                "acs_failed": len(v3_result.feedback.unmet_criteria),
                "tokens_used": v3_result.tokens_used,
            }
        },
    )

    # Step 4: Determine final outcome
    if v3_result.validation_result.passed:
        logger.info(
            "validation.pipeline.complete",
            extra={
                "data": {
                    "outcome": "pass",
                    "tokens_used": v3_result.tokens_used,
                    "cost": str(v3_result.cost),
                }
            },
        )
        return PipelineResult(
            passed=True,
            outcome=PipelineOutcome.PASS,
            v6_result=v6_result,
            v3_result=v3_result,
            feedback=None,
            tokens_used=v3_result.tokens_used,
            tokens_input=v3_result.tokens_input,
            tokens_output=v3_result.tokens_output,
            cost=v3_result.cost,
        )

    # V3 failed
    logger.info(
        "validation.pipeline.complete",
        extra={
            "data": {
                "outcome": "fail_v3",
                "tokens_used": v3_result.tokens_used,
                "cost": str(v3_result.cost),
            }
        },
    )
    return PipelineResult(
        passed=False,
        outcome=PipelineOutcome.FAIL_V3,
        v6_result=v6_result,
        v3_result=v3_result,
        feedback=v3_result.feedback,
        tokens_used=v3_result.tokens_used,
        tokens_input=v3_result.tokens_input,
        tokens_output=v3_result.tokens_output,
        cost=v3_result.cost,
    )
