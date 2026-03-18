"""V3 reflexion validation — LLM-based self-evaluation for story outputs."""

from __future__ import annotations

import logging
import re
from decimal import Decimal
from typing import TYPE_CHECKING

from pydantic import Field

from arcwright_ai.core.exceptions import AgentError, ValidationError
from arcwright_ai.core.io import read_text_async
from arcwright_ai.core.types import ArcwrightModel

if TYPE_CHECKING:
    from pathlib import Path

    from arcwright_ai.agent.sandbox import PathValidator

__all__: list[str] = [
    "ACResult",
    "ReflexionFeedback",
    "V3ReflexionResult",
    "ValidationResult",
    "run_v3_reflexion",
]

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Compiled module-level regex patterns
# ---------------------------------------------------------------------------

_AC_SECTION_PATTERN: re.Pattern[str] = re.compile(
    r"##\s+Acceptance Criteria[^\n]*\n(.*?)(?=\n##\s|\Z)",
    re.DOTALL | re.IGNORECASE,
)
_NUMBERED_AC_PATTERN: re.Pattern[str] = re.compile(
    r"^(\d+)\.\s+(.+?)(?=^\d+\.\s|\Z)",
    re.MULTILINE | re.DOTALL,
)
_AC_VERDICT_PATTERN: re.Pattern[str] = re.compile(
    r"AC-(\S+):\s*(PASS|FAIL)",
    re.IGNORECASE,
)
_AC_RATIONALE_PATTERN: re.Pattern[str] = re.compile(
    r"Rationale:\s*(.+?)(?=\n(?:AC-|Suggested Fix:|$)|\Z)",
    re.DOTALL | re.IGNORECASE,
)
_AC_FIX_PATTERN: re.Pattern[str] = re.compile(
    r"Suggested Fix:\s*(.+?)(?=\n(?:AC-|\Z)|\Z)",
    re.DOTALL | re.IGNORECASE,
)

# ---------------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------------


class ACResult(ArcwrightModel):
    """Result of evaluating a single acceptance criterion.

    Attributes:
        ac_id: Identifier for the acceptance criterion (e.g., "AC-1", "1").
        passed: Whether the criterion was met.
        rationale: Explanation of why the criterion passed or failed.
    """

    ac_id: str
    passed: bool
    rationale: str


class ValidationResult(ArcwrightModel):
    """Complete result of V3 reflexion validation for a story.

    Attributes:
        passed: True only if ALL acceptance criteria pass.
        ac_results: Per-AC evaluation results.
        raw_response: Full reflexion output text for provenance.
        attempt_number: Which retry attempt this represents (1-based).
    """

    passed: bool
    ac_results: list[ACResult] = Field(default_factory=list)
    raw_response: str = ""
    attempt_number: int = 1


class ReflexionFeedback(ArcwrightModel):
    """Structured feedback from V3 reflexion for retry prompt injection.

    This is the contract consumed by Story 3.4's agent_dispatch node.
    When a retry occurs, feedback_per_criterion is appended to the
    next agent prompt so the agent knows exactly what to fix.

    Attributes:
        passed: Whether all criteria were met.
        unmet_criteria: List of AC IDs that failed.
        feedback_per_criterion: Mapping of AC ID → failure description + fix suggestion.
        attempt_number: Which retry attempt produced this feedback.
    """

    passed: bool
    unmet_criteria: list[str] = Field(default_factory=list)
    feedback_per_criterion: dict[str, str] = Field(default_factory=dict)
    attempt_number: int = 1


class V3ReflexionResult(ArcwrightModel):
    """Composite result from a V3 reflexion validation run.

    Bundles the validation verdict, structured feedback, and cost
    data into a single return value.

    Attributes:
        validation_result: The detailed per-AC validation results.
        feedback: Structured feedback for retry prompt injection.
        tokens_used: Total tokens consumed (input + output) by reflexion.
        tokens_input: Input tokens consumed by reflexion.
        tokens_output: Output tokens consumed by reflexion.
        cost: Estimated cost in USD for the reflexion invocation.
    """

    validation_result: ValidationResult
    feedback: ReflexionFeedback
    tokens_used: int = 0
    tokens_input: int = 0
    tokens_output: int = 0
    cost: Decimal = Decimal("0")


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


async def _extract_acceptance_criteria(story_path: Path) -> list[tuple[str, str]]:
    """Extract acceptance criteria from a story markdown file.

    Reads the story file, locates the ``## Acceptance Criteria`` section, and
    parses numbered criteria into ``(ac_id, ac_text)`` tuples.

    Args:
        story_path: Path to the story markdown file.

    Returns:
        List of ``(ac_id, ac_text)`` tuples, e.g.
        ``[("1", "Given X When Y Then Z"), ("2", "Given A When B Then C")]``.
        Returns an empty list if no acceptance criteria section is found.
    """
    content = await read_text_async(story_path)

    section_match = _AC_SECTION_PATTERN.search(content)
    if not section_match:
        return []

    section_text = section_match.group(1)
    criteria: list[tuple[str, str]] = []

    for match in _NUMBERED_AC_PATTERN.finditer(section_text):
        ac_id = match.group(1).strip()
        ac_text = match.group(2).strip()
        # Collapse internal whitespace / newlines for readability
        ac_text_clean = re.sub(r"\s+", " ", ac_text)
        criteria.append((ac_id, ac_text_clean))

    return criteria


def _build_reflexion_prompt(
    acceptance_criteria: list[tuple[str, str]],
    agent_output: str,
) -> str:
    """Construct a structured reflexion prompt for the LLM.

    Builds a prompt instructing the LLM to evaluate each acceptance criterion
    as PASS or FAIL with structured rationale. The format is designed for
    reliable regex parsing by ``_parse_reflexion_response``.

    Args:
        acceptance_criteria: List of ``(ac_id, ac_text)`` tuples.
        agent_output: The full implementation output from the agent.

    Returns:
        A plain-string prompt ready to pass to ``invoke_agent()``.
    """
    ac_lines = "\n".join(f"{ac_id}. {ac_text}" for ac_id, ac_text in acceptance_criteria)

    return (
        "## Reflexion Validation Task\n\n"
        "You are evaluating whether an agent's implementation output satisfies\n"
        "each acceptance criterion for a story. For EACH criterion below,\n"
        "determine if it is PASS or FAIL, and provide a specific rationale.\n\n"
        "### Format Requirements\n"
        "For each acceptance criterion, respond with EXACTLY this format:\n\n"
        "AC-{id}: PASS\n"
        "Rationale: {explanation of why this criterion is met}\n\n"
        "OR\n\n"
        "AC-{id}: FAIL\n"
        "Rationale: {explanation of what is missing or incorrect}\n"
        "Suggested Fix: {specific action to fix the issue}\n\n"
        "### Acceptance Criteria\n"
        f"{ac_lines}\n\n"
        "### Agent Implementation Output\n"
        f"{agent_output}\n"
    )


def _parse_reflexion_response(
    raw_response: str,
    expected_ac_ids: list[str],
) -> tuple[list[ACResult], dict[str, str]]:
    """Parse the LLM reflexion response into structured AC results.

    Uses regex patterns to extract per-AC verdicts, rationale, and suggested
    fixes. ACs missing from the response are treated as FAIL with a default
    rationale per the story specification.

    Args:
        raw_response: The full text output from the reflexion invocation.
        expected_ac_ids: List of AC IDs that are expected in the response.

    Returns:
        A tuple of:
            - ``list[ACResult]``: Per-AC evaluation results.
            - ``dict[str, str]``: ``feedback_per_criterion`` mapping AC ID →
              combined failure description + suggested fix (failed ACs only).
    """
    # Split the response into per-AC blocks for isolated parsing
    blocks: dict[str, str] = {}
    # Split on the AC-id: PASS/FAIL markers to isolate each block
    split_pattern = re.compile(r"(?=AC-\S+:\s*(?:PASS|FAIL))", re.IGNORECASE)
    parts = split_pattern.split(raw_response)

    for part in parts:
        verdict_match = _AC_VERDICT_PATTERN.search(part)
        if verdict_match:
            ac_id = verdict_match.group(1).strip()
            blocks[ac_id] = part

    ac_results: list[ACResult] = []
    feedback_per_criterion: dict[str, str] = {}

    for ac_id in expected_ac_ids:
        block = blocks.get(ac_id)
        if block is None:
            # AC not evaluated by the LLM — treat as FAIL
            ac_results.append(
                ACResult(
                    ac_id=ac_id,
                    passed=False,
                    rationale="Reflexion did not evaluate this criterion",
                )
            )
            feedback_per_criterion[ac_id] = "Reflexion did not evaluate this criterion"
            continue

        verdict_match = _AC_VERDICT_PATTERN.search(block)
        verdict = verdict_match.group(2).upper() if verdict_match else "FAIL"
        passed = verdict == "PASS"

        rationale_match = _AC_RATIONALE_PATTERN.search(block)
        rationale = (
            rationale_match.group(1).strip()
            if rationale_match
            else "Reflexion did not provide rationale for this criterion"
        )

        fix_match = _AC_FIX_PATTERN.search(block)
        fix = fix_match.group(1).strip() if fix_match else ""

        ac_results.append(ACResult(ac_id=ac_id, passed=passed, rationale=rationale))

        if not passed:
            parts_joined = rationale
            if fix:
                parts_joined = f"{rationale} Suggested Fix: {fix}"
            feedback_per_criterion[ac_id] = parts_joined

    return ac_results, feedback_per_criterion


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


async def run_v3_reflexion(
    agent_output: str,
    story_path: Path,
    project_root: Path,
    *,
    model: str,
    cwd: Path,
    sandbox: PathValidator,
    api_key: str,
    attempt_number: int = 1,
) -> V3ReflexionResult:
    """Run V3 reflexion validation: LLM self-evaluation of agent output against ACs.

    Extracts acceptance criteria from the story file, constructs a reflexion
    prompt, invokes the Claude Code SDK for self-evaluation, parses the
    response, and returns structured validation results with token tracking.

    Args:
        agent_output: The full implementation output from the agent to evaluate.
        story_path: Path to the story markdown file containing acceptance criteria.
        project_root: Root path of the project (used for context, not directly consumed).
        model: Claude model identifier (e.g., ``"claude-sonnet-4-20250514"``).
        cwd: Working directory for the reflexion agent; also the sandbox boundary.
        sandbox: Path validator enforcing sandbox rules during reflexion.
        api_key: Anthropic API key passed as ``ANTHROPIC_API_KEY`` to the SDK subprocess.
        attempt_number: Which retry attempt this represents (1-based). Defaults to 1.

    Returns:
        ``V3ReflexionResult`` containing validation verdict, structured feedback
        for retry injection, and token/cost data for budget tracking.

    Raises:
        ValidationError: On unexpected SDK failure (crash, timeout, empty response)
            or unrecoverable parsing failure. AC-level failures are structured
            results, NOT exceptions.
    """
    from arcwright_ai.agent.invoker import invoke_agent

    # Extract acceptance criteria from the story file
    acceptance_criteria = await _extract_acceptance_criteria(story_path)

    logger.info(
        "validation.v3.start",
        extra={
            "data": {
                "story": str(story_path),
                "attempt_number": attempt_number,
                "acs_count": len(acceptance_criteria),
            }
        },
    )

    if not acceptance_criteria:
        logger.warning(
            "validation.v3.no_acs",
            extra={"data": {"story": str(story_path)}},
        )
        empty_validation = ValidationResult(
            passed=True,
            ac_results=[],
            raw_response="",
            attempt_number=attempt_number,
        )
        empty_feedback = ReflexionFeedback(
            passed=True,
            unmet_criteria=[],
            feedback_per_criterion={},
            attempt_number=attempt_number,
        )
        return V3ReflexionResult(
            validation_result=empty_validation,
            feedback=empty_feedback,
            tokens_used=0,
            cost=Decimal("0"),
        )

    ac_ids = [ac_id for ac_id, _ in acceptance_criteria]
    prompt = _build_reflexion_prompt(acceptance_criteria, agent_output)

    # Invoke the reflexion agent via the SDK
    try:
        result = await invoke_agent(prompt, model=model, cwd=cwd, sandbox=sandbox, api_key=api_key)
    except AgentError as exc:
        raise ValidationError(
            f"Reflexion SDK invocation failed for story {story_path.name}: {exc}",
            details={"original_error": str(exc), "story": str(story_path)},
        ) from exc
    except Exception as exc:
        raise ValidationError(
            f"Unexpected error during reflexion for story {story_path.name}: {exc}",
            details={"original_error": str(exc), "story": str(story_path)},
        ) from exc

    if not result.output_text:
        raise ValidationError(
            f"Reflexion returned empty response for story {story_path.name}",
            details={"story": str(story_path)},
        )

    # Parse the reflexion response
    ac_results, feedback_per_criterion = _parse_reflexion_response(result.output_text, ac_ids)

    overall_passed = all(r.passed for r in ac_results)
    unmet_criteria = [r.ac_id for r in ac_results if not r.passed]
    tokens_used = result.tokens_input + result.tokens_output

    validation_result = ValidationResult(
        passed=overall_passed,
        ac_results=ac_results,
        raw_response=result.output_text,
        attempt_number=attempt_number,
    )
    feedback = ReflexionFeedback(
        passed=overall_passed,
        unmet_criteria=unmet_criteria,
        feedback_per_criterion=feedback_per_criterion,
        attempt_number=attempt_number,
    )

    logger.info(
        "validation.v3.complete",
        extra={
            "data": {
                "passed": overall_passed,
                "acs_evaluated": len(ac_results),
                "acs_failed": len(unmet_criteria),
                "tokens_used": tokens_used,
            }
        },
    )

    return V3ReflexionResult(
        validation_result=validation_result,
        feedback=feedback,
        tokens_used=tokens_used,
        tokens_input=result.tokens_input,
        tokens_output=result.tokens_output,
        cost=result.total_cost,
    )
