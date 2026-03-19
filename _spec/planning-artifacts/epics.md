---
stepsCompleted: ['step-01-validate-prerequisites', 'step-02-design-epics', 'step-03-create-stories', 'step-04-final-validation']
inputDocuments:
  - '_spec/planning-artifacts/prd.md'
  - '_spec/planning-artifacts/architecture.md'
date: 2026-03-02
author: Ed
epicCount: 12
storyCount: 50
totalPoints: 228
frCoverage: '36/36'
nfrCoverage: '20/20'
amendedDate: 2026-03-16
amendedBy: Ed
amendments:
  - date: '2026-03-15'
    description: 'Epic 11: BMAD 6.1 Framework Upgrade — 3 stories, 13 pts. Course correction CC-2026-03-15 approved.'
  - date: '2026-03-16'
    description: 'Epic 12: CI-Aware Merge Wait for Epic Chain Integrity — 4 stories, 19 pts. Tech spec ci-aware-merge-wait.md approved.'
---

# Arcwright AI - Epic Breakdown

## Overview

This document provides the complete epic and story breakdown for Arcwright AI, decomposing the requirements from the PRD and Architecture into implementable stories.

## Requirements Inventory

### Functional Requirements

**Orchestration & Execution**

- FR1: Developer can dispatch all stories in an epic for sequential autonomous execution
- FR2: Developer can dispatch a single story for autonomous execution
- FR3: System executes stories one at a time in dependency order within an epic
- FR4: System halts execution when a story fails validation after maximum retries, preserving all completed work
- FR5: Developer can resume a halted epic from the failure point, skipping previously completed stories
- FR6: System creates an isolated git worktree for each story execution
- FR7: System cleans up worktrees via manual command, automatic on next dispatch, or post-merge hook (all idempotent)

**Validation & Quality**

- FR8: System evaluates each story's implementation against its acceptance criteria using reflexion (V3)
- FR9: System retries story implementation when reflexion identifies unmet acceptance criteria, up to a configurable maximum
- FR10: System performs invariant checks (V6) on each story — file existence, schema validity, naming conventions
- FR11: System generates a structured failure report when a story halts, including retry history and the specific unmet criteria

**Decision Provenance**

- FR12: System logs every implementation decision where the agent chose between multiple alternatives, deviated from acceptance criteria, or selected a design pattern — each logged as a provenance entry during story execution
- FR13: Each provenance entry includes the decision, alternatives considered, rationale, and references to acceptance criteria or architecture docs
- FR14: Provenance is written as markdown files in `.arcwright-ai/runs/<run-id>/provenance/`
- FR15: Provenance is attached to generated pull requests for code review context

**Context Injection**

- FR16: System reads BMAD planning artifacts and injects the story's acceptance criteria, the matching architecture section, and applicable domain requirements into each agent prompt
- FR17: System responds with the applicable BMAD rule when the agent queries about workflow steps, artifact formats, or naming conventions (answerer component, static rule lookup)
- FR18: System resolves story dependencies and artifact references before agent invocation

**Agent Invocation**

- FR19: System invokes Claude Code SDK per story with no persistent agent state between stories
- FR20: System enforces that agent file operations cannot modify files outside the project base directory
- FR21: System writes temporary files to `.arcwright-ai/tmp/`, auto-added to `.gitignore`, cleaned up at story completion
- FR22: System implements backoff and queuing when API rate limits are hit

**Cost & Resource Tracking**

- FR23: System tracks token consumption and estimated cost per story and per run
- FR24: Developer can view cost summary as part of run status output
- FR25: System enforces a per-story token ceiling — halts before the next SDK invocation if cumulative tokens exceed the configured limit

**Project Setup & Configuration**

- FR26: Developer can initialize a new Arcwright AI project via `arcwright-ai init`, which scaffolds the `.arcwright-ai/` directory, generates a default config file, adds temp/run directories to `.gitignore`, and detects existing BMAD artifacts
- FR27: Developer can validate project setup via `arcwright-ai validate-setup`, which checks API key, project structure, artifact presence, and config validity with pass/fail per check and actionable fix instructions on failure
- FR28: System loads configuration with precedence: environment variables > project config > global config > defaults
- FR29: System warns on unknown config keys (forward compatibility) and errors on missing required keys or invalid value types with specific messages
- FR30: Developer can configure model version, token ceiling, branch naming template, cost limits, timeout, and reproducibility settings

**Run Visibility**

- FR31: Developer can check current or last run status via CLI, including completion state and cost summary
- FR32: System generates a run summary as a markdown file in `.arcwright-ai/runs/<run-id>/summary.md` containing story completion status, validation results, cost, and provenance references
- FR33: System generates structured halt reports as markdown files when execution stops due to failure, cost, or timeout

**SCM Integration**

- FR34: System creates git branches per story using a configurable naming template
- FR35: System generates pull requests for completed stories with decision provenance embedded
- FR36: System manages worktree lifecycle — creation before story execution, disposal after validation failure

### NonFunctional Requirements

**Reliability**

- NFR1: System never silently produces incorrect output — every story completion path passes through V3 or V6 validation. No validation bypass paths exist in the architecture.
- NFR2: Partial epic completion is always recoverable — completed stories are preserved, `--resume` picks up where it left off
- NFR3: System handles unexpected SDK errors (network timeout, API 500, malformed response) gracefully — retry or halt, never crash
- NFR4: Worktree isolation prevents any story execution from corrupting the main branch or other stories' worktrees
- NFR5: Config validation catches all invalid states at startup — never fails mid-run due to bad config

**Security**

- NFR6: API keys never written to project-level files or committed to git
- NFR7: Agent file operations cannot escape the project base directory
- NFR8: `.arcwright-ai/tmp/` and `.arcwright-ai/runs/` added to `.gitignore` automatically on init

**Performance & Cost Efficiency**

- NFR9: Orchestration overhead < 30 seconds per story (excluding agent invocation and validation)
- NFR10: Token ceiling enforcement stops spending before the next invocation, not after
- NFR11: Retry cycles converge or halt within configured limits — no infinite retry loops
- NFR12a: Cost tracking captures every SDK invocation with no missed calls
- NFR12b: Tracked cost vs. actual invoice ≤ 10% variance

**Integration**

- NFR13: System works with AI agent SDK version pinned in project dependencies — no implicit dependency on latest SDK
- NFR14: Git operations work with standard git 2.25+ — no dependency on git features introduced after 2.25
- NFR15: Generated PRs conform to SCM platform API format and render correctly in pull request view

**Observability**

- NFR16: Every run produces a complete summary file without requiring additional commands
- NFR17: Decision provenance is human-readable without tooling — plain markdown, clear structure
- NFR18: Halt reports contain all 4 required diagnostic fields: (1) failing AC ID, (2) retry count + history, (3) last agent output (truncated), (4) suggested fix

**System-Wide Quality Attributes**

- NFR19: All operations that may be retried or re-invoked are idempotent — repeated execution produces the same result as single execution
- NFR20: System completes local operations even when external services (GitHub, git remote) are unavailable. External failures surfaced as warnings, not halts.

### Additional Requirements

**From Architecture — Starter Template & Project Scaffold**

- Custom scaffold selected — no existing Python template matches the LangGraph + Typer + Claude Code SDK + `.arcwright-ai/` stack. Project scaffold is the first implementation story.
- 8 packages aligned to subsystem map: `cli/`, `engine/`, `validation/`, `agent/`, `context/`, `output/`, `scm/`, `core/`
- Python 3.11+, Typer CLI, Pydantic models, PyYAML, Ruff + mypy + pre-commit, pytest + pytest-asyncio

**From Architecture — Core Architectural Decisions**

- D1 (State Model): Hybrid approach — preflight assembles context payload into LangGraph state, downstream nodes consume. Pydantic models for `ProjectState`, `StoryState`, `BudgetState`.
- D2 (Retry & Halt): Validation-only retries (V3 reflexion failures only). Dual budget — invocation count ceiling AND cost ceiling. Halt entire epic on failure.
- D3 (Provenance Format): One markdown file per story, validation history included, collapsible `<details>` blocks for PR embedding. Path contract: `.arcwright-ai/runs/<run-id>/stories/<story-slug>/validation.md`
- D4 (Context Injection): Dispatch-time assembly in preflight node. Strict regex-only reference resolution in MVP (FR IDs, architecture section anchors). No fuzzy matching. No LLM fallback.
- D5 (Run Directory Schema): Run ID format `YYYYMMDD-HHMMSS-<short-uuid>`. Story slug as directory name. `run.yaml` for metadata. LangGraph state is authority during execution; run dir files are transition checkpoints.
- D6 (Error Handling): 6-class exception hierarchy (`ArcwrightError` → `ConfigError`, `ProjectError`, `ContextError`, `AgentError`, `ValidationError`, `ScmError`). Exit codes 0-5.
- D7 (Git Operations): Shell out to `git` CLI via async subprocess wrapper. Worktree lifecycle with atomic guarantees. Branch naming: `arcwright-ai/<story-slug>`. Fetch + fast-forward merge before worktree creation. Push + PR after validation. Optional auto-merge.
- D8 (Logging & Observability): Two channels — Rich/Typer formatted text for humans (stderr), JSONL structured log for machines (`.arcwright-ai/runs/<run-id>/log.jsonl`).

**From Architecture — Cross-Cutting Constraints**

- Package Dependency DAG (mandatory): `cli → engine → {validation, agent, context, output, scm} → core`. Cross-domain imports forbidden.
- Async-first: All I/O is async (`asyncio.to_thread()` for file I/O, `asyncio.create_subprocess_exec` for git). CLI wraps with `asyncio.run()`.
- Observe mode hooks: `core/events.py` — every subsystem calls `emit()`, MVP default is no-op/log. Design in MVP, ship later.
- 5-layer dependency model: Design data structures for all 5 layers (phase ordering → existence checks → status gates → assignee locks → hash staleness), implement layers 1-2 in MVP.
- Task lifecycle: `queued → preflight → running → validating → success/retry/escalated` — architectural backbone, every subsystem respects it.
- Budget check node: Explicit conditional edge before agent dispatch; retries route through budget_check.
- `core/io.py`: Primitives ONLY — YAML pair + async text pair. No domain logic.

**From Architecture — Testing Infrastructure**

- Mock SDK client: Predictable async generator responses for success, failure, rate limit, malformed scenarios
- Synthetic BMAD project fixtures: `valid_project/` (passes V6), `invalid_project/` (fails V6), `partial_project/` (resume testing)
- `tmp_project` conftest fixture for integration tests
- SCM tests marked `@pytest.mark.slow` with real git operations
- Integration test directory: `test_dispatch_flow.py`, `test_resume_flow.py`, `test_budget_halt_flow.py`

### FR Coverage Map

| FR | Epic | Description |
|----|------|-------------|
| FR1 | Epic 2 | Dispatch all stories in an epic for sequential execution |
| FR2 | Epic 2 | Dispatch a single story for execution |
| FR3 | Epic 2 | Sequential execution in dependency order |
| FR4 | Epic 5 | Halt on max retry failure, preserve completed work |
| FR5 | Epic 5 | Resume halted epic from failure point |
| FR6 | Epic 6 | Git worktree isolation per story |
| FR7 | Epic 6 | Worktree cleanup (MVP: manual only per D7; automatic & post-merge deferred to Growth) |
| FR8 | Epic 3 | V3 reflexion validation against acceptance criteria |
| FR9 | Epic 3 | Retry on reflexion failure up to configurable max |
| FR10 | Epic 3 | V6 invariant checks (file exists, schema, naming) |
| FR11 | Epic 3 | Structured failure report on halt |
| FR12 | Epic 4 | Log implementation decisions as provenance entries |
| FR13 | Epic 4 | Structured provenance entries (decision, alternatives, rationale) |
| FR14 | Epic 4 | Provenance written to `.arcwright-ai/runs/` |
| FR15 | Epic 6 | Provenance attached to PRs |
| FR16 | Epic 2 | Read BMAD artifacts, inject into agent prompt |
| FR17 | Epic 2 | Answerer static rule lookup |
| FR18 | Epic 2 | Resolve story dependencies and artifact refs |
| FR19 | Epic 2 | Claude Code SDK invocation per story (stateless) |
| FR20 | Epic 2 | Agent file operations can't escape project dir |
| FR21 | Epic 2 | Temp files to `.arcwright-ai/tmp/`, cleaned up |
| FR22 | Epic 2 | Rate limit backoff and queuing |
| FR23 | Epic 7 | Track token consumption and cost per story/run |
| FR24 | Epic 7 | View cost summary in run status |
| FR25 | Epic 7 | Per-story token ceiling enforcement |
| FR26 | Epic 1 | `arcwright-ai init` scaffolds project |
| FR27 | Epic 1 | `arcwright-ai validate-setup` with pass/fail checks |
| FR28 | Epic 1 | Config precedence: env > project > global > defaults |
| FR29 | Epic 1 | Config validation: warn unknown, error missing |
| FR30 | Epic 1 | Configurable model, token ceiling, branch naming, etc. |
| FR31 | Epic 5 | CLI run status with completion state and cost |
| FR32 | Epic 4 | Run summary as markdown in `.arcwright-ai/runs/` |
| FR33 | Epic 4 | Structured halt reports as markdown |
| FR34 | Epic 6 | Git branches per story with configurable naming |
| FR35 | Epic 6 | PR generation with decision provenance embedded |
| FR36 | Epic 6 | Worktree lifecycle management |
| FR37 | Epic 9 | Configurable default branch with auto-detect fallback |
| FR38 | Epic 9 | Fetch + fast-forward merge before worktree creation |
| FR39 | Epic 9 | Optional auto-merge PR after creation |

## Epic List

### Epic 1: Project Foundation & Configuration
Developer can install Arcwright AI, initialize a project, validate their setup, and have confidence the tool is correctly configured before ever dispatching a run.
**FRs covered:** FR26, FR27, FR28, FR29, FR30
**NFRs addressed:** NFR5, NFR6, NFR8

### Epic 2: Orchestration Engine & Agent Invocation
Developer can dispatch a single story and have the LangGraph engine invoke Claude Code SDK to produce an implementation — the core execution loop works end-to-end for one story.
**FRs covered:** FR1, FR2, FR3, FR16, FR17, FR18, FR19, FR20, FR21, FR22
**NFRs addressed:** NFR1, NFR3, NFR4, NFR7, NFR9, NFR13

### Epic 3: Validation & Retry Pipeline
Developer can trust that every story output is validated against acceptance criteria (V3 reflexion) and invariant rules (V6), with automatic retry on failure — no silent bad output.
**FRs covered:** FR8, FR9, FR10, FR11
**NFRs addressed:** NFR1, NFR11

### Epic 4: Decision Provenance & Run Artifacts
Developer wakes up to a complete reasoning trail — every significant implementation decision is logged, structured, and ready for review. Run summaries and halt reports provide instant morning-review UX.
**FRs covered:** FR12, FR13, FR14, FR32, FR33
**NFRs addressed:** NFR16, NFR17, NFR18

### Epic 5: Halt, Resume & Epic Dispatch
Developer can dispatch a full epic (multiple stories), have the system halt loudly on unrecoverable failure preserving all completed work, and resume from the failure point — the overnight dispatch pattern works.
**FRs covered:** FR1, FR3, FR4, FR5, FR31
**NFRs addressed:** NFR2, NFR3

### Epic 6: SCM Integration & PR Generation
Developer gets clean git branches per story, worktree lifecycle management, automated commits with push, and pull requests with decision provenance embedded — code review is decision-centric, not line-by-line.
**FRs covered:** FR6, FR7, FR15, FR34, FR35, FR36
**NFRs addressed:** NFR4, NFR14, NFR15, NFR19, NFR20

### Epic 7: Cost Tracking & Budget Enforcement
Developer has full visibility into API spend per story and per run, with budget enforcement that halts before overspending — economics are transparent and controllable.
**FRs covered:** FR23, FR24, FR25
**NFRs addressed:** NFR10, NFR12a, NFR12b

### Epic 8: Role-Based Model Registry
Developer can configure separate LLM models for code generation and code review, enabling adversarial quality patterns where a fast model writes code and a thorough model reviews it — optimizing both speed and cost.
**Architecture Decision:** D9 (Role-Based Model Registry)
**FRs covered:** FR22, FR30
**NFRs addressed:** NFR12a, NFR12b

### Epic 9: SCM Enhancements — Fetch, Default Branch & Auto-Merge
Developer dispatches an overnight epic run and every story starts from the latest upstream code, creates PRs against the correct default branch, and optionally auto-merges — the full chain from dispatch to merged code runs unattended.
**FRs covered:** FR37, FR38, FR39
**NFRs addressed:** NFR4, NFR19, NFR20

### Epic 12: CI-Aware Merge Wait for Epic Chain Integrity
Developer dispatches a multi-story epic with auto-merge enabled and the engine waits for each story's CI checks to pass and the PR to merge before starting the next story — ensuring every story builds on verified, merged code. If CI fails, the epic halts cleanly.
**FRs covered:** FR4, FR39
**NFRs addressed:** NFR1, NFR2, NFR19
**Tech Spec:** `_spec/implementation-artifacts/ci-aware-merge-wait.md`

## Epic 1: Project Foundation & Configuration

Developer can install Arcwright AI, initialize a project, validate their setup, and have confidence the tool is correctly configured before ever dispatching a run.

### Story 1.1: Project Scaffold & Package Structure

**Priority**: HIGH | **Points**: 8

As a developer contributing to Arcwright AI,
I want a fully scaffolded Python project with the 8-package structure defined in the architecture,
So that all subsequent stories have a working build, test, and lint pipeline to develop against.

**Acceptance Criteria:**

**Given** an empty project directory
**When** the scaffold is created
**Then** the directory structure matches the architecture doc exactly: `src/arcwright_ai/` with `cli/`, `engine/`, `validation/`, `agent/`, `context/`, `output/`, `scm/`, `core/` packages
**And** `pyproject.toml` defines metadata, dependencies (LangGraph, Typer, Pydantic, PyYAML, Claude Code SDK), `[dev]` extras (pytest, pytest-asyncio, ruff, mypy), and build config
**And** every `__init__.py` defines `__all__` with re-exports only, no logic
**And** `py.typed` marker file exists for PEP 561
**And** `.pre-commit-config.yaml` configures ruff + mypy hooks
**And** `.github/workflows/ci.yml` runs pytest + ruff check + ruff format --check + mypy --strict
**And** `pip install -e ".[dev]"` succeeds and `arcwright-ai --help` shows "Arcwright AI" with no commands (empty Typer app)
**And** `ruff check .` passes with zero violations
**And** `mypy --strict src/` passes with zero errors
**And** `pytest` runs with zero tests collected (test directories exist, no test files yet)

### Story 1.2: Core Types, Lifecycle & Exception Hierarchy

**Priority**: HIGH | **Points**: 5

As a developer building Arcwright AI subsystems,
I want the shared type definitions, task lifecycle state machine, and exception hierarchy established in `core/`,
So that all subsequent subsystem stories import from a stable, well-tested foundation.

**Acceptance Criteria:**

**Given** the `core/` package exists from Story 1.1
**When** core types are implemented
**Then** `core/types.py` defines `StoryId`, `EpicId`, `RunId` (typed `str` wrappers), `ArtifactRef` (with optional extension fields for dependency layers 3-5), `ContextBundle`, `BudgetState`, and `ProvenanceEntry` as Pydantic models
**And** `core/lifecycle.py` defines `TaskState` as a `StrEnum` with states: `queued`, `preflight`, `running`, `validating`, `success`, `retry`, `escalated`
**And** `core/lifecycle.py` includes a transition validation function that rejects invalid state transitions
**And** `core/exceptions.py` defines the full hierarchy: `ArcwrightError` → `ConfigError`, `ProjectError`, `ContextError`, `AgentError` (with `AgentTimeoutError`, `AgentBudgetError`), `ValidationError`, `ScmError` (with `WorktreeError`, `BranchError`), `RunError`
**And** every exception carries `message` (str) and optional `details` (dict)
**And** `core/constants.py` defines `DIR_ARCWRIGHT`, `DIR_SPEC`, `EXIT_SUCCESS` through `EXIT_INTERNAL`, `MAX_RETRIES`, `BRANCH_PREFIX`, and all magic strings
**And** `core/events.py` defines an `EventEmitter` protocol with `emit()` and a `NoOpEmitter` default implementation
**And** `core/io.py` provides `load_yaml()`, `save_yaml()`, `read_text_async()`, `write_text_async()` — primitives only, no domain logic
**And** `ArcwrightModel` base class uses `frozen=True`, `extra="forbid"`, `str_strip_whitespace=True`
**And** all public classes/functions have Google-style docstrings
**And** unit tests in `tests/test_core/` cover all types, lifecycle transitions (valid + invalid), exception construction, constants, events, and io functions

### Story 1.3: Configuration System with Two-Tier Loading

**Priority**: HIGH | **Points**: 5

As a developer setting up Arcwright AI,
I want a configuration system that loads settings from environment variables, project config, and global config with proper precedence,
So that I can configure API keys, model versions, token ceilings, and project-specific settings with confidence that invalid config is caught at startup.

**Acceptance Criteria:**

**Given** a `core/config.py` module
**When** configuration is loaded
**Then** `RunConfig` Pydantic model validates all fields: `api.claude_api_key`, `model.version`, `limits.tokens_per_story`, `limits.cost_per_run`, `limits.retry_budget`, `limits.timeout_per_story`, `methodology.artifacts_path`, `methodology.type`, `scm.branch_template`, `reproducibility.enabled`, `reproducibility.retention`
**And** precedence chain is enforced: env vars (`ARCWRIGHT_*`) > project config (`.arcwright-ai/config.yaml`) > global config (`~/.arcwright-ai/config.yaml`) > built-in defaults
**And** unknown keys produce a warning (not error) for forward compatibility
**And** missing required keys produce an error with specific "missing field: X" message and fix instruction
**And** invalid value types produce an error with expected vs actual type
**And** API keys are never loaded from project-level config files (global or env var only) per NFR6
**And** `ConfigError` is raised with actionable messages on any validation failure
**And** `load_config()` function accepts optional `project_root: Path` and returns a validated `RunConfig`
**And** unit tests cover: full precedence chain, env var override, missing required fields, unknown keys (warning), invalid types (error), API key source restriction

### Story 1.4: CLI Init Command

**Priority**: HIGH | **Points**: 3

As a developer starting a new Arcwright AI project,
I want to run `arcwright-ai init` to scaffold the `.arcwright-ai/` directory with default config and `.gitignore` entries,
So that my project is ready for dispatching runs with minimal manual setup.

**Acceptance Criteria:**

**Given** a project directory with an existing `_spec/` directory containing BMAD artifacts
**When** I run `arcwright-ai init`
**Then** `.arcwright-ai/` directory is created with `config.yaml` (default values), `runs/` (empty), `worktrees/` (empty), `tmp/` (empty)
**And** `.arcwright-ai/tmp/` and `.arcwright-ai/runs/` are added to the project `.gitignore` (created if it doesn't exist, appended if it does)
**And** the init command detects and reports BMAD artifacts found in `_spec/`: PRD, architecture, epics, stories
**And** running `arcwright-ai init` on an already-initialized project is idempotent — existing config is preserved, missing directories are created, `.gitignore` entries are not duplicated
**And** output is formatted using Rich/Typer to stderr per D8
**And** exit code is 0 on success
**And** unit tests cover: fresh init, idempotent re-init, BMAD artifact detection, `.gitignore` append behavior

### Story 1.5: CLI Validate-Setup Command

**Priority**: HIGH | **Points**: 5

As a developer about to dispatch my first run,
I want to run `arcwright-ai validate-setup` to verify my configuration, API key, and project structure with clear pass/fail per check,
So that I catch configuration problems before they become mid-run failures.

**Acceptance Criteria:**

**Given** an initialized Arcwright AI project
**When** I run `arcwright-ai validate-setup`
**Then** the command checks and reports pass/fail for each: (1) Claude API key present and non-empty, (2) BMAD project structure detected at configured artifacts path, (3) planning artifacts found (PRD, architecture, epics), (4) story artifacts found with acceptance criteria, (5) Arcwright AI config valid per schema
**And** each failed check includes a specific fix instruction (e.g., "Expected: `./_spec/` — check config.yaml → methodology.artifacts_path")
**And** if a critical check fails (API key, project structure), subsequent dependent checks are skipped with a "Cannot validate — requires [failed check]" message
**And** exit code is 0 if all checks pass, 3 (ConfigError) if any critical check fails
**And** output uses Rich/Typer formatting to stderr per D8
**And** unit tests cover: all-pass scenario, missing API key, wrong artifacts path, missing planning artifacts, invalid config, dependent check skipping

## Epic 2: Orchestration Engine & Agent Invocation

Developer can dispatch a single story and have the LangGraph engine invoke Claude Code SDK to produce an implementation — the core execution loop works end-to-end for one story.

### Story 2.1: LangGraph State Models & Graph Skeleton

**Priority**: HIGH | **Points**: 5

As a developer building the orchestration engine,
I want the Pydantic state models (`ProjectState`, `StoryState`) and a minimal LangGraph StateGraph skeleton with placeholder nodes,
So that subsequent stories can implement real node logic into a working graph framework.

**Acceptance Criteria:**

**Given** the `engine/` package and `core/` types from Epic 1
**When** state models and graph are implemented
**Then** `engine/state.py` defines `StoryState` (mutable, `frozen=False`) with fields: `story_id`, `epic_id`, `run_id`, `story_path`, `project_root`, `status` (TaskState), `context_bundle` (optional ContextBundle), `agent_output` (optional str), `validation_result` (optional), `retry_count` (int), `budget` (BudgetState), `config` (RunConfig reference)
**And** `engine/state.py` defines `ProjectState` with fields: `epic_id`, `run_id`, `stories` (list of StoryState), `config`, `status`, `completed_stories`, `current_story_index`
**And** `BudgetState` in `core/types.py` defines the core engine fields: `invocation_count` (int), `total_tokens` (int), `estimated_cost` (Decimal), `max_invocations` (int), `max_cost` (Decimal) — sufficient for the `budget_check` node to function. Per-story breakdown, pricing model, and run.yaml serialization are owned by Story 7.1.
**And** `engine/graph.py` defines `build_story_graph()` that returns a compiled LangGraph `StateGraph` with nodes: `preflight`, `budget_check`, `agent_dispatch`, `validate`, `commit`, and conditional edges: budget_check → agent_dispatch (if OK) or escalated (if exceeded), validate → commit (success) or budget_check (retry) or escalated
**And** all nodes are placeholder async functions that log entry/exit and pass through state with appropriate status transitions
**And** `engine/nodes.py` contains all node function stubs with correct signatures: `async def preflight_node(state: StoryState) -> StoryState`
**And** graph can be compiled and invoked with a test StoryState without errors
**And** unit tests verify graph construction, node routing (success path, retry path, escalated path), and state model validation

### Story 2.2: Context Injector — BMAD Artifact Reader & Reference Resolver

**Priority**: HIGH | **Points**: 5

As a developer dispatching a story,
I want the system to read BMAD planning artifacts and resolve FR/NFR/architecture references from the story file into a focused context bundle,
So that the agent receives the relevant requirements, architecture decisions, and acceptance criteria for the story it's implementing.

**Acceptance Criteria:**

**Given** a story markdown file with FR references (e.g., `FR-1`, `NFR-5`) and architecture section references
**When** `context/injector.py` processes the story
**Then** the story parser extracts the story text, acceptance criteria, and all natural references (FR IDs, NFR IDs, architecture section anchors)
**And** the context resolver maps FR/NFR IDs via regex (`FR-?\d+`, `NFR-?\d+`) to their definitions in the PRD document
**And** architecture references are resolved to the relevant section text from `architecture.md`
**And** the bundle builder assembles a `ContextBundle` containing: story text, resolved requirement snippets, relevant architecture excerpts, project conventions
**And** every context payload entry carries a source reference (file path + section anchor) for provenance tracing
**And** unresolved references are logged as `context.unresolved` structured events (not errors) — agent proceeds with available context
**And** no fuzzy matching or LLM fallback — pure regex pattern matching only per D4
**And** the assembled bundle is serializable to markdown for checkpoint writing
**And** unit tests cover: successful reference resolution, unresolved references (logged not errored), empty story (no refs), architecture section lookup, bundle assembly

### Story 2.3: Context Answerer — Static Rule Lookup Engine

**Priority**: MEDIUM | **Points**: 3

As a developer whose agent needs to query BMAD conventions during implementation,
I want a static rule lookup engine that responds to agent questions about workflow steps, artifact formats, and naming conventions,
So that the agent can follow project conventions without LLM-based interpretation.

**Acceptance Criteria:**

**Given** a `context/answerer.py` module
**When** the answerer is initialized with a project's BMAD artifacts
**Then** it indexes document sections by heading, building a searchable map of rules and conventions
**And** `lookup_answer(question_pattern: str) -> str | None` matches questions against indexed patterns using regex
**And** unmatched patterns return `None` and are logged as a provenance note ("no answer available")
**And** the answerer handles queries about: naming conventions, file structure patterns, coding standards, artifact format rules
**And** answers include the source document path and section for traceability
**And** unit tests cover: successful pattern match, no match (returns None), multiple matches (returns most specific), index building from sample BMAD artifacts

### Story 2.4: Agent Sandbox — Path Validation Layer

**Priority**: HIGH | **Points**: 3

As a developer ensuring agent safety,
I want an application-level path validation layer that prevents the agent from modifying files outside the project boundary,
So that story execution cannot corrupt the main branch, other worktrees, or the host system.

**Acceptance Criteria:**

**Given** `agent/sandbox.py` implemented as a pure validator function
**When** the sandbox validates a file operation
**Then** `validate_path(path: Path, project_root: Path, operation: str) -> bool` returns `True` only if the resolved path is within `project_root`
**And** path traversal attempts (e.g., `../../etc/passwd`, symlink escape) are rejected and raise `SandboxViolation` (subclass of `AgentError`)
**And** temp file operations are validated to target `.arcwright-ai/tmp/` only
**And** the sandbox has zero coupling to Claude Code SDK — it validates `(path, operation) → allow/deny` as a pure function
**And** the sandbox is designed for dependency injection into the invoker (not imported directly by invoker)
**And** unit tests cover: valid paths (within project), path traversal rejection, symlink escape detection, temp file validation, `.arcwright-ai/` subdirectory access

### Story 2.5: Agent Invoker — Claude Code SDK Integration

**Priority**: HIGH | **Points**: 8

As a developer dispatching a story,
I want the system to invoke Claude Code SDK with the assembled context bundle and receive the agent's implementation output,
So that stories are implemented by the AI agent in a stateless, sandboxed session.

**Acceptance Criteria:**

**Given** `agent/invoker.py` and `agent/prompt.py` modules
**When** a story is dispatched to the agent
**Then** `prompt.py` assembles the SDK prompt from the `ContextBundle`: story text + resolved requirements + architecture excerpts + project conventions formatted as a single prompt string
**And** `invoker.py` invokes Claude Code SDK as an async generator with: the assembled prompt, model version from config, and session-specific parameters
**And** each invocation is stateless — no persistent agent state between stories per FR19
**And** the invoker passes every file operation through the sandbox validator (injected) before applying
**And** SDK errors (network timeout, API 500, malformed response) are caught and wrapped as `AgentError` subclasses per D6
**And** rate limit responses (HTTP 429 / SDK rate limit errors) trigger exponential backoff with jitter per FR22: starting at 1s, capping at 60s, transparent to the user, logged as structured event `agent.rate_limit` with wait duration
**And** token consumption from the SDK response is captured and returned alongside the agent output for budget tracking
**And** temp files are written to `.arcwright-ai/tmp/` per FR21
**And** defines `MockSDKClient` test fixture that returns configurable: `output_text` (str), `tokens_input` (int), `tokens_output` (int), `error` (optional exception type) — used by all downstream stories that test through the engine pipeline
**And** unit tests use the `MockSDKClient` fixture (not ad-hoc mocks): success response, failure response, rate limit response, malformed response, sandbox violation

### Story 2.6: Preflight Node — Context Assembly & Dispatch Preparation

**Priority**: HIGH | **Points**: 5

As a developer dispatching a story,
I want the preflight graph node to resolve all context, prepare the execution environment, and write the context bundle checkpoint,
So that the agent receives complete context and provenance can trace exactly what information informed the implementation.

**Acceptance Criteria:**

**Given** the preflight node in the LangGraph StateGraph
**When** a story enters the preflight node
**Then** the node invokes `context/injector.py` to resolve all references and build the `ContextBundle`
**And** the assembled bundle is stored in `StoryState.context_bundle`
**And** the context bundle is written as a checkpoint to `.arcwright-ai/runs/<run-id>/stories/<story-slug>/context-bundle.md`
**And** `StoryState.status` transitions from `queued` to `preflight` then to `running`
**And** on context resolution failure, `ContextError` is raised (exit code 3 — user-fixable)
**And** structured log events are emitted: `context.resolve` with refs found/unresolved counts
**And** the node returns the full `StoryState` (not partial dicts) using `model_copy(update={...})`
**And** unit tests verify: successful preflight with bundle written, context error handling, state transitions, checkpoint file creation

### Story 2.7: Agent Dispatch Node & Single Story CLI Command

**Priority**: HIGH | **Points**: 8

As a developer,
I want to run `arcwright-ai dispatch --story STORY-N.N` and have the full preflight → budget_check → agent_dispatch pipeline execute for a single story,
So that I can verify the core execution loop works end-to-end.

**Acceptance Criteria:**

**Given** the LangGraph StateGraph with implemented preflight and agent_dispatch nodes
**When** I run `arcwright-ai dispatch --story STORY-1.1`
**Then** the CLI parses the story identifier and loads the corresponding story file from the epics/stories artifacts
**And** the engine builds and runs the StateGraph for the single story
**And** the preflight node assembles context, the budget_check node passes (first run, no budget consumed), and the agent_dispatch node invokes the SDK
**And** agent output is written to `.arcwright-ai/runs/<run-id>/stories/<story-slug>/agent-output.md`
**And** `StoryState.budget` is updated with tokens consumed and estimated cost
**And** CLI output shows story start, agent invocation, and completion status using Rich/Typer formatting
**And** structured JSONL events are written to `.arcwright-ai/runs/<run-id>/log.jsonl` for: `run.start`, `story.start`, `context.resolve`, `agent.dispatch`, `agent.response`
**And** exit code is 0 on successful agent completion (validation not yet wired)
**And** `arcwright-ai dispatch --epic EPIC-N` dispatches all stories in the epic sequentially in dependency order per FR1/FR3 (basic sequential iteration only — no pre-dispatch confirmation, scope validation, or cost estimates; full epic dispatch UX is Story 5.1)
**And** integration test with mock SDK verifies the full CLI → engine → context → agent pipeline

## Epic 3: Validation & Retry Pipeline

Developer can trust that every story output is validated against acceptance criteria (V3 reflexion) and invariant rules (V6), with automatic retry on failure — no silent bad output.

### Story 3.1: V6 Invariant Validation — Deterministic Rule Checks

**Priority**: HIGH | **Points**: 5

As a developer who needs confidence in code quality,
I want deterministic invariant checks that verify file existence, schema validity, and naming conventions on every story output,
So that basic structural correctness is guaranteed without relying on LLM judgment.

**Acceptance Criteria:**

**Given** `validation/v6_invariant.py` module
**When** V6 validation runs against a story's agent output
**Then** the validator checks: (1) all files referenced in the story exist in the worktree, (2) generated files follow project naming conventions from `core/constants.py`, (3) Python files are syntactically valid (AST parse), (4) any schema-constrained files (YAML configs, Pydantic models) pass schema validation
**And** each check returns a structured result: check name, pass/fail, failure details if applicable
**And** the overall V6 result is pass (all checks pass) or fail (any check fails) with a list of specific failures
**And** V6 failures are immediate — no retry, no LLM judgment. These are objective rule violations.
**And** the validator is extensible — new invariant checks can be added as functions registered in a check registry
**And** unit tests cover: all-pass scenario, missing file detection, naming convention violation, syntax error detection, schema validation failure

### Story 3.2: V3 Reflexion Validation — LLM Self-Evaluation

**Priority**: HIGH | **Points**: 8

As a developer who needs the agent to verify its own work against acceptance criteria,
I want V3 reflexion validation that has the agent self-evaluate whether its implementation satisfies each acceptance criterion,
So that the agent catches its own mistakes before the story is marked as complete.

**Acceptance Criteria:**

**Given** `validation/v3_reflexion.py` module
**When** V3 reflexion validation runs against a story's agent output
**Then** the validator constructs a reflexion prompt containing: the story's acceptance criteria, the agent's implementation output, and the instruction to evaluate each AC as pass/fail with rationale
**And** the reflexion prompt is sent to the Claude Code SDK (separate invocation from implementation — stateless)
**And** the reflexion response is parsed to extract: per-AC pass/fail, rationale for each, overall story pass/fail
**And** token consumption from the reflexion invocation is tracked in `BudgetState` (validation costs count toward budget)
**And** a `ValidationResult` model captures all per-AC results, overall verdict, and the raw reflexion response
**And** reflexion feedback is returned as a `ReflexionFeedback` dataclass: `passed` (bool), `unmet_criteria` (list of AC IDs that failed), `feedback_per_criterion` (dict mapping AC ID → specific failure description + suggested fix), `attempt_number` (int) — this is the contract consumed by Story 2.5's retry prompt injection via the `agent_dispatch` node
**And** V3 failure (any AC fails) triggers a retry signal — not an immediate halt
**And** unit tests use mock SDK fixture: all-ACs-pass response, single-AC-fail response, malformed reflexion response, reflexion timeout

### Story 3.3: Validation Pipeline — Artifact-Specific Routing

**Priority**: HIGH | **Points**: 5

As a developer dispatching stories,
I want a unified validation pipeline that routes story outputs through both V6 invariant and V3 reflexion checks in the correct order,
So that every story passes through the complete validation chain before being marked as complete.

**Acceptance Criteria:**

**Given** `validation/pipeline.py` module
**When** a story's agent output enters the validation pipeline
**Then** V6 invariant checks run first (cheap, deterministic)
**And** if V6 fails, the story is marked as failed immediately — no V3 reflexion (save the API call)
**And** if V6 passes, V3 reflexion validation runs
**And** if V3 passes, the overall validation result is `SUCCESS`
**And** if V3 fails, the overall validation result includes the specific failed ACs and signals `RETRY`
**And** the pipeline returns a comprehensive `ValidationResult` combining V6 and V3 results
**And** all validation results are serializable for provenance writing
**And** structured log events are emitted: `validation.start`, `validation.pass` or `validation.fail` with details
**And** unit tests cover: V6-fail short-circuits V3, V6-pass + V3-pass, V6-pass + V3-fail, pipeline result aggregation

### Story 3.4: Validate Node & Retry Loop Integration

**Priority**: HIGH | **Points**: 5

As a developer dispatching stories,
I want the validation node wired into the LangGraph StateGraph with retry logic that re-dispatches the agent on V3 failure up to a configurable maximum,
So that the system automatically fixes validation failures without human intervention, and halts loudly when retries are exhausted.

**Acceptance Criteria:**

**Given** the `validate` node in the LangGraph StateGraph
**When** the validate node processes a story
**Then** it invokes `validation/pipeline.py` with the story's agent output
**And** on `SUCCESS`: transitions state to `success` and routes to the `commit` node
**And** on `RETRY`: increments `StoryState.retry_count`, includes the V3 reflexion feedback in the next agent prompt (so the agent knows what to fix), and routes back to `budget_check` → `agent_dispatch`
**And** on `ESCALATED` (retry count >= `MAX_RETRIES` from config): transitions state to `escalated`, generates a structured failure report per FR11
**And** the failure report includes: story ID, failing acceptance criteria IDs, retry count, retry history (what failed on each attempt), last agent output (truncated), and a suggested fix
**And** retry history is preserved in `StoryState` — each retry's validation result is accumulated, not overwritten
**And** structured log events: `validation.pass`, `validation.fail` (with retry count), `story.complete` or `run.halt`
**And** integration test verifies: success path (no retry), single-retry path (fail → retry → pass), max-retry path (fail → fail → fail → escalated with report)

---

## Epic 4: Decision Provenance & Run Artifacts

> **Value prop**: Every decision the AI makes is recorded with full rationale, and every run produces a complete artifact trail — giving operators confidence, auditability, and the ability to understand exactly what happened and why.

### Story 4.1: Provenance Recorder — Decision Logging During Execution

**Priority**: HIGH | **Points**: 5
**Requirements**: FR12, FR13, FR14

**Description:**
As an operator reviewing completed work,
I want every AI decision recorded with timestamp, alternatives considered, and rationale,
So that I can audit why the AI made specific choices and build trust in the system.

**Acceptance Criteria:**

**Given** `output/provenance.py` module with a `ProvenanceEntry` dataclass
**When** an agent makes a decision during story execution
**Then** it creates a `ProvenanceEntry` with: `timestamp` (ISO 8601), `decision` (what was decided), `alternatives` (list of options considered), `rationale` (why this choice), `references` (list of requirement/architecture refs)
**And** entries are written to `.arcwright-ai/runs/<run-id>/stories/<story-slug>/validation.md` per the D3↔D5 path contract
**And** the markdown format includes: "## Agent Decisions" section with each decision as a subsection, "## Validation History" as a table (attempt | result | feedback), "## Context Provided" listing the requirements/architecture refs given to the agent
**And** large content blocks (agent output, full diffs) use collapsible `<details>` blocks
**And** provenance exposes `append_entry(path: Path, entry: ProvenanceEntry)` and `write_entries(path: Path, entries: list[ProvenanceEntry])` APIs — both callable from any context, no engine dependency
**And** unit tests verify: entry creation with all fields, markdown rendering format, append to existing file, write multiple entries

### Story 4.2: Run Manager — Run Directory Lifecycle & State Tracking

**Priority**: HIGH | **Points**: 5
**Requirements**: D5 (run directory schema)

**Description:**
As an operator managing multiple runs,
I want each run to have a unique directory with structured state tracking,
So that I can see the status of any run at a glance and resume interrupted runs.

**Acceptance Criteria:**

**Given** `output/run_manager.py` module
**When** a new run is initiated via `arcwright-ai dispatch`
**Then** it creates a run directory at `.arcwright-ai/runs/<run-id>/` with run ID format `YYYYMMDD-HHMMSS-<short-uuid>` (e.g., `20260302-143022-a1b2c3`)
**And** creates `run.yaml` containing: `run_id`, `start_time` (ISO 8601), `config_snapshot` (copy of relevant config at run start), `status` (queued → running → completed | halted | timed_out), `budget` (allocated and spent per-story and total), `stories` (map of story-slug → status/retry_count/timestamps)
**And** `run.yaml` is updated at every state transition (story start, validation pass/fail, retry, completion, halt)
**And** tracks `last_completed_story` for resume support
**And** provides `get_run_status(run_id) → RunStatus` and `list_runs() → List[RunSummary]` functions
**And** unit tests verify: directory creation, run.yaml schema, status transitions, resume pointer accuracy

### Story 4.3: Run Summary & Halt Report Generation

**Priority**: HIGH | **Points**: 5
**Requirements**: FR32, FR33, NFR16, NFR17, NFR18

**Description:**
As an operator who has just completed (or been interrupted during) a run,
I want a comprehensive summary of what happened and actionable next steps,
So that I can quickly understand results and know exactly how to continue.

**Acceptance Criteria:**

**Given** `output/summary.py` module
**When** a run completes (success, halt, or timeout)
**Then** it writes `summary.md` to `.arcwright-ai/runs/<run-id>/summary.md`
**And** success summaries include: stories completed (with links to artifacts), total cost, total duration, validation pass rates
**And** halt reports include the 4 required diagnostic fields per NFR18: (1) which story failed, (2) what validation criteria failed, (3) retry history with feedback, (4) suggested manual fix
**And** halt reports include the exact resume command: `arcwright-ai dispatch --epic EPIC-N --resume`
**And** every run produces a summary regardless of outcome (success, halt, timeout) per NFR16
**And** summaries are human-readable markdown with clear sections and no jargon
**And** unit tests verify: success summary format, halt report with all 4 diagnostic fields, timeout summary, resume command accuracy

### Story 4.4: Provenance & Summary Integration with Engine Nodes

**Priority**: HIGH | **Points**: 5
**Requirements**: D5 (write policy), FR12, FR32

**Description:**
As a system maintainer,
I want provenance recording and summary generation wired into the LangGraph execution nodes,
So that artifacts are produced automatically at the right moments without manual intervention.

**Acceptance Criteria:**

**Given** the LangGraph StateGraph nodes from Epic 2
**When** each node executes
**Then** this story contains zero new data models or file I/O logic — it exclusively wires the APIs from Stories 4.1, 4.2, and 4.3 into the LangGraph node callbacks
**And** `agent_dispatch` node → calls `provenance.append_entry()` to write `agent-output.md` to the story's run directory
**And** `validate` node → calls `provenance.append_entry()` to append validation results to `validation.md`
**And** `commit` node → calls `run_manager.update_status()` to update `run.yaml` with story completion status and timestamps
**And** `run_complete` conditional edge → calls `summary.write_summary()` to write `summary.md`
**And** run directory files are written as checkpoints at state transitions only, per D5 write policy (no intermediate writes outside of transitions)
**And** if a node fails to write an artifact, the error is logged but does not halt execution (artifact writing is best-effort, not blocking)
**And** integration test verifies: full run produces all expected artifacts (run.yaml, agent-output.md per story, validation.md per story, summary.md) in correct directory structure

---

## Epic 5: Halt, Resume & Epic Dispatch

> **Value prop**: Developer can dispatch a full epic (multiple stories), have the system halt loudly on unrecoverable failure preserving all completed work, and resume from the failure point — the overnight dispatch pattern works.

### Story 5.1: Epic Dispatch — CLI-to-Engine Pipeline

**Priority**: HIGH | **Points**: 5
**Requirements**: FR1, FR3

**Description:**
As a developer with a fully planned epic,
I want to dispatch all stories for autonomous sequential execution with a single command,
So that I can start an overnight run and review results in the morning.

**Acceptance Criteria:**

**Given** `cli/dispatch.py` accepting `--epic EPIC-N` and `--story STORY-N.N` flags
**When** the developer runs `arcwright-ai dispatch --epic EPIC-3`
**Then** it validates the epic scope exists in planning artifacts (`_spec/`)
**And** resolves all stories for the epic in dependency order (reads story metadata)
**And** builds `ProjectState` with all stories as `TaskState.QUEUED` and initializes `BudgetState` from config ceilings (invocation count + cost)
**And** shows pre-dispatch confirmation: story count, estimated cost (story count × average), execution plan with story order — waits for user confirm (or `--yes` flag to skip)
**And** invokes `engine/graph.py` to build and run the StateGraph — nodes execute sequentially per FR3
**And** exit code 0 on full success, non-zero per D6 taxonomy on failure (2 = budget, 3 = validation, 4 = SCM)
**And** integration test: dispatch with mock engine verifies story ordering, state initialization, and confirmation flow

### Story 5.2: Halt Controller — Graceful Halt on Unrecoverable Failure

**Priority**: HIGH | **Points**: 5
**Requirements**: FR4, NFR2, NFR3

**Description:**
As a developer running an overnight dispatch,
I want the system to halt loudly on unrecoverable failure while preserving all completed work,
So that I never get silent breakage and can trust that completed stories are safe.

**Acceptance Criteria:**

**Given** the engine encounters an unrecoverable condition during story execution
**When** halt triggers on any of 3 conditions per D2: (1) validation fail count exhausted (retry_count >= MAX_RETRIES), (2) budget exceeded (invocation count or cost ceiling), (3) agent error (SDK crash, sandbox violation)
**Then** it completes any in-flight cleanup (worktree preservation, provenance flush) before halting
**And** updates `run.yaml` status to `halted` with the halt reason and halting story ID
**And** preserves all previously completed stories — their commits, worktrees (if still present), and provenance are untouched per NFR2
**And** CLI outputs structured halt summary: stories completed (list), story that caused halt, halt reason (validation/budget/error), current budget consumption (tokens and cost), exact `arcwright-ai dispatch --epic EPIC-N --resume` command
**And** `AgentBudgetError` → exit code 2, validation exhaustion → exit code 3, `ScmError` → exit code 4
**And** NFR3 enforcement: unexpected SDK errors (network timeout, API 500, malformed response) are caught, logged with full context, and trigger halt — never crash with unhandled exception
**And** unit tests verify: each halt trigger produces correct exit code, halt summary contains all required fields, completed stories are not modified after halt

### Story 5.3: Resume Controller — Resume Halted Epic from Failure Point

**Priority**: HIGH | **Points**: 5
**Requirements**: FR5, NFR2, NFR19

**Description:**
As a developer who fixed the issue that caused a halt,
I want to resume the epic from the failure point without re-running completed stories,
So that I don't waste time or money re-executing work that already passed.

**Acceptance Criteria:**

**Given** `cli/dispatch.py` accepts `--resume` flag on `--epic` dispatch
**When** the developer runs `arcwright-ai dispatch --epic EPIC-3 --resume`
**Then** it reads `run.yaml` via `output/run_manager.py` to determine `last_completed_story` and run status
**And** rebuilds the StateGraph starting from the first incomplete story — completed stories are excluded from the graph
**And** if the halted story's worktree still exists, it is cleaned up and recreated from clean state (fresh start, not resume mid-story)
**And** budget state is carried forward from the previous run (remaining budget, not reset)
**And** `--resume` on an already-completed run is a no-op with informative message per NFR19 idempotency
**And** `--resume` without a prior run for the specified epic → clear error: "No previous run found for EPIC-N. Use `arcwright-ai dispatch --epic EPIC-N` without --resume."
**And** integration test verifies: 5-story epic, halt at story 3, resume skips stories 1-2, executes 3-5 with correct budget carry-forward

### Story 5.4: Halt & Resume Integration with Run Artifacts

**Priority**: MEDIUM | **Points**: 3
**Requirements**: FR33, NFR18

**Description:**
As a developer reviewing a halted run,
I want complete diagnostic artifacts that tell me exactly what happened and how to fix it,
So that failure recovery is fast and informed rather than guesswork.

**Acceptance Criteria:**

**Given** the engine triggers a halt during epic execution
**When** the halt handler runs
**Then** `output/summary.py` writes halt report to `summary.md` with all 4 NFR18 diagnostic fields: (1) failing story + AC IDs, (2) retry count + history per attempt, (3) last agent output (truncated to 500 lines), (4) suggested fix based on failure pattern
**And** halt provenance entry is recorded in the failing story's `validation.md` with budget state at halt time
**And** failed story's worktree is preserved (not cleaned up) and its path is logged in `summary.md` for manual inspection
**And** on resume: new entries are appended to the existing `summary.md` (shows both the halt and the resumed results in chronological order)
**And** the halt report includes the exact resume command: `arcwright-ai dispatch --epic EPIC-N --resume`
**And** unit tests verify: halt report contains all 4 diagnostic fields, resume appends to existing summary, worktree path is valid

### Story 5.5: Run Status Command — Live & Historical Run Visibility

**Priority**: MEDIUM | **Points**: 3
**Requirements**: FR31

**Description:**
As a developer monitoring an in-progress run or reviewing past runs,
I want a status command that shows run state, story progress, and cost at a glance,
So that I can check on overnight runs without digging through files.

**Acceptance Criteria:**

**Given** `cli/status.py` implementing the `arcwright-ai status` command
**When** the developer runs `arcwright-ai status`
**Then** it reads the latest `run.yaml` and displays: run ID, status (running/completed/halted), stories completed/pending/failed (with story slugs), elapsed time, cost consumed (formatted human-readable)
**And** `arcwright-ai status <run-id>` shows the same information for a specific historical run
**And** `arcwright-ai status` with no active or historical runs → clear message: "No runs found. Use `arcwright-ai dispatch` to start a run."
**And** if a run is in progress, status reflects live state from the current `run.yaml` (not cached)
**And** output uses Rich/Typer formatting to stderr per D8
**And** exit code 0 on success, 1 if specified run-id not found
**And** unit tests verify: active run display, completed run display, halted run display, no-runs message, invalid run-id error

---

## Epic 6: SCM Integration & PR Generation

> **Value prop**: Developer gets clean git branches per story, worktree lifecycle management, automated commits, and pull requests with decision provenance embedded — code review is decision-centric, not line-by-line.

### Story 6.1: Git Subprocess Wrapper — Safe Shell-Out Foundation

**Priority**: HIGH | **Points**: 3
**Requirements**: D7 (git operations strategy)

**Description:**
As a system maintainer,
I want all git operations to flow through a single async subprocess wrapper,
So that git interactions are consistent, logged, and error-handled in one place.

**Acceptance Criteria:**

**Given** `scm/git.py` module with a single entry point
**When** any part of the system needs to execute a git command
**Then** it calls `async def git(*args: str, cwd: Path | None = None) → GitResult(stdout, stderr, returncode)`
**And** every command and its result are logged to the structured logger (event type `git.*`)
**And** non-zero return code raises `ScmError` with command, stderr, and exit code in the exception
**And** all git calls across the entire codebase go through this wrapper — no `subprocess.run("git ...")` anywhere else (enforced by code review convention)
**And** handles common git error patterns: lock file contention (retry with backoff up to 3 attempts), permission denied (clear `ScmError`), not a git repo (clear `ScmError`)
**And** unit tests verify: successful command returns `GitResult`, non-zero exit raises `ScmError`, logging output contains full command string

### Story 6.2: Worktree Manager — Atomic Create/Delete with Recovery

**Priority**: HIGH | **Points**: 8
**Requirements**: FR6, FR36, NFR4, NFR19

**Description:**
As a developer dispatching stories,
I want each story to execute in an isolated git worktree,
So that no story can corrupt the main branch or interfere with other stories.

**Acceptance Criteria:**

**Given** `scm/worktree.py` module
**When** the engine needs to create an execution environment for a story
**Then** `create_worktree(story_slug: str, base_ref: str) → Path` creates worktree at `.arcwright-ai/worktrees/<story-slug>` with branch `arcwright-ai/<story-slug>`
**And** `remove_worktree(story_slug: str)` removes worktree and optionally deletes the branch
**And** atomic guarantee: if `git worktree add` fails mid-operation, cleanup restores consistent state — no partial worktrees, no orphaned branches per D7
**And** existing worktree for same story slug → `WorktreeError` with clear message (no `--force`, no implicit cleanup per D7)
**And** each story executes within its worktree directory — worktree path is the sandbox boundary per NFR4
**And** worktree is preserved on validation failure (not cleaned up) for manual inspection
**And** all operations idempotent per NFR19: removing an already-removed worktree is a no-op, not an error
**And** base ref defaults to current HEAD; configurable via `--base-ref` on dispatch
**And** integration tests with real git: create worktree, verify isolation (file changes don't affect main), remove worktree, verify cleanup

### Story 6.3: Branch Manager & Commit Strategy

**Priority**: HIGH | **Points**: 5
**Requirements**: FR34, NFR14

**Description:**
As a developer reviewing overnight results,
I want clean git branches per story with structured commit messages,
So that the git history is organized and traceable back to the run that produced it.

**Acceptance Criteria:**

**Given** `scm/branch.py` module
**When** a story is dispatched and completes validation
**Then** branch naming follows convention: `arcwright-ai/<story-slug>` — namespaced, predictable, greppable per D7
**And** `create_branch(story_slug: str, base_ref: str)` creates branch; existing branch → `BranchError` (no force operations per D7)
**And** commit inside worktree uses: `git add .` + `git commit -m "[arcwright-ai] <story-title>\n\nStory: <story-file-path>\nRun: <run-id>"`
**And** after successful commit, `push_branch()` pushes the branch to remote with merge-ours reconciliation for concurrent remote changes
**And** no force operations anywhere — no `--force`, no `reset --hard`, no rebase per D7
**And** compatible with git 2.25+ per NFR14 (no features introduced after git 2.25, which is Ubuntu 20.04 floor)
**And** unit tests verify: branch naming format, commit message format, `BranchError` on existing branch, no force flags in any generated command

### Story 6.4: PR Body Generator with Provenance Embedding

**Priority**: HIGH | **Points**: 5
**Requirements**: FR15, FR35, NFR15, NFR17

**Description:**
As a code reviewer (like Carlos in Journey 5),
I want PRs with decision provenance embedded so I can review decisions, not just lines,
So that code review is faster and focused on whether the AI thought correctly.

**Acceptance Criteria:**

**Given** `scm/pr.py` module
**When** a story completes successfully and a PR body is needed
**Then** `generate_pr_body(run_id: str, story_slug: str) → str` reads provenance from `.arcwright-ai/runs/<run-id>/stories/<story-slug>/validation.md` per the D3↔D5 path contract
**And** PR body includes: story title, story acceptance criteria (as a checklist), validation results (pass/retry count), **Decision Provenance** section with each decision as a subsection (decision, alternatives considered, rationale, references)
**And** large content blocks (full agent output, diffs >50 lines) use collapsible `<details>` blocks to keep the PR view readable
**And** provenance references acceptance criteria and architecture docs by ID (e.g., "AC-2", "D7") per NFR17
**And** output renders as valid markdown in GitHub's pull request view per NFR15
**And** unit tests verify: PR body contains all required sections, `<details>` blocks for large content, AC/architecture cross-references present, valid markdown structure

### Story 6.5: Worktree Cleanup Command

**Priority**: MEDIUM | **Points**: 3
**Requirements**: FR7, NFR19

**Description:**
As a developer managing disk space after multiple runs,
I want a cleanup command that removes stale worktrees and branches,
So that completed run artifacts don't accumulate indefinitely.

**Acceptance Criteria:**

**Given** `cli/clean.py` implementing the `arcwright-ai clean` command
**When** the developer runs cleanup
**Then** `arcwright-ai clean` (default): removes completed worktrees + merged branches
**And** `arcwright-ai clean --all`: removes ALL arcwright-namespaced worktrees and branches (including failed/stale)
**And** cleanup is never automatic per D7 — always user-initiated (no lazy cleanup on dispatch, no post-merge hooks in MVP)
**And** all cleanup operations are idempotent per NFR19 — cleaning an already-clean state is a no-op
**And** reports what was cleaned: "Removed 3 worktrees, deleted 3 branches" or "Nothing to clean"
**And** NFR20: cleanup succeeds even without network (all local git operations)
**And** integration tests with real git: create worktrees, run cleanup, verify removal, run cleanup again (verify idempotent no-op)

### Story 6.6: SCM Integration with Engine Nodes

**Priority**: HIGH | **Points**: 5
**Requirements**: FR6, FR36, D7

**Description:**
As a system maintainer,
I want SCM operations wired into the LangGraph execution nodes at the right lifecycle points,
So that worktree isolation and commit happen automatically without manual intervention.

**Acceptance Criteria:**

**Given** the LangGraph StateGraph nodes from Epic 2
**When** the engine executes a story through the pipeline
**Then** `preflight` node fetches and fast-forward merges the remote default branch, then calls `scm/worktree.py` to create worktree from the updated tip; sets `cwd` for agent dispatch to the worktree path
**And** `commit` node calls `scm/branch.py` to commit inside worktree, `push_branch()` to push to remote, `scm/pr.py` to generate PR body and open pull request, optionally `merge_pull_request()` when `scm.auto_merge` enabled, then `scm/worktree.py` to remove worktree
**And** on ESCALATED (halt): worktree is preserved for inspection, path logged to provenance and summary
**And** on RETRY: worktree is reused — agent re-executes in the same worktree with reflexion feedback (no worktree teardown/recreate per retry)
**And** all git commands run with `cwd=worktree_path` except worktree add/remove which run from project root per D7
**And** `ScmError` during preflight → story skipped, logged, halt triggered (cannot execute without isolation boundary)
**And** integration test verifies: full story lifecycle through preflight → agent → validate → commit with real git operations, worktree exists during execution, worktree removed after commit

---

## Epic 7: Cost Tracking & Budget Enforcement

> **Value prop**: Developer has full visibility into API spend per story and per run, with budget enforcement that halts before overspending — economics are transparent and controllable.

### Story 7.1: BudgetState Model & Cost Accumulation

**Priority**: HIGH | **Points**: 5
**Requirements**: FR23, NFR12a, NFR12b

**Description:**
As a developer running autonomous dispatches,
I want every SDK invocation's token usage and cost tracked accurately,
So that I have full visibility into what each story and run costs.

**Acceptance Criteria:**

**Given** `BudgetState` (core fields defined in Story 2.1) in `core/types.py`
**When** the engine tracks cost during story execution
**Then** this story extends `BudgetState` with per-story tracking fields: `total_tokens_input` (int), `total_tokens_output` (int), `per_story` (dict mapping story slug → `StoryCost` with tokens_input/tokens_output/cost/invocations), and adds `StoryCost` dataclass
**And** cost estimation uses configurable per-model token pricing with separate input vs output rates (stored in config under `model.pricing`)
**And** `BudgetState` is updated by the `agent_dispatch` node after every SDK invocation — 100% capture with no missed calls per NFR12a
**And** tracked cost uses SDK-reported token counts (not prompt-length estimates) to maintain ≤ 10% variance from actual billing per NFR12b
**And** `BudgetState` is persisted to `run.yaml` budget section at every state transition via run manager
**And** unit tests verify: accumulation across multiple invocations, per-story breakdown accuracy, serialization to/from `run.yaml`, Decimal precision (no floating point cost errors)

### Story 7.2: Budget Check Node — Dual Ceiling Enforcement

**Priority**: HIGH | **Points**: 5
**Requirements**: FR25, NFR10, D2

**Description:**
As a developer with budget limits configured,
I want the system to halt before overspending — not after,
So that I maintain control over API costs and never get surprise bills.

**Acceptance Criteria:**

**Given** `budget_check` node in `engine/nodes.py`
**When** the engine is about to invoke the SDK for a story (including retries)
**Then** it reads `BudgetState` and checks both invocation count ceiling AND estimated cost ceiling — whichever is hit first triggers halt per D2 dual budget model
**And** enforcement is pre-invocation per NFR10: halts *before* the next SDK call, not after — overshoot limited to at most one invocation's token cost
**And** on budget exceeded: transitions story to ESCALATED, raises `AgentBudgetError` (exit code 2), records a provenance entry with full budget state at halt time
**And** budget ceilings loaded from config: `limits.tokens_per_story` (per-story ceiling), `limits.cost_per_run` (per-run ceiling)
**And** V3 reflexion retries count against the same `BudgetState` — no separate validation budget in MVP (separate budget is Growth phase per architecture gap analysis)
**And** unit tests verify: halt at invocation count ceiling, halt at cost ceiling, pre-invocation check timing (budget checked before SDK call not after), retry invocations consume budget

### Story 7.3: Cost Display in CLI Status & Run Summary

**Priority**: MEDIUM | **Points**: 3
**Requirements**: FR24, FR31

**Description:**
As a developer monitoring run progress or reviewing completed runs,
I want cost information displayed clearly in status and summary outputs,
So that I can make informed decisions about dispatching and budget allocation.

**Acceptance Criteria:**

**Given** cost data accumulated in `BudgetState` and persisted in `run.yaml`
**When** the developer checks status or reviews a completed run
**Then** `arcwright-ai status` includes cost section: total tokens (input + output), estimated cost, per-story breakdown (table), budget remaining (% and absolute amount)
**And** run summary (`summary.md`) includes cost section: total cost, per-story costs (table), retry overhead (cost spent on retries vs. first-pass), budget utilization percentage
**And** cost is formatted human-readable: "$1.17" not "0.00117 USD", "12,450 tokens" not "12450"
**And** if run is in progress, status shows live cost from current `run.yaml`
**And** unit tests verify: cost formatting, per-story breakdown renders correctly, budget remaining calculation, retry overhead calculation

### Story 7.4: Cost Tracking Integration with Engine Pipeline

**Priority**: HIGH | **Points**: 3
**Requirements**: FR23, NFR12a

**Description:**
As a system maintainer,
I want cost tracking wired into the engine pipeline so no invocation can bypass it,
So that cost data is always complete and trustworthy.

**Acceptance Criteria:**

**Given** the LangGraph StateGraph execution pipeline
**When** any SDK invocation occurs (first-pass or retry)
**Then** `agent_dispatch` node updates `BudgetState` with SDK-reported token counts immediately after each invocation
**And** the `budget_check` → `agent_dispatch` → budget update flow is atomic — no invocation can bypass cost tracking
**And** cost is accumulated for both first-pass invocations and V3 reflexion retry invocations identically
**And** `run.yaml` budget section is updated at every state transition (not just at run completion) — crash recovery preserves cost data
**And** if SDK doesn't report token counts (error scenario), log a warning and estimate from prompt length — never skip tracking, never leave a gap in the cost record
**And** integration test verifies: 3-story run accumulates correct total across all stories, retry costs are included in both per-story and per-run totals, `run.yaml` reflects final cost accurately, zero invocations missed in tracking

---

## Epic 8: Role-Based Model Registry

> **Value prop**: Developer can configure separate LLM models for code generation and code review, enabling adversarial quality patterns where a fast model writes code and a thorough model reviews it — optimizing both speed and cost.

### Story 8.1: ModelRole Enum, ModelSpec, ModelRegistry & Config Migration

**Priority**: HIGH | **Points**: 5
**Requirements**: FR22, FR30, D9
**Dependencies**: Story 1.3 (Configuration System)

**Description:**
As a developer configuring Arcwright AI,
I want to assign different models to different pipeline roles (generation vs. review),
So that I can optimize cost and quality by using a fast model for code generation and a thorough model for code review.

**Acceptance Criteria:**

**Given** `core/types.py` and `core/config.py` as the foundation for model configuration
**When** the role-based model registry is implemented
**Then** `ModelRole` is defined as a `StrEnum` in `core/config.py` with values `GENERATE = "generate"` and `REVIEW = "review"`
**And** `ModelSpec` is a frozen Pydantic model with fields: `version` (str) and `pricing` (ModelPricing, default factory)
**And** `ModelRegistry` is a frozen Pydantic model with a `roles: dict[str, ModelSpec]` field and a `get(role: ModelRole | str) -> ModelSpec` method that returns the spec for the requested role, falling back to the `generate` role if the requested role is not configured, raising `ConfigError` if no `generate` fallback exists
**And** `RunConfig.model` (singular, `ModelConfig`) is replaced by `RunConfig.models` (`ModelRegistry`)
**And** backward-compatible config migration is implemented: if `models` key exists in YAML → use new registry format; if `model` (singular) key exists → auto-migrate to `models.generate` with a `DeprecationWarning`; if neither → use defaults (`generate` role with `claude-sonnet-4-20250514`)
**And** the config YAML format supports both minimal (just `generate`) and full (`generate` + `review`) configurations:
```yaml
# Full config
models:
  generate:
    version: claude-sonnet-4-20250514
    pricing:
      input_rate: "3.00"
      output_rate: "15.00"
  review:
    version: claude-opus-4-5
    pricing:
      input_rate: "15.00"
      output_rate: "75.00"

# Minimal config (review falls back to generate)
models:
  generate:
    version: claude-sonnet-4-20250514
```
**And** environment variable overrides follow the pattern `ARCWRIGHT_AI_MODEL_{ROLE}_VERSION` and `ARCWRIGHT_AI_MODEL_{ROLE}_PRICING_{FIELD}` (e.g., `ARCWRIGHT_AI_MODEL_GENERATE_VERSION`, `ARCWRIGHT_AI_MODEL_REVIEW_VERSION`, `ARCWRIGHT_AI_MODEL_REVIEW_PRICING_INPUT_RATE`)
**And** the existing `ARCWRIGHT_MODEL_VERSION` env var is treated as an alias for `ARCWRIGHT_AI_MODEL_GENERATE_VERSION` with a `DeprecationWarning`
**And** `_KNOWN_SECTION_FIELDS` and `_KNOWN_SUBSECTION_FIELDS` are updated for unknown-key warnings on the new `models` structure
**And** `core/constants.py` `__all__` is updated with new env var constant names; old `ENV_MODEL_*` constants are retained as deprecated aliases
**And** unit tests in `tests/test_core/test_config.py` verify: (1) new `models` format loads correctly, (2) old `model` singular key auto-migrates with deprecation warning, (3) missing both keys uses defaults, (4) env var overrides with `ARCWRIGHT_AI_MODEL_{ROLE}_*` pattern, (5) fallback behavior when only `generate` is configured and `review` is requested, (6) `ConfigError` when `generate` role is missing and a role is requested
**And** all existing tests that construct `RunConfig` are updated to use the new `models` field

**Files touched:**
- `core/config.py` — `ModelRole`, `ModelSpec`, `ModelRegistry`, `RunConfig`, `_apply_env_overrides()`, `_KNOWN_SECTION_FIELDS`, `_KNOWN_SUBSECTION_FIELDS`, backward-compat migration in `load_config()`
- `core/constants.py` — New `ENV_MODEL_GENERATE_VERSION`, `ENV_MODEL_REVIEW_VERSION`, etc.; deprecation aliases
- `core/types.py` — No structural changes; `ModelPricing` stays where it is
- `tests/test_core/test_config.py` — New test cases + fixture updates

### Story 8.2: Engine Node Wiring — Role-Based Model Resolution

**Priority**: HIGH | **Points**: 5
**Requirements**: FR22, D9
**Dependencies**: Story 8.1

**Description:**
As a system running the execution pipeline,
I want `agent_dispatch_node` to use the `generate` model role and `validate_node` to use the `review` model role,
So that code generation and code review use their configured models independently.

**Acceptance Criteria:**

**Given** `ModelRegistry` is available on `state.config.models` (from Story 8.1)
**When** the engine nodes resolve their model
**Then** `agent_dispatch_node` in `engine/nodes.py` calls `state.config.models.get(ModelRole.GENERATE)` to obtain the `ModelSpec` and passes `spec.version` to `invoke_agent()` and `spec.pricing` to `calculate_invocation_cost()`
**And** all 6 existing references to `state.config.model.version` and `state.config.model.pricing` in `agent_dispatch_node` (including error paths and provenance logging) are updated to use `state.config.models.get(ModelRole.GENERATE)`
**And** `validate_node` in `engine/nodes.py` calls `state.config.models.get(ModelRole.REVIEW)` to obtain the `ModelSpec` and passes `spec.version` to `run_validation_pipeline()`
**And** `validate_node` uses `spec.pricing` from the `REVIEW` role for cost tracking of validation invocations
**And** `run_validation_pipeline()` in `validation/pipeline.py` receives the model version as before (no signature change) — the role resolution happens at the node level, not inside the pipeline
**And** provenance entries that log model version now log both the role name and the resolved model version (e.g., `"model": "claude-sonnet-4-20250514", "role": "generate"`) for traceability
**And** when only `generate` role is configured (no `review` role), `validate_node` falls back to the `generate` model via `ModelRegistry.get()` — no new fallback logic needed in nodes
**And** unit tests in `tests/test_engine/test_nodes.py` verify: (1) `agent_dispatch_node` resolves `GENERATE` role, (2) `validate_node` resolves `REVIEW` role, (3) fallback to `generate` when `review` not configured, (4) cost tracking uses correct per-role pricing, (5) provenance entries include role metadata
**And** all existing node tests that reference `state.config.model` are updated to use `state.config.models`

**Files touched:**
- `engine/nodes.py` — `agent_dispatch_node` (6 reference updates), `validate_node` (model + pricing references), provenance fields
- `validation/pipeline.py` — No structural changes; receives model version string as before
- `tests/test_engine/test_nodes.py` — Updated fixtures + new role-resolution tests

### Story 8.3: Cost Display Per Role & Config Template Update

**Priority**: MEDIUM | **Points**: 4
**Requirements**: FR24, D9
**Dependencies**: Story 8.2

**Description:**
As a developer reviewing run costs,
I want cost breakdowns split by model role (generation cost vs. review cost),
So that I can see exactly how much each phase of the pipeline costs and optimize model selection accordingly.

**Acceptance Criteria:**

**Given** cost data accumulated in `BudgetState` with per-invocation tracking and model role metadata
**When** cost information is displayed in CLI status or run summaries
**Then** `arcwright-ai status` includes a cost breakdown by role: "Generation cost: $X (N invocations)" and "Review cost: $Y (M invocations)" in addition to the existing total cost display
**And** run summary (`summary.md`) includes a "Cost by Model Role" section with a table showing role, model version, invocations, tokens (in/out), and cost for each configured role
**And** the per-story cost table in both status and summary distinguishes between generation and review costs when both are present
**And** `BudgetState` or `StoryCost` in `core/types.py` is extended with per-role cost tracking fields (e.g., `cost_by_role: dict[str, Decimal]`) to support the breakdown without requiring schema-breaking changes
**And** the `_serialize_budget()` function in `output/run_manager.py` correctly serializes the new per-role fields to `run.yaml`
**And** `arcwright-ai init` generates an updated default config template that uses the new `models` format (with `generate` and `review` sections) instead of the old `model` format
**And** the config template includes inline comments explaining model role configuration and how fallback works
**And** cost formatting remains human-readable: "$1.17" not "0.00117 USD", "12,450 tokens" not "12450"
**And** unit tests verify: (1) per-role cost display formatting, (2) summary table generation with role breakdown, (3) backward compat — runs with old single-model data display correctly without role breakdown, (4) config template generates valid YAML with models section

**Files touched:**
- `core/types.py` — `StoryCost` or `BudgetState` per-role tracking field
- `output/summary.py` — Role-based cost formatting functions
- `output/run_manager.py` — `_serialize_budget()` updates for per-role fields
- `cli/status.py` — Role-based cost display in status output
- `cli/init.py` — Updated config template with `models` format
- `tests/test_output/` — Summary and cost display tests
- `tests/test_cli/` — Status display and init template tests

---

## Epic 9: SCM Enhancements — Fetch, Default Branch & Auto-Merge

> **Value prop**: Developer dispatches an overnight epic run and every story starts from the latest upstream code, creates PRs against the correct default branch, and optionally auto-merges — the full chain from dispatch to merged code runs unattended.

### Story 9.1: ScmConfig Enhancements — Default Branch & Auto-Merge Configuration

**Priority**: HIGH | **Points**: 3
**Requirements**: FR37, FR39, FR30
**Dependencies**: Epic 6 (complete)

**Description:**
As a developer configuring Arcwright AI for my project,
I want to specify the default branch and enable auto-merge in my project config,
So that SCM operations target the correct branch and PRs merge automatically when configured.

**Acceptance Criteria:**

**Given** `core/config.py` `ScmConfig` Pydantic model
**When** the developer configures SCM settings in `.arcwright-ai/config.yaml`
**Then** `ScmConfig` gains two new optional fields: `default_branch: str = ""` (empty string means auto-detect) and `auto_merge: bool = False`
**And** when `default_branch` is set to a non-empty string (e.g., `"main"`, `"develop"`), `_detect_default_branch()` in `scm/pr.py` returns that value immediately without running any git commands
**And** when `default_branch` is empty or unset, `_detect_default_branch()` uses the existing 3-step cascade: `git remote show origin` → `gh repo view --json defaultBranchRef` → `git rev-parse --abbrev-ref origin/HEAD` → fallback `"main"`
**And** `auto_merge` defaults to `False` — when `True`, the commit node will call `merge_pull_request()` after PR creation
**And** config validation: `default_branch` accepts any non-empty string (branch name validation is intentionally lenient — git will reject invalid names); `auto_merge` must be boolean
**And** `_KNOWN_SUBSECTION_FIELDS` is updated to include `default_branch` and `auto_merge` under the `scm` section for unknown-key warnings
**And** `arcwright-ai init` config template includes commented-out `default_branch` and `auto_merge` fields with explanatory comments
**And** unit tests verify: (1) empty `default_branch` triggers auto-detect cascade, (2) non-empty `default_branch` short-circuits detection, (3) `auto_merge` defaults to `False`, (4) config round-trips through YAML load/save, (5) unknown key warnings still work for `scm` section

**Files touched:**
- `core/config.py` — `ScmConfig` new fields, `_KNOWN_SUBSECTION_FIELDS` update
- `scm/pr.py` — `_detect_default_branch()` accepts optional config override
- `cli/init.py` — Config template update
- `tests/test_core/test_config.py` — New ScmConfig field tests
- `tests/test_scm/test_pr.py` — Default branch detection tests with config override

### Story 9.2: Fetch & Sync Default Branch Before Worktree Creation

**Priority**: HIGH | **Points**: 5
**Requirements**: FR38, D7
**Dependencies**: Story 9.1

**Description:**
As a developer dispatching stories overnight,
I want each story's worktree to start from the latest upstream code,
So that stories don't build on stale commits and merge conflicts are minimized.

**Acceptance Criteria:**

**Given** `scm/branch.py` module and `engine/nodes.py` `preflight_node`
**When** the engine is about to create a worktree for a story
**Then** a new `fetch_and_sync(default_branch: str, remote: str = "origin", *, project_root: Path) → str` function in `scm/branch.py`:
  1. Runs `git fetch <remote> <default_branch>` to fetch latest commits from remote
  2. Runs `git merge --ff-only <remote>/<default_branch>` to fast-forward the local default branch (if currently on it), or just uses `<remote>/<default_branch>` as the base_ref
  3. Returns the resolved commit SHA of `<remote>/<default_branch>` as the base_ref for worktree creation
**And** `preflight_node` in `engine/nodes.py` calls `fetch_and_sync()` before `create_worktree()`, passing the returned SHA as `base_ref`
**And** if `--base-ref` is explicitly provided by the user on the CLI, `fetch_and_sync()` is skipped and the user-provided base ref is used directly
**And** network failure during fetch → `ScmError` with clear message ("Failed to fetch from remote — check network connectivity"); story is skipped and halted (cannot guarantee fresh base without fetch)
**And** fast-forward failure (local branch has diverged) → log warning, use `<remote>/<default_branch>` as base_ref directly (detached worktree off remote tip — safe, no local merge needed)
**And** the default branch name is resolved via `_detect_default_branch()` (which respects `scm.default_branch` config from Story 9.1)
**And** fetch runs once per dispatch when processing multiple stories in an epic (cached after first fetch for the duration of the run, not per-story)
**And** unit tests verify: (1) `fetch_and_sync()` calls correct git commands, (2) returned SHA is used as base_ref, (3) network failure raises `ScmError`, (4) ff-only failure falls back to remote ref, (5) explicit `--base-ref` bypasses fetch
**And** integration tests with real git: create remote, push commits, verify worktree starts from remote tip (not stale local HEAD)

**Files touched:**
- `scm/branch.py` — New `fetch_and_sync()` function
- `engine/nodes.py` — `preflight_node` calls `fetch_and_sync()` before `create_worktree()`
- `engine/state.py` — Optional `base_ref` field on state for caching resolved ref across stories
- `tests/test_scm/test_branch.py` — Unit tests for `fetch_and_sync()`
- `tests/test_scm/test_branch_integration.py` — Integration tests with real git remote

### Story 9.3: Auto-Merge PR After Creation

**Priority**: HIGH | **Points**: 5
**Requirements**: FR39, D7
**Dependencies**: Story 9.1

**Description:**
As a developer running overnight dispatches,
I want PRs to auto-merge after creation when configured,
So that completed stories flow through to the default branch without manual intervention.

**Acceptance Criteria:**

**Given** `scm/pr.py` module and `engine/nodes.py` `commit_node`
**When** a PR is successfully created and `scm.auto_merge` is `True` in config
**Then** a new `merge_pull_request(pr_url: str, strategy: str = "squash", *, project_root: Path) → bool` function in `scm/pr.py`:
  1. Extracts PR number from the `pr_url` returned by `open_pull_request()`
  2. Runs `gh pr merge <pr_number> --squash --delete-branch` to squash-merge and clean up the remote branch
  3. Returns `True` on success, `False` on merge failure (e.g., merge conflicts, required reviews pending)
**And** `commit_node` in `engine/nodes.py` calls `merge_pull_request()` after `open_pull_request()` when `state.config.scm.auto_merge is True`
**And** merge failure is non-fatal — the PR remains open, merge failure is logged to provenance as a warning, and the story is still marked as `SUCCESS` (the code was committed and PR created; merge is best-effort)
**And** when `scm.auto_merge` is `False` (default), `merge_pull_request()` is never called — existing behavior preserved
**And** the `--delete-branch` flag cleans up the remote `arcwright-ai/<story-slug>` branch after merge, reducing branch clutter
**And** for epic dispatches with multiple stories, auto-merge happens per-story immediately after PR creation (not batched at the end), so subsequent stories can build on merged changes when combined with Story 9.2's fetch
**And** provenance entry records: merge attempt timestamp, success/failure, merge strategy, resulting merge commit SHA (when successful)
**And** unit tests verify: (1) `merge_pull_request()` calls correct `gh` command, (2) successful merge returns `True`, (3) merge failure returns `False` without raising, (4) `commit_node` skips merge when `auto_merge` is `False`, (5) provenance includes merge metadata
**And** integration tests: create real PR (if CI has gh auth), verify merge succeeds and branch is deleted

**Files touched:**
- `scm/pr.py` — New `merge_pull_request()` function
- `engine/nodes.py` — `commit_node` calls `merge_pull_request()` conditionally
- `output/provenance.py` — Merge event recording
- `tests/test_scm/test_pr.py` — Unit tests for `merge_pull_request()`
- `tests/test_engine/test_nodes.py` — `commit_node` auto-merge tests

### Story 9.4: End-to-End SCM Enhancement Integration Tests

**Priority**: MEDIUM | **Points**: 5
**Requirements**: FR37, FR38, FR39, D7
**Dependencies**: Stories 9.1, 9.2, 9.3

**Description:**
As a system maintainer,
I want integration tests that verify the full enhanced SCM flow end-to-end,
So that fetch → worktree → commit → push → PR → merge works as an unbroken chain.

**Acceptance Criteria:**

**Given** all SCM enhancements from Stories 9.1–9.3 are implemented
**When** integration tests execute the full enhanced SCM lifecycle
**Then** test scenario 1 (single story, auto-merge enabled): fetch remote → create worktree from remote tip → make changes → commit → push → PR → merge → verify branch deleted and changes on default branch
**And** test scenario 2 (epic chain, auto-merge enabled): dispatch 2 stories sequentially; story 2's worktree starts from story 1's merged changes (verifies fetch-after-merge picks up previous story's work)
**And** test scenario 3 (auto-merge disabled): full flow stops at PR creation; PR remains open, no merge attempted
**And** test scenario 4 (configured default branch): `scm.default_branch` set to custom branch name; verify all operations target that branch, not auto-detected one
**And** test scenario 5 (network failure simulation): mock fetch failure; verify graceful halt with clear error message
**And** test scenario 6 (merge conflict): create conflicting changes on default branch; auto-merge fails gracefully, PR remains open, story still marked SUCCESS
**And** all tests marked `@pytest.mark.slow` (real git operations)
**And** tests use `tmp_path` fixture with real git repos (local bare remote + working clone)

**Files touched:**
- `tests/test_scm/test_scm_integration.py` — New integration test file covering all 6 scenarios
- `tests/conftest.py` — Shared fixture for creating local bare remote + clone pair

---

## Epic 10: Ad-Hoc Improvements & Housekeeping

**Added:** 2026-03-15 | **Stories:** 8 (ad-hoc — stories added as needed) | **Points:** 28+

**Purpose:** Collects small, cross-cutting improvements that don't warrant their own epic. These are housekeeping tasks, build infrastructure changes, and quality-of-life improvements identified during or after the main implementation sprints.

**Scope:** Non-functional improvements to build, packaging, CI, developer experience, and project hygiene. Stories in this epic do NOT modify core application logic and carry minimal regression risk.

---

### Story 10.1: Dynamic Versioning with hatch-vcs

**Priority**: MEDIUM | **Points**: 3
**Requirements**: NFR19 (idempotency), Architecture Decision 1 (Starter Template / Hatchling backend)
**Dependencies**: Story 1.1 (project scaffold)

**Description:**
As a maintainer of Arcwright AI,
I want the package version to be derived automatically from git tags using hatch-vcs,
So that version management requires zero manual edits, dev builds are uniquely identifiable, and releases are a simple `git tag` + push.

**Acceptance Criteria:**

**Given** `pyproject.toml` exists with a static `version = "0.1.0"` **When** the migration is applied **Then** the `version` key is removed from `[project]`, `"version"` is added to the `dynamic` list, and `[tool.hatch.version]` configures `hatch-vcs` as the version source
**And** `[build-system].requires` includes both `"hatchling"` and `"hatch-vcs"`
**And** `src/arcwright_ai/__init__.py` reads version dynamically via `importlib.metadata.version("arcwright-ai")` with a `PackageNotFoundError` fallback to `"0.0.0.dev0"`
**And** `git tag -a v0.1.0` is created on the current HEAD as the initial version baseline
**And** `pip install -e .` produces a package reporting version `0.1.0`
**And** dev builds after the tag produce PEP 440 versions like `0.1.1.dev3`
**And** `ruff check`, `mypy --strict`, and `pytest` all pass with zero issues

**Files touched:**
- `pyproject.toml` — Build system requires, dynamic version, hatch.version config
- `src/arcwright_ai/__init__.py` — Dynamic version resolution via importlib.metadata

---

### Story 10.2: PyJWT `crit` Header Extension Vulnerability Remediation

**Priority**: HIGH | **Points**: 2
**Requirements**: NFR20 (security), Dependabot Alert #3
**Dependencies**: None

**Description:**
As a maintainer of Arcwright AI,
I want to upgrade the transitive PyJWT dependency from 2.11.0 to ≥2.12.0,
So that the application is not exposed to CVE-2026-32597 (High), where PyJWT accepts unknown `crit` header extensions without validation.

**Acceptance Criteria:**

**Given** PyJWT 2.11.0 is pinned in `uv.lock` as a transitive dependency (via `mcp` → `claude-code-sdk`) **When** `uv lock --upgrade-package pyjwt` is run **Then** the lockfile resolves PyJWT to ≥2.12.0
**And** no changes to `pyproject.toml` dependency declarations are needed (unless upstream constrains conflict)
**And** `ruff check`, `mypy --strict`, and `pytest` all pass with zero regressions
**And** Dependabot alert #3 (CVE-2026-32597) is auto-closed after merge

**Files touched:**
- `uv.lock` — Lockfile regeneration with upgraded PyJWT pin

---

### Story 10.3: LangGraph Major Version Upgrade & Deserialization Vulnerability Remediation

**Priority**: HIGH | **Points**: 5
**Requirements**: NFR20 (security), Dependabot Alerts #1, #2
**Dependencies**: None

**Description:**
As a maintainer of Arcwright AI,
I want to upgrade langgraph from 0.6.x to ≥1.0.10 (and transitively langgraph-checkpoint from 3.x to ≥4.0.0),
So that the application is not exposed to CVE-2026-28277 (unsafe msgpack deserialization in checkpoint loading) or CVE-2026-27794 (BaseCache deserialization of untrusted data leading to potential RCE).

**Note:** This story covers _two_ CVEs because the packages are tightly coupled — upgrading `langgraph` to ≥1.0.10 requires `langgraph-checkpoint` ≥4.0.0. This is a **major version upgrade** (0.x → 1.x) that will likely require code migration in the orchestration engine.

**Acceptance Criteria:**

**Given** `pyproject.toml` specifies `langgraph>=0.2,<1.0` **When** the upgrade is applied **Then** the constraint is changed to `langgraph>=1.0.10,<2.0`
**And** the lockfile resolves `langgraph` ≥1.0.10 and `langgraph-checkpoint` ≥4.0.0
**And** all source code and tests are migrated to the langgraph 1.x API surface
**And** `ruff check`, `mypy --strict`, and `pytest` all pass with zero regressions
**And** Dependabot alerts #1 (CVE-2026-27794) and #2 (CVE-2026-28277) are auto-closed after merge

**Files touched:**
- `pyproject.toml` — Version constraint change (`langgraph>=1.0.10,<2.0`)
- `uv.lock` — Lockfile regeneration
- `src/arcwright_ai/engine/` — Graph construction, node implementations (migration to 1.x API)
- `tests/` — Test fixture and mock updates for 1.x API surface

---

### Story 10.4: Agent SCM Guardrails & Commit-Node Resilience

**Priority**: HIGH | **Points**: 5
**Requirements**: Architecture (commit node pipeline), NFR (reliable SCM pipeline)
**Dependencies**: Story 2.5 (agent invoker), Story 2.7 (commit node)

**Description:**
As a user running Arcwright AI story execution,
I want the pipeline to always push a branch and create a PR when the agent produces code changes,
So that successful validation runs are not silently left unpushed due to the agent committing changes itself during dispatch.

**Bug:** The agent (Claude) runs with `permission_mode="bypassPermissions"` and no system prompt. It can — and does — run `git commit` itself during the dispatch phase. The pipeline's `commit_node` then finds `git status --porcelain` empty, raises `BranchError("no_changes")`, and the entire push → PR → auto-merge chain is silently skipped.

**Acceptance Criteria:**

**Given** the agent is invoked via `claude_code_sdk.query()` in `invoker.py` **When** `ClaudeCodeOptions` is constructed **Then** a `system_prompt` is set prohibiting the agent from running `git commit`, `git push`, `git checkout`, `git branch`, or any SCM-mutating commands, stating that all SCM operations are managed by the pipeline
**Given** the agent has already committed changes during dispatch (worktree is clean, but HEAD has advanced past the branch creation point) **When** `commit_story()` runs **Then** it detects the agent-created commits by comparing HEAD against the base ref, logs at INFO level, and returns the latest commit hash without raising `BranchError`
**Given** the agent committed some changes but also left additional uncommitted changes **When** `commit_story()` runs **Then** it stages and commits the remaining changes on top, returning the new commit hash
**Given** the worktree is truly empty (no agent commits, no uncommitted changes) **When** `commit_story()` runs **Then** it raises `BranchError` as before
**And** `ruff check`, `mypy --strict`, and `pytest` all pass with zero regressions

**Files touched:**
- `src/arcwright_ai/agent/invoker.py` — System prompt with SCM guardrails
- `src/arcwright_ai/scm/branch.py` — `commit_story()` resilience for agent-created commits
- `src/arcwright_ai/engine/nodes.py` — Pass base ref to `commit_story()`
- `tests/` — New tests for all commit scenarios

---

### Story 10.5: Retry Attempts Should Rebuild Fresh Context

**Priority**: HIGH | **Points**: 3
**Requirements**: FR9, FR16, FR18, NFR1, NFR11
**Dependencies**: Story 3.4 (validate node and retry loop)

**Description:**
As a maintainer of Arcwright AI,
I want each retry attempt to run with a fresh execution context,
So that retries do not inherit stale context bundles or worktree state from prior failed attempts.

**Bug:** Retry currently routes from `validate` back to `budget_check` and then to `agent_dispatch` without re-running `preflight`, which means the retry reuses the existing `context_bundle` and worktree state. If artifacts or files changed between attempts, retry behavior can diverge from current source-of-truth context.

**Acceptance Criteria:**

**Given** validation returns a retry outcome **When** the next attempt starts **Then** context for the retry is rebuilt from disk before agent invocation (either by routing through `preflight` or by an equivalent explicit context refresh step)
**And** the retry prompt includes current context plus prior validation feedback, not stale context from a previous attempt
**Given** a retry follows a failed attempt **When** the retry executes file changes **Then** it uses an isolated fresh working state that is deterministic and does not depend on residual uncommitted files from prior attempts
**And** tests cover retry context refresh behavior, including a regression case proving stale context is not reused

**Files touched (expected):**
- `src/arcwright_ai/engine/graph.py` - retry edge/routing behavior
- `src/arcwright_ai/engine/nodes.py` - retry transition and context refresh behavior
- `src/arcwright_ai/engine/state.py` - any state additions needed for retry context reset
- `tests/test_engine/` - retry-context regression tests

---

### Story 10.6: Auto-Merge Success Marked Error on Branch Cleanup Failure

**Priority**: HIGH | **Points**: 3
**Requirements**: FR39, FR4, NFR1, NFR2, NFR20
**Dependencies**: Story 9.3 (auto-merge), Story 12.4 (halt on merge failure)

**Description:**
As a maintainer running unattended dispatch,
I want merge status and cleanup status tracked separately,
So that successful PR merges are not reported as merge failures when local branch cleanup fails.

**Bug:** In auto-merge flow, a successful remote merge can be followed by local cleanup failure (for example, deleting a branch still checked out in a worktree). The run currently reports an error merge outcome, which can incorrectly signal merge failure and influence dispatch halt behavior.

**Acceptance Criteria:**

**Given** PR merge succeeds remotely **When** local branch/worktree cleanup fails **Then** merge outcome remains success and cleanup failure is recorded as warning/non-blocking
**Given** merge is successful **When** dispatch evaluates continuation **Then** it does not halt because of cleanup-only failure
**And** structured logs and run summary clearly separate merge result from cleanup result
**And** tests cover merge-success+cleanup-failure, merge-failure, and fully-success paths

**Files touched (expected):**
- `src/arcwright_ai/scm/pr.py` - merge result semantics
- `src/arcwright_ai/scm/worktree.py` - cleanup result semantics
- `src/arcwright_ai/engine/nodes.py` - commit/merge outcome propagation
- `src/arcwright_ai/output/summary.py` - unambiguous reporting
- `tests/test_scm/` and `tests/test_engine/` - regression coverage

---

### Story 10.7: Validate Node Overwrites Provenance — Decision Provenance Missing from PRs

**Priority**: HIGH | **Points**: 5
**Requirements**: FR12, FR13, FR14, FR15, FR35, NFR17
**Dependencies**: Story 4.4 (provenance integration), Story 6.4 (PR body generator)

**Description:**
As a code reviewer using Arcwright AI,
I want pull requests to contain the Decision Provenance section with all agent decisions recorded during story execution,
So that I can review the reasoning behind implementation choices, not just the code diff.

**Bug:** `validate_node` in `engine/nodes.py` unconditionally overwrites `validation.md` using `_serialize_validation_checkpoint()`, which writes an entirely different format (`# Validation Result` / `## V6 Invariant Checks` / `## V3 Reflexion Results`) that lacks the `## Agent Decisions` section. This destroys the provenance entries previously written by `agent_dispatch_node` via `append_entry()`. When `commit_node` later calls `generate_pr_body()`, `_extract_decisions()` finds no `## Agent Decisions` header and returns an empty list, rendering "No agent decisions recorded" in every PR.

On retries, the problem compounds: `agent_dispatch_node` calls `append_entry()` on the already-overwritten file (wrong format), so decisions are appended as orphaned `### Decision:` blocks not under a `## Agent Decisions` heading — still invisible to the parser.

**Acceptance Criteria:**

**Given** `agent_dispatch_node` writes provenance entries to `validation.md` **When** `validate_node` writes validation results **Then** the existing `## Agent Decisions` section and all `### Decision:` subsections are preserved intact
**Given** `validate_node` completes **When** `commit_node` calls `generate_pr_body()` **Then** `_extract_decisions()` returns all agent decisions recorded during dispatch and validation
**Given** a story completes with one or more agent decisions **When** the PR is created via `open_pull_request()` **Then** the PR body contains a populated `### Decision Provenance` section with each decision's title, timestamp, alternatives, rationale, and references
**Given** a retry cycle occurs (validate → retry → dispatch → validate) **When** the final PR is generated **Then** decisions from all attempts are present in the provenance, not just the last attempt
**And** `ruff check`, `mypy --strict`, and `pytest` all pass with zero regressions
**And** integration-level test coverage verifies the full pipeline: dispatch writes decisions → validate preserves them → PR body includes them

**Files touched (expected):**
- `src/arcwright_ai/engine/nodes.py` — Fix `validate_node` to not overwrite provenance; write validation checkpoint to a separate file or merge results into the existing provenance structure
- `src/arcwright_ai/output/provenance.py` — Potentially add a merge/update function for validation results
- `tests/test_engine/` — Integration test covering dispatch→validate→PR pipeline with provenance preservation
- `tests/test_scm/test_pr.py` — Test with realistic validation.md content (post-validate format)

---

### Story 10.8: Pre-Release Versioning for Develop Branch — Test vs. Stable Differentiation

**Priority**: MEDIUM | **Points**: 3
**Requirements**: NFR19 (idempotency), Story 10.1 (hatch-vcs)
**Dependencies**: Story 10.1 (dynamic versioning with hatch-vcs)

**Description:**
As a user or tester of Arcwright AI,
I want to distinguish between stable releases merged to `main` and test/pre-release versions merged to `develop`,
So that I can install the correct version for my use case — stable for production or pre-release for early testing — using standard pip semantics.

**Context:** The project uses a two-branch model: `main` for stable releases and `develop` for integration/testing. Currently, hatch-vcs derives versions from git tags but there is no convention or CI infrastructure to publish pre-release versions (alpha, beta, release candidate) from the `develop` branch. Users cannot differentiate between a test build and a stable release without inspecting git history.

**Design:**
- **Stable releases** (merged to `main`): Tagged `v1.0.0` → version `1.0.0` → published to PyPI
- **Pre-releases** (tagged on `develop`): Tagged `v1.1.0rc1` → version `1.1.0rc1` → published to TestPyPI (and optionally PyPI with pre-release flag)
- **Dev builds** (untagged commits on any branch): Automatically versioned `1.0.1.dev7` by hatch-vcs — local only, never published
- PEP 440 pre-release segments (`a`, `b`, `rc`) are natively supported by hatch-vcs and pip; no version-resolution code changes needed

**Acceptance Criteria:**

**Given** the existing `publish.yml` workflow triggers on `v*` tags **When** a stable tag like `v1.0.0` is pushed from `main` **Then** the package is built and published to PyPI as version `1.0.0` (existing behavior, unchanged)
**Given** a new `publish-test.yml` workflow exists **When** a pre-release tag like `v1.1.0rc1`, `v1.1.0a1`, or `v1.1.0b1` is pushed from `develop` **Then** the package is built and published to TestPyPI as the corresponding PEP 440 pre-release version
**And** `publish-test.yml` uses OIDC trusted publishing against the TestPyPI environment (no stored API tokens)
**And** `publish.yml` is updated to exclude pre-release tags (only triggers on tags matching `v[0-9]+.[0-9]+.[0-9]+` without pre-release suffixes) so stable and pre-release publishes never collide
**Given** a user runs `pip install arcwright-ai` **Then** only stable versions are installed (pip excludes pre-releases by default)
**Given** a user runs `pip install --pre arcwright-ai` or `pip install arcwright-ai==1.1.0rc1` **Then** the pre-release version from TestPyPI is installable via `--index-url https://test.pypi.org/simple/ --extra-index-url https://pypi.org/simple/`
**And** `arcwright-ai --version` (or `__version__`) correctly reports the pre-release version string (e.g., `1.1.0rc1`)
**And** the project README or CONTRIBUTING.md documents the tagging convention and install commands for each channel
**And** no changes to `src/arcwright_ai/__init__.py` version resolution are required (hatch-vcs handles PEP 440 pre-release tags natively)
**And** `ruff check`, `mypy --strict`, and `pytest` all pass with zero regressions

**Files touched:**
- `.github/workflows/publish.yml` — Narrow tag filter to exclude pre-release suffixes
- `.github/workflows/publish-test.yml` — New workflow: build + publish to TestPyPI on pre-release tags
- `README.md` or `CONTRIBUTING.md` — Document tagging convention and install commands for stable vs. test channels

---

### Story 10.9: CLI Version Command

**Priority**: LOW | **Points**: 2
**Requirements**: Developer experience, NFR (usability)
**Dependencies**: Story 10.1 (dynamic versioning with hatch-vcs)

**Description:**
As a user of Arcwright AI,
I want to check which version I'm running from the command line,
So that I can quickly verify my installed version for debugging, support, and compatibility purposes.

**Acceptance Criteria:**

**Given** the CLI is installed **When** the user runs `arcwright-ai version` **Then** the installed package version is printed to stdout (e.g., `arcwright-ai 0.2.0`) and the process exits with code 0
**And** `arcwright-ai --version` prints the same version string and exits with code 0 without invoking any subcommand
**And** in editable installs without a git tag, the fallback version `0.0.0.dev0` is displayed (consistent with `__version__` from Story 10.1)
**And** `version` appears in `arcwright-ai --help` command list and `--version` appears as a top-level option
**And** `ruff check`, `mypy --strict`, and `pytest` all pass with zero regressions

**Files touched:**
- `src/arcwright_ai/cli/app.py` — Add `--version` callback to app and `version` subcommand
- `tests/test_cli/` — Tests for version command and `--version` flag

---

### Story 10.10: Redact API Key from LangSmith Traces via SecretStr

**Priority**: HIGH | **Points**: 2
**Requirements**: NFR6 (API key security), NFR20 (security)
**Dependencies**: Story 1.3 (configuration system)

**Description:**
As a maintainer using LangSmith for trace observability,
I want the Anthropic API key to be redacted from all LangGraph checkpoint serialisations,
So that the raw key value never appears in the LangSmith UI or any trace export.

**Bug:** `ApiConfig.claude_api_key` is typed as a plain `str`. Since `RunConfig` (containing `ApiConfig`) is embedded in `StoryState` — the LangGraph state model — every checkpoint serialisation exposes the key in cleartext in LangSmith traces.

**Acceptance Criteria:**

**Given** `ApiConfig` defines `claude_api_key` **When** the field type is inspected **Then** it is `pydantic.SecretStr`, not `str`
**Given** a `RunConfig` instance is serialised to dict or JSON (as happens during LangGraph checkpoint writes) **When** the output is inspected **Then** the `claude_api_key` value appears as `"**********"`, not the raw key
**Given** engine nodes (`agent_dispatch_node`, `validate_node`) need the raw key for SDK invocation **When** they access the key **Then** they call `.get_secret_value()` to obtain the plaintext value
**And** all existing config loading paths (env var, global YAML, .env file) continue to work — Pydantic coerces `str → SecretStr` automatically
**And** `ruff check`, `mypy --strict`, and `pytest` all pass with zero regressions

**Files touched:**
- `src/arcwright_ai/core/config.py` — `ApiConfig.claude_api_key` type change to `SecretStr`, import addition
- `src/arcwright_ai/engine/nodes.py` — `.get_secret_value()` calls in `agent_dispatch_node` and `validate_node`
- `tests/test_core/test_config.py` — Update assertions to use `.get_secret_value()`

---

## Epic 11: BMAD 6.1 Framework Upgrade

> **Value prop**: Developer upgrades the project's BMAD development infrastructure from v6.0.3 to v6.1.0, gaining the new skills-based architecture, Edge Case Hunter code review capability, critical bug fixes, and a 91% smaller framework footprint — without any disruption to the product's source code or test suite.

### Story 11.1: Pre-Upgrade Audit & Backup

**Priority**: HIGH | **Points**: 3
**Requirements**: NFR19 (idempotency)
**Dependencies**: None

**Description:**
As the maintainer of Arcwright AI,
I want to audit the current `_bmad/` installation for any custom modifications and create a backup before the 6.1 upgrade,
So that no custom work is lost and the upgrade can be safely rolled back if needed.

**Acceptance Criteria:**

**Given** the project is on BMAD v6.0.3 (installed 2026-02-26) **When** the pre-upgrade audit is performed **Then** a diff is generated between the stock 6.0.3 installation and the current `_bmad/` directory to identify any custom modifications to agents, workflows, configs, or memory files
**And** the `_bmad/_memory/` sidecar directory contents are documented (these are user customizations that must survive the upgrade)
**And** the `.github/copilot-instructions.md` current content is documented as the baseline for post-upgrade comparison
**And** a full backup of `_bmad/` is created at `_bmad-backup-6.0.3/` (gitignored)
**And** the audit results are documented in a brief markdown report listing: (1) custom modifications found (if any), (2) sidecar data to preserve, (3) copilot-instructions.md baseline, (4) backup location verified
**And** no product source code (`src/`, `tests/`) is modified in this story

**Files touched:**
- `.gitignore` — Add `_bmad-backup-*` exclusion
- `_spec/implementation-artifacts/11-1-pre-upgrade-audit-and-backup.md` — Story file

---

### Story 11.2: Execute BMAD 6.1 Installation & Migration

**Priority**: HIGH | **Points**: 5
**Requirements**: NFR19 (idempotency), NFR5 (config validation at startup)
**Dependencies**: Story 11.1

**Description:**
As the maintainer of Arcwright AI,
I want to run the BMAD 6.1 installer to upgrade the project's development infrastructure from the workflow/XML engine to the new skills-based architecture,
So that the project uses the latest BMAD framework with all bug fixes, the Edge Case Hunter capability, and the leaner skills-based workflow execution model.

**Acceptance Criteria:**

**Given** the pre-upgrade audit (Story 11.1) is complete and backup verified **When** `npx bmad-method@6.1.0 install` is executed in the project root **Then** the installer completes successfully, upgrading all installed modules: core (6.0.3→6.1.0), bmm (6.0.3→6.1.0), bmb, cis, tea to their 6.1-compatible versions
**And** `_bmad/_config/manifest.yaml` reflects the new version numbers
**And** all `_bmad/bmm/workflows/` are converted to the new skills-based format (SKILL.md entrypoints replacing workflow.yaml + workflow.xml engine)
**And** `.github/copilot-instructions.md` is regenerated with 6.1 agent/skill references
**And** `_bmad/_memory/` sidecar data is preserved through the upgrade (tech-writer-sidecar, storyteller-sidecar contents unchanged)
**And** `_bmad/bmm/config.yaml` retains all project-specific values (user_name, paths, language settings)
**And** if the installer fails or produces errors, the backup from Story 11.1 is used to restore `_bmad/` to the pre-upgrade state
**And** no product source code (`src/`, `tests/`) is modified in this story

**Files touched:**
- `_bmad/` — Full framework upgrade (installer-managed)
- `.github/copilot-instructions.md` — Regenerated by installer
- `_bmad/_config/manifest.yaml` — Updated version metadata

---

### Story 11.3: Post-Upgrade Verification & Development Workflow Smoke Test

**Priority**: HIGH | **Points**: 5
**Requirements**: NFR1 (no silent failures), NFR5 (config validation)
**Dependencies**: Story 11.2

**Description:**
As the maintainer of Arcwright AI,
I want to verify that the 6.1 upgrade did not break any product functionality or development workflows,
So that I can confidently continue development using the new skills-based BMAD infrastructure.

**Acceptance Criteria:**

**Given** BMAD 6.1 installation is complete (Story 11.2) **When** the verification suite is executed **Then** `ruff check` passes with zero issues across all source code
**And** `mypy --strict` passes with zero issues
**And** `pytest` full suite passes with zero failures (confirming product code is unaffected by the `_bmad/` upgrade)
**And** `arcwright-ai validate-setup` passes all checks when run against the project (confirming the CLI still detects BMAD artifacts correctly)
**And** the BMAD development workflows are functional under the new skills-based system: (1) `/bmad-bmm-create-story` or equivalent skill can be invoked, (2) `/bmad-bmm-dev-story` or equivalent skill can be invoked, (3) `/bmad-bmm-code-review` or equivalent skill can be invoked
**And** the `_spec/` planning artifacts (prd.md, architecture.md, epics.md) are unchanged and accessible
**And** the `_spec/implementation-artifacts/sprint-status.yaml` is unchanged
**And** the backup directory `_bmad-backup-6.0.3/` is removed after successful verification
**And** no product source code (`src/`, `tests/`) is modified in this story

**Files touched:**
- `.gitignore` — Remove `_bmad-backup-*` exclusion (cleanup)
- `_spec/implementation-artifacts/11-3-post-upgrade-verification.md` — Story file

---

## Epic 12: CI-Aware Merge Wait for Epic Chain Integrity

> **Value prop**: Developer dispatches a multi-story epic overnight with `auto_merge: true` and the engine waits for each story's CI checks to pass and the PR to merge before starting the next story — ensuring every story builds on verified, merged code. If CI fails, the epic halts cleanly and the developer can fix the PR, let auto-merge complete, and `--resume`.

### Story 12.1: MergeOutcome Enum, Config Field & State Plumbing

**Priority**: HIGH | **Points**: 3
**Requirements**: FR39 (auto-merge)
**Dependencies**: Epic 9 (complete)
**Tech Spec**: `_spec/implementation-artifacts/ci-aware-merge-wait.md` (Tasks 1, 5)

**Description:**
As a developer configuring Arcwright AI for CI-aware epic dispatch,
I want a `merge_wait_timeout` config field and a `MergeOutcome` enum,
So that the merge subsystem can report structured outcomes and the dispatch loop can make halt decisions.

**Acceptance Criteria:**

**Given** `core/config.py` `ScmConfig` Pydantic model
**When** `merge_wait_timeout` is added
**Then** `ScmConfig` gains `merge_wait_timeout: int = 0` — seconds to wait for CI after auto-merge; `0` = fire-and-forget (backward compatible default)
**And** config validation emits a structured log warning when `auto_merge=True` and `merge_wait_timeout=0`: _"auto_merge is enabled but merge_wait_timeout is 0 — CI checks will not be waited for. Set merge_wait_timeout to enable chain integrity."_
**And** `_KNOWN_SECTION_FIELDS["scm"]` auto-includes `merge_wait_timeout` via `ScmConfig.model_fields.keys()` (no manual update needed)
**And** `MergeOutcome` StrEnum is defined in `scm/pr.py` with values: `MERGED`, `SKIPPED`, `CI_FAILED`, `TIMEOUT`, `ERROR`
**And** `MergeOutcome` is exported from `scm/__init__.py`
**And** `StoryState` in `engine/state.py` gains `merge_outcome: str | None = None`
**And** `_DEFAULT_CONFIG_YAML` in `cli/status.py` includes commented-out `merge_wait_timeout` with `# recommended: 1200 (20 min) when auto_merge is true`
**And** existing config round-trip tests still pass (new field has a default)
**And** unit tests verify: (1) `merge_wait_timeout` defaults to 0, (2) config loads with explicit timeout, (3) footgun warning is logged when `auto_merge=True` + `timeout=0`, (4) `MergeOutcome` enum values match expected strings, (5) `StoryState` accepts `merge_outcome` field
**And** `ruff check .` and `mypy --strict src/` pass with zero issues

**Files touched:**
- `src/arcwright_ai/core/config.py` — `ScmConfig.merge_wait_timeout` field
- `src/arcwright_ai/scm/pr.py` — `MergeOutcome` StrEnum
- `src/arcwright_ai/scm/__init__.py` — Export `MergeOutcome`
- `src/arcwright_ai/engine/state.py` — `StoryState.merge_outcome` field
- `src/arcwright_ai/cli/status.py` — Config template update
- `tests/test_core/test_config.py` — Config field + warning tests
- `tests/test_scm/test_pr.py` — `MergeOutcome` enum tests

---

### Story 12.2: Rewrite merge_pull_request() with CI Wait

**Priority**: HIGH | **Points**: 8
**Requirements**: FR39 (auto-merge), NFR1 (no silent incorrect output), NFR19 (idempotent)
**Dependencies**: Story 12.1
**Tech Spec**: `_spec/implementation-artifacts/ci-aware-merge-wait.md` (Task 2)

**Description:**
As a developer with `auto_merge: true` and `merge_wait_timeout > 0`,
I want `merge_pull_request()` to queue auto-merge, wait for CI, and confirm the PR actually merged,
So that subsequent stories in an epic always build on verified, merged code.

**Acceptance Criteria:**

**Given** `scm/pr.py` `merge_pull_request()` function
**When** `wait_timeout > 0`
**Then** signature changes to `async def merge_pull_request(pr_url, strategy, *, project_root, wait_timeout=0) -> MergeOutcome`
**And** Step A: runs `gh pr merge <number> <strategy_flag> --delete-branch --auto` to queue auto-merge; parses stderr — if `"auto-merge is not allowed"` is found, returns `MergeOutcome.ERROR` with actionable log: _"Auto-merge is not enabled for this repository. Enable it in Settings → General → Allow auto-merge."_
**And** Step B: runs `gh pr checks <number> --watch --fail-fast` wrapped in `asyncio.wait_for(timeout=wait_timeout)` — exit 0 → proceed to Step C; exit 1 → return `MergeOutcome.CI_FAILED`
**And** on `asyncio.TimeoutError`: calls `proc.terminate()` + `await proc.wait()` with 5s grace period (falls back to `proc.kill()` if needed); runs `gh pr view --json state` to check if PR is already `MERGED` before returning `MergeOutcome.TIMEOUT`
**And** Step C: verifies PR merged via `gh pr view <number> --json state --jq .state` — retries up to 3 times with 5s sleep if not yet `MERGED`; returns `MergeOutcome.MERGED` on success, `MergeOutcome.ERROR` if still not merged
**And** when `wait_timeout == 0` (backward compatible): runs `gh pr merge <number> <strategy_flag> --delete-branch` (no `--auto`, immediate merge, same as current) — returns `MergeOutcome.MERGED` on success, `MergeOutcome.ERROR` on failure
**And** guard clauses unchanged: `gh` not found → `MergeOutcome.ERROR`, invalid URL → `MergeOutcome.ERROR`
**And** all outcomes logged via structured logging with `merge_outcome` field
**And** all existing `merge_pull_request` tests updated from `bool` assertions to `MergeOutcome` assertions (return type is the only breaking change; all use `wait_timeout=0` default)
**And** new unit tests: `test_merge_pr_auto_flag_when_wait_timeout_positive`, `test_merge_pr_checks_watch_called_after_auto`, `test_merge_pr_returns_merged_on_ci_pass`, `test_merge_pr_returns_ci_failed_on_check_failure`, `test_merge_pr_returns_timeout_on_asyncio_timeout`, `test_merge_pr_no_wait_when_timeout_zero`, `test_merge_pr_returns_skipped_never`, `test_merge_pr_timeout_verify_actually_merged`, `test_merge_pr_timeout_subprocess_sigterm` (timing simulation), `test_merge_pr_auto_merge_not_allowed_stderr`
**And** `ruff check .` and `mypy --strict src/` pass with zero issues

**Files touched:**
- `src/arcwright_ai/scm/pr.py` — Rewrite `merge_pull_request()`, update return type
- `tests/test_scm/test_pr.py` — Update existing tests (bool → MergeOutcome), add 10 new tests

---

### Story 12.3: commit_node MergeOutcome Integration

**Priority**: HIGH | **Points**: 5
**Requirements**: FR39, NFR1, NFR16 (provenance)
**Dependencies**: Story 12.2
**Tech Spec**: `_spec/implementation-artifacts/ci-aware-merge-wait.md` (Task 3)

**Description:**
As the engine's commit_node,
I want to pass the configured `merge_wait_timeout` to `merge_pull_request()` and record the structured `MergeOutcome` on story state,
So that merge results flow correctly into provenance records and are available for the dispatch loop to inspect.

**Acceptance Criteria:**

**Given** `engine/nodes.py` `commit_node` auto-merge block
**When** `auto_merge` is `True`
**Then** `merge_pull_request()` is called with `wait_timeout=state.config.scm.merge_wait_timeout`
**And** the existing `merge_succeeded: bool` conditional is replaced with `MergeOutcome` switch logic:
  - `MERGED` → call `get_pull_request_merge_sha()`, fetch merge SHA, record provenance as success
  - `CI_FAILED` / `TIMEOUT` / `ERROR` → skip `get_pull_request_merge_sha()` (no merge SHA to fetch), record provenance with failure details
**And** `state.merge_outcome = merge_outcome.value` is set on the returned state
**And** when `auto_merge` is `False`, `merge_pull_request()` is never called and `state.merge_outcome = MergeOutcome.SKIPPED.value`
**And** all outcomes recorded in provenance entries with the correct merge status
**And** existing commit_node behavior preserved when `wait_timeout=0` (backward compatible)
**And** unit tests: `test_commit_node_sets_merge_outcome_merged`, `test_commit_node_sets_merge_outcome_ci_failed`, `test_commit_node_sets_merge_outcome_skipped`, `test_commit_node_passes_wait_timeout_from_config`
**And** `ruff check .` and `mypy --strict src/` pass with zero issues

**Files touched:**
- `src/arcwright_ai/engine/nodes.py` — Update auto-merge block: `wait_timeout` arg, `MergeOutcome` switch, state field
- `tests/test_engine/test_nodes.py` — 4 new/updated commit_node tests

---

### Story 12.4: Dispatch Loop Halt on Merge Failure

**Priority**: HIGH | **Points**: 3
**Requirements**: FR4 (halt on failure), NFR2 (recoverable partial completion)
**Dependencies**: Story 12.3
**Tech Spec**: `_spec/implementation-artifacts/ci-aware-merge-wait.md` (Task 4)

**Description:**
As the epic dispatch loop,
I want to inspect the `merge_outcome` on a completed story's state and halt the epic when CI failed or timed out,
So that subsequent stories never build on stale, unmerged code.

**Acceptance Criteria:**

**Given** `cli/dispatch.py` `_dispatch_epic_async()` story loop
**When** `graph.ainvoke()` returns a story with status SUCCESS
**Then** the dispatch loop checks `result.merge_outcome`
**And** if `merge_outcome` is `"ci_failed"` or `"timeout"`, the loop breaks with a warning log: _"Epic halted: Story {slug} PR merge failed (CI {outcome}). Fix the PR and run `arcwright dispatch --resume` to continue."_
**And** if `merge_outcome` is `"merged"`, `"skipped"`, or `None`, the loop continues to the next story
**And** the halt behavior does NOT change the story's SUCCESS status — the story code was valid, only the merge failed
**And** backward compatibility: when `merge_outcome` is `None` (pre-existing stories without the field), the loop continues
**And** `MergeOutcome` is imported from `arcwright_ai.scm` (enum, not bare strings) for the comparison
**And** unit test: `test_dispatch_halts_on_ci_failed_merge_outcome`, `test_dispatch_halts_on_timeout_merge_outcome`, `test_dispatch_continues_on_merged_outcome`, `test_dispatch_continues_on_none_outcome`
**And** `ruff check .` and `mypy --strict src/` pass with zero issues

**Files touched:**
- `src/arcwright_ai/cli/dispatch.py` — Merge outcome check after story SUCCESS
- `tests/test_cli/test_dispatch.py` (or inline) — 4 dispatch halt tests