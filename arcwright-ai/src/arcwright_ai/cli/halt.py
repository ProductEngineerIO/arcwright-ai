"""CLI halt — Graceful halt coordination for unrecoverable failures.

Provides :class:`HaltController`, which consolidates all halt-related
operations for both exception-based halts (errors escaping the graph) and
graph-level halts (non-SUCCESS terminal states from the dispatch loop).
"""

from __future__ import annotations

import logging
import re
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

import typer

from arcwright_ai.core.constants import (
    DIR_ARCWRIGHT,
    DIR_RUNS,
    DIR_STORIES,
    EXIT_AGENT,
    EXIT_CONFIG,
    EXIT_INTERNAL,
    EXIT_SCM,
    EXIT_SUCCESS,
    EXIT_VALIDATION,
    VALIDATION_FILENAME,
)
from arcwright_ai.core.exceptions import (
    AgentBudgetError,
    AgentError,
    AgentTimeoutError,
    ArcwrightError,
    ConfigError,
    ContextError,
    ProjectError,
    SandboxViolation,
    ScmError,
    ValidationError,
)
from arcwright_ai.core.lifecycle import TaskState
from arcwright_ai.core.types import BudgetState, ProvenanceEntry, StoryId
from arcwright_ai.output.provenance import append_entry
from arcwright_ai.output.run_manager import RunStatusValue, update_run_status
from arcwright_ai.output.summary import write_halt_report

if TYPE_CHECKING:
    from pathlib import Path

    from arcwright_ai.engine.state import StoryState

__all__: list[str] = ["HaltController"]

logger = logging.getLogger(__name__)

# Length of the "epic-" prefix used when parsing epic_spec strings.
_EPIC_PREFIX_LEN: int = 5


class HaltController:
    """Coordinates graceful halt operations for unrecoverable failures.

    Handles both exception-based halts (errors escaping the graph) and
    graph-level halts (non-SUCCESS terminal states).  Instantiated once per
    dispatch run so that ``project_root``, ``run_id``, and ``epic_spec`` are
    shared across all halt operations without threading them through every call.

    Attributes:
        project_root: Absolute path to the project root.
        run_id: Run identifier string.
        epic_spec: Epic identifier (e.g., ``"5"`` or ``"epic-5"``), used to
            build the resume command shown in halt output.
    """

    def __init__(
        self,
        *,
        project_root: Path,
        run_id: str,
        epic_spec: str,
        previous_run_id: str | None = None,
    ) -> None:
        """Initialise the halt controller.

        Args:
            project_root: Absolute path to the project root.
            run_id: Run identifier string.
            epic_spec: Epic identifier (e.g., ``"5"`` or ``"epic-5"``), used
                when rendering the resume command in halt output.
            previous_run_id: Optional run ID of the original halted run when
                this controller is operating in resume mode.  When provided it
                is passed to ``write_halt_report()`` so the combined summary
                includes the previous run's artifacts.
        """
        self.project_root = project_root
        self.run_id = run_id
        self.epic_spec = epic_spec
        self.previous_run_id = previous_run_id

    # ---------------------------------------------------------------------------
    # Public entry points
    # ---------------------------------------------------------------------------

    async def handle_halt(
        self,
        *,
        story_id: StoryId,
        exception: Exception,
        accumulated_budget: BudgetState,
        completed_stories: list[str],
        last_completed: str | None,
    ) -> int:
        """Handle an exception-based halt.

        Coordinates the full halt sequence for exceptions that escape the graph:
        writes a halt report, flushes a provenance entry, updates run status,
        emits a JSONL event, and outputs a structured halt summary to stderr.

        All artifact writes are best-effort — failures are logged at WARNING
        level and do **not** prevent the halt controller from returning an exit
        code.

        Args:
            story_id: Identifier of the story whose execution raised *exception*.
            exception: Exception that triggered the halt.
            accumulated_budget: Budget state accumulated at halt time.
            completed_stories: Slugs of stories that completed successfully
                before this halt.
            last_completed: Slug of the most recently completed story, or
                ``None`` if this is the first story.

        Returns:
            CLI exit code per the D6 taxonomy.

        Raises:
            AssertionError: If *story_id* is in *completed_stories* — the halt
                controller must never be called for an already-completed story.
        """
        story_slug = str(story_id)

        # NFR2 guard: never write to a completed story's directory.
        assert story_slug not in completed_stories, (
            f"HaltController.handle_halt() called for an already-completed story: {story_slug!r}. "
            "Completed story directories must not be modified after halt."
        )

        exit_code = self._determine_exit_code_for_exception(exception)
        halt_reason = self._halt_reason_for_exception(exception)
        suggested_fix = self._suggested_fix_for_exception(exception)

        # AC#2: Write halt report (best-effort).
        try:
            await write_halt_report(
                self.project_root,
                self.run_id,
                halted_story=story_slug,
                halt_reason=halt_reason,
                validation_history=[],
                last_agent_output="",
                suggested_fix=suggested_fix,
                failing_ac_ids=[],
                worktree_path=None,
                previous_run_id=self.previous_run_id,
            )
        except Exception as exc:
            logger.warning(
                "halt.write_halt_report_error",
                extra={"data": {"story": story_slug, "error": str(exc)}},
            )

        # AC#3: Flush provenance entry (best-effort).
        await self._flush_provenance(story_slug, halt_reason, accumulated_budget)

        # AC#4: Update run status (best-effort).
        try:
            await update_run_status(
                self.project_root,
                self.run_id,
                status=RunStatusValue.HALTED,
                last_completed_story=last_completed,
                budget=accumulated_budget,
            )
        except Exception as exc:
            logger.warning(
                "halt.update_run_status_error",
                extra={"data": {"story": story_slug, "error": str(exc)}},
            )

        # AC#5: Emit structured halt summary and JSONL event.
        self._emit_halt_summary(story_slug, halt_reason, accumulated_budget, completed_stories)
        self._emit_halt_jsonl_event(story_slug, halt_reason, accumulated_budget, completed_stories)

        return exit_code

    async def handle_graph_halt(
        self,
        *,
        story_state: StoryState,
        accumulated_budget: BudgetState,
        completed_stories: list[str],
        last_completed: str | None,
    ) -> int:
        """Handle a non-SUCCESS graph result.

        Coordinates the halt sequence for stories that completed graph
        execution but returned a non-SUCCESS terminal status (``ESCALATED``,
        ``RETRY``, etc.).  Extracts richer diagnostic data from the graph
        result and produces a comprehensive halt report with validation history.

        The ``finalize_node`` inside the engine graph may already have written
        a per-story halt report; this method writes the *run-level* summary
        that includes cross-story context (completed stories list) not
        available inside the graph.

        All artifact writes are best-effort — failures are logged at WARNING
        level and do **not** prevent the halt controller from returning an exit
        code.

        Args:
            story_state: Terminal story execution state returned by the graph.
            accumulated_budget: Budget state accumulated at halt time (may
                differ from ``story_state.budget`` if post-run accumulation
                occurred).
            completed_stories: Slugs of stories that completed successfully
                before this halt.
            last_completed: Slug of the most recently completed story, or
                ``None`` if this is the first story.

        Returns:
            CLI exit code per the D6 taxonomy.

        Raises:
            AssertionError: If the failing story slug is already present in
                *completed_stories*.
        """
        story_slug = str(story_state.story_id)

        # NFR2 guard parity with handle_halt(): never write to a completed
        # story's directory in the graph-halt path.
        assert story_slug not in completed_stories, (
            f"HaltController.handle_graph_halt() called for an already-completed story: {story_slug!r}. "
            "Completed story directories must not be modified after halt."
        )

        exit_code = self._determine_exit_code_for_graph_state(story_state)
        halt_reason = self._halt_reason_for_graph_state(story_state)
        validation_history = self._build_validation_history(story_state)
        last_agent_output = story_state.agent_output or ""
        suggested_fix = self._suggested_fix_for_graph_state(story_state)

        # AC#2: Write halt report with full diagnostic data (best-effort).
        # finalize_node already wrote a per-story report; we overwrite with
        # a run-level report that includes cross-story completed_stories context.
        failing_ac_ids = self._extract_failing_ac_ids_from_state(story_state)
        raw_worktree_path = getattr(story_state, "worktree_path", None)
        worktree_path = str(raw_worktree_path) if raw_worktree_path is not None else None
        try:
            await write_halt_report(
                self.project_root,
                self.run_id,
                halted_story=story_slug,
                halt_reason=halt_reason,
                validation_history=validation_history,
                last_agent_output=last_agent_output,
                suggested_fix=suggested_fix,
                failing_ac_ids=failing_ac_ids,
                worktree_path=worktree_path,
                previous_run_id=self.previous_run_id,
            )
        except Exception as exc:
            logger.warning(
                "halt.write_halt_report_error",
                extra={"data": {"story": story_slug, "error": str(exc)}},
            )

        # AC#3: Flush provenance entry (best-effort).
        await self._flush_provenance(story_slug, halt_reason, accumulated_budget)

        # AC#4: Update run status (best-effort).
        try:
            await update_run_status(
                self.project_root,
                self.run_id,
                status=RunStatusValue.HALTED,
                last_completed_story=last_completed,
                budget=accumulated_budget,
            )
        except Exception as exc:
            logger.warning(
                "halt.update_run_status_error",
                extra={"data": {"story": story_slug, "error": str(exc)}},
            )

        # AC#5: Emit structured halt summary and JSONL event.
        self._emit_halt_summary(story_slug, halt_reason, accumulated_budget, completed_stories)
        self._emit_halt_jsonl_event(story_slug, halt_reason, accumulated_budget, completed_stories)

        return exit_code

    # ---------------------------------------------------------------------------
    # Static helpers — exit code mapping
    # ---------------------------------------------------------------------------

    @staticmethod
    def _determine_exit_code_for_exception(exception: Exception) -> int:
        """Map an exception to a CLI exit code per the D6 taxonomy.

        Checks exception types from most-specific to least-specific to ensure
        correct resolution for subclass hierarchies (e.g., ``AgentBudgetError``
        before ``AgentError``).

        Args:
            exception: Exception that triggered the halt.

        Returns:
            Exit code aligned with the D6 taxonomy:
            1 (validation), 2 (agent/budget), 3 (config), 4 (SCM), 5 (internal).
        """
        if isinstance(exception, (AgentBudgetError, AgentTimeoutError, SandboxViolation)):
            return EXIT_AGENT
        if isinstance(exception, AgentError):
            return EXIT_AGENT
        if isinstance(exception, ScmError):
            # Covers WorktreeError, BranchError, and base ScmError.
            return EXIT_SCM
        if isinstance(exception, ValidationError):
            return EXIT_VALIDATION
        if isinstance(exception, (ConfigError, ContextError, ProjectError)):
            return EXIT_CONFIG
        if isinstance(exception, ArcwrightError):
            return EXIT_INTERNAL
        return EXIT_INTERNAL

    @staticmethod
    def _determine_exit_code_for_graph_state(story_state: StoryState) -> int:
        """Map a terminal graph state to a CLI exit code per the D6 taxonomy.

        Differentiates between budget-exceeded halts (exit code 2) and
        validation-exhaustion halts (exit code 1) by inspecting retry history.

        Args:
            story_state: Terminal story execution state from the graph.

        Returns:
            Exit code aligned with the D6 taxonomy:
            0 (success), 1 (validation exhaustion), 2 (budget exceeded), 5 (unknown terminal).
        """
        status = story_state.status
        if status == TaskState.SUCCESS:
            return EXIT_SUCCESS
        if status == TaskState.RETRY:
            # RETRY is a non-SUCCESS terminal in the halt path — validation.
            return EXIT_VALIDATION
        if status == TaskState.ESCALATED:
            # No retry history means the budget check node triggered escalation.
            if not story_state.retry_history:
                return EXIT_AGENT
            # Retry history present: exhaustion-based halt → validation exit code.
            return EXIT_VALIDATION
        return EXIT_INTERNAL

    # ---------------------------------------------------------------------------
    # Static helpers — halt reason strings
    # ---------------------------------------------------------------------------

    @staticmethod
    def _halt_reason_for_exception(exception: Exception) -> str:
        """Map an exception to a human-readable halt reason string.

        Returns one of the standard halt reason values defined in AC#5.

        Args:
            exception: Exception that triggered the halt.

        Returns:
            Human-readable halt reason string.
        """
        if isinstance(exception, AgentTimeoutError):
            return "SDK error"
        if isinstance(exception, AgentBudgetError):
            return "budget exceeded"
        if isinstance(exception, SandboxViolation):
            return "sandbox violation"
        if isinstance(exception, AgentError):
            details = getattr(exception, "details", None)
            if isinstance(details, dict):
                if details.get("error_category") == "sdk":
                    return "SDK error"
                original_error = str(details.get("original_error", "")).lower()
                if any(token in original_error for token in ("timeout", "httpstatus", "connection", "sdk")):
                    return "SDK error"
            if "sdk" in str(exception).lower():
                return "SDK error"
            return "agent error"
        if isinstance(exception, ScmError):
            return "SCM error"
        if isinstance(exception, ValidationError):
            return "validation exhaustion"
        if isinstance(exception, (ConfigError, ContextError, ProjectError)):
            return "config/context error"
        return "internal error"

    @staticmethod
    def _halt_reason_for_graph_state(story_state: StoryState) -> str:
        """Derive a human-readable halt reason from the terminal graph state.

        Mirrors the logic of ``_derive_halt_reason()`` from ``engine/nodes.py``
        but maps to the user-facing halt reason vocabulary from AC#5.

        Args:
            story_state: Terminal story execution state from the graph.

        Returns:
            Human-readable halt reason string.
        """
        status = story_state.status
        if status == TaskState.RETRY:
            return "validation exhaustion"
        if status == TaskState.ESCALATED:
            if not story_state.retry_history:
                return "budget exceeded"
            last = story_state.retry_history[-1]
            outcome_str = str(last.outcome) if hasattr(last, "outcome") else ""
            if outcome_str == "fail_v6":
                return "validation exhaustion"
            if story_state.retry_count >= story_state.config.limits.retry_budget:
                return "validation exhaustion"
            return "validation exhaustion"
        return "internal error"

    # ---------------------------------------------------------------------------
    # Static helpers — suggested fix strings
    # ---------------------------------------------------------------------------

    @staticmethod
    def _suggested_fix_for_exception(exception: Exception) -> str:
        """Derive a suggested fix message from an exception type.

        Args:
            exception: Exception that triggered the halt.

        Returns:
            Human-readable suggested fix string.
        """
        if isinstance(exception, AgentBudgetError):
            return (
                "Budget ceiling was exceeded. Consider increasing `limits.cost_per_run` "
                "or `limits.tokens_per_story` in pyproject.toml."
            )
        if isinstance(exception, SandboxViolation):
            return (
                "Agent attempted a file operation outside the project boundary. "
                "Review agent file access patterns and ensure the story does not require "
                "external file system access."
            )
        if isinstance(exception, AgentTimeoutError):
            return (
                "Agent session exceeded the time budget. Consider increasing "
                "`limits.timeout_per_story` or breaking the story into smaller subtasks."
            )
        if isinstance(exception, AgentError):
            return (
                "Agent invocation failed. Check API key validity, network connectivity, "
                "and the agent invocation logs for details."
            )
        if isinstance(exception, ScmError):
            return (
                "A git operation failed. Review the repository state for conflicts, "
                "permission issues, or detached HEAD conditions."
            )
        if isinstance(exception, ValidationError):
            return "Review the validation failures and address the identified issues."
        if isinstance(exception, (ConfigError, ContextError, ProjectError)):
            return (
                "Configuration or context error. Verify pyproject.toml settings, "
                "BMAD artifact paths, and that arcwright-ai init has been run."
            )
        return "Review the error details in the run log and check for configuration issues."

    @staticmethod
    def _suggested_fix_for_graph_state(story_state: StoryState) -> str:
        """Derive a suggested fix message from the terminal graph state.

        Mirrors the logic of ``_derive_suggested_fix()`` from ``engine/nodes.py``.

        Args:
            story_state: Terminal story execution state from the graph.

        Returns:
            Human-readable suggested fix string.
        """
        if not story_state.retry_history:
            return (
                "Budget ceiling was exceeded. Consider increasing `limits.cost_per_run` "
                "or `limits.tokens_per_story` in pyproject.toml."
            )
        last = story_state.retry_history[-1]
        outcome_str = str(last.outcome) if hasattr(last, "outcome") else ""
        if outcome_str == "fail_v6":
            return "Fix the V6 invariant rule violations and re-run the story."
        feedback = getattr(last, "feedback", None)
        if feedback is not None:
            feedback_per_criterion = getattr(feedback, "feedback_per_criterion", {})
            if feedback_per_criterion:
                parts = [f"AC {ac_id}: {detail}" for ac_id, detail in feedback_per_criterion.items()]
                return "\n".join(parts)
        return "Review the validation failures and address the identified issues."

    # ---------------------------------------------------------------------------
    # Private instance helpers
    # ---------------------------------------------------------------------------

    async def _flush_provenance(
        self,
        story_slug: str,
        halt_reason: str,
        accumulated_budget: BudgetState,
    ) -> None:
        """Append a halt provenance entry to the failing story's validation.md.

        Best-effort: failures are logged at WARNING level.

        Args:
            story_slug: Slug of the story that halted.
            halt_reason: Human-readable halt reason string.
            accumulated_budget: Budget state at halt time.
        """
        provenance_path = (
            self.project_root / DIR_ARCWRIGHT / DIR_RUNS / self.run_id / DIR_STORIES / story_slug / VALIDATION_FILENAME
        )
        entry = ProvenanceEntry(
            decision=f"Halt: {halt_reason}",
            alternatives=[],
            rationale=(
                f"Budget state: invocations={accumulated_budget.invocation_count}, "
                f"tokens={accumulated_budget.total_tokens}, "
                f"cost=${accumulated_budget.estimated_cost}"
            ),
            ac_references=[],
            timestamp=datetime.now(tz=UTC).isoformat(),
        )
        try:
            await append_entry(provenance_path, entry)
        except Exception as exc:
            logger.warning(
                "halt.flush_provenance_error",
                extra={"data": {"story": story_slug, "error": str(exc)}},
            )

    def _emit_halt_summary(
        self,
        story_slug: str,
        halt_reason: str,
        accumulated_budget: BudgetState,
        completed_stories: list[str],
    ) -> None:
        """Output a structured halt summary to stderr.

        Displays the full halt context per AC#5: completed stories list,
        failing story, halt reason, budget consumption, and the resume command.

        Args:
            story_slug: Slug of the story that caused the halt.
            halt_reason: Human-readable halt reason string.
            accumulated_budget: Budget state at halt time.
            completed_stories: Slugs of stories that completed successfully.
        """
        resume_cmd = self._build_resume_command()
        typer.echo(f"\n✗ Epic {self.epic_spec} halted at story {story_slug}.", err=True)
        typer.echo(f"  Stories completed ({len(completed_stories)}): {completed_stories}", err=True)
        typer.echo(f"  Halted story: {story_slug}", err=True)
        typer.echo(f"  Halt reason: {halt_reason}", err=True)
        typer.echo(
            f"  💰 Budget: ${accumulated_budget.estimated_cost} cost | {accumulated_budget.total_tokens} tokens",
            err=True,
        )
        typer.echo(f"  🔁 Resume with: {resume_cmd}", err=True)

    def _emit_halt_jsonl_event(
        self,
        story_slug: str,
        halt_reason: str,
        accumulated_budget: BudgetState,
        completed_stories: list[str],
    ) -> None:
        """Emit a structured JSONL run.halt event via the arcwright_ai root logger.

        Args:
            story_slug: Slug of the story that caused the halt.
            halt_reason: Human-readable halt reason string.
            accumulated_budget: Budget state at halt time.
            completed_stories: Slugs of stories that completed successfully.
        """
        root_logger = logging.getLogger("arcwright_ai")
        root_logger.info(
            "run.halt",
            extra={
                "data": {
                    "halted_story": story_slug,
                    "reason": halt_reason,
                    "completed_count": len(completed_stories),
                    "budget_cost": str(accumulated_budget.estimated_cost),
                    "budget_tokens": accumulated_budget.total_tokens,
                }
            },
        )

    def _build_resume_command(self) -> str:
        """Build the resume CLI command string for display in halt output.

        Returns:
            Formatted resume command string, e.g.
            ``"arcwright-ai dispatch --epic EPIC-5 --resume"``.
        """
        epic_part = self.epic_spec
        if epic_part.lower().startswith("epic-"):
            epic_part = epic_part[_EPIC_PREFIX_LEN:]
        return f"arcwright-ai dispatch --epic EPIC-{epic_part} --resume"

    @staticmethod
    def _build_validation_history(story_state: StoryState) -> list[dict[str, Any]]:
        """Build a validation history list from story state retry history.

        Mirrors the logic of ``_build_validation_history_dicts()`` from
        ``engine/nodes.py`` without importing from the engine package at runtime.

        Args:
            story_state: Story execution state containing retry history.

        Returns:
            List of dicts with keys ``"attempt"``, ``"outcome"``, and
            ``"failures"``.
        """
        history: list[dict[str, Any]] = []
        for i, result in enumerate(story_state.retry_history):
            outcome_str = str(result.outcome) if hasattr(result, "outcome") else "unknown"
            failures = ""
            if outcome_str == "fail_v6":
                v6_result = getattr(result, "v6_result", None)
                if v6_result is not None and hasattr(v6_result, "failures"):
                    failures = f"V6: {len(v6_result.failures)} checks failed"
            else:
                feedback = getattr(result, "feedback", None)
                if feedback is not None:
                    unmet = getattr(feedback, "unmet_criteria", [])
                    if unmet:
                        failures = f"V3: ACs {', '.join(unmet)}"
            history.append({"attempt": i + 1, "outcome": outcome_str, "failures": failures})
        return history

    @staticmethod
    def _normalize_ac_id(raw_value: object) -> str | None:
        """Normalize raw AC identifier text to a numeric AC ID.

        Args:
            raw_value: Raw AC identifier value from validation feedback.

        Returns:
            Numeric AC ID as a string (e.g. ``"3"``), or ``None`` when
            no AC ID can be parsed.
        """
        match = re.search(r"(\d+)", str(raw_value))
        if match is None:
            return None
        return match.group(1)

    @staticmethod
    def _extract_failing_ac_ids_from_state(story_state: StoryState) -> list[str]:
        """Extract failing AC IDs from a terminal story state's retry history.

        Inspects V3 feedback ``unmet_criteria`` and V6 ``failures`` across all
        retry attempts and returns the unique set of AC identifier strings.

        Args:
            story_state: Terminal story execution state from the graph.

        Returns:
            Sorted list of unique failing AC ID strings.  An empty list is
            returned when no retry history is available (e.g. budget-exceeded
            halts with no validation attempts).
        """
        ac_ids: set[str] = set()
        for result in story_state.retry_history:
            feedback = getattr(result, "feedback", None)
            if feedback is not None:
                unmet = getattr(feedback, "unmet_criteria", [])
                for ac_ref in unmet:
                    normalized = HaltController._normalize_ac_id(ac_ref)
                    if normalized is not None:
                        ac_ids.add(normalized)
            v6_result = getattr(result, "v6_result", None)
            if v6_result is not None and hasattr(v6_result, "failures"):
                for failure in v6_result.failures:
                    ac_ref = getattr(failure, "ac_id", None)
                    if ac_ref is None:
                        continue
                    normalized = HaltController._normalize_ac_id(ac_ref)
                    if normalized is not None:
                        ac_ids.add(normalized)
        return sorted(ac_ids, key=int)
