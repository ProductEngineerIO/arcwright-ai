"""Engine nodes — Individual graph node implementations for orchestration pipeline."""

from __future__ import annotations

import asyncio
import logging
import re
from datetime import UTC, datetime
from decimal import Decimal
from typing import TYPE_CHECKING, Any

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
from arcwright_ai.core.exceptions import ContextError, ScmError, ValidationError
from arcwright_ai.core.io import write_text_async
from arcwright_ai.core.lifecycle import TaskState
from arcwright_ai.core.types import ProvenanceEntry
from arcwright_ai.engine.state import StoryState  # noqa: TC001
from arcwright_ai.output.provenance import append_entry, render_validation_row
from arcwright_ai.output.run_manager import update_run_status, update_story_status
from arcwright_ai.output.summary import write_halt_report, write_success_summary
from arcwright_ai.scm.branch import commit_story
from arcwright_ai.scm.worktree import create_worktree, remove_worktree
from arcwright_ai.validation.pipeline import PipelineOutcome, PipelineResult, run_validation_pipeline
from arcwright_ai.validation.v6_invariant import V6CheckResult, V6ValidationResult

if TYPE_CHECKING:
    from pathlib import Path

__all__: list[str] = [
    "_derive_story_title",
    "agent_dispatch_node",
    "budget_check_node",
    "commit_node",
    "finalize_node",
    "preflight_node",
    "route_budget_check",
    "route_validation",
    "validate_node",
]

logger = logging.getLogger(__name__)


def _derive_story_title(story_id: str) -> str:
    """Derive a human-readable title from a story ID slug.

    Args:
        story_id: Story identifier slug (e.g., "6-6-scm-integration").

    Returns:
        Title-cased story name (e.g., "Scm Integration").
    """
    parts = story_id.split("-", 2)
    name_part = parts[2] if len(parts) > 2 else story_id
    return name_part.replace("-", " ").title()


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

    checkpoint_dir: Path = (
        state.project_root / DIR_ARCWRIGHT / DIR_RUNS / str(state.run_id) / DIR_STORIES / str(state.story_id)
    )
    await asyncio.to_thread(checkpoint_dir.mkdir, parents=True, exist_ok=True)

    # Create isolated git worktree BEFORE context assembly (AC: #1, #6, #7, #8)
    worktree_path = None
    try:
        story_slug = str(state.story_id)
        try:
            worktree_path = await create_worktree(story_slug, project_root=state.project_root)
        except ScmError as stale_exc:
            # If a worktree was preserved from a prior escalated run, remove it
            # and retry rather than escalating immediately.  This allows fresh
            # `dispatch --story` retries without manual `git worktree remove`.
            if "already exists" in stale_exc.message:
                logger.info(
                    "scm.worktree.stale_cleanup",
                    extra={
                        "data": {
                            "story": story_slug,
                            "reason": "stale_from_prior_escalation",
                            "original_error": stale_exc.message,
                        }
                    },
                )
                await remove_worktree(story_slug, project_root=state.project_root, delete_branch=True, force=True)
                worktree_path = await create_worktree(story_slug, project_root=state.project_root)
            else:
                raise
        logger.info(
            "scm.worktree.create",
            extra={
                "data": {
                    "story": str(state.story_id),
                    "worktree_path": str(worktree_path),
                    "story_slug": str(state.story_id),
                }
            },
        )
    except ScmError as exc:
        logger.error(
            "scm.preflight.error",
            extra={
                "data": {
                    "story": str(state.story_id),
                    "error": exc.message,
                    "details": exc.details,
                }
            },
        )
        halt_report = "\n".join(
            [
                f"# Halt Report: Story {state.story_id}",
                "",
                "## Summary",
                "",
                f"- **Story**: {state.story_id}",
                f"- **Epic**: {state.epic_id}",
                f"- **Run**: {state.run_id}",
                "- **Status**: ESCALATED",
                "- **Reason**: preflight_worktree_creation_failed",
                "",
                "## Error",
                "",
                f"- **Type**: {type(exc).__name__}",
                f"- **Message**: {exc.message}",
                f"- **Details**: {exc.details}",
                "",
                "## Resume Command",
                "",
                "```bash",
                f"arcwright-ai resume {state.run_id}",
                "```",
                "",
            ]
        )
        try:
            await write_text_async(checkpoint_dir / HALT_REPORT_FILENAME, halt_report)
        except Exception as report_exc:
            logger.warning(
                "summary.write_error",
                extra={
                    "data": {
                        "node": "preflight",
                        "story": str(state.story_id),
                        "error": str(report_exc),
                    }
                },
            )
        escalated = state.model_copy(
            update={
                "status": TaskState.ESCALATED,
                "worktree_path": None,
                "agent_output": f"Preflight SCM error: {exc.message}",
            }
        )
        logger.info(
            "engine.node.exit",
            extra={"data": {"node": "preflight", "story": str(state.story_id), "status": str(escalated.status)}},
        )
        return escalated

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
    serialised = serialize_bundle_to_markdown(bundle)
    await write_text_async(checkpoint_dir / CONTEXT_BUNDLE_FILENAME, serialised)

    # Transition: PREFLIGHT → RUNNING
    updated = state.model_copy(
        update={"context_bundle": bundle, "status": TaskState.RUNNING, "worktree_path": worktree_path}
    )

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

    # Use worktree_path as cwd if available; fall back to project_root for backward compat (AC: #2, #5, #6)
    agent_cwd = state.worktree_path if state.worktree_path is not None else state.project_root
    logger.info(
        "agent.dispatch",
        extra={
            "data": {
                "story": str(state.story_id),
                "cwd": str(agent_cwd),
                "using_worktree": state.worktree_path is not None,
            }
        },
    )

    try:
        result = await invoke_agent(
            prompt,
            model=state.config.model.version,
            cwd=agent_cwd,
            sandbox=validate_path,
        )
    except Exception as exc:
        # SDK crash before any output — escalate cleanly so finalize_node can
        # still run and remove the worktree (prevents worktree leaks).
        logger.error(
            "agent.sdk_error",
            extra={
                "data": {
                    "node": "agent_dispatch",
                    "story": str(state.story_id),
                    "attempt": state.retry_count + 1,
                    "error": str(exc),
                }
            },
        )
        checkpoint_dir: Path = (
            state.project_root / DIR_ARCWRIGHT / DIR_RUNS / str(state.run_id) / DIR_STORIES / str(state.story_id)
        )
        await asyncio.to_thread(checkpoint_dir.mkdir, parents=True, exist_ok=True)
        sdk_error_check = V6CheckResult(
            check_name="agent_sdk_error",
            passed=False,
            failure_detail=str(exc),
        )
        synthetic_v6 = V6ValidationResult(passed=False, results=[sdk_error_check])
        synthetic_pipeline = PipelineResult(
            passed=False,
            outcome=PipelineOutcome.FAIL_V6,
            v6_result=synthetic_v6,
        )
        halt_report = _generate_halt_report(state, synthetic_pipeline, state.retry_history, reason="agent_sdk_error")
        await write_text_async(checkpoint_dir / HALT_REPORT_FILENAME, halt_report)
        logger.info(
            "engine.node.exit",
            extra={
                "data": {
                    "node": "agent_dispatch",
                    "story": str(state.story_id),
                    "status": str(TaskState.ESCALATED),
                }
            },
        )
        return state.model_copy(update={"status": TaskState.ESCALATED, "agent_output": ""})

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

    # Provenance: record agent invocation decision (best-effort)
    try:
        refs: list[str] = []
        if state.context_bundle is not None and state.context_bundle.domain_requirements:
            refs = re.findall(r"(?:FR|NFR)-?\d+", state.context_bundle.domain_requirements)
        provenance_entry = ProvenanceEntry(
            decision=f"Agent invoked for story {state.story_id} (attempt {state.retry_count + 1})",
            alternatives=[state.config.model.version],
            rationale=(
                f"Prompt length: {len(prompt)} chars, retry_count: {state.retry_count},"
                f" has_feedback: {feedback is not None}"
            ),
            ac_references=refs,
            timestamp=datetime.now(tz=UTC).isoformat(),
        )
        provenance_path = checkpoint_dir / VALIDATION_FILENAME
        await append_entry(provenance_path, provenance_entry)
    except Exception as exc:
        logger.warning(
            "provenance.write_error",
            extra={
                "data": {
                    "node": "agent_dispatch",
                    "story": str(state.story_id),
                    "error": str(exc),
                }
            },
        )

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

    # Pass-through: agent_dispatch already escalated (e.g. SDK crash before output).
    # The halt report was written there; nothing more to do here.
    if state.status == TaskState.ESCALATED:
        logger.info(
            "engine.node.exit",
            extra={"data": {"node": "validate", "story": str(state.story_id), "status": str(state.status)}},
        )
        return state

    try:
        pipeline_result = await run_validation_pipeline(
            agent_output=state.agent_output,
            story_path=state.story_path,
            project_root=state.project_root,
            model=state.config.model.version,
            cwd=state.project_root,
            sandbox=validate_path,
            attempt_number=state.retry_count + 1,
        )
    except Exception as exc:
        # SDK or filesystem crash during validation — convert to ESCALATED so
        # finalize_node can still run and remove the worktree (prevents leaks).
        logger.error(
            "validation.sdk_error",
            extra={
                "data": {
                    "story": str(state.story_id),
                    "attempt": state.retry_count + 1,
                    "error": str(exc),
                }
            },
        )
        sdk_error_check = V6CheckResult(
            check_name="validation_sdk_error",
            passed=False,
            failure_detail=str(exc),
        )
        synthetic_v6 = V6ValidationResult(passed=False, results=[sdk_error_check])
        pipeline_result = PipelineResult(
            passed=False,
            outcome=PipelineOutcome.FAIL_V6,
            v6_result=synthetic_v6,
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

    # Provenance: record validation decision (best-effort)
    try:
        attempt_number = state.retry_count + 1
        outcome_str = pipeline_result.outcome.value

        # Build rationale based on outcome
        if pipeline_result.outcome == PipelineOutcome.PASS:
            v6_count = len(pipeline_result.v6_result.results)
            v3_info = ""
            if pipeline_result.v3_result is not None:
                v3_passed = sum(1 for ac in pipeline_result.v3_result.validation_result.ac_results if ac.passed)
                v3_total = len(pipeline_result.v3_result.validation_result.ac_results)
                v3_info = f", V3: {v3_passed}/{v3_total} ACs"
            rationale = f"All checks passed (V6: {v6_count} checks{v3_info})"
        elif pipeline_result.outcome == PipelineOutcome.FAIL_V6:
            rationale = f"V6 invariant failures: {len(pipeline_result.v6_result.failures)}"
        else:
            unmet = pipeline_result.feedback.unmet_criteria if pipeline_result.feedback else []
            rationale = f"V3 reflexion failures: ACs {', '.join(unmet)}" if unmet else "V3 validation failed"

        validation_row = render_validation_row(
            attempt_number,
            outcome_str,
            rationale,
        )
        rationale = f"{rationale}\nValidation row: {validation_row}"

        failed_acs = list(pipeline_result.feedback.unmet_criteria) if pipeline_result.feedback else []

        validation_provenance_entry = ProvenanceEntry(
            decision=f"Validation attempt {attempt_number}: {outcome_str}",
            alternatives=[],
            rationale=rationale,
            ac_references=failed_acs,
            timestamp=datetime.now(tz=UTC).isoformat(),
        )
        await append_entry(checkpoint_dir / VALIDATION_FILENAME, validation_provenance_entry)
    except Exception as exc:
        logger.warning(
            "provenance.write_error",
            extra={
                "data": {
                    "node": "validate",
                    "story": str(state.story_id),
                    "error": str(exc),
                }
            },
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

        # Provenance: record escalation decision (best-effort)
        try:
            escalation_entry = ProvenanceEntry(
                decision=f"Escalation decision for attempt {state.retry_count + 1}: v6_invariant_failure",
                alternatives=[],
                rationale="Validation escalated due to V6 invariant failure.",
                ac_references=[],
                timestamp=datetime.now(tz=UTC).isoformat(),
            )
            await append_entry(checkpoint_dir / VALIDATION_FILENAME, escalation_entry)
        except Exception as exc:
            logger.warning(
                "provenance.write_error",
                extra={
                    "data": {
                        "node": "validate",
                        "story": str(state.story_id),
                        "error": str(exc),
                    }
                },
            )

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

        # Provenance: record escalation decision (best-effort)
        try:
            failed_acs = list(pipeline_result.feedback.unmet_criteria) if pipeline_result.feedback else []
            escalation_entry = ProvenanceEntry(
                decision=f"Escalation decision for attempt {new_retry_count}: max_retries_exhausted",
                alternatives=[],
                rationale="Validation escalated because retry budget was exhausted.",
                ac_references=failed_acs,
                timestamp=datetime.now(tz=UTC).isoformat(),
            )
            await append_entry(checkpoint_dir / VALIDATION_FILENAME, escalation_entry)
        except Exception as exc:
            logger.warning(
                "provenance.write_error",
                extra={
                    "data": {
                        "node": "validate",
                        "story": str(state.story_id),
                        "error": str(exc),
                    }
                },
            )

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
    """Commit node — updates run.yaml, commits worktree, and removes worktree.

    Calls run_manager to update story status to "success" with completion
    timestamp, and updates the run-level last_completed_story pointer and
    budget snapshot. If a worktree_path is set, calls ``commit_story`` to
    stage and commit changes, then ``remove_worktree`` to clean up the
    worktree. All writes and SCM operations are best-effort — failures are
    logged as warnings but do not halt execution.

    Args:
        state: Current story execution state (expected SUCCESS).

    Returns:
        State unchanged.
    """
    logger.info("engine.node.enter", extra={"data": {"node": "commit", "story": str(state.story_id)}})

    story_slug = str(state.story_id)
    project_root = state.project_root
    run_id = str(state.run_id)

    # Update story status in run.yaml (best-effort)
    try:
        await update_story_status(
            project_root,
            run_id,
            story_slug,
            status="success",
            completed_at=datetime.now(tz=UTC).isoformat(),
        )
    except Exception as exc:
        logger.warning(
            "run_manager.write_error",
            extra={
                "data": {
                    "node": "commit",
                    "story": story_slug,
                    "operation": "update_story_status",
                    "error": str(exc),
                }
            },
        )

    # Update run-level state (best-effort)
    try:
        await update_run_status(
            project_root,
            run_id,
            last_completed_story=story_slug,
            budget=state.budget,
        )
    except Exception as exc:
        logger.warning(
            "run_manager.write_error",
            extra={
                "data": {
                    "node": "commit",
                    "story": story_slug,
                    "operation": "update_run_status",
                    "error": str(exc),
                }
            },
        )

    # SCM: commit and remove worktree (AC: #3, #6, #13)
    if state.worktree_path is not None:
        story_title = _derive_story_title(story_slug)

        # Commit story changes in worktree (best-effort, non-fatal)
        try:
            commit_hash = await commit_story(
                story_slug=story_slug,
                story_title=story_title,
                story_path=str(state.story_path),
                run_id=run_id,
                worktree_path=state.worktree_path,
            )
            logger.info(
                "scm.commit",
                extra={
                    "data": {
                        "story": story_slug,
                        "commit_hash": commit_hash,
                        "worktree_path": str(state.worktree_path),
                    }
                },
            )
        except ScmError as exc:
            logger.warning(
                "scm.commit.error",
                extra={"data": {"story": story_slug, "error": exc.message, "details": exc.details}},
            )

        # Remove worktree after commit (best-effort, non-fatal)
        try:
            await remove_worktree(story_slug, project_root=project_root)
            logger.info(
                "scm.worktree.remove",
                extra={
                    "data": {
                        "story": story_slug,
                        "worktree_path": str(state.worktree_path),
                    }
                },
            )
        except ScmError as exc:
            logger.warning(
                "scm.worktree.remove.error",
                extra={"data": {"story": story_slug, "error": exc.message, "details": exc.details}},
            )

    logger.info(
        "engine.node.exit",
        extra={"data": {"node": "commit", "story": str(state.story_id), "status": str(state.status)}},
    )
    return state


def _derive_halt_reason(state: StoryState) -> str:
    """Derive the halt reason string from the terminal state.

    Args:
        state: Story execution state in ESCALATED terminal status.

    Returns:
        Halt reason string: "budget_exceeded", "v6_invariant_failure",
        "max_retries_exhausted", or "validation_failure".
    """
    if not state.retry_history:
        return "budget_exceeded"
    last = state.retry_history[-1]
    if last.outcome == PipelineOutcome.FAIL_V6:
        return "v6_invariant_failure"
    if state.retry_count >= state.config.limits.retry_budget:
        return "max_retries_exhausted"
    return "validation_failure"


def _summarize_failures(result: PipelineResult) -> str:
    """Summarize validation failures for a single PipelineResult.

    Args:
        result: The pipeline result to summarize.

    Returns:
        Human-readable failure summary string, or empty string for PASS.
    """
    if result.outcome == PipelineOutcome.FAIL_V6:
        return f"V6: {len(result.v6_result.failures)} checks failed"
    if result.feedback is not None and result.feedback.unmet_criteria:
        return f"V3: ACs {', '.join(result.feedback.unmet_criteria)}"
    return ""


def _build_validation_history_dicts(state: StoryState) -> list[dict[str, Any]]:
    """Build a list of validation history dicts from state retry history.

    Args:
        state: Story execution state containing retry_history.

    Returns:
        List of dicts with keys "attempt", "outcome", "failures".
    """
    return [
        {
            "attempt": i + 1,
            "outcome": result.outcome.value,
            "failures": _summarize_failures(result),
        }
        for i, result in enumerate(state.retry_history)
    ]


def _derive_suggested_fix(state: StoryState) -> str:
    """Derive a suggested fix message from the terminal state.

    Args:
        state: Story execution state in ESCALATED terminal status.

    Returns:
        Human-readable suggested fix string.
    """
    if not state.retry_history:
        return "Review the validation failures and address underlying issues."
    last = state.retry_history[-1]
    if last.outcome == PipelineOutcome.FAIL_V6:
        return "Fix the V6 invariant rule violations and re-run the story."
    if last.feedback is not None and last.feedback.feedback_per_criterion:
        parts = [f"AC {ac_id}: {detail}" for ac_id, detail in last.feedback.feedback_per_criterion.items()]
        return "\n".join(parts)
    return "Review the validation failures and address underlying issues."


async def finalize_node(state: StoryState) -> StoryState:
    """Finalize node — writes run-level summary at graph termination.

    Examines the terminal state (SUCCESS or ESCALATED) and writes the
    appropriate run-level summary via output/summary. When ESCALATED and a
    worktree_path is set, the worktree is preserved for manual inspection and
    a ``scm.worktree.preserved`` event is logged. All writes are best-effort —
    failures are logged but do not affect the returned state.

    Args:
        state: Current story execution state in a terminal status.

    Returns:
        State unchanged.
    """
    logger.info("engine.node.enter", extra={"data": {"node": "finalize", "story": str(state.story_id)}})

    project_root = state.project_root
    run_id = str(state.run_id)
    story_slug = str(state.story_id)

    try:
        if state.status == TaskState.SUCCESS:
            await write_success_summary(project_root, run_id)
        elif state.status == TaskState.ESCALATED:
            halt_reason = _derive_halt_reason(state)
            validation_history_dicts = _build_validation_history_dicts(state)
            last_agent_output = state.agent_output or ""
            suggested_fix = _derive_suggested_fix(state)

            await write_halt_report(
                project_root,
                run_id,
                halted_story=story_slug,
                halt_reason=halt_reason,
                validation_history=validation_history_dicts,
                last_agent_output=last_agent_output,
                suggested_fix=suggested_fix,
                worktree_path=str(state.worktree_path) if state.worktree_path is not None else None,
            )

            # Preserve worktree on ESCALATED — do NOT remove (AC: #4)
            if state.worktree_path is not None:
                logger.info(
                    "scm.worktree.preserved",
                    extra={
                        "data": {
                            "story": story_slug,
                            "worktree_path": str(state.worktree_path),
                            "reason": "story_escalated",
                        }
                    },
                )
    except Exception as exc:
        logger.warning(
            "summary.write_error",
            extra={
                "data": {
                    "node": "finalize",
                    "story": story_slug,
                    "status": str(state.status),
                    "error": str(exc),
                }
            },
        )

    logger.info(
        "engine.node.exit",
        extra={"data": {"node": "finalize", "story": str(state.story_id), "status": str(state.status)}},
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
    if state.status == TaskState.ESCALATED:
        return "exceeded"

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
