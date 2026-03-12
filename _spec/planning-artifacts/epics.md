---
stepsCompleted: ['step-01-validate-prerequisites', 'step-02-design-epics', 'step-03-create-stories', 'step-04-final-validation']
inputDocuments:
  - '_spec/planning-artifacts/prd.md'
  - '_spec/planning-artifacts/architecture.md'
date: 2026-03-02
author: Ed
epicCount: 8
storyCount: 38
totalPoints: 186
frCoverage: '36/36'
nfrCoverage: '20/20'
amendedDate: 2026-03-11
amendedBy: Bob (SM)
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
- D7 (Git Operations): Shell out to `git` CLI via async subprocess wrapper. Worktree lifecycle with atomic guarantees. Branch naming: `arcwright/<story-slug>`.
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
Developer gets clean git branches per story, worktree lifecycle management, automated commits, and pull requests with decision provenance embedded — code review is decision-centric, not line-by-line.
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
**Then** `create_worktree(story_slug: str, base_ref: str) → Path` creates worktree at `.arcwright-ai/worktrees/<story-slug>` with branch `arcwright/<story-slug>`
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
**Then** branch naming follows convention: `arcwright/<story-slug>` — namespaced, predictable, greppable per D7
**And** `create_branch(story_slug: str, base_ref: str)` creates branch; existing branch → `BranchError` (no force operations per D7)
**And** commit inside worktree uses: `git add .` + `git commit -m "[arcwright] <story-title>\n\nStory: <story-file-path>\nRun: <run-id>"`
**And** no push in MVP — all operations are local only
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
**Then** `preflight` node calls `scm/worktree.py` to create worktree before agent execution; sets `cwd` for agent dispatch to the worktree path
**And** `commit` node calls `scm/branch.py` to commit inside worktree, then `scm/worktree.py` to remove worktree
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