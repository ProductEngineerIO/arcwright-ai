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
from arcwright_ai.core.config import ModelRole
from arcwright_ai.core.constants import (
    AGENT_OUTPUT_FILENAME,
    BRANCH_PREFIX,
    CONTEXT_BUNDLE_FILENAME,
    DIR_ARCWRIGHT,
    DIR_RUNS,
    DIR_STORIES,
    HALT_REPORT_FILENAME,
    STORY_COPY_FILENAME,
    VALIDATION_FILENAME,
)
from arcwright_ai.core.errors import CLAUDE_ERROR_REGISTRY, ClaudeErrorCategory
from arcwright_ai.core.exceptions import ContextError, ScmError, ValidationError
from arcwright_ai.core.io import write_text_async
from arcwright_ai.core.lifecycle import TaskState
from arcwright_ai.core.types import BudgetState, ProvenanceEntry, StoryCost, calculate_invocation_cost
from arcwright_ai.engine.state import StoryState  # noqa: TC001
from arcwright_ai.output.decisions import extract_agent_decisions
from arcwright_ai.output.provenance import append_entry, merge_validation_checkpoint, render_validation_row
from arcwright_ai.output.run_manager import update_run_status, update_story_status
from arcwright_ai.output.summary import write_halt_report, write_success_summary
from arcwright_ai.scm.branch import commit_story, delete_remote_branch, fetch_and_sync, push_branch
from arcwright_ai.scm.git import git
from arcwright_ai.scm.pr import (
    MergeOutcome,
    _detect_default_branch,
    generate_pr_body,
    get_pull_request_merge_sha,
    merge_pull_request,
    open_pull_request,
)
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

        # Resolve base_ref: use user-provided --base-ref or fetch remote tip (AC: #5, #6)
        if state.base_ref is not None:
            resolved_base_ref: str | None = state.base_ref
        else:
            default_branch = await _detect_default_branch(
                state.project_root,
                story_slug,
                default_branch_override=state.config.scm.default_branch,
            )
            remote = state.config.scm.remote.strip() or "origin"
            resolved_base_ref = await fetch_and_sync(default_branch, remote, project_root=state.project_root)

        try:
            worktree_path = await create_worktree(story_slug, resolved_base_ref, project_root=state.project_root)
        except ScmError as stale_exc:
            # If a worktree was preserved from a prior escalated run, remove it
            # and retry rather than escalating immediately.  This allows fresh
            # `dispatch --story` retries without manual `git worktree remove`.
            stale_msg = stale_exc.message + " " + str(stale_exc.details or "")
            if "already exists" in stale_msg:
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
                # Also delete the remote branch so the fresh push doesn't hit
                # a non-fast-forward rejection from the prior run's push.
                remote = state.config.scm.remote.strip() if state.config.scm.remote.strip() else "origin"
                await delete_remote_branch(BRANCH_PREFIX + story_slug, project_root=state.project_root, remote=remote)
                worktree_path = await create_worktree(story_slug, resolved_base_ref, project_root=state.project_root)
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

    # Copy the original story file into the run directory for provenance
    # (used by scm/pr.py to extract ACs when generating the PR body).
    try:
        story_content = await asyncio.to_thread(state.story_path.read_text, encoding="utf-8")
        await write_text_async(checkpoint_dir / STORY_COPY_FILENAME, story_content)
    except Exception as copy_exc:
        logger.warning(
            "preflight.story_copy_failed",
            extra={
                "data": {
                    "story": str(state.story_id),
                    "error": str(copy_exc),
                }
            },
        )

    # Transition: PREFLIGHT → RUNNING
    updated = state.model_copy(
        update={"context_bundle": bundle, "status": TaskState.RUNNING, "worktree_path": worktree_path}
    )

    logger.info(
        "engine.node.exit",
        extra={"data": {"node": "preflight", "story": str(state.story_id), "status": str(updated.status)}},
    )
    return updated


def _is_budget_exceeded(budget: BudgetState) -> bool:
    """Check whether any budget ceiling has been breached.

    Args:
        budget: Current budget state.

    Returns:
        True if invocation or cost ceiling is exceeded, False otherwise.
    """
    if budget.max_invocations > 0 and budget.invocation_count >= budget.max_invocations:
        return True
    return budget.max_cost > Decimal(0) and budget.estimated_cost >= budget.max_cost


def _determine_breached_ceiling(budget: BudgetState) -> str:
    """Determine which budget ceiling was breached.

    Args:
        budget: Current budget state with ceiling values.

    Returns:
        String identifying the breached ceiling: ``"invocation_ceiling"``,
        ``"cost_ceiling"``, ``"both (invocation_ceiling and cost_ceiling)"``,
        or ``"unknown"``.
    """
    invocation_breached = budget.max_invocations > 0 and budget.invocation_count >= budget.max_invocations
    cost_breached = budget.max_cost > Decimal(0) and budget.estimated_cost >= budget.max_cost
    if invocation_breached and cost_breached:
        return "both (invocation_ceiling and cost_ceiling)"
    if invocation_breached:
        return "invocation_ceiling"
    if cost_breached:
        return "cost_ceiling"
    return "unknown"


async def budget_check_node(state: StoryState) -> StoryState:
    """Budget check node — enforces dual ceiling enforcement before agent dispatch.

    Checks both the invocation count ceiling and estimated cost ceiling per
    the D2 dual budget model.  When either ceiling is breached, records a
    provenance entry with the full budget state (including which ceiling was
    breached) and transitions to ESCALATED so the graph routes to
    ``finalize_node``.

    If the incoming state is RETRY (from a validation retry cycle),
    transitions back to RUNNING so the agent can be re-invoked.
    Otherwise passes state through unchanged.

    The routing decision (ok vs exceeded) is made by ``route_budget_check``.

    Note:
        The node does NOT raise ``AgentBudgetError`` directly — LangGraph nodes
        that raise exceptions abort graph execution, preventing ``finalize_node``
        from running.  Instead, the ESCALATED status is returned and the CLI
        dispatch layer (``HaltController``) maps it to exit code 2.

    Args:
        state: Current story execution state.

    Returns:
        Updated state with status ESCALATED on budget exceeded, RUNNING on
        retry transition, or unchanged otherwise.
    """
    logger.info("engine.node.enter", extra={"data": {"node": "budget_check", "story": str(state.story_id)}})
    if route_budget_check(state) == "exceeded":
        budget = state.budget
        breached_ceiling = _determine_breached_ceiling(budget)

        # Record provenance entry (best-effort per Boundary #6)
        try:
            checkpoint_dir = (
                state.project_root / DIR_ARCWRIGHT / DIR_RUNS / str(state.run_id) / DIR_STORIES / str(state.story_id)
            )
            provenance_path = checkpoint_dir / VALIDATION_FILENAME
            entry = ProvenanceEntry(
                decision="Budget ceiling exceeded \u2014 halting execution",
                alternatives=["continue (would exceed budget)", "reduce scope"],
                rationale=(
                    f"Budget state at halt: "
                    f"invocation_count={budget.invocation_count}/{budget.max_invocations}, "
                    f"estimated_cost=${budget.estimated_cost}/{budget.max_cost}, "
                    f"total_tokens={budget.total_tokens}. "
                    f"Breached ceiling: {breached_ceiling}"
                ),
                ac_references=["FR25", "NFR10", "D2"],
                timestamp=datetime.now(tz=UTC).isoformat(),
            )
            await append_entry(provenance_path, entry)
        except Exception as exc:
            logger.warning(
                "budget_check.provenance_error",
                extra={"data": {"story": str(state.story_id), "error": str(exc)}},
            )

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


def _extract_sdk_usage_from_error(exc: Exception) -> tuple[int, int]:
    """Extract token usage from an SDK error object when available.

    Attempts multiple known shapes for usage metadata:
    - ``exc.details["usage"]`` (AgentError wrapping)
    - ``exc.usage``
    - ``exc.result_message.usage``

    Returns:
        Tuple of ``(tokens_input, tokens_output)``. Missing values default to 0.
    """

    def _to_int(value: Any) -> int:
        try:
            return max(0, int(value))
        except (TypeError, ValueError):
            return 0

    usage_candidates: list[Any] = []

    details = getattr(exc, "details", None)
    if isinstance(details, dict):
        usage_candidates.append(details.get("usage"))
        usage_candidates.append(
            {
                "input_tokens": details.get("tokens_input", 0),
                "output_tokens": details.get("tokens_output", 0),
            }
        )

    usage_candidates.append(getattr(exc, "usage", None))

    result_message = getattr(exc, "result_message", None)
    if result_message is not None:
        usage_candidates.append(getattr(result_message, "usage", None))

    for usage in usage_candidates:
        if not isinstance(usage, dict):
            continue
        tokens_input = _to_int(usage.get("input_tokens", 0))
        tokens_output = _to_int(usage.get("output_tokens", 0))
        if tokens_input > 0 or tokens_output > 0:
            return (tokens_input, tokens_output)

    return (0, 0)


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

    gen_spec = state.config.models.get(ModelRole.GENERATE)
    feedback = state.validation_result.feedback if state.validation_result is not None else None
    # Use worktree_path as cwd if available; fall back to project_root for backward compat (AC: #2, #5, #6)
    agent_cwd = state.worktree_path if state.worktree_path is not None else state.project_root
    prompt = build_prompt(
        state.context_bundle,
        feedback=feedback,
        working_directory=agent_cwd,
        sandbox_feedback=state.sandbox_feedback,
    )
    logger.info(
        "agent.dispatch",
        extra={
            "data": {
                "story": str(state.story_id),
                "model": gen_spec.version,
                "role": "generate",
                "prompt_length": len(prompt),
                "retry_count": state.retry_count,
                "has_feedback": feedback is not None,
            }
        },
    )

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
            model=gen_spec.version,
            cwd=agent_cwd,
            sandbox=validate_path,
            api_key=state.config.api.claude_api_key.get_secret_value(),
        )
    except Exception as exc:
        # SDK crash before any output — escalate cleanly so finalize_node can
        # still run and remove the worktree (prevents worktree leaks).
        exc_details = getattr(exc, "details", {})
        captured_stderr = exc_details.get("captured_stderr", "") if isinstance(exc_details, dict) else ""
        exit_code = exc_details.get("exit_code") if isinstance(exc_details, dict) else None
        failure_detail = _sdk_failure_detail_from_exception(exc)
        log_data: dict[str, Any] = {
            "node": "agent_dispatch",
            "story": str(state.story_id),
            "attempt": state.retry_count + 1,
            "error": failure_detail,
        }
        if captured_stderr:
            log_data["captured_stderr"] = captured_stderr[:2048]
        if exit_code is not None:
            log_data["exit_code"] = exit_code
        logger.error(
            "agent.sdk_error",
            extra={"data": log_data},
        )
        checkpoint_dir: Path = (
            state.project_root / DIR_ARCWRIGHT / DIR_RUNS / str(state.run_id) / DIR_STORIES / str(state.story_id)
        )
        await asyncio.to_thread(checkpoint_dir.mkdir, parents=True, exist_ok=True)
        sdk_error_check = V6CheckResult(
            check_name="agent_sdk_error",
            passed=False,
            failure_detail=failure_detail,
        )
        synthetic_v6 = V6ValidationResult(passed=False, results=[sdk_error_check])
        synthetic_pipeline = PipelineResult(
            passed=False,
            outcome=PipelineOutcome.FAIL_V6,
            v6_result=synthetic_v6,
        )
        halt_report = _generate_halt_report(state, synthetic_pipeline, state.retry_history, reason="agent_sdk_error")
        await write_text_async(checkpoint_dir / HALT_REPORT_FILENAME, halt_report)
        # Track token consumption for budget integrity on SDK error paths.
        # Prefer SDK-reported usage when available; estimate only as fallback.
        sdk_tokens_input, sdk_tokens_output = _extract_sdk_usage_from_error(exc)
        is_estimated = sdk_tokens_input == 0 and sdk_tokens_output == 0
        tokens_input = sdk_tokens_input if not is_estimated else len(prompt) // 4  # ~4 chars/token heuristic
        tokens_output = sdk_tokens_output if not is_estimated else 0
        cost_estimate = calculate_invocation_cost(tokens_input, tokens_output, gen_spec.pricing)
        error_story_slug = str(state.story_id)
        existing_error_story_cost = state.budget.per_story.get(error_story_slug, StoryCost())
        _existing_err_gen_cost = existing_error_story_cost.cost_by_role.get("generate", Decimal("0"))
        _existing_err_gen_invocations = existing_error_story_cost.invocations_by_role.get("generate", 0)
        _existing_err_gen_tokens_in = existing_error_story_cost.tokens_input_by_role.get("generate", 0)
        _existing_err_gen_tokens_out = existing_error_story_cost.tokens_output_by_role.get("generate", 0)
        _new_cost_by_role_err = {
            **existing_error_story_cost.cost_by_role,
            "generate": _existing_err_gen_cost + cost_estimate,
        }
        _new_invocations_by_role_err = {
            **existing_error_story_cost.invocations_by_role,
            "generate": _existing_err_gen_invocations + 1,
        }
        _new_tokens_input_by_role_err = {
            **existing_error_story_cost.tokens_input_by_role,
            "generate": _existing_err_gen_tokens_in + tokens_input,
        }
        _new_tokens_output_by_role_err = {
            **existing_error_story_cost.tokens_output_by_role,
            "generate": _existing_err_gen_tokens_out + tokens_output,
        }
        new_error_story_cost = StoryCost(
            tokens_input=existing_error_story_cost.tokens_input + tokens_input,
            tokens_output=existing_error_story_cost.tokens_output + tokens_output,
            cost=existing_error_story_cost.cost + cost_estimate,
            invocations=existing_error_story_cost.invocations + 1,
            cost_by_role=_new_cost_by_role_err,
            invocations_by_role=_new_invocations_by_role_err,
            tokens_input_by_role=_new_tokens_input_by_role_err,
            tokens_output_by_role=_new_tokens_output_by_role_err,
        )
        new_per_story_error = {**state.budget.per_story, error_story_slug: new_error_story_cost}
        new_budget_error = state.budget.model_copy(
            update={
                "invocation_count": state.budget.invocation_count + 1,
                "total_tokens": state.budget.total_tokens + tokens_input + tokens_output,
                "total_tokens_input": state.budget.total_tokens_input + tokens_input,
                "total_tokens_output": state.budget.total_tokens_output + tokens_output,
                "estimated_cost": state.budget.estimated_cost + cost_estimate,
                "per_story": new_per_story_error,
            }
        )
        if is_estimated:
            logger.warning(
                "budget.estimated_from_prompt",
                extra={
                    "data": {
                        "story": str(state.story_id),
                        "estimated": True,
                        "estimated_input": tokens_input,
                        "estimated_output": tokens_output,
                        "estimated_cost": str(cost_estimate),
                        "reason": "sdk_error",
                    }
                },
            )
        else:
            logger.info(
                "budget.sdk_error_usage_fallback",
                extra={
                    "data": {
                        "story": str(state.story_id),
                        "estimated": False,
                        "tokens_input": tokens_input,
                        "tokens_output": tokens_output,
                        "estimated_cost": str(cost_estimate),
                        "reason": "sdk_error_partial_usage",
                    }
                },
            )
        # Persist budget to run.yaml (best-effort per Boundary #1)
        try:
            await update_run_status(
                state.project_root,
                str(state.run_id),
                budget=new_budget_error,
            )
        except Exception as persist_exc:
            logger.warning(
                "run_manager.write_error",
                extra={
                    "data": {
                        "node": "agent_dispatch",
                        "story": str(state.story_id),
                        "operation": "persist_budget_post_dispatch_error",
                        "error": str(persist_exc),
                    }
                },
            )
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
        _exc_details_fc = getattr(exc, "details", {})
        _failure_category = _exc_details_fc.get("failure_category") if isinstance(_exc_details_fc, dict) else None
        return state.model_copy(
            update={
                "status": TaskState.ESCALATED,
                "agent_output": "",
                "budget": new_budget_error,
                "failure_category": _failure_category,
            }
        )
    invocation_cost = calculate_invocation_cost(
        result.tokens_input,
        result.tokens_output,
        gen_spec.pricing,
    )
    if invocation_cost != result.total_cost:
        logger.info(
            "budget.cost_variance",
            extra={
                "data": {
                    "story": str(state.story_id),
                    "pricing_cost": str(invocation_cost),
                    "sdk_cost": str(result.total_cost),
                }
            },
        )
    story_slug = str(state.story_id)
    existing_story_cost = state.budget.per_story.get(story_slug, StoryCost())
    _existing_gen_cost = existing_story_cost.cost_by_role.get("generate", Decimal("0"))
    _existing_gen_invocations = existing_story_cost.invocations_by_role.get("generate", 0)
    _existing_gen_tokens_in = existing_story_cost.tokens_input_by_role.get("generate", 0)
    _existing_gen_tokens_out = existing_story_cost.tokens_output_by_role.get("generate", 0)
    _new_cost_by_role = {
        **existing_story_cost.cost_by_role,
        "generate": _existing_gen_cost + invocation_cost,
    }
    _new_invocations_by_role = {
        **existing_story_cost.invocations_by_role,
        "generate": _existing_gen_invocations + 1,
    }
    _new_tokens_input_by_role = {
        **existing_story_cost.tokens_input_by_role,
        "generate": _existing_gen_tokens_in + result.tokens_input,
    }
    _new_tokens_output_by_role = {
        **existing_story_cost.tokens_output_by_role,
        "generate": _existing_gen_tokens_out + result.tokens_output,
    }
    new_story_cost = StoryCost(
        tokens_input=existing_story_cost.tokens_input + result.tokens_input,
        tokens_output=existing_story_cost.tokens_output + result.tokens_output,
        cost=existing_story_cost.cost + invocation_cost,
        invocations=existing_story_cost.invocations + 1,
        cost_by_role=_new_cost_by_role,
        invocations_by_role=_new_invocations_by_role,
        tokens_input_by_role=_new_tokens_input_by_role,
        tokens_output_by_role=_new_tokens_output_by_role,
    )
    new_per_story = {**state.budget.per_story, story_slug: new_story_cost}
    new_budget = state.budget.model_copy(
        update={
            "invocation_count": state.budget.invocation_count + 1,
            "total_tokens": state.budget.total_tokens + result.tokens_input + result.tokens_output,
            "total_tokens_input": state.budget.total_tokens_input + result.tokens_input,
            "total_tokens_output": state.budget.total_tokens_output + result.tokens_output,
            "estimated_cost": state.budget.estimated_cost + invocation_cost,
            "per_story": new_per_story,
        }
    )

    # Write agent output checkpoint
    checkpoint_dir_success: Path = (
        state.project_root / DIR_ARCWRIGHT / DIR_RUNS / str(state.run_id) / DIR_STORIES / str(state.story_id)
    )
    await asyncio.to_thread(checkpoint_dir_success.mkdir, parents=True, exist_ok=True)
    await write_text_async(checkpoint_dir_success / AGENT_OUTPUT_FILENAME, result.output_text)
    attempt_output_filename = f"agent-output.attempt-{state.retry_count + 1}.md"
    await write_text_async(checkpoint_dir_success / attempt_output_filename, result.output_text)

    # Provenance: record agent invocation decision (best-effort)
    try:
        refs: list[str] = []
        if state.context_bundle is not None and state.context_bundle.domain_requirements:
            refs = re.findall(r"(?:FR|NFR)-?\d+", state.context_bundle.domain_requirements)
        provenance_entry = ProvenanceEntry(
            decision=f"Agent invoked for story {state.story_id} (attempt {state.retry_count + 1})",
            alternatives=[gen_spec.version],
            rationale=(
                f"Prompt length: {len(prompt)} chars, retry_count: {state.retry_count},"
                f" has_feedback: {feedback is not None}, role: generate"
            ),
            ac_references=refs,
            timestamp=datetime.now(tz=UTC).isoformat(),
        )
        provenance_path = checkpoint_dir_success / VALIDATION_FILENAME
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

    # Persist budget to run.yaml (best-effort per Boundary #1)
    try:
        await update_run_status(
            state.project_root,
            str(state.run_id),
            budget=new_budget,
        )
    except Exception as exc:
        logger.warning(
            "run_manager.write_error",
            extra={
                "data": {
                    "node": "agent_dispatch",
                    "story": str(state.story_id),
                    "operation": "persist_budget_post_dispatch",
                    "error": str(exc),
                }
            },
        )

    # Transition: RUNNING → VALIDATING
    next_sandbox_feedback: str | None = None
    if result.outside_boundary_denied_paths:
        denied_path = result.outside_boundary_denied_paths[0]
        next_sandbox_feedback = (
            f"Previous attempt was blocked by sandbox while writing '{denied_path}'. "
            "Convert all absolute paths to project-relative paths rooted at the current working directory "
            "(for example '/.../src/app/file.ts' -> 'src/app/file.ts')."
        )

    updated = state.model_copy(
        update={
            "agent_output": result.output_text,
            "budget": new_budget,
            "status": TaskState.VALIDATING,
            "sandbox_feedback": next_sandbox_feedback,
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

    review_spec = state.config.models.get(ModelRole.REVIEW)
    try:
        pipeline_result = await run_validation_pipeline(
            agent_output=state.agent_output,
            story_path=state.story_path,
            project_root=state.project_root,
            model=review_spec.version,
            cwd=state.worktree_path or state.project_root,
            sandbox=validate_path,
            api_key=state.config.api.claude_api_key.get_secret_value(),
            attempt_number=state.retry_count + 1,
        )
    except Exception as exc:
        # SDK or filesystem crash during validation — convert to ESCALATED so
        # finalize_node can still run and remove the worktree (prevents leaks).
        failure_detail = _sdk_failure_detail_from_exception(exc)
        logger.error(
            "validation.sdk_error",
            extra={
                "data": {
                    "story": str(state.story_id),
                    "attempt": state.retry_count + 1,
                    "error": failure_detail,
                }
            },
        )
        sdk_error_check = V6CheckResult(
            check_name="validation_sdk_error",
            passed=False,
            failure_detail=failure_detail,
        )
        synthetic_v6 = V6ValidationResult(passed=False, results=[sdk_error_check])
        pipeline_result = PipelineResult(
            passed=False,
            outcome=PipelineOutcome.FAIL_V6,
            v6_result=synthetic_v6,
        )

    # Update budget with validation costs, including per-story review role metrics
    _validate_story_slug = str(state.story_id)
    _existing_story_cost_v = state.budget.per_story.get(_validate_story_slug, StoryCost())
    _existing_review_cost = _existing_story_cost_v.cost_by_role.get("review", Decimal("0"))
    _existing_review_invocations = _existing_story_cost_v.invocations_by_role.get("review", 0)
    _existing_review_tokens_in = _existing_story_cost_v.tokens_input_by_role.get("review", 0)
    _existing_review_tokens_out = _existing_story_cost_v.tokens_output_by_role.get("review", 0)
    _had_review_activity = (
        pipeline_result.cost > Decimal("0") or pipeline_result.tokens_used > 0 or pipeline_result.v3_result is not None
    )
    _new_cost_by_role_v = {
        **_existing_story_cost_v.cost_by_role,
        "review": _existing_review_cost + pipeline_result.cost,
    }
    _new_invocations_by_role_v = {
        **_existing_story_cost_v.invocations_by_role,
        "review": _existing_review_invocations + (1 if _had_review_activity else 0),
    }
    _new_tokens_input_by_role_v = {
        **_existing_story_cost_v.tokens_input_by_role,
        "review": _existing_review_tokens_in + pipeline_result.tokens_input,
    }
    _new_tokens_output_by_role_v = {
        **_existing_story_cost_v.tokens_output_by_role,
        "review": _existing_review_tokens_out + pipeline_result.tokens_output,
    }
    _new_story_cost_v = _existing_story_cost_v.model_copy(
        update={
            "tokens_input": _existing_story_cost_v.tokens_input + pipeline_result.tokens_input,
            "tokens_output": _existing_story_cost_v.tokens_output + pipeline_result.tokens_output,
            "cost": _existing_story_cost_v.cost + pipeline_result.cost,
            "invocations": _existing_story_cost_v.invocations + (1 if _had_review_activity else 0),
            "cost_by_role": _new_cost_by_role_v,
            "invocations_by_role": _new_invocations_by_role_v,
            "tokens_input_by_role": _new_tokens_input_by_role_v,
            "tokens_output_by_role": _new_tokens_output_by_role_v,
        }
    )
    _new_per_story_v = {**state.budget.per_story, _validate_story_slug: _new_story_cost_v}
    new_budget = state.budget.model_copy(
        update={
            "invocation_count": state.budget.invocation_count + (1 if _had_review_activity else 0),
            "total_tokens": state.budget.total_tokens + pipeline_result.tokens_used,
            "total_tokens_input": state.budget.total_tokens_input + pipeline_result.tokens_input,
            "total_tokens_output": state.budget.total_tokens_output + pipeline_result.tokens_output,
            "estimated_cost": state.budget.estimated_cost + pipeline_result.cost,
            "per_story": _new_per_story_v,
        }
    )

    # Persist budget to run.yaml (best-effort per Boundary #1)
    try:
        await update_run_status(
            state.project_root,
            str(state.run_id),
            budget=new_budget,
        )
    except Exception as exc:
        logger.warning(
            "run_manager.write_error",
            extra={
                "data": {
                    "node": "validate",
                    "story": str(state.story_id),
                    "operation": "persist_budget_post_validation",
                    "error": str(exc),
                }
            },
        )

    # Accumulate retry history
    new_retry_history = [*state.retry_history, pipeline_result]

    # Provenance: merge validation checkpoint and record decision (best-effort)
    checkpoint_dir: Path = (
        state.project_root / DIR_ARCWRIGHT / DIR_RUNS / str(state.run_id) / DIR_STORIES / str(state.story_id)
    )
    await asyncio.to_thread(checkpoint_dir.mkdir, parents=True, exist_ok=True)
    try:
        attempt_number = state.retry_count + 1
        outcome_str = pipeline_result.outcome.value

        # Build feedback summary for the validation history row
        if pipeline_result.outcome == PipelineOutcome.PASS:
            v6_count = len(pipeline_result.v6_result.results)
            v3_info = ""
            if pipeline_result.v3_result is not None:
                v3_passed = sum(1 for ac in pipeline_result.v3_result.validation_result.ac_results if ac.passed)
                v3_total = len(pipeline_result.v3_result.validation_result.ac_results)
                v3_info = f", V3: {v3_passed}/{v3_total} ACs"
            feedback_summary = f"All checks passed (V6: {v6_count} checks{v3_info})"
        elif pipeline_result.outcome == PipelineOutcome.FAIL_V6:
            feedback_summary = f"V6 invariant failures: {len(pipeline_result.v6_result.failures)}"
        else:
            unmet = pipeline_result.feedback.unmet_criteria if pipeline_result.feedback else []
            feedback_summary = f"V3 reflexion failures: ACs {', '.join(unmet)}" if unmet else "V3 validation failed"

        # Merge validation row into provenance file — preserves ## Agent Decisions
        await merge_validation_checkpoint(
            checkpoint_dir / VALIDATION_FILENAME,
            attempt=attempt_number,
            outcome=outcome_str,
            feedback=feedback_summary,
        )

        validation_row = render_validation_row(
            attempt_number,
            outcome_str,
            feedback_summary,
        )
        rationale = f"{feedback_summary}\nValidation row: {validation_row}"

        failed_acs = list(pipeline_result.feedback.unmet_criteria) if pipeline_result.feedback else []

        validation_provenance_entry = ProvenanceEntry(
            decision=f"Validation attempt {attempt_number}: {outcome_str}",
            alternatives=[review_spec.version],
            rationale=f"{rationale}, model: {review_spec.version} (role: review)",
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
        commit_hash: str | None = None
        try:
            # Resolve branch-creation base ref for agent-commit detection (Story 10.4).
            # git merge-base HEAD <default_branch> returns the point where the worktree
            # branch was cut from the default branch.  If HEAD has advanced past that
            # point the agent already committed; commit_story() detects this and returns
            # the agent's commit hash without making an additional commit.
            resolved_base_ref: str | None = None
            try:
                default_branch = await _detect_default_branch(
                    project_root,
                    story_slug,
                    default_branch_override=state.config.scm.default_branch,
                )
                base_result = await git("merge-base", "HEAD", default_branch, cwd=state.worktree_path)
                resolved_base_ref = base_result.stdout.strip()
            except Exception as base_exc:
                logger.debug(
                    "scm.commit.base_ref_resolution_failed",
                    extra={"data": {"story": story_slug, "error": str(base_exc)}},
                )
                # Fall through with None — commit_story() falls back to existing behaviour.

            commit_hash = await commit_story(
                story_slug=story_slug,
                story_title=story_title,
                story_path=str(state.story_path),
                run_id=run_id,
                worktree_path=state.worktree_path,
                base_ref=resolved_base_ref,
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

        # Push branch and open PR after successful commit (AC: #8, best-effort)
        pr_url: str | None = None
        if commit_hash is not None:
            branch_name = BRANCH_PREFIX + story_slug
            configured_remote = state.config.scm.remote.strip() if state.config.scm.remote.strip() else "origin"

            # Push branch to remote (AC: #1, #2) — best-effort wrapper handles ScmError internally
            push_succeeded = False
            try:
                push_succeeded = await push_branch(
                    branch_name,
                    project_root=project_root,
                    remote=configured_remote,
                    worktree_path=state.worktree_path,
                )
            except Exception as exc:
                logger.warning(
                    "scm.push.error",
                    extra={"data": {"story": story_slug, "error": str(exc)}},
                )

            if push_succeeded:
                # Extract implementation decisions before PR body generation (best-effort)
                _extraction_base_ref = resolved_base_ref or "HEAD~1"
                _checkpoint_dir_extract: Path = (
                    project_root / DIR_ARCWRIGHT / DIR_RUNS / run_id / DIR_STORIES / story_slug
                )
                _provenance_path_extract = _checkpoint_dir_extract / VALIDATION_FILENAME
                _review_spec_extract = state.config.models.get(ModelRole.REVIEW)
                try:
                    _extraction_result = await extract_agent_decisions(
                        state.worktree_path,
                        _checkpoint_dir_extract,
                        _extraction_base_ref,
                        _provenance_path_extract,
                        model=_review_spec_extract.version,
                        api_key=state.config.api.claude_api_key.get_secret_value(),
                        story_slug=story_slug,
                        project_root=project_root,
                    )
                except Exception as _extract_exc:
                    logger.warning(
                        "decisions.extract.error",
                        extra={"data": {"story": story_slug, "error": str(_extract_exc)}},
                    )
                    _extraction_result = None

                # Accumulate extraction cost into budget (review role)
                if _extraction_result is not None:
                    _ext_slug = story_slug
                    _ext_existing = state.budget.per_story.get(_ext_slug, StoryCost())
                    _ext_cost = _extraction_result.total_cost
                    _ext_ti = _extraction_result.tokens_input
                    _ext_to = _extraction_result.tokens_output
                    _ext_new_story = _ext_existing.model_copy(
                        update={
                            "tokens_input": _ext_existing.tokens_input + _ext_ti,
                            "tokens_output": _ext_existing.tokens_output + _ext_to,
                            "cost": _ext_existing.cost + _ext_cost,
                            "invocations": _ext_existing.invocations + 1,
                            "cost_by_role": {
                                **_ext_existing.cost_by_role,
                                "review": _ext_existing.cost_by_role.get("review", Decimal("0")) + _ext_cost,
                            },
                            "invocations_by_role": {
                                **_ext_existing.invocations_by_role,
                                "review": _ext_existing.invocations_by_role.get("review", 0) + 1,
                            },
                            "tokens_input_by_role": {
                                **_ext_existing.tokens_input_by_role,
                                "review": _ext_existing.tokens_input_by_role.get("review", 0) + _ext_ti,
                            },
                            "tokens_output_by_role": {
                                **_ext_existing.tokens_output_by_role,
                                "review": _ext_existing.tokens_output_by_role.get("review", 0) + _ext_to,
                            },
                        }
                    )
                    state = state.model_copy(
                        update={
                            "budget": state.budget.model_copy(
                                update={
                                    "invocation_count": state.budget.invocation_count + 1,
                                    "total_tokens": state.budget.total_tokens + _ext_ti + _ext_to,
                                    "total_tokens_input": state.budget.total_tokens_input + _ext_ti,
                                    "total_tokens_output": state.budget.total_tokens_output + _ext_to,
                                    "estimated_cost": state.budget.estimated_cost + _ext_cost,
                                    "per_story": {**state.budget.per_story, _ext_slug: _ext_new_story},
                                }
                            )
                        }
                    )

                # Generate PR body and open PR (AC: #3, #4)
                try:
                    pr_body = await generate_pr_body(run_id, story_slug, project_root=project_root)
                    pr_url = await open_pull_request(
                        branch_name,
                        story_slug,
                        pr_body,
                        project_root=project_root,
                        default_branch=state.config.scm.default_branch,
                    )
                except Exception as exc:
                    logger.warning(
                        "scm.pr.error",
                        extra={"data": {"story": story_slug, "error": str(exc)}},
                    )
            else:
                logger.warning(
                    "scm.pr.create.skipped",
                    extra={"data": {"story": story_slug, "reason": "push_failed_or_skipped"}},
                )

            # Store PR URL in run.yaml (AC: #9)
            if pr_url is not None:
                try:
                    await update_story_status(
                        project_root,
                        run_id,
                        story_slug,
                        status="success",
                        pr_url=pr_url,
                    )
                except Exception as exc:
                    logger.warning(
                        "run_manager.write_error",
                        extra={
                            "data": {
                                "node": "commit",
                                "story": story_slug,
                                "operation": "update_story_status_pr_url",
                                "error": str(exc),
                            }
                        },
                    )

        # Auto-merge PR when configured (Story 9.3 — best-effort, non-fatal)
        if pr_url is not None and state.config.scm.auto_merge:
            merge_attempted_at = datetime.now(tz=UTC).isoformat()
            merge_strategy = "squash"
            merge_outcome = MergeOutcome.ERROR
            merge_sha = "not_merged"
            try:
                merge_outcome = await merge_pull_request(
                    pr_url,
                    strategy=merge_strategy,
                    project_root=project_root,
                    wait_timeout=state.config.scm.merge_wait_timeout,
                )
            except Exception as exc:
                logger.warning(
                    "scm.pr.merge.error",
                    extra={"data": {"story": story_slug, "error": str(exc)}},
                )

            if merge_outcome is MergeOutcome.MERGED:
                try:
                    merge_sha = await get_pull_request_merge_sha(pr_url, project_root=project_root) or "unknown"
                except Exception as exc:
                    logger.warning(
                        "scm.pr.merge.sha.error",
                        extra={"data": {"story": story_slug, "error": str(exc)}},
                    )

            # Record merge provenance (best-effort)
            try:
                checkpoint_dir = state.project_root / DIR_ARCWRIGHT / DIR_RUNS / run_id / DIR_STORIES / story_slug
                provenance_path = checkpoint_dir / VALIDATION_FILENAME
                merge_entry = ProvenanceEntry(
                    decision="Auto-merge PR after creation",
                    alternatives=["manual merge", "skip merge"],
                    rationale=(
                        f"merge_attempted_at={merge_attempted_at}; "
                        f"merge_status={merge_outcome.value}; "
                        f"strategy={merge_strategy}; "
                        f"pr_url={pr_url}; "
                        f"merge_sha={merge_sha}"
                    ),
                    ac_references=["FR39", "D7"],
                    timestamp=datetime.now(tz=UTC).isoformat(),
                )
                await append_entry(provenance_path, merge_entry)
            except Exception as prov_exc:
                logger.warning(
                    "provenance.write_error",
                    extra={"data": {"story": story_slug, "error": str(prov_exc)}},
                )

            state.merge_outcome = merge_outcome.value

        elif commit_hash is not None and state.config.scm.auto_merge:
            # auto_merge=True but PR creation failed — no merge attempted
            state.merge_outcome = MergeOutcome.ERROR.value

        elif commit_hash is not None:
            # auto_merge=False — merge intentionally skipped
            state.merge_outcome = MergeOutcome.SKIPPED.value

        # Store PR URL in state (AC: #9)
        if pr_url is not None:
            state = state.model_copy(update={"pr_url": pr_url})

        # Remove worktree after commit (best-effort, non-fatal).
        # Pass delete_branch=True when merge succeeded so the local story branch is
        # always cleaned up — even when gh --delete-branch could not delete it while
        # the worktree was still checked out (Story 10.6).
        _branch_merged = state.merge_outcome == MergeOutcome.MERGED.value
        try:
            await remove_worktree(story_slug, project_root=project_root, delete_branch=_branch_merged)
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

    Inspects ``BudgetState`` to detect budget-caused escalation regardless of
    whether retry history is present (retries can also push budget over).
    Falls back to validation-based reasons when budget ceilings are not
    breached, and detects agent SDK errors when no retry history exists.

    Args:
        state: Story execution state in ESCALATED terminal status.

    Returns:
        Halt reason string: ``"agent_sdk_error"``, ``"budget_exceeded"``,
        ``"v6_invariant_failure"``, ``"max_retries_exhausted"``, or
        ``"validation_failure"``.
    """
    if _is_budget_exceeded(state.budget):
        return "budget_exceeded"
    if not state.retry_history:
        return "agent_sdk_error"
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


def _summarize_sdk_stderr(stderr: str) -> str | None:
    """Condense captured Claude stderr into a single diagnostic line for reports."""

    cleaned_lines: list[str] = []
    for raw_line in stderr.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        line = re.sub(r"^\d{4}-\d{2}-\d{2}T[^ ]+ \[(?:DEBUG|INFO|WARN|ERROR)\]\s*", "", line)
        if line and line not in cleaned_lines:
            cleaned_lines.append(line)

    if not cleaned_lines:
        return None

    priority_patterns = (
        r"fatal",
        r"invalid",
        r"denied",
        r"unauthorized",
        r"forbidden",
        r"timeout",
        r"credit balance",
        r"billing",
        r"model access",
        r"failed to",
        r"unable to",
        r"broken symlink",
        r"missing file",
        r"io error",
    )
    for line in cleaned_lines:
        if any(re.search(pattern, line, re.IGNORECASE) for pattern in priority_patterns):
            return line[:240]

    return cleaned_lines[0][:240]


def _sdk_failure_detail_from_exception(exc: Exception) -> str:
    """Build a halt-report-friendly detail string for SDK/process failures."""

    message = str(exc)
    details = getattr(exc, "details", None)
    if not isinstance(details, dict):
        return message

    classified_message = details.get("classified_message")
    if isinstance(classified_message, str) and classified_message:
        return classified_message

    captured_stderr = details.get("captured_stderr")
    if not isinstance(captured_stderr, str) or not captured_stderr.strip():
        return message

    stderr_summary = _summarize_sdk_stderr(captured_stderr)
    if not stderr_summary:
        return message

    if "Check stderr output for details" in message or "Command failed with exit code" in message:
        return f"Claude SDK subprocess failed before producing output. Diagnostic stderr: {stderr_summary}"
    return f"{message} | Diagnostic stderr: {stderr_summary}"


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

    When the halt is budget-related, includes budget consumption details
    (invocation count, cost, tokens, and which ceiling was breached) to
    help the operator decide whether to increase limits.

    Args:
        state: Story execution state in ESCALATED terminal status.

    Returns:
        Human-readable suggested fix string.
    """
    budget = state.budget
    if _is_budget_exceeded(budget):
        breached = _determine_breached_ceiling(budget)
        return (
            f"Budget ceiling exceeded ({breached}). "
            f"Budget consumption: "
            f"invocations={budget.invocation_count}/{budget.max_invocations}, "
            f"cost=${budget.estimated_cost}/${budget.max_cost}, "
            f"total_tokens={budget.total_tokens}. "
            "Consider increasing `limits.cost_per_run` or `limits.tokens_per_story` in pyproject.toml."
        )
    if not state.retry_history:
        failure_cat = getattr(state, "failure_category", None)
        if failure_cat:
            try:
                category = ClaudeErrorCategory(failure_cat)
                if category in (
                    ClaudeErrorCategory.BILLING_ERROR,
                    ClaudeErrorCategory.AUTH_ERROR,
                    ClaudeErrorCategory.MODEL_ACCESS_ERROR,
                ):
                    cls_entry = CLAUDE_ERROR_REGISTRY[category]
                    steps = "\n".join(f"  {i + 1}. {step}" for i, step in enumerate(cls_entry.remediation_steps))
                    return (
                        f"\u26a0\ufe0f  Claude Platform/Account Issue \u2014 {cls_entry.title}\n"
                        "This is a Claude platform/account issue, not a story code defect.\n"
                        f"{cls_entry.summary}\n\nTo resolve:\n{steps}"
                    )
            except ValueError:
                pass
        return (
            "Agent invocation failed before producing any output (SDK error). "
            "Check the `agent.sdk_stderr` log event and halt report for details. "
            "Common causes: invalid API key, insufficient API credits, model access denied, network error, "
            "or Claude Code CLI misconfiguration."
        )
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

            # Persist budget to run.yaml on ESCALATED (best-effort per Boundary #1)
            try:
                await update_run_status(
                    project_root,
                    run_id,
                    budget=state.budget,
                )
            except Exception as persist_exc:
                logger.warning(
                    "run_manager.write_error",
                    extra={
                        "data": {
                            "node": "finalize",
                            "story": story_slug,
                            "operation": "persist_budget_on_halt",
                            "error": str(persist_exc),
                        }
                    },
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
