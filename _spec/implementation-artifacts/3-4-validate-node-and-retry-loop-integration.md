# Story 3.4: Validate Node & Retry Loop Integration

Status: done

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

## Story

As a developer dispatching stories,
I want the validation node wired into the LangGraph StateGraph with retry logic that re-dispatches the agent on V3 failure up to a configurable maximum,
so that the system automatically fixes validation failures without human intervention, and halts loudly when retries are exhausted.

## Acceptance Criteria (BDD)

1. **Given** the `validate_node` function in `engine/nodes.py` **When** it processes a story after `agent_dispatch` **Then** it invokes `run_validation_pipeline()` from `validation/pipeline.py` with parameters: `agent_output=state.agent_output`, `story_path=state.story_path`, `project_root=state.project_root`, `model=state.config.model.version`, `cwd=state.project_root`, `sandbox=validate_path`, `attempt_number=state.retry_count + 1`. If `state.agent_output` is `None`, it raises `ValidationError("validate_node requires agent_output from agent_dispatch")` immediately.

2. **Given** the pipeline returns `PipelineOutcome.PASS` **When** the validate node evaluates the result **Then** it transitions `state.status` to `TaskState.SUCCESS`, stores the `PipelineResult` in `state.validation_result`, appends the result to `state.retry_history`, updates `state.budget` with `pipeline_result.tokens_used` and `pipeline_result.cost`, writes a validation checkpoint to the run directory, emits `validation.pass` structured log event, and routes to the `commit` node via `route_validation`.

3. **Given** the pipeline returns `PipelineOutcome.FAIL_V3` and `state.retry_count < state.config.limits.retry_budget` **When** the validate node evaluates the result **Then** it transitions `state.status` to `TaskState.RETRY`, increments `state.retry_count` by 1, stores the `PipelineResult` (with its `ReflexionFeedback`) in `state.validation_result`, appends the result to `state.retry_history`, updates `state.budget` with pipeline costs, writes a validation checkpoint, emits `validation.fail` structured log event with `retry_count` and `outcome: "retry"`, and routes back to `budget_check` → `agent_dispatch` via `route_validation`.

4. **Given** the pipeline returns `PipelineOutcome.FAIL_V3` and `state.retry_count >= state.config.limits.retry_budget` **When** the validate node evaluates the result **Then** it transitions `state.status` to `TaskState.ESCALATED`, increments `state.retry_count` by 1, stores the `PipelineResult` in `state.validation_result`, appends to `state.retry_history`, updates budget, writes a validation checkpoint, generates a structured halt report (per FR11) written to the run directory as `halt-report.md`, emits `validation.fail` with `outcome: "escalated"` and `run.halt` with `reason: "max_retries_exhausted"`, and routes to `END` via `route_validation`.

5. **Given** the pipeline returns `PipelineOutcome.FAIL_V6` **When** the validate node evaluates the result **Then** it transitions `state.status` to `TaskState.ESCALATED` **immediately** — no retry regardless of `retry_count`. Stores the result, appends to retry_history, updates budget (V6 costs are zero so budget change is zero), writes a validation checkpoint, generates a structured halt report written as `halt-report.md`, emits `validation.fail` with `outcome: "fail_v6"` and `run.halt` with `reason: "v6_invariant_failure"`, and routes to `END` via `route_validation`.

6. **Given** the halt report generation function `_generate_halt_report` **When** it creates a halt report for an escalated story **Then** the markdown report includes: story ID (`state.story_id`), failing acceptance criteria IDs (from `pipeline_result.feedback.unmet_criteria` if V3, or V6 failure summary if V6), total retry count (`state.retry_count`), retry history table (one row per attempt showing attempt number, outcome, and failure summary), last agent output truncated to 2000 characters, and a suggested fix section (from `pipeline_result.feedback.feedback_per_criterion` if V3, or "Fix V6 invariant violations and re-run" if V6).

7. **Given** `StoryState` in `engine/state.py` **When** this story updates it **Then** `validation_result` type changes from `dict[str, Any] | None` to `PipelineResult | None = None` (import `PipelineResult` from `arcwright_ai.validation.pipeline`), and a new field `retry_history: list[PipelineResult] = Field(default_factory=list)` is added to accumulate validation results across attempts. The `from typing import Any` import is removed if no longer used. The docstring for `validation_result` is updated to reflect the concrete type.

8. **Given** `build_prompt` in `agent/prompt.py` **When** this story extends it **Then** the function signature changes to `def build_prompt(bundle: ContextBundle, *, feedback: ReflexionFeedback | None = None) -> str`. When `feedback` is not None and `feedback.passed` is False, a `## Previous Validation Feedback` section is appended to the prompt containing: the attempt number (`feedback.attempt_number`), the list of unmet criteria IDs (`feedback.unmet_criteria`), and for each unmet criterion, the specific failure description and suggested fix from `feedback.feedback_per_criterion`. This section is omitted when `feedback` is None or `feedback.passed` is True.

9. **Given** `agent_dispatch_node` in `engine/nodes.py` **When** this story modifies it for retry support **Then** before calling `build_prompt`, it extracts feedback: `feedback = state.validation_result.feedback if state.validation_result is not None else None`. It passes `feedback=feedback` to `build_prompt`. On retry attempts, the log event `agent.dispatch` includes `"retry_count": state.retry_count` and `"has_feedback": feedback is not None` in its data dict. No other changes to agent_dispatch_node.

10. **Given** the `route_validation` function in `engine/nodes.py` **When** this story is implemented **Then** `route_validation` remains unchanged — it already routes based on `TaskState.SUCCESS` → `"success"`, `TaskState.RETRY` → `"retry"`, and all other states → `"escalated"`. The `validate_node` sets the correct `TaskState` before returning. No changes to `route_validation`.

11. **Given** the `engine/graph.py` module **When** this story is implemented **Then** the graph structure is unchanged — `build_story_graph()` already has the correct conditional edges: `validate → (success: commit, retry: budget_check, escalated: END)`. No modifications to graph.py.

12. **Given** existing tests in `tests/test_engine/test_nodes.py` **When** this story replaces the validate_node placeholder **Then** the existing test `test_validate_node_transitions_to_success` is updated to monkeypatch `run_validation_pipeline` to return a `PipelineResult` with `outcome=PASS` (the test previously asserted the placeholder's automatic SUCCESS transition). Fixture `mock_pipeline_pass` is added to monkeypatch the pipeline in the `arcwright_ai.engine.nodes` module namespace.

13. **Given** existing tests in `tests/test_engine/test_graph.py` **When** this story replaces the validate_node placeholder **Then** a `mock_pipeline` fixture is added that monkeypatches `run_validation_pipeline` in `arcwright_ai.engine.nodes` to return a PASS result. The existing `test_graph_success_path_end_to_end` and `test_graph_invocation_no_errors` tests are updated to use both `mock_agent` and `mock_pipeline` fixtures. The existing `test_graph_budget_exceeded_path_escalates_and_exits` test is unaffected (budget check triggers before validate_node runs).

14. **Given** new unit tests for `validate_node` in `tests/test_engine/test_nodes.py` **When** the test suite runs **Then** tests cover: (a) success path — pipeline PASS → status SUCCESS, validation_result populated, retry_history has 1 entry, budget updated; (b) V3 failure within retry budget — pipeline FAIL_V3 with retry_count=0 and retry_budget=3 → status RETRY, retry_count incremented to 1, validation_result has feedback; (c) V3 failure at retry limit — pipeline FAIL_V3 with retry_count=3 and retry_budget=3 → status ESCALATED, halt report written; (d) V6 failure immediate escalation — pipeline FAIL_V6 → status ESCALATED regardless of retry_count, halt report written; (e) retry_history accumulates across attempts — multiple validation runs accumulate in list; (f) budget updated with pipeline costs — tokens_used and cost added to BudgetState; (g) validation checkpoint written to run directory at expected path; (h) halt report written on escalation (both V3 exhaust and V6 failure paths); (i) ValidationError raised when agent_output is None; (j) structured log events emitted — `validation.pass` on success, `validation.fail` + `run.halt` on escalation.

15. **Given** new integration tests in `tests/test_engine/test_graph.py` **When** the test suite runs **Then** tests cover: (a) success path — pipeline returns PASS, graph traverses preflight → budget_check → agent_dispatch → validate → commit → END, final status is SUCCESS; (b) single-retry path — pipeline returns FAIL_V3 on first call, PASS on second call, graph traverses validate → budget_check → agent_dispatch → validate → commit → END, final status is SUCCESS, retry_count is 1; (c) max-retry escalated path — pipeline returns FAIL_V3 on every call with `retry_budget=2`, graph escalates after 3 attempts (fail → fail → fail → ESCALATED), final status is ESCALATED with halt report.

16. **Given** new tests for `build_prompt` in `tests/test_agent/test_prompt.py` **When** the test suite runs **Then** tests cover: (a) `build_prompt` with `feedback=None` produces no feedback section (existing behavior preserved); (b) `build_prompt` with `ReflexionFeedback(passed=False, ...)` appends "## Previous Validation Feedback" section containing unmet criteria and failure descriptions; (c) `build_prompt` with `ReflexionFeedback(passed=True)` does not append feedback section (passed feedback is not injected).

17. **Given** story implementation is complete **When** `ruff check .` is run **Then** zero violations.

18. **Given** story implementation is complete **When** `.venv/bin/python -m mypy --strict src/` is run **Then** zero errors.

19. **Given** all public classes and functions **When** every docstring is inspected **Then** each conforms to Google-style (Args, Returns, Raises sections where appropriate).

20. **Given** any existing tests in the full test suite **When** this story is complete **Then** no existing tests break beyond the explicitly updated tests in ACs #12 and #13. All validation pipeline tests (`test_pipeline.py`), V6 tests (`test_v6_invariant.py`), and V3 tests (`test_v3_reflexion.py`) remain unmodified and passing.

## Tasks / Subtasks

- [x] Task 1: Update `StoryState` in `engine/state.py` (AC: #7)
  - [x] 1.1: Change `validation_result` type from `dict[str, Any] | None` to `PipelineResult | None = None`:
    ```python
    validation_result: PipelineResult | None = None
    ```
  - [x] 1.2: Add `retry_history` field:
    ```python
    retry_history: list[PipelineResult] = Field(default_factory=list)
    ```
  - [x] 1.3: Add import `from arcwright_ai.validation.pipeline import PipelineResult  # noqa: TC001`
  - [x] 1.4: Remove `from typing import Any` if no longer used elsewhere in the file
  - [x] 1.5: Update `validation_result` docstring:
    ```
    validation_result: Last validation pipeline result (None until validation runs).
    retry_history: Accumulated validation results across retry attempts.
    ```

- [x] Task 2: Extend `build_prompt` in `agent/prompt.py` for feedback injection (AC: #8)
  - [x] 2.1: Update function signature:
    ```python
    def build_prompt(bundle: ContextBundle, *, feedback: ReflexionFeedback | None = None) -> str:
    ```
  - [x] 2.2: Add conditional feedback section at the end of the prompt:
    ```python
    if feedback is not None and not feedback.passed:
        feedback_lines: list[str] = [
            "## Previous Validation Feedback",
            "",
            f"**Attempt {feedback.attempt_number} failed.** The following acceptance criteria were NOT met:",
            "",
        ]
        for ac_id in feedback.unmet_criteria:
            detail = feedback.feedback_per_criterion.get(ac_id, "No details provided")
            feedback_lines.append(f"### AC {ac_id}")
            feedback_lines.append(detail)
            feedback_lines.append("")
        feedback_lines.append(
            "**Fix all unmet criteria above before completing this story.**"
        )
        parts.append("\n".join(feedback_lines))
    ```
  - [x] 2.3: Add `TYPE_CHECKING` import for `ReflexionFeedback`:
    ```python
    if TYPE_CHECKING:
        from arcwright_ai.core.types import ContextBundle
        from arcwright_ai.validation.v3_reflexion import ReflexionFeedback
    ```

- [x] Task 3: Replace `validate_node` placeholder in `engine/nodes.py` (AC: #1, #2, #3, #4, #5, #6, #9, #10)
  - [x] 3.1: Add new imports:
    ```python
    from arcwright_ai.core.constants import HALT_REPORT_FILENAME, VALIDATION_FILENAME
    from arcwright_ai.core.exceptions import AgentError, ContextError, ValidationError
    from arcwright_ai.validation.pipeline import PipelineOutcome, PipelineResult, run_validation_pipeline
    ```
    Note: `ContextError` and `AgentError` are already imported. `ValidationError` is new. Add `HALT_REPORT_FILENAME` and `VALIDATION_FILENAME` to the existing `from arcwright_ai.core.constants import (...)` block.
  - [x] 3.2: Add `PipelineResult` to `TYPE_CHECKING` imports (or runtime import as needed — since `PipelineResult` is used in the function body for type annotations in locals, a `TYPE_CHECKING` import is NOT sufficient; it must be a runtime import). Actually, `PipelineResult` is only used as the return type of `run_validation_pipeline` and it's the type of `state.validation_result` — the validate_node doesn't need to reference the class name at runtime. But it IS used in `_generate_halt_report` type annotation. Use runtime import since it's used in function bodies.
  - [x] 3.3: Replace the `validate_node` placeholder with real implementation:
    ```python
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
            state.project_root
            / DIR_ARCWRIGHT
            / DIR_RUNS
            / str(state.run_id)
            / DIR_STORIES
            / str(state.story_id)
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
            halt_report = _generate_halt_report(
                state, pipeline_result, new_retry_history, reason="v6_invariant_failure"
            )
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
            halt_report = _generate_halt_report(
                state, pipeline_result, new_retry_history, reason="max_retries_exhausted"
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
    ```
  - [x] 3.4: Modify `agent_dispatch_node` to inject feedback on retry (AC: #9):
    ```python
    # Before build_prompt call, add:
    feedback = state.validation_result.feedback if state.validation_result is not None else None
    prompt = build_prompt(state.context_bundle, feedback=feedback)
    ```
    Update the `agent.dispatch` log event to include retry context:
    ```python
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
    ```
  - [x] 3.5: Add private helper `_serialize_validation_checkpoint`:
    ```python
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
    ```
  - [x] 3.6: Add private helper `_generate_halt_report`:
    ```python
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
            f"- **Status**: ESCALATED",
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
            for check in last_result.v6_result.results:
                if not check.passed:
                    lines.append(
                        f"- **{check.check_name}**: {check.failure_detail or 'Failed'}"
                    )
            lines.append("")

        # Retry history table
        lines.extend([
            "## Retry History",
            "",
            "| Attempt | Outcome | Failures |",
            "|---------|---------|----------|",
        ])
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
            lines.append(
                "Fix the V6 invariant rule violations listed above and re-run the story."
            )
        else:
            lines.append("Review the validation failures and address underlying issues.")
        lines.append("")

        # Resume command
        lines.extend([
            "## Resume Command",
            "",
            f"```bash",
            f"arcwright-ai resume {state.run_id}",
            f"```",
            "",
        ])

        return "\n".join(lines)
    ```

- [x] Task 4: Update existing tests in `tests/test_engine/test_nodes.py` (AC: #12)
  - [x] 4.1: Add `mock_pipeline_pass` fixture:
    ```python
    @pytest.fixture
    def mock_pipeline_pass(monkeypatch: pytest.MonkeyPatch) -> PipelineResult:
        """Monkeypatch run_validation_pipeline to return PASS result."""
        from arcwright_ai.validation.pipeline import PipelineOutcome, PipelineResult
        from arcwright_ai.validation.v6_invariant import V6CheckResult, V6ValidationResult

        v6 = V6ValidationResult(passed=True, results=[
            V6CheckResult(check_name="file_existence", passed=True),
        ])
        result = PipelineResult(
            passed=True,
            outcome=PipelineOutcome.PASS,
            v6_result=v6,
            tokens_used=300,
            cost=Decimal("0.005"),
        )

        async def _mock(*args: object, **kwargs: object) -> PipelineResult:
            return result

        monkeypatch.setattr("arcwright_ai.engine.nodes.run_validation_pipeline", _mock)
        return result
    ```
  - [x] 4.2: Update `test_validate_node_transitions_to_success` to use the new fixture:
    ```python
    @pytest.mark.asyncio
    async def test_validate_node_transitions_to_success(
        make_story_state: StoryState,
        mock_pipeline_pass: PipelineResult,
    ) -> None:
        state = make_story_state.model_copy(
            update={
                "status": TaskState.VALIDATING,
                "agent_output": "Mock implementation output",
                "project_root": make_story_state.project_root,
            }
        )
        result = await validate_node(state)
        assert result.status == TaskState.SUCCESS
        assert result.validation_result is not None
        assert result.validation_result.passed is True
    ```
    **Critical**: must provide a `tmp_path`-backed state or monkeypatch `asyncio.to_thread` and `write_text_async` so the checkpoint write doesn't fail. Use `tmp_path` in the fixture for `project_root`.

- [x] Task 5: Add new validate_node unit tests in `tests/test_engine/test_nodes.py` (AC: #14)
  - [x] 5.1: Add `mock_pipeline_fail_v3` fixture (returns FAIL_V3 with feedback)
  - [x] 5.2: Add `mock_pipeline_fail_v6` fixture (returns FAIL_V6)
  - [x] 5.3: Add `validate_ready_state` fixture — state with VALIDATING status, agent_output populated, `tmp_path` project_root
  - [x] 5.4: Test `test_validate_node_v3_fail_within_retry_budget_transitions_to_retry` — retry_count=0, retry_budget=3 → RETRY, retry_count becomes 1
  - [x] 5.5: Test `test_validate_node_v3_fail_at_retry_limit_transitions_to_escalated` — retry_count=3, retry_budget=3 → ESCALATED, halt report written
  - [x] 5.6: Test `test_validate_node_v6_fail_transitions_to_escalated_immediately` — FAIL_V6, retry_count=0 → ESCALATED, halt report written, no retry
  - [x] 5.7: Test `test_validate_node_updates_budget_with_pipeline_costs` — budget.total_tokens and budget.estimated_cost include pipeline costs
  - [x] 5.8: Test `test_validate_node_accumulates_retry_history` — after each call, retry_history grows by one entry
  - [x] 5.9: Test `test_validate_node_writes_validation_checkpoint` — `validation.md` exists at expected path after validate_node runs
  - [x] 5.10: Test `test_validate_node_writes_halt_report_on_v3_escalation` — `halt-report.md` exists with expected content on MAX_RETRIES escalation
  - [x] 5.11: Test `test_validate_node_writes_halt_report_on_v6_failure` — `halt-report.md` exists with V6 failure content
  - [x] 5.12: Test `test_validate_node_raises_validation_error_when_agent_output_missing` — agent_output=None → `ValidationError`
  - [x] 5.13: Test `test_validate_node_emits_validation_pass_log_event` — caplog captures `validation.pass` with expected data
  - [x] 5.14: Test `test_validate_node_emits_validation_fail_and_halt_log_events` — caplog captures `validation.fail` + `run.halt` on escalation
  - [x] 5.15: Test `test_validate_node_retry_includes_feedback_in_validation_result` — after RETRY, `state.validation_result.feedback` is populated and has `unmet_criteria`

- [x] Task 6: Update existing graph integration tests in `tests/test_engine/test_graph.py` (AC: #13)
  - [x] 6.1: Add `mock_pipeline` fixture that monkeypatches `run_validation_pipeline` in `arcwright_ai.engine.nodes`:
    ```python
    @pytest.fixture
    def mock_pipeline(monkeypatch: pytest.MonkeyPatch) -> None:
        """Monkeypatch run_validation_pipeline for graph integration tests."""
        from arcwright_ai.validation.pipeline import PipelineOutcome, PipelineResult
        from arcwright_ai.validation.v6_invariant import V6CheckResult, V6ValidationResult

        v6 = V6ValidationResult(passed=True, results=[
            V6CheckResult(check_name="file_existence", passed=True),
        ])
        result = PipelineResult(
            passed=True,
            outcome=PipelineOutcome.PASS,
            v6_result=v6,
        )

        async def _mock(*args: object, **kwargs: object) -> PipelineResult:
            return result

        monkeypatch.setattr("arcwright_ai.engine.nodes.run_validation_pipeline", _mock)
    ```
  - [x] 6.2: Update `test_graph_success_path_end_to_end` to include `mock_pipeline` fixture
  - [x] 6.3: Update `test_graph_invocation_no_errors` to include `mock_pipeline` fixture

- [x] Task 7: Add new graph integration tests in `tests/test_engine/test_graph.py` (AC: #15)
  - [x] 7.1: Test `test_graph_retry_path_v3_fail_then_pass` — first pipeline call returns FAIL_V3, second returns PASS. Final status SUCCESS, retry_count=1. Use a counter-based mock:
    ```python
    call_count = 0
    async def _mock_retry(*args, **kwargs):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            return fail_v3_result
        return pass_result
    ```
  - [x] 7.2: Test `test_graph_max_retry_escalated_path` — pipeline always returns FAIL_V3. Configure `retry_budget=2` in RunConfig. Final status ESCALATED after 3 calls (retry_count=2 on first call ≥ no, retry_count starts 0 < 2 → retry, then 1 < 2 → retry, then 2 >= 2 → escalated).

- [x] Task 8: Add new tests for `build_prompt` in `tests/test_agent/test_prompt.py` (AC: #16)
  - [x] 8.1: Test `test_build_prompt_without_feedback_has_no_feedback_section` — call with `feedback=None`, assert "Previous Validation Feedback" not in output
  - [x] 8.2: Test `test_build_prompt_with_failed_feedback_includes_feedback_section` — call with `ReflexionFeedback(passed=False, unmet_criteria=["2"], feedback_per_criterion={"2": "Missing X"}, attempt_number=1)`, assert "## Previous Validation Feedback" in output, assert "AC 2" in output, assert "Missing X" in output
  - [x] 8.3: Test `test_build_prompt_with_passed_feedback_has_no_feedback_section` — call with `ReflexionFeedback(passed=True, attempt_number=1)`, assert "Previous Validation Feedback" not in output

- [x] Task 9: Validate all quality gates (AC: #17, #18, #19, #20)
  - [x] 9.1: Run `ruff check .` — zero violations
  - [x] 9.2: Run `ruff format --check .` — no formatting diffs
  - [x] 9.3: Run `.venv/bin/python -m mypy --strict src/` — zero errors
  - [x] 9.4: Run `pytest tests/test_engine/test_nodes.py -v` — all tests (old + new) pass
  - [x] 9.5: Run `pytest tests/test_engine/test_graph.py -v` — all tests (old + new) pass
  - [x] 9.6: Run `pytest tests/test_agent/test_prompt.py -v` — all tests (old + new) pass
  - [x] 9.7: Run `pytest` — full test suite passes, zero regressions
  - [x] 9.8: Verify every public function/class has a Google-style docstring

## Dev Notes

### Critical Architecture Constraints

#### Package Dependency DAG — `engine/` Position
```
cli → engine → {validation, agent, context, output, scm} → core
```
- `engine/nodes.py` imports from `validation/`, `agent/`, `context/`, `core/` — all permitted.
- `engine/state.py` imports from `validation/pipeline.py` (for `PipelineResult` type) — permitted since `engine → validation` is allowed.
- The validate node calls `run_validation_pipeline()` — this is the engine mediating between the validation package and the graph.
- **No new cross-domain imports introduced** — all imports follow the existing DAG.

#### D1: State Model — PipelineResult Integration
`StoryState.validation_result` changes from `dict[str, Any] | None` to `PipelineResult | None`. This is the type migration deferred from Story 2.1 (listed in Epic 2 tech debt). `PipelineResult` is a frozen `ArcwrightModel`, stored in the mutable `StoryState`. Pydantic handles this natively (frozen models inside mutable parents).

The new `retry_history: list[PipelineResult]` field uses `Field(default_factory=list)` per the "no mutable defaults" rule from Epic 1 pitfalls.

#### D2: Retry & Halt Strategy — Implementation Contract
This story implements the full retry/halt logic per architecture Decision 2:
- **V3 failures are retryable**: `PipelineOutcome.FAIL_V3` triggers RETRY if within budget, ESCALATED if not.
- **V6 failures are NOT retryable**: `PipelineOutcome.FAIL_V6` triggers immediate ESCALATED — V6 failures are objective rule violations requiring human intervention.
- **Retry budget from config**: `state.config.limits.retry_budget` (configurable, default 3) — NOT the `MAX_RETRIES` constant. The constant exists as a fallback default but the config is the runtime authority.
- **Check semantics**: `state.retry_count >= config.limits.retry_budget` means: with `retry_budget=3`, the story gets 1 initial attempt + up to 3 retries = 4 total attempts before escalation.

#### D2: Feedback Injection in Retry Loop
When the agent is re-dispatched after a V3 failure:
1. `validate_node` stores `PipelineResult` (with `ReflexionFeedback`) in `state.validation_result`
2. `route_validation` returns `"retry"` → routes to `budget_check`
3. `budget_check_node` transitions RETRY → RUNNING
4. `agent_dispatch_node` extracts `state.validation_result.feedback` and passes to `build_prompt`
5. `build_prompt` appends a "## Previous Validation Feedback" section with unmet criteria and fix suggestions
6. Agent receives the full context bundle PLUS specific feedback on what failed

#### D5: Validation Checkpoint Writing
The validate node writes `validation.md` to the run directory at every attempt (success or failure). This is a checkpoint per the D5 write policy: "run directory files are written as checkpoints at state transitions only." The halt report (`halt-report.md`) is written only on escalation.

Both files are written to: `.arcwright-ai/runs/<run-id>/stories/<story-slug>/`

#### D6: Error Handling — validate_node as Pipeline Error Boundary
The validate_node is the error boundary for the validation pipeline:
- **Structured failures** (`PipelineResult` with FAIL_V3 / FAIL_V6) → handled by routing logic (RETRY or ESCALATED)
- **Unexpected errors** (`ValidationError` from pipeline — e.g. filesystem crash, SDK crash during V3) → propagated uncaught to the graph, which terminates the run
- **Missing precondition** (`agent_output is None`) → raise `ValidationError` immediately

The validate_node does NOT catch `ValidationError` from the pipeline. If the pipeline raises, it's a true internal error that should halt the entire run.

#### D8: Structured Logging Events
New events emitted by the validate node:
- `validation.pass` — story passed all validation, includes `story`, `attempt`, `tokens_used`
- `validation.fail` — story failed validation, includes `story`, `outcome` ("retry" | "escalated" | "fail_v6"), `retry_count`
- `run.halt` — story escalated, includes `story`, `reason` ("max_retries_exhausted" | "v6_invariant_failure"), `retry_count`
- `engine.node.enter` / `engine.node.exit` — standard node lifecycle events (existing pattern)

All use `logger.info("event.name", extra={"data": {...}})` pattern per D8.

### Design Decisions for This Story

#### Retry Count Semantics
`retry_count` starts at 0 and is incremented by `validate_node` on each V3 failure that triggers RETRY or ESCALATED. The check `retry_count >= retry_budget` uses the CURRENT retry_count BEFORE incrementing. This means:
- `retry_budget=3` → up to 3 retries (4 total attempts) before escalation
- `retry_budget=0` → first V3 failure escalates immediately (no retries)

#### V6 Failure Does Not Increment retry_count
When V6 fails, `retry_count` is NOT incremented because no retry was attempted. V6 failures are immediate escalation — the retry_count reflects failed V3 retry attempts only.

#### Feedback is None After V6 Failure
`PipelineResult.feedback` is `None` when outcome is `FAIL_V6` (V3 was never invoked). The halt report handles this by showing V6 failure details instead of AC-level feedback.

#### build_prompt Feedback Section Position
The feedback section is appended LAST in the prompt (after Story, Requirements, Architecture, and Conventions sections). This ensures the feedback is the freshest context the agent sees, following the "recency bias" pattern in LLM prompts — the most immediately actionable content should be closest to the response generation point.

#### _generate_halt_report is Private
The halt report generator is a private helper in `engine/nodes.py`, not a public API. It's only called by `validate_node`. When Epic 4 (Provenance & Run Artifacts) is implemented, the halt report generation may move to `output/summary.py`. For now, keeping it in `nodes.py` avoids premature abstraction and respects the package boundary (the halt report content depends on engine state).

#### _serialize_validation_checkpoint is Private
Same reasoning — it's a private helper for the validation checkpoint write. Not shared outside nodes.py.

### Existing Code to Consume (NOT Create)

These modules are already fully implemented from previous stories. This story's code will **call** them — no modifications needed:

| Module | Function/Class | Source Story | Purpose |
|---|---|---|---|
| `core/types.py` | `ArcwrightModel`, `BudgetState` | Story 1.2 | Base model, budget tracking |
| `core/exceptions.py` | `ValidationError` | Story 1.2 | Raised when agent_output is None |
| `core/lifecycle.py` | `TaskState` | Story 1.2 | Lifecycle state enum (SUCCESS, RETRY, ESCALATED) |
| `core/constants.py` | `DIR_ARCWRIGHT`, `DIR_RUNS`, `DIR_STORIES`, `HALT_REPORT_FILENAME`, `VALIDATION_FILENAME` | Stories 1.2, 1.3 | Directory and file name constants |
| `core/io.py` | `write_text_async` | Story 1.3 | Async file writing |
| `core/config.py` | `RunConfig`, `LimitsConfig` | Story 1.3 | `limits.retry_budget` for configurable max retries |
| `validation/pipeline.py` | `run_validation_pipeline`, `PipelineResult`, `PipelineOutcome` | Story 3.3 | Validation pipeline orchestrator and result models |
| `validation/v3_reflexion.py` | `ReflexionFeedback` | Story 3.2 | Feedback model for retry prompt injection (TYPE_CHECKING import in prompt.py) |
| `validation/v6_invariant.py` | `V6ValidationResult`, `V6CheckResult` | Story 3.1 | V6 result models (referenced via PipelineResult) |
| `agent/invoker.py` | `invoke_agent` | Story 2.5 | Agent invocation (unchanged) |
| `agent/sandbox.py` | `validate_path` | Story 2.4 | Path validation function passed to pipeline |
| `agent/prompt.py` | `build_prompt` | Story 2.6 | Prompt construction (extended by this story) |
| `context/injector.py` | `build_context_bundle` | Story 2.2 | Context assembly (unchanged) |

### Modules This Story Modifies

| Module | Action | Symbols Created / Modified | Purpose |
|---|---|---|---|
| `engine/state.py` | MODIFY | `validation_result` type → `PipelineResult \| None`, add `retry_history` field | State model evolution for real validation |
| `engine/nodes.py` | MODIFY | Replace `validate_node` placeholder, add `_serialize_validation_checkpoint`, `_generate_halt_report`, modify `agent_dispatch_node` for feedback | Real validation + retry logic |
| `agent/prompt.py` | MODIFY | Extend `build_prompt` signature with `feedback` parameter | Retry feedback injection |
| `tests/test_engine/test_nodes.py` | MODIFY | Update existing test, add ~12 new tests | Validate node test coverage |
| `tests/test_engine/test_graph.py` | MODIFY | Update 2 existing tests, add 2 new integration tests | Graph integration with real validate node |
| `tests/test_agent/test_prompt.py` | MODIFY | Add 3 new tests | Feedback prompt injection tests |

### Modules This Story Does NOT Touch

- `engine/graph.py` — graph structure already has correct conditional edges (AC #11)
- `engine/nodes.py` route_validation — already correct (AC #10)
- `validation/pipeline.py` — consumed, not modified
- `validation/v3_reflexion.py` — consumed, not modified
- `validation/v6_invariant.py` — consumed, not modified
- `validation/__init__.py` — no new exports
- `agent/invoker.py` — unchanged
- `agent/sandbox.py` — unchanged
- `context/injector.py` — unchanged
- `core/types.py` — unchanged
- `core/constants.py` — all needed constants already exist (`HALT_REPORT_FILENAME`, `VALIDATION_FILENAME`)
- `core/io.py` — unchanged
- `core/exceptions.py` — `ValidationError` already defined
- `tests/test_validation/*` — zero validation test impact
- `tests/test_agent/test_invoker.py` — unchanged
- `tests/test_agent/test_sandbox.py` — unchanged

### How This Story Feeds into Subsequent Stories

| Downstream Story | What It Consumes from 3.4 | Integration Point |
|---|---|---|
| **4.1: Provenance Recorder** | `PipelineResult` serialization, retry history data | Provenance writes `validation.md` with richer format; may replace `_serialize_validation_checkpoint` |
| **4.4: Provenance Integration** | Validation checkpoint + halt report in run directory | Provenance integration reads from these files |
| **5.2: Halt Controller** | Escalated state + halt report | Halt controller orchestrates the full halt flow using the report this story generates |
| **5.3: Resume Controller** | `retry_count`, `retry_history`, last completed state | Resume reads the last state to pick up where the run halted |

### Previous Story Intelligence

**From Story 3.3 (Validation Pipeline — Artifact-Specific Routing):**
- `run_validation_pipeline()` signature: `async def run_validation_pipeline(agent_output: str, story_path: Path, project_root: Path, *, model: str, cwd: Path, sandbox: PathValidator, attempt_number: int = 1) -> PipelineResult`
- Returns `PipelineResult` with `.outcome`, `.passed`, `.v6_result`, `.v3_result`, `.feedback`, `.tokens_used`, `.cost`
- `PipelineOutcome`: `PASS`, `FAIL_V6`, `FAIL_V3`
- `.feedback` is `ReflexionFeedback | None` — populated only on `FAIL_V3`, None on PASS and FAIL_V6
- `.tokens_used` and `.cost` are 0/Decimal("0") when V6 short-circuits (no LLM involvement)
- Pipeline does NOT catch `ValidationError` — unexpected errors propagate to caller
- `PipelineResult` is an `ArcwrightModel` (frozen, `extra="forbid"`)
- V6 `failures` is a `computed_field` — included in `model_dump()` but must be stripped before `model_validate()` due to `extra="forbid"`. This is relevant if writing round-trip tests.

**From Story 2.7 (Agent Dispatch Node):**
- Current `validate_node` is a placeholder: `state.model_copy(update={"status": TaskState.SUCCESS})`
- `agent_dispatch_node` writes agent output to `AGENT_OUTPUT_FILENAME` checkpoint
- Budget update pattern: `state.budget.model_copy(update={...})`
- Checkpoint write pattern: `asyncio.to_thread(mkdir) + write_text_async()`

**From Epic 2 Retrospective — Critical Finding:**
- "Integration tests break on placeholder-to-real transitions" — this story MUST update existing graph integration tests (Action 3 from Epic 2 retro). Tests `test_graph_success_path_end_to_end` and `test_graph_invocation_no_errors` will break without a pipeline mock.
- "Exit code / terminal state mapping bugs" — ensure ESCALATED state is correctly detected in tests. Budget-exceeded path already tests ESCALATED; validation escalation needs the same coverage.
- Node error pattern: log entry → process → log exit (or log error + exit → re-raise)

### Known Pitfalls from Epics 1 & 2 (MANDATORY — From Retro Actions)

1. **`__all__` must be alphabetically sorted** (RUF022 — enforced by ruff). Not optional.
2. **Placeholder modules ship with empty `__all__: list[str] = []` only** — no aspirational exports for symbols not yet implemented.
3. **Pydantic mutable default fields require `Field(default_factory=list)`** — never bare `= []`. Used for `retry_history`.
4. **Config sub-models must override `extra="ignore"`** (not `extra="forbid"`) for forward-compatible unknown key handling. (Not applicable — `StoryState` uses `extra="forbid"` and is NOT a config model.)
5. **Always use `.venv/bin/python -m mypy --strict src/`** — not bare `mypy`.
6. **Test subdirectories require `__init__.py`** for robust pytest import resolution. (`tests/test_engine/__init__.py` already exists.)
7. **Exit code assertions are MANDATORY in test tasks** — every exit code/outcome path must have an explicit test assertion. ESCALATED tests must assert `state.status == TaskState.ESCALATED`. RETRY tests must assert `state.status == TaskState.RETRY`.
8. **When replacing a placeholder node with real logic, story MUST include a task to update existing graph integration tests with appropriate mocks/fixtures.** THIS IS THAT STORY — Tasks 4 and 6 explicitly address this.
9. **ACs must be self-contained** — all implementation details inline above, no indirection to dev notes for core requirements.
10. **Logger setup functions must restore previous state or use context managers to prevent side-effect leakage.** (Not applicable — this story doesn't modify logger configuration.)
11. **Carry forward all Epic 1 pitfalls** (items 1-6 above still valid).
12. **`from __future__ import annotations` required as first line in every `.py` file.**

### Git Intelligence

Last 5 commits:
```
600c201 feat(validation): add story 3.3 pipeline routing spec and update sprint status
d995086 feat(validation): implement V3 reflexion validation LLM self-evaluation (Story 3.2)
4cdfeb7 feat(validation): implement V6 invariant validation deterministic rule checks (Story 3.1)
94198d0 fix: monkeypatch SDK parse_message to skip unknown message types (rate_limit_event)
f47be0f fix(invoker): handle SDK MessageParseError for rate_limit_event
```

**Patterns:**
- Commit prefix for this story: `feat(engine):` for validating node replacement and retry loop
- All Epic 3 validation modules (V6, V3, pipeline) are committed and available
- Test suite at approximately 353 tests (post Story 3.3)
- Both `ruff check` and `mypy --strict` pass (confirmed in Story 3.3 completion)
- Files changed in Epic 3 so far: V6 (+504 lines), V3 (+417 lines), pipeline (+218 lines), plus tests

### Testing Patterns

**Test naming convention:** `test_<function_name>_<scenario>`:
```python
async def test_validate_node_v3_fail_within_retry_budget_transitions_to_retry(): ...
async def test_validate_node_v6_fail_transitions_to_escalated_immediately(): ...
```

**Monkeypatching the pipeline directly:**
This story's tests monkeypatch `run_validation_pipeline` within the `engine.nodes` module namespace:
```python
monkeypatch.setattr("arcwright_ai.engine.nodes.run_validation_pipeline", _mock)
```
This is the cleanest approach because the validate_node is the routing layer — testing its logic, not the pipeline internals.

**State fixtures for validate_node tests:**
The validate_node requires:
- `state.agent_output` to be non-None
- `state.project_root` to be a real directory (for checkpoint writes)
- `state.status == TaskState.VALIDATING`
- `state.config` with `limits.retry_budget`

Create a `validate_ready_state(tmp_path)` fixture that provides all of these.

**Counter-based mocks for integration retry tests:**
```python
call_count = 0
async def _mock_pipeline(*args, **kwargs):
    nonlocal call_count
    call_count += 1
    if call_count <= fail_count:
        return fail_v3_result
    return pass_result
monkeypatch.setattr("arcwright_ai.engine.nodes.run_validation_pipeline", _mock_pipeline)
```

**Async tests:** Use `@pytest.mark.asyncio` explicitly. `asyncio_mode = "auto"` is configured in `pyproject.toml`.

**Assertion style:** Plain `assert` + `pytest.raises`. No assertion libraries.

**Caplog for structured log events:** Verify event names AND data fields:
```python
pass_records = [r for r in caplog.records if r.message == "validation.pass"]
assert len(pass_records) == 1
assert pass_records[0].data["story"] == str(state.story_id)  # type: ignore[attr-defined]
```

### Project Structure Notes

**Files to MODIFY:**

| File | Action | Content |
|---|---|---|
| `src/arcwright_ai/engine/state.py` | MODIFY | `validation_result` type change, add `retry_history` field |
| `src/arcwright_ai/engine/nodes.py` | MODIFY | Replace validate_node placeholder, add private helpers, modify agent_dispatch_node |
| `src/arcwright_ai/agent/prompt.py` | MODIFY | Extend build_prompt with feedback parameter |
| `tests/test_engine/test_nodes.py` | MODIFY | Update 1 existing test, add ~12 new tests |
| `tests/test_engine/test_graph.py` | MODIFY | Update 2 existing tests, add 2 new integration tests |
| `tests/test_agent/test_prompt.py` | MODIFY | Add 3 new tests |

**Files NOT touched** (no changes needed):
- `engine/graph.py` — graph structure already correct with conditional edges
- `validation/pipeline.py` — consumed, not modified
- `validation/v3_reflexion.py` — consumed, not modified
- `validation/v6_invariant.py` — consumed, not modified
- `validation/__init__.py` — no new exports
- `agent/invoker.py` — unchanged
- `agent/sandbox.py` — unchanged
- `context/injector.py` — unchanged
- `core/types.py` — unchanged
- `core/constants.py` — all constants already exist
- `core/io.py` — unchanged
- `core/exceptions.py` — ValidationError already defined
- All `tests/test_validation/*` — ZERO validation test impact
- `tests/test_agent/test_invoker.py` — unchanged
- `tests/test_agent/test_sandbox.py` — unchanged
- `tests/test_core/*` — unchanged

**Alignment with architecture:**
- `engine/nodes.py` implements the validate node per data flow diagram: "validation/pipeline.py → route to V3/V6"
- Retry loop follows D2: V3 failures retry, V6 failures escalate immediately
- Budget update pattern matches existing `agent_dispatch_node` pattern (`budget.model_copy(update={...})`)
- State transitions follow `core/lifecycle.py` rules: VALIDATING → SUCCESS/RETRY/ESCALATED
- Structured logging follows D8 JSONL pattern
- Checkpoint writes follow D5 write policy (state transitions only)
- Package DAG: `engine → {validation, agent, core}` — only permitted imports

### Cross-Story Context (Epic 3 Stories)

| Story | Relationship to 3.4 | Status |
|---|---|---|
| 3.1: V6 Invariant Validation | Provides result models consumed via pipeline | done |
| 3.2: V3 Reflexion Validation | Provides feedback models consumed via pipeline and prompt injection | done |
| 3.3: Validation Pipeline | Provides `run_validation_pipeline()`, `PipelineResult`, `PipelineOutcome` consumed by validate_node | done |
| 3.4: This story | Wires pipeline into graph, implements retry loop, completes Epic 3 | current |

### References

- [Source: _spec/planning-artifacts/architecture.md#Decision-2 — V3 retryable, V6 immediate escalation, dual budget model]
- [Source: _spec/planning-artifacts/architecture.md#Decision-5 — Run directory schema, checkpoint write policy]
- [Source: _spec/planning-artifacts/architecture.md#Decision-6 — ValidationError for unexpected errors, exit code 1]
- [Source: _spec/planning-artifacts/architecture.md#Decision-8 — Structured JSONL logging pattern]
- [Source: _spec/planning-artifacts/architecture.md#Package-Dependency-DAG — engine depends on validation, agent, core]
- [Source: _spec/planning-artifacts/architecture.md#Data-Flow — validate node calls validation/pipeline.py]
- [Source: _spec/planning-artifacts/architecture.md#Core-Execution-Chain — FR1→3→8→9→4→5 chain this story completes]
- [Source: _spec/planning-artifacts/architecture.md#Async-Patterns — asyncio.to_thread for file I/O]
- [Source: _spec/planning-artifacts/architecture.md#Pydantic-Model-Patterns — frozen models, Field(default_factory=list)]
- [Source: _spec/planning-artifacts/architecture.md#Testing-Patterns — naming, isolation, assertions, async]
- [Source: _spec/planning-artifacts/epics.md#Story-3.4 — Acceptance criteria, story definition]
- [Source: _spec/planning-artifacts/epics.md#Epic-3 — Epic context, FR8-11 coverage]
- [Source: _spec/planning-artifacts/prd.md#FR8 — V3 reflexion evaluation]
- [Source: _spec/planning-artifacts/prd.md#FR9 — Retry on reflexion failure, configurable max]
- [Source: _spec/planning-artifacts/prd.md#FR10 — V6 invariant checks]
- [Source: _spec/planning-artifacts/prd.md#FR11 — Structured failure report on halt]
- [Source: _spec/planning-artifacts/prd.md#NFR1 — Zero silent failures]
- [Source: _spec/implementation-artifacts/epic-2-retro-2026-03-03.md — Pitfalls, action items, integration test breakage pattern]
- [Source: _spec/implementation-artifacts/3-3-validation-pipeline-artifact-specific-routing.md — Pipeline API, handoff notes, routing contract]
- [Source: arcwright-ai/src/arcwright_ai/engine/nodes.py — Current validate_node placeholder, agent_dispatch_node]
- [Source: arcwright-ai/src/arcwright_ai/engine/state.py — Current StoryState with dict[str, Any] placeholder]
- [Source: arcwright-ai/src/arcwright_ai/engine/graph.py — Graph structure with conditional edges]
- [Source: arcwright-ai/src/arcwright_ai/validation/pipeline.py — PipelineOutcome, PipelineResult, run_validation_pipeline]
- [Source: arcwright-ai/src/arcwright_ai/validation/v3_reflexion.py — ReflexionFeedback model]
- [Source: arcwright-ai/src/arcwright_ai/agent/prompt.py — Current build_prompt implementation]
- [Source: arcwright-ai/src/arcwright_ai/agent/sandbox.py — validate_path function]
- [Source: arcwright-ai/src/arcwright_ai/core/config.py — LimitsConfig.retry_budget (default=3)]
- [Source: arcwright-ai/src/arcwright_ai/core/constants.py — HALT_REPORT_FILENAME, VALIDATION_FILENAME]
- [Source: arcwright-ai/src/arcwright_ai/core/lifecycle.py — TaskState enum, VALID_TRANSITIONS]
- [Source: arcwright-ai/tests/test_engine/test_nodes.py — Existing validate_node test, fixture patterns]
- [Source: arcwright-ai/tests/test_engine/test_graph.py — Existing graph integration tests, mock_agent fixture]

## Dev Agent Record

### Agent Model Used

Claude Sonnet 4.6 (GitHub Copilot)

### Debug Log References

### Completion Notes List

- Replaced validate_node placeholder with full pipeline-driven implementation (V3/V6 routing, retry loop, halt report generation).
- Updated StoryState: `validation_result` type migrated from `dict[str, Any] | None` to `PipelineResult | None`; added `retry_history: list[PipelineResult]` field.
- Extended `build_prompt` with `feedback: ReflexionFeedback | None = None` parameter; appends `## Previous Validation Feedback` section on retry.
- Modified `agent_dispatch_node` to extract feedback from `validation_result` and pass it to `build_prompt`; updated `agent.dispatch` log event with `retry_count` and `has_feedback`.
- Added private helpers `_serialize_validation_checkpoint` and `_generate_halt_report` in `engine/nodes.py`.
- Added `mock_pipeline_pass`, `mock_pipeline_fail_v3`, `mock_pipeline_fail_v6` fixtures plus `validate_ready_state` fixture in test_nodes.py.
- Updated existing `test_validate_node_transitions_to_success` to use new fixtures and real pipeline mock.
- Added 12 new validate_node unit tests covering all routing paths, budget, retry_history, checkpoints, halt reports, log events, and ValidationError.
- Added `mock_pipeline` fixture and updated 2 existing graph tests; added `test_graph_retry_path_v3_fail_then_pass` and `test_graph_max_retry_escalated_path` integration tests.
- Added 3 new `build_prompt` feedback tests.
- All 370 tests pass; ruff check: 0 violations; ruff format: clean; mypy --strict: 0 errors.
- Code-review follow-up fix: corrected V3 escalation halt-report retry count to use incremented value; added regression assertion in `test_validate_node_writes_halt_report_on_v3_escalation`.
- Story artifact sync: updated story status to `done`, refreshed File List with spec tracking files, and synced sprint status entry.

### File List

- src/arcwright_ai/engine/state.py
- src/arcwright_ai/engine/nodes.py
- src/arcwright_ai/agent/prompt.py
- tests/test_engine/test_nodes.py
- tests/test_engine/test_graph.py
- tests/test_agent/test_prompt.py
- _spec/implementation-artifacts/3-4-validate-node-and-retry-loop-integration.md
- _spec/implementation-artifacts/sprint-status.yaml

## Change Log

- 2026-03-04: Story created by BMAD create-story workflow with comprehensive context engine analysis.
- 2026-03-04: Story implemented by dev-story workflow — validate_node wired with real pipeline, retry loop, halt report, feedback injection, and full test coverage (370 tests, 0 regressions).
- 2026-03-04: Code-review workflow applied automatic fixes — corrected halt-report retry count on max-retry escalation, added regression assertion, updated story/sprint tracking to done.
