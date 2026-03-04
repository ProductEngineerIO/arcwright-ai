"""Engine nodes — Individual graph node implementations for orchestration pipeline."""

from __future__ import annotations

import asyncio
import logging
from decimal import Decimal
from typing import TYPE_CHECKING

from arcwright_ai.agent.invoker import invoke_agent
from arcwright_ai.agent.prompt import build_prompt
from arcwright_ai.agent.sandbox import validate_path
from arcwright_ai.context.injector import build_context_bundle, serialize_bundle_to_markdown
from arcwright_ai.core.constants import (
    AGENT_OUTPUT_FILENAME,
    CONTEXT_BUNDLE_FILENAME,
    DIR_ARCWRIGHT,
    DIR_RUNS,
    DIR_STORIES,
    HALT_REPORT_FILENAME,
    VALIDATION_FILENAME,
)
from arcwright_ai.core.exceptions import AgentError, ContextError, ValidationError
from arcwright_ai.core.io import write_text_async
from arcwright_ai.core.lifecycle import TaskState
from arcwright_ai.engine.state import StoryState  # noqa: TC001
from arcwright_ai.validation.pipeline import PipelineOutcome, PipelineResult, run_validation_pipeline

if TYPE_CHECKING:
    from pathlib import Path

__all__: list[str] = [
    "agent_dispatch_node",
    "budget_check_node",
    "commit_node",
    "preflight_node",
    "route_budget_check",
    "route_validation",
    "validate_node",
]

logger = logging.getLogger(__name__)


async def preflight_node(state: StoryState) -> StoryState:
    """Preflight node — resolves context, writes checkpoint, transitions to RUNNING.

    Invokes the context injector to build a ContextBundle from the story's
    BMAD artifacts, stores the bundle in state, serialises it to the run
    directory as a provenance checkpoint, and transitions status from
    QUEUED → PREFLIGHT → RUNNING.

    Args:
        state: Current story execution state (expected status: QUEUED).

    Returns:
        Updated state with context_bundle populated and status set to RUNNING.

    Raises:
        ContextError: If the story file is missing or context resolution fails.
    """
    logger.info("engine.node.enter", extra={"data": {"node": "preflight", "story": str(state.story_id)}})

    # Transition: QUEUED → PREFLIGHT
    state = state.model_copy(update={"status": TaskState.PREFLIGHT})

    try:
        bundle = await build_context_bundle(
            state.story_path,
            state.project_root,
            artifacts_path=state.config.methodology.artifacts_path,
        )
    except ContextError:
        logger.info(
            "context.error",
            extra={"data": {"node": "preflight", "story": str(state.story_id), "status": str(state.status)}},
        )
        logger.info(
            "engine.node.exit",
            extra={"data": {"node": "preflight", "story": str(state.story_id), "status": str(state.status)}},
        )
        raise

    # Build checkpoint path and write
    checkpoint_dir: Path = (
        state.project_root / DIR_ARCWRIGHT / DIR_RUNS / str(state.run_id) / DIR_STORIES / str(state.story_id)
    )
    await asyncio.to_thread(checkpoint_dir.mkdir, parents=True, exist_ok=True)
    serialised = serialize_bundle_to_markdown(bundle)
    await write_text_async(checkpoint_dir / CONTEXT_BUNDLE_FILENAME, serialised)

    # Transition: PREFLIGHT → RUNNING
    updated = state.model_copy(update={"context_bundle": bundle, "status": TaskState.RUNNING})

    logger.info(
        "engine.node.exit",
        extra={"data": {"node": "preflight", "story": str(state.story_id), "status": str(updated.status)}},
    )
    return updated


async def budget_check_node(state: StoryState) -> StoryState:
    """Placeholder budget check node — handles budget/execution status transitions.

    If the budget is already exceeded, transitions to ESCALATED so the graph
    can terminate in an explicit escalated state. If the incoming state is
    RETRY (e.g., from a validation retry cycle), transitions back to RUNNING
    so the agent can be re-invoked. Otherwise passes state through unchanged.
    The routing decision (ok vs exceeded) is made by ``route_budget_check``.

    Args:
        state: Current story execution state.

    Returns:
        Updated state with status adjusted if coming from RETRY.
    """
    logger.info("engine.node.enter", extra={"data": {"node": "budget_check", "story": str(state.story_id)}})
    if route_budget_check(state) == "exceeded":
        updated = state.model_copy(update={"status": TaskState.ESCALATED})
        logger.info(
            "engine.node.exit",
            extra={"data": {"node": "budget_check", "story": str(state.story_id), "status": str(updated.status)}},
        )
        return updated
    if state.status == TaskState.RETRY:
        updated = state.model_copy(update={"status": TaskState.RUNNING})
        logger.info(
            "engine.node.exit",
            extra={"data": {"node": "budget_check", "story": str(state.story_id), "status": str(updated.status)}},
        )
        return updated
    logger.info(
        "engine.node.exit",
        extra={"data": {"node": "budget_check", "story": str(state.story_id), "status": str(state.status)}},
    )
    return state


async def agent_dispatch_node(state: StoryState) -> StoryState:
    """Agent dispatch node — invokes Claude Code SDK with assembled context.

    Builds the SDK prompt from the preflight context bundle, invokes the
    agent, captures output and token usage, writes the agent output
    checkpoint, and transitions status from RUNNING → VALIDATING.

    Args:
        state: Current story execution state (expected status: RUNNING,
            context_bundle populated by preflight).

    Returns:
        Updated state with agent_output, budget updated, status VALIDATING.

    Raises:
        ContextError: If context_bundle is None (preflight did not run).
        AgentError: If the SDK invocation fails.
    """
    logger.info("engine.node.enter", extra={"data": {"node": "agent_dispatch", "story": str(state.story_id)}})

    if state.context_bundle is None:
        raise ContextError("agent_dispatch_node requires context_bundle from preflight")

    feedback = state.validation_result.feedback if state.validation_result is not None else None
    prompt = build_prompt(state.context_bundle, feedback=feedback)
    logger.info(
        "agent.dispatch",
        extra={
            "data": {
                "story": str(state.story_id),
                "model": state.config.model.version,
                "prompt_length": len(prompt),
                "retry_count": state.retry_count,
                "has_feedback": feedback is not None,
            }
        },
    )

    try:
        result = await invoke_agent(
            prompt,
            model=state.config.model.version,
            cwd=state.project_root,
            sandbox=validate_path,
        )
    except AgentError:
        logger.info(
            "agent.error",
            extra={"data": {"node": "agent_dispatch", "story": str(state.story_id), "status": str(state.status)}},
        )
        logger.info(
            "engine.node.exit",
            extra={"data": {"node": "agent_dispatch", "story": str(state.story_id), "status": str(state.status)}},
        )
        raise

    # Update budget
    new_budget = state.budget.model_copy(
        update={
            "invocation_count": state.budget.invocation_count + 1,
            "total_tokens": state.budget.total_tokens + result.tokens_input + result.tokens_output,
            "estimated_cost": state.budget.estimated_cost + result.total_cost,
        }
    )

    # Write agent output checkpoint
    checkpoint_dir: Path = (
        state.project_root / DIR_ARCWRIGHT / DIR_RUNS / str(state.run_id) / DIR_STORIES / str(state.story_id)
    )
    await asyncio.to_thread(checkpoint_dir.mkdir, parents=True, exist_ok=True)
    await write_text_async(checkpoint_dir / AGENT_OUTPUT_FILENAME, result.output_text)

    # Transition: RUNNING → VALIDATING
    updated = state.model_copy(
        update={
            "agent_output": result.output_text,
            "budget": new_budget,
            "status": TaskState.VALIDATING,
        }
    )

    logger.info(
        "engine.node.exit",
        extra={"data": {"node": "agent_dispatch", "story": str(state.story_id), "status": str(updated.status)}},
    )
    return updated


def _serialize_validation_checkpoint(result: PipelineResult, attempt_number: int) -> str:
    """Serialize a PipelineResult to markdown for the validation checkpoint.

    Args:
        result: The pipeline result to serialize.
        attempt_number: Current attempt number (1-based).

    Returns:
        Markdown string for the validation checkpoint file.
    """
    lines: list[str] = [
        "# Validation Result",
        "",
        f"- **Outcome**: {result.outcome.value}",
        f"- **Passed**: {result.passed}",
        f"- **Attempt**: {attempt_number}",
        f"- **Tokens Used**: {result.tokens_used}",
        f"- **Cost**: ${result.cost}",
        "",
        "## V6 Invariant Checks",
        "",
    ]
    for check in result.v6_result.results:
        status = "PASS" if check.passed else "FAIL"
        line = f"- [{status}] {check.check_name}"
        if not check.passed and check.failure_detail:
            line += f": {check.failure_detail}"
        lines.append(line)

    if result.v3_result is not None:
        lines.extend(["", "## V3 Reflexion Results", ""])
        for ac in result.v3_result.validation_result.ac_results:
            status = "PASS" if ac.passed else "FAIL"
            lines.append(f"- [{status}] AC {ac.ac_id}: {ac.rationale}")

    lines.append("")
    return "\n".join(lines)


def _generate_halt_report(
    state: StoryState,
    last_result: PipelineResult,
    retry_history: list[PipelineResult],
    *,
    reason: str,
) -> str:
    """Generate a structured halt report for escalated stories per FR11.

    Args:
        state: Current story execution state at halt time.
        last_result: The final validation pipeline result that caused escalation.
        retry_history: All accumulated validation results across attempts.
        reason: Halt reason string (e.g. "max_retries_exhausted", "v6_invariant_failure").

    Returns:
        Markdown string for the halt report file.
    """
    lines: list[str] = [
        f"# Halt Report: Story {state.story_id}",
        "",
        "## Summary",
        "",
        f"- **Story**: {state.story_id}",
        f"- **Epic**: {state.epic_id}",
        f"- **Run**: {state.run_id}",
        "- **Status**: ESCALATED",
        f"- **Reason**: {reason}",
        f"- **Total Attempts**: {len(retry_history)}",
        f"- **Retry Count**: {state.retry_count}",
        "",
    ]

    # Failing criteria
    if last_result.feedback is not None and last_result.feedback.unmet_criteria:
        lines.extend(["## Failing Acceptance Criteria", ""])
        for ac_id in last_result.feedback.unmet_criteria:
            detail = last_result.feedback.feedback_per_criterion.get(ac_id, "")
            lines.append(f"- **AC {ac_id}**: {detail}")
        lines.append("")
    elif last_result.outcome == PipelineOutcome.FAIL_V6:
        lines.extend(["## V6 Invariant Failures", ""])
        for check in last_result.v6_result.failures:
            lines.append(f"- **{check.check_name}**: {check.failure_detail or 'Failed'}")
        lines.append("")

    # Retry history table
    lines.extend(
        [
            "## Retry History",
            "",
            "| Attempt | Outcome | Failures |",
            "|---------|---------|----------|",
        ]
    )
    for i, result in enumerate(retry_history, 1):
        failure_summary = ""
        if result.outcome == PipelineOutcome.FAIL_V6:
            failure_summary = f"V6: {len(result.v6_result.failures)} checks failed"
        elif result.feedback is not None:
            failure_summary = f"V3: ACs {', '.join(result.feedback.unmet_criteria)}"
        lines.append(f"| {i} | {result.outcome.value} | {failure_summary} |")
    lines.append("")

    # Last agent output (truncated)
    lines.extend(["## Last Agent Output (Truncated)", ""])
    if state.agent_output:
        truncated = state.agent_output[-2000:] if len(state.agent_output) > 2000 else state.agent_output
        if len(state.agent_output) > 2000:
            lines.append(f"*... truncated ({len(state.agent_output)} chars total) ...*")
            lines.append("")
        lines.append("```")
        lines.append(truncated)
        lines.append("```")
    else:
        lines.append("*No agent output available*")
    lines.append("")

    # Suggested fix
    lines.extend(["## Suggested Fix", ""])
    if last_result.feedback is not None and last_result.feedback.feedback_per_criterion:
        for ac_id, detail in last_result.feedback.feedback_per_criterion.items():
            lines.append(f"- **AC {ac_id}**: {detail}")
    elif last_result.outcome == PipelineOutcome.FAIL_V6:
        lines.append("Fix the V6 invariant rule violations listed above and re-run the story.")
    else:
        lines.append("Review the validation failures and address underlying issues.")
    lines.append("")

    # Resume command
    lines.extend(
        [
            "## Resume Command",
            "",
            "```bash",
            f"arcwright-ai resume {state.run_id}",
            "```",
            "",
        ]
    )

    return "\n".join(lines)


async def validate_node(state: StoryState) -> StoryState:
    """Validate node — runs validation pipeline and determines routing outcome.

    Invokes the validation pipeline (V6 → V3) against the agent's output,
    updates budget with validation costs, accumulates retry history, and
    sets the appropriate lifecycle state based on the pipeline outcome:
    PASS → SUCCESS, FAIL_V3 (within budget) → RETRY, FAIL_V3 (exhausted) or
    FAIL_V6 → ESCALATED with halt report.

    Args:
        state: Current story execution state (expected status: VALIDATING,
            agent_output populated by agent_dispatch).

    Returns:
        Updated state with validation_result, retry_history, budget, and
        status set to SUCCESS, RETRY, or ESCALATED.

    Raises:
        ValidationError: If agent_output is None (agent_dispatch did not run)
            or if the validation pipeline raises an unexpected internal error.
    """
    logger.info(
        "engine.node.enter",
        extra={"data": {"node": "validate", "story": str(state.story_id)}},
    )

    if state.agent_output is None:
        raise ValidationError("validate_node requires agent_output from agent_dispatch")

    pipeline_result = await run_validation_pipeline(
        agent_output=state.agent_output,
        story_path=state.story_path,
        project_root=state.project_root,
        model=state.config.model.version,
        cwd=state.project_root,
        sandbox=validate_path,
        attempt_number=state.retry_count + 1,
    )

    # Update budget with validation costs
    new_budget = state.budget.model_copy(
        update={
            "total_tokens": state.budget.total_tokens + pipeline_result.tokens_used,
            "estimated_cost": state.budget.estimated_cost + pipeline_result.cost,
        }
    )

    # Accumulate retry history
    new_retry_history = [*state.retry_history, pipeline_result]

    # Write validation checkpoint
    checkpoint_dir: Path = (
        state.project_root / DIR_ARCWRIGHT / DIR_RUNS / str(state.run_id) / DIR_STORIES / str(state.story_id)
    )
    await asyncio.to_thread(checkpoint_dir.mkdir, parents=True, exist_ok=True)
    await write_text_async(
        checkpoint_dir / VALIDATION_FILENAME,
        _serialize_validation_checkpoint(pipeline_result, state.retry_count + 1),
    )

    # Route based on pipeline outcome
    if pipeline_result.outcome == PipelineOutcome.PASS:
        updated = state.model_copy(
            update={
                "status": TaskState.SUCCESS,
                "validation_result": pipeline_result,
                "retry_history": new_retry_history,
                "budget": new_budget,
            }
        )
        logger.info(
            "validation.pass",
            extra={
                "data": {
                    "story": str(state.story_id),
                    "attempt": state.retry_count + 1,
                    "tokens_used": pipeline_result.tokens_used,
                }
            },
        )
        logger.info(
            "engine.node.exit",
            extra={
                "data": {
                    "node": "validate",
                    "story": str(state.story_id),
                    "status": str(updated.status),
                }
            },
        )
        return updated

    if pipeline_result.outcome == PipelineOutcome.FAIL_V6:
        halt_report = _generate_halt_report(state, pipeline_result, new_retry_history, reason="v6_invariant_failure")
        await write_text_async(checkpoint_dir / HALT_REPORT_FILENAME, halt_report)

        updated = state.model_copy(
            update={
                "status": TaskState.ESCALATED,
                "validation_result": pipeline_result,
                "retry_history": new_retry_history,
                "budget": new_budget,
            }
        )
        logger.info(
            "validation.fail",
            extra={
                "data": {
                    "story": str(state.story_id),
                    "outcome": "fail_v6",
                    "retry_count": state.retry_count,
                }
            },
        )
        logger.info(
            "run.halt",
            extra={
                "data": {
                    "story": str(state.story_id),
                    "reason": "v6_invariant_failure",
                }
            },
        )
        logger.info(
            "engine.node.exit",
            extra={
                "data": {
                    "node": "validate",
                    "story": str(state.story_id),
                    "status": str(updated.status),
                }
            },
        )
        return updated

    # FAIL_V3 — check retry budget
    new_retry_count = state.retry_count + 1
    if state.retry_count >= state.config.limits.retry_budget:
        # Retries exhausted → ESCALATED
        halt_report_state = state.model_copy(update={"retry_count": new_retry_count})
        halt_report = _generate_halt_report(
            halt_report_state,
            pipeline_result,
            new_retry_history,
            reason="max_retries_exhausted",
        )
        await write_text_async(checkpoint_dir / HALT_REPORT_FILENAME, halt_report)

        updated = state.model_copy(
            update={
                "status": TaskState.ESCALATED,
                "validation_result": pipeline_result,
                "retry_history": new_retry_history,
                "retry_count": new_retry_count,
                "budget": new_budget,
            }
        )
        logger.info(
            "validation.fail",
            extra={
                "data": {
                    "story": str(state.story_id),
                    "outcome": "escalated",
                    "retry_count": new_retry_count,
                }
            },
        )
        logger.info(
            "run.halt",
            extra={
                "data": {
                    "story": str(state.story_id),
                    "reason": "max_retries_exhausted",
                    "retry_count": new_retry_count,
                }
            },
        )
        logger.info(
            "engine.node.exit",
            extra={
                "data": {
                    "node": "validate",
                    "story": str(state.story_id),
                    "status": str(updated.status),
                }
            },
        )
        return updated

    # Retry available
    updated = state.model_copy(
        update={
            "status": TaskState.RETRY,
            "validation_result": pipeline_result,
            "retry_history": new_retry_history,
            "retry_count": new_retry_count,
            "budget": new_budget,
        }
    )
    logger.info(
        "validation.fail",
        extra={
            "data": {
                "story": str(state.story_id),
                "outcome": "retry",
                "retry_count": new_retry_count,
            }
        },
    )
    logger.info(
        "engine.node.exit",
        extra={
            "data": {
                "node": "validate",
                "story": str(state.story_id),
                "status": str(updated.status),
            }
        },
    )
    return updated


async def commit_node(state: StoryState) -> StoryState:
    """Placeholder commit node — passes SUCCESS state through unchanged.

    Args:
        state: Current story execution state (expected SUCCESS).

    Returns:
        State unchanged.
    """
    logger.info("engine.node.enter", extra={"data": {"node": "commit", "story": str(state.story_id)}})
    logger.info(
        "engine.node.exit",
        extra={"data": {"node": "commit", "story": str(state.story_id), "status": str(state.status)}},
    )
    return state


def route_budget_check(state: StoryState) -> str:
    """Route after budget_check node — returns 'exceeded' or 'ok'.

    Returns 'exceeded' if:
    - max_invocations > 0 AND invocation_count >= max_invocations
    - OR max_cost > Decimal(0) AND estimated_cost >= max_cost

    Returns 'ok' otherwise (max values of 0 mean unlimited).

    Args:
        state: Current story execution state.

    Returns:
        'exceeded' if budget limits are breached, 'ok' otherwise.
    """
    budget = state.budget
    if budget.max_invocations > 0 and budget.invocation_count >= budget.max_invocations:
        return "exceeded"
    if budget.max_cost > Decimal(0) and budget.estimated_cost >= budget.max_cost:
        return "exceeded"
    return "ok"


def route_validation(state: StoryState) -> str:
    """Route after validate node — returns 'success', 'retry', or 'escalated'.

    Args:
        state: Current story execution state.

    Returns:
        'success' if status is SUCCESS, 'retry' if RETRY, 'escalated' otherwise.
    """
    if state.status == TaskState.SUCCESS:
        return "success"
    if state.status == TaskState.RETRY:
        return "retry"
    return "escalated"
