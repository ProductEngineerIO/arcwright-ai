# Story 4.4: Provenance & Summary Integration with Engine Nodes

Status: done

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

## Story

As a system maintainer,
I want provenance recording and summary generation wired into the LangGraph execution nodes,
so that artifacts are produced automatically at the right moments without manual intervention.

## Acceptance Criteria (BDD)

1. **Given** the LangGraph StateGraph nodes from Epic 2 **When** each node executes **Then** this story contains zero new data models or file I/O logic — it exclusively wires the APIs from Stories 4.1 (`output/provenance.py`), 4.2 (`output/run_manager.py`), and 4.3 (`output/summary.py`) into the LangGraph node callbacks and graph structure. No new Pydantic models, no new YAML/markdown rendering logic, no new file write primitives.

2. **Given** the `agent_dispatch_node` completes successfully **When** the agent returns a result **Then** the node creates a `ProvenanceEntry` (from `core/types.py`) recording the agent invocation with:
   - `decision`: `"Agent invoked for story {story_id} (attempt {attempt_number})"`
   - `alternatives`: `["{model_version}"]` (the model used, from `state.config.model.version`)
   - `rationale`: `"Prompt length: {prompt_length} chars, retry_count: {retry_count}, has_feedback: {has_feedback}"`
   - `ac_references`: extracted from `state.context_bundle.domain_requirements` (FR/NFR IDs via regex `FR-?\d+|NFR-?\d+`) — empty list if none found or context_bundle is None
   - `timestamp`: `datetime.now(tz=UTC).isoformat()`
   And calls `provenance.append_entry(provenance_path, entry)` where `provenance_path` is `checkpoint_dir / VALIDATION_FILENAME` (same story directory as the existing agent-output checkpoint).
   This call is wrapped in a try/except that catches `Exception`, logs `"provenance.write_error"` with story_id and error details at WARNING level, and continues — artifact writing is best-effort, not blocking (per D5 write policy).

3. **Given** the `validate_node` completes a validation attempt **When** the validation pipeline returns a result **Then** the node creates a `ProvenanceEntry` recording the validation outcome with:
   - `decision`: `"Validation attempt {attempt_number}: {outcome_value}"` (e.g., `"Validation attempt 1: pass"`)
   - `alternatives`: empty list (validation has no alternatives)
   - `rationale`: summary of validation result — for PASS: `"All checks passed (V6: {v6_count} checks, V3: {v3_pass}/{v3_total} ACs)"`, for FAIL_V6: `"V6 invariant failures: {failure_count}"`, for FAIL_V3: `"V3 reflexion failures: ACs {unmet_ac_ids}"`
   - `ac_references`: list of failed AC IDs from `pipeline_result.feedback.unmet_criteria` (if available), else empty list
   - `timestamp`: `datetime.now(tz=UTC).isoformat()`
   And calls `provenance.append_entry(provenance_path, entry)` to append to the **same** `validation.md` file in the story's run directory.
   Additionally, calls `provenance.render_validation_row(attempt_number, outcome, feedback_summary)` and stores the resulting row string in the `ProvenanceEntry`'s rationale context — Story 4.4 does NOT need to separately write validation rows to the file since `append_entry()` manages the document structure.
   This call is wrapped in the same best-effort try/except pattern as AC #2.

4. **Given** the `validate_node` escalates a story (V6 failure or max retries exhausted) **When** the halt report is generated **Then** the existing `_generate_halt_report()` function continues to generate the per-story halt report written to `HALT_REPORT_FILENAME`. In addition, a provenance entry is appended recording the escalation decision. No modification to the halt report generation logic itself — it remains an internal engine function producing the story-level halt report.

5. **Given** the `commit_node` processes a successful story **When** the node executes **Then** it calls:
   - `run_manager.update_story_status(project_root, run_id, story_slug, status="success", completed_at=datetime.now(tz=UTC).isoformat())` to mark the story as completed in `run.yaml`
   - `run_manager.update_run_status(project_root, run_id, last_completed_story=story_slug, budget=state.budget)` to update the run's last completed story pointer and budget snapshot
   Where `story_slug` is `str(state.story_id)`, `project_root` is `state.project_root`, `run_id` is `str(state.run_id)`.
   Both calls are wrapped in best-effort try/except (catch `Exception`, log `"run_manager.write_error"` at WARNING, continue). The commit_node transitions remain unchanged — it still returns state with SUCCESS status.

6. **Given** a new `finalize_node` at the terminal position of the graph **When** the graph reaches any terminal state (SUCCESS after commit, ESCALATED after validation or budget exceeded) **Then** the finalize node examines `state.status` and writes the appropriate run-level summary:
   - `TaskState.SUCCESS` → calls `summary.write_success_summary(project_root, run_id)`
   - `TaskState.ESCALATED` → calls `summary.write_halt_report(project_root, run_id, halted_story=story_slug, halt_reason=halt_reason, validation_history=validation_history_dicts, last_agent_output=agent_output, suggested_fix=suggested_fix)` where:
     - `halt_reason` is derived from the last validation result's outcome (e.g., `"max_retries_exhausted"`, `"v6_invariant_failure"`, `"budget_exceeded"`)
     - `validation_history_dicts` is built from `state.retry_history` by converting each `PipelineResult` to a dict `{"attempt": i, "outcome": result.outcome.value, "failures": failure_summary_str}`
     - `last_agent_output` is `state.agent_output or ""`
     - `suggested_fix` is derived from the last validation result's feedback (if available) or a generic message
   The summary write is best-effort (try/except, log warning, continue). The finalize_node returns state unchanged (state is already in its terminal status).

7. **Given** the graph structure **When** `build_story_graph()` is called **Then** the graph routes ALL terminal paths through the new `finalize_node` before reaching END:
   ```
   START → preflight → budget_check →(ok)→ agent_dispatch → validate →(success)→ commit → finalize → END
                                     ↓(exceeded)→ finalize → END    ↓(retry)→ budget_check
                                                                     ↓(escalated)→ finalize → END
   ```
   The `finalize` node is added via `graph.add_node("finalize", finalize_node)`. The `commit` edge changes from `commit → END` to `commit → finalize`. The budget_check `exceeded` edge changes from `exceeded → END` to `exceeded → finalize`. The validate `escalated` edge changes from `escalated → END` to `escalated → finalize`. A new edge `finalize → END` is added.

8. **Given** the node modifications add imports from `output/` package **When** checking the package dependency DAG **Then** `engine/nodes.py` imports from `output/provenance`, `output/run_manager`, and `output/summary` — all domain packages that are allowed dependencies for `engine/` per the architecture DAG: `engine → {validation, agent, context, output, scm} → core`. No new cross-domain violations.

9. **Given** existing tests in `tests/test_engine/test_nodes.py` and `tests/test_engine/test_graph.py` **When** this story is complete **Then** all 441 existing tests continue to pass. New mocks/patches are added for the `output/` function calls in node tests so that existing test scenarios don't fail due to missing run directories or files. The mocking strategy: patch `arcwright_ai.engine.nodes.append_entry`, `arcwright_ai.engine.nodes.update_story_status`, `arcwright_ai.engine.nodes.update_run_status`, `arcwright_ai.engine.nodes.write_success_summary`, `arcwright_ai.engine.nodes.write_halt_report` as `AsyncMock` instances. Graph tests must be updated to include the `finalize` node in expected routing paths.

10. **Given** new unit tests in `tests/test_engine/test_nodes.py` **When** the test suite runs **Then** tests cover:
    (a) `agent_dispatch_node` creates and appends a ProvenanceEntry after successful invocation — verify `append_entry` called with correct path and entry fields;
    (b) `agent_dispatch_node` provenance write failure is logged but does not raise — verify node completes successfully when `append_entry` raises `OSError`;
    (c) `validate_node` creates and appends a ProvenanceEntry after validation — verify `append_entry` called with correct path and entry containing outcome and failed ACs;
    (d) `validate_node` provenance write failure is logged but does not raise;
    (e) `commit_node` calls `update_story_status()` with `status="success"` and `completed_at` timestamp;
    (f) `commit_node` calls `update_run_status()` with `last_completed_story` and budget;
    (g) `commit_node` run_manager write failure is logged but does not raise;
    (h) `finalize_node` calls `write_success_summary()` when state.status is SUCCESS;
    (i) `finalize_node` calls `write_halt_report()` when state.status is ESCALATED with correct parameters (halted_story, halt_reason, validation_history, last_agent_output, suggested_fix);
    (j) `finalize_node` summary write failure is logged but does not raise;
    (k) `finalize_node` returns state unchanged regardless of summary write outcome;
    (l) `finalize_node` with ESCALATED state and empty retry_history produces valid halt_reason and validation_history_dicts;
    (m) `finalize_node` derives halt_reason from last PipelineResult outcome (FAIL_V6 → "v6_invariant_failure", FAIL_V3 + exhausted → "max_retries_exhausted", budget exceeded → "budget_exceeded");

11. **Given** new/updated tests in `tests/test_engine/test_graph.py` **When** the test suite runs **Then** tests cover:
    (a) Graph structure includes `finalize` node;
    (b) Success path routes: preflight → budget_check → agent_dispatch → validate → commit → finalize → END;
    (c) Escalated path routes: ... → validate → finalize → END;
    (d) Budget exceeded path routes: ... → budget_check → finalize → END;
    (e) Retry path still routes: ... → validate → budget_check → ... (unchanged).

12. **Given** story implementation is complete **When** `ruff check .` is run against the FULL repository **Then** zero violations.

13. **Given** story implementation is complete **When** `.venv/bin/python -m mypy --strict src/` is run **Then** zero errors.

14. **Given** all public classes and functions **When** every docstring is inspected **Then** each conforms to Google-style (Args, Returns, Raises sections where appropriate).

15. **Given** any existing tests in the full test suite **When** this story is complete **Then** no existing tests break. All 441 existing tests continue to pass unmodified or with minimally-updated mocks.

## Tasks / Subtasks

- [x] Task 1: Add output package imports to `engine/nodes.py` (AC: #1, #8)
  - [x] 1.1: Add imports at top of `engine/nodes.py`:
    ```python
    from datetime import UTC, datetime

    from arcwright_ai.core.types import ProvenanceEntry
    from arcwright_ai.output.provenance import append_entry
    from arcwright_ai.output.run_manager import update_run_status, update_story_status
    from arcwright_ai.output.summary import write_halt_report, write_success_summary
    ```
  - [x] 1.2: Add `VALIDATION_FILENAME` to existing constants import if not already present (it IS already imported)
  - [x] 1.3: Update `__all__` in `engine/nodes.py` to include `"finalize_node"` (alphabetically sorted)

- [x] Task 2: Wire provenance into `agent_dispatch_node` (AC: #2)
  - [x] 2.1: After the existing agent-output checkpoint write block, add provenance entry creation:
    ```python
    # Provenance: record agent invocation decision (best-effort)
    try:
        refs: list[str] = []
        if state.context_bundle is not None and state.context_bundle.domain_requirements:
            import re
            refs = re.findall(r"(?:FR|NFR)-?\d+", state.context_bundle.domain_requirements)
        provenance_entry = ProvenanceEntry(
            decision=f"Agent invoked for story {state.story_id} (attempt {state.retry_count + 1})",
            alternatives=[state.config.model.version],
            rationale=f"Prompt length: {len(prompt)} chars, retry_count: {state.retry_count}, has_feedback: {feedback is not None}",
            ac_references=refs,
            timestamp=datetime.now(tz=UTC).isoformat(),
        )
        provenance_path = checkpoint_dir / VALIDATION_FILENAME
        await append_entry(provenance_path, provenance_entry)
    except Exception:
        logger.warning(
            "provenance.write_error",
            extra={"data": {"node": "agent_dispatch", "story": str(state.story_id)}},
        )
    ```
  - [x] 2.2: Move the `import re` to module-level if not already there, or use inline import (prefer module-level)

- [x] Task 3: Wire provenance into `validate_node` (AC: #3, #4)
  - [x] 3.1: After the existing validation checkpoint write, add provenance entry for the validation outcome:
    ```python
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
        
        failed_acs = list(pipeline_result.feedback.unmet_criteria) if pipeline_result.feedback else []
        
        provenance_entry = ProvenanceEntry(
            decision=f"Validation attempt {attempt_number}: {outcome_str}",
            alternatives=[],
            rationale=rationale,
            ac_references=failed_acs,
            timestamp=datetime.now(tz=UTC).isoformat(),
        )
        provenance_path = checkpoint_dir / VALIDATION_FILENAME
        await append_entry(provenance_path, provenance_entry)
    except Exception:
        logger.warning(
            "provenance.write_error",
            extra={"data": {"node": "validate", "story": str(state.story_id)}},
        )
    ```
  - [x] 3.2: Place provenance write AFTER the existing `_serialize_validation_checkpoint` write and BEFORE the outcome routing logic — both writes target the same file but provenance.append_entry handles existing content gracefully

- [x] Task 4: Wire run_manager into `commit_node` (AC: #5)
  - [x] 4.1: Replace the placeholder commit_node with real implementation:
    ```python
    async def commit_node(state: StoryState) -> StoryState:
        """Commit node — updates run.yaml with story completion and budget.

        Calls run_manager to update story status to "success" with completion
        timestamp, and updates the run-level last_completed_story pointer and
        budget snapshot. All writes are best-effort — failures are logged but
        do not halt execution.

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
        except Exception:
            logger.warning(
                "run_manager.write_error",
                extra={"data": {"node": "commit", "story": story_slug, "operation": "update_story_status"}},
            )

        # Update run-level state (best-effort)
        try:
            await update_run_status(
                project_root,
                run_id,
                last_completed_story=story_slug,
                budget=state.budget,
            )
        except Exception:
            logger.warning(
                "run_manager.write_error",
                extra={"data": {"node": "commit", "story": story_slug, "operation": "update_run_status"}},
            )

        logger.info(
            "engine.node.exit",
            extra={"data": {"node": "commit", "story": str(state.story_id), "status": str(state.status)}},
        )
        return state
    ```

- [x] Task 5: Implement `finalize_node` (AC: #6)
  - [x] 5.1: Add new async function in `engine/nodes.py`:
    ```python
    async def finalize_node(state: StoryState) -> StoryState:
        """Finalize node — writes run-level summary at graph termination.

        Examines the terminal state (SUCCESS or ESCALATED) and writes the
        appropriate run-level summary via output/summary. All writes are
        best-effort — failures are logged but do not affect the returned state.

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
                # Build halt report parameters from state
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
                )
        except Exception:
            logger.warning(
                "summary.write_error",
                extra={"data": {"node": "finalize", "story": story_slug, "status": str(state.status)}},
            )

        logger.info(
            "engine.node.exit",
            extra={"data": {"node": "finalize", "story": str(state.story_id), "status": str(state.status)}},
        )
        return state
    ```
  - [x] 5.2: Implement `_derive_halt_reason(state: StoryState) -> str` private helper:
    - If `state.retry_history` is empty: return `"budget_exceeded"` (the only escalation path without retry history is budget)
    - If last result in `state.retry_history` has `outcome == PipelineOutcome.FAIL_V6`: return `"v6_invariant_failure"`
    - If `state.retry_count >= state.config.limits.retry_budget`: return `"max_retries_exhausted"`
    - Else: return `"validation_failure"`
  - [x] 5.3: Implement `_build_validation_history_dicts(state: StoryState) -> list[dict[str, Any]]` private helper:
    - Iterates `state.retry_history` (list of `PipelineResult`)
    - For each result at index `i`: builds dict `{"attempt": i + 1, "outcome": result.outcome.value, "failures": _summarize_failures(result)}`
    - `_summarize_failures(result)`: if FAIL_V6 → `"V6: {count} checks failed"`, if FAIL_V3 with feedback → `"V3: ACs {unmet_ids}"`, else `""`
  - [x] 5.4: Implement `_derive_suggested_fix(state: StoryState) -> str` private helper:
    - If retry_history is not empty and last result has feedback with `feedback_per_criterion`: join the per-criterion feedback into a suggestion
    - If last result is FAIL_V6: `"Fix the V6 invariant rule violations and re-run the story."`
    - Else: `"Review the validation failures and address underlying issues."`

- [x] Task 6: Update `build_story_graph()` in `engine/graph.py` (AC: #7)
  - [x] 6.1: Add `finalize_node` import:
    ```python
    from arcwright_ai.engine.nodes import (
        agent_dispatch_node,
        budget_check_node,
        commit_node,
        finalize_node,  # NEW
        preflight_node,
        route_budget_check,
        route_validation,
        validate_node,
    )
    ```
  - [x] 6.2: Add `finalize` node to the graph: `graph.add_node("finalize", finalize_node)`
  - [x] 6.3: Change `commit → END` edge to `commit → finalize`
  - [x] 6.4: Change budget_check `exceeded` routing from `END` to `"finalize"`
  - [x] 6.5: Change validate `escalated` routing from `END` to `"finalize"`
  - [x] 6.6: Add `finalize → END` edge: `graph.add_edge("finalize", END)`
  - [x] 6.7: Update docstring ASCII art to reflect new graph shape

- [x] Task 7: Update `engine/__init__.py` exports (AC: #8)
  - [x] 7.1: Add `finalize_node` to imports and `__all__` (alphabetically sorted)

- [x] Task 8: Update existing tests in `tests/test_engine/test_nodes.py` (AC: #9, #15)
  - [x] 8.1: Add `AsyncMock` patches for the new output function calls. For all existing node tests that exercise `agent_dispatch_node`, `validate_node`, and `commit_node`, add patches:
    ```python
    @pytest.fixture(autouse=True)
    def _mock_output_functions(monkeypatch: pytest.MonkeyPatch) -> None:
        """Patch output functions called by engine nodes to prevent real I/O."""
        monkeypatch.setattr("arcwright_ai.engine.nodes.append_entry", AsyncMock())
        monkeypatch.setattr("arcwright_ai.engine.nodes.update_story_status", AsyncMock())
        monkeypatch.setattr("arcwright_ai.engine.nodes.update_run_status", AsyncMock())
        monkeypatch.setattr("arcwright_ai.engine.nodes.write_success_summary", AsyncMock())
        monkeypatch.setattr("arcwright_ai.engine.nodes.write_halt_report", AsyncMock())
    ```
  - [x] 8.2: Verify all 41 existing `test_nodes.py` tests pass with the new patches
  - [x] 8.3: For `commit_node` tests — existing tests just assert state passes through; they still pass because the run_manager calls are mocked

- [x] Task 9: Update existing tests in `tests/test_engine/test_graph.py` (AC: #11)
  - [x] 9.1: Update graph structure assertions to include `finalize` node
  - [x] 9.2: Update path assertions: success path now ends `... → commit → finalize → END`
  - [x] 9.3: Update escalated/exceeded path assertions to route through `finalize`
  - [x] 9.4: Add patches for output functions in graph integration tests (similar to Task 8.1)

- [x] Task 10: Create new tests for provenance wiring (AC: #10a-d)
  - [x] 10.1: Test `agent_dispatch_node` calls `append_entry` with correct ProvenanceEntry fields (decision contains story_id, alternatives contains model version, rationale contains prompt length)
  - [x] 10.2: Test `agent_dispatch_node` continues successfully when `append_entry` raises `OSError`
  - [x] 10.3: Test `validate_node` calls `append_entry` with correct ProvenanceEntry (decision contains attempt number and outcome, ac_references contains failed ACs for FAIL_V3)
  - [x] 10.4: Test `validate_node` continues successfully when `append_entry` raises `OSError`

- [x] Task 11: Create new tests for commit_node wiring (AC: #10e-g)
  - [x] 11.1: Test `commit_node` calls `update_story_status` with `status="success"` and non-None `completed_at`
  - [x] 11.2: Test `commit_node` calls `update_run_status` with `last_completed_story` matching story_id and budget matching state.budget
  - [x] 11.3: Test `commit_node` continues successfully when `update_story_status` raises `RunError`

- [x] Task 12: Create new tests for finalize_node (AC: #10h-m)
  - [x] 12.1: Test `finalize_node` calls `write_success_summary(project_root, run_id)` when status is SUCCESS
  - [x] 12.2: Test `finalize_node` calls `write_halt_report` when status is ESCALATED with correct `halted_story`, `halt_reason`, `validation_history`, `last_agent_output`, `suggested_fix`
  - [x] 12.3: Test `finalize_node` returns state unchanged regardless of summary write outcome
  - [x] 12.4: Test `finalize_node` continues successfully when `write_success_summary` raises
  - [x] 12.5: Test `finalize_node` with ESCALATED and empty `retry_history` → halt_reason is `"budget_exceeded"`, validation_history_dicts is `[]`
  - [x] 12.6: Test `_derive_halt_reason` returns `"v6_invariant_failure"` when last result is FAIL_V6
  - [x] 12.7: Test `_derive_halt_reason` returns `"max_retries_exhausted"` when retry_count >= retry_budget and last result is FAIL_V3
  - [x] 12.8: Test `_build_validation_history_dicts` converts PipelineResult list to correct dict format

- [x] Task 13: Create new graph structure tests (AC: #11)
  - [x] 13.1: Test graph includes `finalize` node
  - [x] 13.2: Test success path routing includes finalize before END
  - [x] 13.3: Test escalated path routing goes through finalize
  - [x] 13.4: Test budget exceeded path routing goes through finalize

- [x] Task 14: Run quality gates (AC: #12, #13, #14, #15)
  - [x] 14.1: `ruff check .` — zero violations against FULL repository
  - [x] 14.2: `ruff format --check .` — zero formatting issues
  - [x] 14.3: `.venv/bin/python -m mypy --strict src/` — zero errors
  - [x] 14.4: `pytest` — all tests pass (441 existing + ~25 new)
  - [x] 14.5: Verify Google-style docstrings on all public functions
  - [x] 14.6: Verify `git diff --name-only` matches Dev Agent Record file list

## Dev Notes

### Architecture & Design Context

**Package Dependency DAG**: `engine → {validation, agent, context, output, scm} → core`. Story 4.4 adds `engine → output` imports which are explicitly permitted by the DAG. The `output/` package has ZERO engine dependency (enforced in Stories 4.1–4.3). The flow direction is: engine nodes CALL output functions, output functions NEVER call engine functions.

**D5 — Write Policy**: LangGraph state is the authority during graph execution. Run directory files are written as **checkpoints at state transitions only**:
- After preflight → `context-bundle.md` (exists from Story 2.6)
- After agent response → `agent-output.md` (exists from Story 2.7) + provenance entry (NEW in 4.4)
- After validation → `validation.md` checkpoint (exists from Story 3.4) + provenance entry (NEW in 4.4)
- After commit → `run.yaml` update via run_manager (NEW in 4.4)
- After graph termination → `summary.md` via finalize_node (NEW in 4.4)

No subsystem should read run directory files during active graph execution — they may be stale.

**Best-Effort Artifact Writing**: Per the epics AC: "if a node fails to write an artifact, the error is logged but does not halt execution." This means EVERY output API call in this story must be wrapped in `try: ... except Exception: logger.warning(...)`. The exception catch is broad (`Exception`) because artifact writes should never crash the orchestration pipeline — the agent's output in LangGraph state is the authoritative result, artifacts are supplementary.

**Existing `_serialize_validation_checkpoint()` and `_generate_halt_report()`**: These engine-internal functions in `nodes.py` are NOT removed by this story. They continue to serve their current purpose:
- `_serialize_validation_checkpoint()` writes the basic V6+V3 result summary to `validation.md`
- `_generate_halt_report()` writes the per-story halt report to `halt-report.md`

Story 4.4 ADDS provenance entries (via `provenance.append_entry()`) to the **same** `validation.md` file. The `append_entry()` function handles existing content gracefully — it reads the file, inserts the new decision before `## Validation History`, and rewrites. The checkpoint write and the provenance write both target `validation.md` in sequence. This is safe because both writes are in the same async node function (sequential, not concurrent) and `append_entry` reads the latest file content before writing.

**finalize_node vs. Post-Graph Hook**: The summary writing is implemented as a graph node rather than a post-graph CLI hook because:
1. The graph state carries all information needed for summary construction
2. A graph node keeps the pipeline self-contained and testable
3. The CLI should not need to understand internal pipeline state to write summaries
4. Future epic dispatch (Story 5.1) can reuse the graph without duplicating summary logic

**`_derive_halt_reason` Logic**: The halt reason must be inferred from state because it's not stored as an explicit field:
- Empty `retry_history` + ESCALATED = budget exceeded (the only path to ESCALATED without running validation)
- Last `retry_history` entry with `FAIL_V6` = V6 invariant failure
- `retry_count >= retry_budget` with FAIL_V3 = max retries exhausted
- Other = generic validation failure

**ProvenanceEntry for Agent Dispatch**: The `ac_references` field extracts FR/NFR IDs from the context bundle's domain requirements. This uses a regex scan (`FR-?\d+|NFR-?\d+`) to find references. If the context bundle has no domain requirements or is None, the list is empty. The regex is identical to patterns used in `context/injector.py` (Story 2.2).

**ProvenanceEntry for Validation**: The validation provenance entry records the outcome of each validation attempt. For FAIL_V3, the `ac_references` lists the unmet AC IDs from `ReflexionFeedback.unmet_criteria`. For FAIL_V6, ac_references is empty (V6 checks don't map to ACs). For PASS, ac_references is empty (nothing failed).

### Existing Code to Reuse — DO NOT REINVENT

- **`ProvenanceEntry`** from `core/types.py` — frozen Pydantic model with `decision`, `alternatives`, `rationale`, `ac_references`, `timestamp`.
- **`append_entry(path, entry)`** from `output/provenance.py` — appends to validation.md, creates file if absent. Handles existing content (inserts before ## Validation History).
- **`render_validation_row(attempt, result, feedback)`** from `output/provenance.py` — formats a validation table row. Available but NOT required for this story's provenance entries (the validate_node provenance is an Agent Decisions entry, not a validation table row).
- **`update_story_status(project_root, run_id, story_slug, *, status, started_at, completed_at, retry_count)`** from `output/run_manager.py` — updates a story's entry in `run.yaml`.
- **`update_run_status(project_root, run_id, *, status, last_completed_story, budget)`** from `output/run_manager.py` — updates run-level fields in `run.yaml`. Accepts `BudgetState` directly for budget.
- **`write_success_summary(project_root, run_id)`** from `output/summary.py` — reads `run.yaml` via `get_run_status()`, writes `summary.md`.
- **`write_halt_report(project_root, run_id, *, halted_story, halt_reason, validation_history, last_agent_output, suggested_fix)`** from `output/summary.py` — reads `run.yaml`, writes halt report as `summary.md`.
- **`write_timeout_summary(project_root, run_id)`** from `output/summary.py` — NOT used in this story (timeout is an external condition, not a graph-internal state).
- **`PipelineOutcome`** from `validation/pipeline.py` — StrEnum with `PASS`, `FAIL_V3`, `FAIL_V6`.
- **`PipelineResult`** from `validation/pipeline.py` — has `outcome`, `v6_result`, `v3_result`, `feedback`, `tokens_used`, `cost`, `passed`.
- **`ReflexionFeedback`** from `validation/v3_reflexion.py` — has `unmet_criteria` (list[str]), `feedback_per_criterion` (dict[str, str]).
- **`_serialize_validation_checkpoint()`** — KEEP AS-IS. Do NOT remove or modify.
- **`_generate_halt_report()`** — KEEP AS-IS. Do NOT remove or modify.

### Relationship to Other Stories in Epic 4

- **Story 4.1 (done)**: Created `output/provenance.py` — `append_entry()`, `write_entries()`, `render_validation_row()`. This story CALLS `append_entry()`.
- **Story 4.2 (done)**: Created `output/run_manager.py` — `update_story_status()`, `update_run_status()`, `get_run_status()`. This story CALLS `update_story_status()` and `update_run_status()`.
- **Story 4.3 (review)**: Created `output/summary.py` — `write_success_summary()`, `write_halt_report()`, `write_timeout_summary()`. This story CALLS `write_success_summary()` and `write_halt_report()`.
- **Story 4.4 (this)**: Wires all three into the engine nodes and graph.

### Relationship to Future Stories

- **Story 5.1 (Epic Dispatch)**: Will use `create_run()`, `update_run_status()`, and iterate the story graph for each story. The `finalize_node` added here handles per-story summary writing. Epic-level dispatch will need additional logic for multi-story runs — but the single-story graph correctly produces artifacts already.
- **Story 5.2 (Halt Controller)**: Will use the escalated path through `finalize_node` to ensure halt reports are always written. The halt controller adds CLI-level error handling around graph invocation.
- **Story 5.4 (Halt & Resume Integration)**: May append to existing `summary.md` on resume. The idempotent write behavior of `write_success_summary` / `write_halt_report` (overwrite semantics) provides a clean baseline.

### Testing Patterns

- **Mocking output functions**: All output API calls made by engine nodes MUST be mocked in node unit tests. Use `monkeypatch.setattr` to replace the function at the import site (`arcwright_ai.engine.nodes.append_entry`, etc.). Do NOT mock at the source module (`arcwright_ai.output.provenance.append_entry`) — mock at the callsite.
- **Best-effort testing**: For each output call, write one test that verifies the call is made with correct arguments, and one test that verifies the node completes successfully when the call raises. Use `AsyncMock(side_effect=OSError("disk full"))` for failure scenarios.
- **StoryState fixture**: Reuse the existing `make_run_config()` and `StoryState` construction patterns from existing test_nodes.py tests.
- **Graph tests**: Use `graph.get_graph().nodes` to verify finalize_node is present. Use the existing path-tracing patterns from test_graph.py.
- Use `tmp_path` fixture for any file I/O tests.
- Use `@pytest.mark.asyncio` decorators for all async test functions.

### Project Structure Notes

Files modified by this story:
```
src/arcwright_ai/engine/
├── __init__.py          # MODIFIED: add finalize_node export
├── graph.py             # MODIFIED: add finalize node and reroute terminal edges
└── nodes.py             # MODIFIED: add provenance/run_manager/summary wiring + finalize_node

tests/test_engine/
├── test_nodes.py        # MODIFIED: add mocks for output functions, add new tests
└── test_graph.py        # MODIFIED: update graph structure assertions, add finalize tests
```

Files NOT modified (confirmed unchanged):
```
src/arcwright_ai/output/provenance.py    # Unchanged — called as-is
src/arcwright_ai/output/run_manager.py   # Unchanged — called as-is
src/arcwright_ai/output/summary.py       # Unchanged — called as-is
src/arcwright_ai/output/__init__.py      # Unchanged — no new exports needed
src/arcwright_ai/core/types.py           # Unchanged — ProvenanceEntry used as-is
```

### Known Pitfalls from Epics 1-3

1. **`__all__` ordering must be alphabetical** — ruff enforces this. Adding `finalize_node` to `engine/nodes.py` and `engine/__init__.py` `__all__` must be in sorted position.
2. **No aspirational exports** — only export symbols that actually exist and are implemented. Do NOT pre-export any Story 5.x symbols.
3. **`from __future__ import annotations`** at the top of every module — already present in all files being modified.
4. **Quality gate commands must be run against the FULL repository** (`ruff check .`, not just `ruff check src/arcwright_ai/engine/`), and failures in ANY file must be reported honestly. Do not self-report "zero violations" if violations exist anywhere.
5. **File list in Dev Agent Record must match actual git changes** — verify against `git status` before claiming completion. This was a 7/11 systemic pattern across Epics 2-3.
6. **Google-style docstrings on ALL public functions** — include Args, Returns, Raises sections.
7. **When replacing a placeholder node with real logic, story MUST update existing graph integration tests with appropriate mocks/fixtures** — commit_node goes from placeholder to real logic; existing tests MUST be updated with mocks for the new I/O calls.
8. **Off-by-one in state mutation sequences** — when computing `attempt_number` for provenance entries, use `state.retry_count + 1` (the attempt that just happened), not `state.retry_count` (the count before this attempt).
9. **Structured log event payloads must include ALL fields documented in ACs** — provenance.write_error and run_manager.write_error log events must include `node` and `story` fields.
10. **Use `asyncio.to_thread()` for synchronous operations in async functions** — `datetime.now()` is sync and fast (no thread needed), `Path.mkdir()` is sync (wrap in `asyncio.to_thread()`). The output APIs (`append_entry`, `update_story_status`, etc.) are already async — just `await` them.
11. **`RunStatus.budget` is `dict[str, Any]`** — but `update_run_status()` accepts `BudgetState` directly (it handles serialization internally). Pass `state.budget` (which is `BudgetState`) directly.
12. **Mock at callsite, not source module** — when patching `append_entry` in tests, use `monkeypatch.setattr("arcwright_ai.engine.nodes.append_entry", AsyncMock())`, NOT `monkeypatch.setattr("arcwright_ai.output.provenance.append_entry", AsyncMock())`. The former replaces the name in the calling module's namespace.
13. **Two writes to validation.md in validate_node** — `_serialize_validation_checkpoint()` writes the file first (overwrite), then `append_entry()` reads and appends. This ordering means the provenance entry is added to whatever `_serialize_validation_checkpoint` wrote. Since both happen in the same async function (no concurrency), this is safe.

### Git Intelligence

Recent commits (last 5):
1. `feat(output): implement Story 4.3 — run summary & halt report generation`
2. `feat(story-4.2): create story and scaffold run manager module`
3. `feat(output): create story 4.1 provenance recorder and update sprint status`
4. `chore: Epic 3 retrospective, fix ruff UP037 in invoker.py, close sprint tracking`
5. `fix(agent): change ~/.claude/ handling from allow to silent deny`

Patterns: output package established (3 modules complete), engine/nodes.py at 646 lines (approach 300-line split threshold for consideration but not this story's concern).

### References

- [Source: _spec/planning-artifacts/architecture.md — Decision 3: Provenance Format]
- [Source: _spec/planning-artifacts/architecture.md — Decision 5: Run Directory Schema and Write Policy]
- [Source: _spec/planning-artifacts/architecture.md — Decision 6: Error Handling Taxonomy]
- [Source: _spec/planning-artifacts/architecture.md — Package Dependency DAG]
- [Source: _spec/planning-artifacts/architecture.md — Async Patterns]
- [Source: _spec/planning-artifacts/architecture.md — Python Code Style Patterns]
- [Source: _spec/planning-artifacts/epics.md — Epic 4, Story 4.4]
- [Source: _spec/planning-artifacts/prd.md — FR12 (log decisions), FR32 (run summary)]
- [Source: _spec/planning-artifacts/prd.md — NFR16 (every run produces summary), NFR17 (human-readable markdown)]
- [Source: _spec/implementation-artifacts/4-1-provenance-recorder-decision-logging-during-execution.md — append_entry API, ProvenanceEntry usage]
- [Source: _spec/implementation-artifacts/4-2-run-manager-run-directory-lifecycle-and-state-tracking.md — update_story_status, update_run_status API]
- [Source: _spec/implementation-artifacts/4-3-run-summary-and-halt-report-generation.md — write_success_summary, write_halt_report API, three-function design rationale]
- [Source: _spec/implementation-artifacts/epic-2-retro-2026-03-03.md — Action Items: integration test breakage for placeholder-to-real transitions]
- [Source: _spec/implementation-artifacts/epic-3-retro-2026-03-04.md — Action Items: quality gates on full repo, off-by-one prevention, file list reconciliation]
- [Source: src/arcwright_ai/engine/nodes.py — current node implementations, _serialize_validation_checkpoint, _generate_halt_report]
- [Source: src/arcwright_ai/engine/graph.py — current graph structure]
- [Source: src/arcwright_ai/engine/state.py — StoryState fields, retry_history, budget]
- [Source: src/arcwright_ai/output/provenance.py — append_entry(), render_validation_row()]
- [Source: src/arcwright_ai/output/run_manager.py — update_story_status(), update_run_status(), RunStatusValue]
- [Source: src/arcwright_ai/output/summary.py — write_success_summary(), write_halt_report()]
- [Source: src/arcwright_ai/core/types.py — ProvenanceEntry, BudgetState, ContextBundle]
- [Source: src/arcwright_ai/core/constants.py — VALIDATION_FILENAME, HALT_REPORT_FILENAME, DIR_ARCWRIGHT, DIR_RUNS, DIR_STORIES]
- [Source: src/arcwright_ai/validation/pipeline.py — PipelineOutcome, PipelineResult]

## Dev Agent Record

### Agent Model Used

Claude Sonnet 4.6

### Debug Log References

### Completion Notes List

- Wired `append_entry` into `agent_dispatch_node` after agent-output checkpoint write — best-effort try/except, provenance targets `validation.md` in story run dir.
- Wired `append_entry` into `validate_node` after `_serialize_validation_checkpoint` write — outcome-specific rationale for PASS/FAIL_V6/FAIL_V3, includes unmet AC IDs in `ac_references`.
- Replaced placeholder `commit_node` with real implementation — calls `update_story_status` (status="success") and `update_run_status` (last_completed_story + budget), both best-effort.
- Implemented `finalize_node` with three private helpers: `_derive_halt_reason`, `_build_validation_history_dicts`, `_derive_suggested_fix` — calls `write_success_summary` or `write_halt_report` based on terminal status.
- Updated `build_story_graph()` to route ALL terminal paths (commit, validate escalated, budget_check exceeded) through `finalize` before END.
- Added autouse `_mock_output_functions` fixture to both test_nodes.py and test_graph.py — prevents real I/O in all 441 existing tests.
- Added 21 new tests covering AC #10a-m and AC #11a-e.
- All 462 tests pass. `ruff check .`, `ruff format --check .`, and `mypy --strict src/` all clean.

### File List

- `arcwright-ai/src/arcwright_ai/engine/__init__.py`
- `arcwright-ai/src/arcwright_ai/engine/graph.py`
- `arcwright-ai/src/arcwright_ai/engine/nodes.py`
- `arcwright-ai/tests/test_engine/test_graph.py`
- `arcwright-ai/tests/test_engine/test_nodes.py`
- `_spec/implementation-artifacts/4-4-provenance-and-summary-integration-with-engine-nodes.md` (review updates)
- `_spec/implementation-artifacts/sprint-status.yaml` (status sync)

## Change Log

- 2026-03-04: Story 4.4 created with comprehensive context — ready for dev.
- 2026-03-04: Story 4.4 implemented by Claude Sonnet 4.6 — all 14 tasks complete, 462 tests pass, quality gates clean. Status: review.
- 2026-03-04: Senior code review (AI) completed; fixed missing validation-row provenance context, added escalation provenance entries for escalated validation outcomes, and added error details to best-effort warning logs. Status set to done.
- 2026-03-04: Full repository quality gates re-run after review fixes: `ruff check .`, `mypy --strict src/`, and full `pytest` all pass.

## Senior Developer Review (AI)

### Outcome

Approved after fixes.

### Findings (Resolved)

1. **HIGH — Missing `render_validation_row` integration in `validate_node`**
  - Story AC #3 requires calling `render_validation_row(attempt_number, outcome, feedback_summary)` and preserving that row context in provenance rationale.
  - Fix applied in `arcwright-ai/src/arcwright_ai/engine/nodes.py`: `validate_node` now calls `render_validation_row(...)` and appends the row string to the provenance rationale context.

2. **HIGH — Missing escalation provenance entry on escalation paths**
  - Story AC #4 requires appending a provenance entry when validation escalates.
  - Fix applied in `arcwright-ai/src/arcwright_ai/engine/nodes.py`: both escalation routes in `validate_node` now append an explicit escalation `ProvenanceEntry` (`v6_invariant_failure` and `max_retries_exhausted`).

3. **MEDIUM — Best-effort warning logs omitted error details**
  - Story AC #2/#3 and D5 expectations call for warning logs that include error details.
  - Fix applied in `arcwright-ai/src/arcwright_ai/engine/nodes.py`: all relevant best-effort `except Exception` blocks now capture `exc` and include `error: str(exc)` in structured log payloads (`provenance.write_error`, `run_manager.write_error`, `summary.write_error`).

### Verification

- Targeted tests passed after fixes:
  - `.venv/bin/pytest tests/test_engine/test_nodes.py tests/test_engine/test_graph.py`
  - Result: `70 passed`.
- Full quality gates passed after fixes:
  - `.venv/bin/ruff check .` → `All checks passed!`
  - `.venv/bin/python -m mypy --strict src/` → `Success: no issues found in 37 source files`
  - `.venv/bin/pytest` → `462 passed`.
