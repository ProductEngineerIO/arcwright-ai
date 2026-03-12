---
stepsCompleted: [1, 2, 3, 4, 5, 6, 7, 8]
lastStep: 8
status: 'amended'
completedAt: '2026-02-27'
amendedAt: '2026-03-11'
amendments:
  - date: '2026-03-11'
    description: 'Decision 9: Role-Based Model Registry — dual-model support for code generation vs. review with extensible role pattern'
inputDocuments:
  - '_spec/planning-artifacts/prd.md'
  - '_spec/planning-artifacts/product-brief-arcwright-ai-2026-02-26.md'
  - '_spec/planning-artifacts/prd-validation-report-2026-02-26.md'
  - '_spec/brainstorming/brainstorming-session-2026-02-26.md'
workflowType: 'architecture'
project_name: 'Arcwright AI'
user_name: 'Ed'
date: '2026-02-27'
---

# Architecture Decision Document

_This document builds collaboratively through step-by-step discovery. Sections are appended as we work through each architectural decision together._

## Project Context Analysis

### Requirements Overview

**Functional Requirements:**
36 FRs organized across 7 domains: Orchestration & Execution (FR1-7), Validation & Quality (FR8-11), Decision Provenance (FR12-15), Context Injection (FR16-18), Agent Invocation (FR19-22), Cost & Resource Tracking (FR23-25), Project Setup & Configuration (FR26-30), Run Visibility (FR31-33), and SCM Integration (FR34-36). The orchestration and validation domains carry the highest architectural weight — they define the core execution loop that every story traverses.

**Critical FR Chains:**
The FRs are not independent — they form execution chains where a flaw in any single FR breaks the product thesis:

- **Core Execution Chain:** FR1 (dispatch epic) → FR3 (sequential execution) → FR8 (V3 evaluation) → FR9 (retry on failure) → FR4 (halt on max retries) → FR5 (resume from halt). This is the overnight dispatch loop — the entire MVP thesis lives or dies on this path.
- **Provenance Chain:** FR12 (log decisions) → FR13 (structured entries) → FR14 (write to runs/) → FR15 (attach to PRs). This is the trust mechanism — breaks here mean code review devolves to line-by-line reading.
- **Context Chain:** FR16 (read BMAD artifacts) → FR17 (answerer rule lookup) → FR18 (resolve dependencies) → FR19 (invoke SDK with assembled context). This is how the agent gets smart — breaks here mean the agent works blind.
- **Safety Chain:** FR6 (worktree isolation) → FR20 (path traversal prevention) → FR21 (temp file containment) → FR36 (worktree lifecycle). This is the sandbox — breaks here risk corrupting the main branch.

**Non-Functional Requirements:**
20 NFRs across Reliability (NFR1-5), Security (NFR6-8), Performance & Cost (NFR9-12), Integration (NFR13-15), Observability (NFR16-18), and System-Wide Quality (NFR19-20). The reliability requirements are the most architecturally constraining — zero silent failures (NFR1), full progress recovery (NFR2), and worktree isolation (NFR4) collectively demand a state machine with explicit transitions and no implicit success paths.

**Scale & Complexity:**

- Primary domain: Developer Infrastructure — Python CLI + LangGraph orchestration engine
- Complexity level: High — novel combination of deterministic workflow orchestration, non-deterministic AI agent invocation, and SCM integration
- Estimated architectural subsystems: 10 major subsystems (enumerated below)

### Architectural Subsystem Map

| # | Subsystem | Scope | Key FRs/NFRs |
|---|-----------|-------|---------------|
| 1 | **Orchestration Engine** | LangGraph StateGraph — DAG execution, state transitions, retry logic | FR1-5, NFR1-2 |
| 2 | **Validation Framework** | V3 reflexion + V6 invariant pipelines, artifact-specific routing | FR8-11, NFR1 |
| 3 | **Agent Invoker** | Claude Code SDK integration — prompt construction, streaming, result parsing | FR19, FR22 |
| 4 | **Agent Sandbox** | Path validation layer between orchestrator and SDK — enforces file write boundaries, prevents path traversal | FR20-21, NFR7 |
| 5 | **Context Injector / Answerer** | BMAD artifact reading, context assembly, static rule lookup engine | FR16-18 |
| 6 | **Provenance Recorder** | Decision logging, structured markdown generation, PR attachment | FR12-15, NFR17 |
| 7 | **SCM Manager** | Git worktree lifecycle, branch management, PR generation | FR6-7, FR34-36, NFR4 |
| 8 | **Configuration System** | Two-tier config with env var override, Pydantic validation, precedence chain, role-based model registry | FR26-30, NFR5 |
| 9 | **Run State Manager (`.arcwright-ai/`)** | File-based persistent state — runs, provenance, config, tmp. The product's state outside of LangGraph. | FR31-33, NFR8, NFR16 |
| 10 | **CLI Surface** | Click/Typer thin wrapper over Python API — 7 MVP commands | FR26-27, NFR19 |

### First-Class Architectural Constraints

**1. State Lifecycle Model (Foundational)**
The task lifecycle `queued → preflight → running → validating → success/retry/escalated` is not a cross-cutting concern — it is the **architectural backbone**. The entire trust model depends on state transitions being explicit and auditable. NFR1 (zero silent failures) and NFR2 (full progress recovery) both collapse if any state transition is implicit or can be bypassed. Every subsystem must respect and report through this lifecycle.

**2. Orchestrator-Agent Contract Boundary**
The orchestrator is responsible for: context assembly, prompt construction, invocation, and result interpretation. The agent (Claude Code SDK) is a **pure execution black box** — it receives a prompt, it returns output. The agent sandbox (subsystem #4) sits between them, gating file operations. Any behavior crossing this boundary is a design smell. This contract must be explicit in the architecture to prevent scope creep into persistent agent state.

**3. Observe Mode Instrumentability (Design Now, Ship Later)**
The PRD defers observe mode to Growth, but explicitly states: "the execution pipeline must be architecturally instrumentable in MVP." This means every subsystem must expose hooks for observation — the architecture cannot treat this as a Growth-phase afterthought. The pipeline must support a "dry run" mode from day one even though the `--observe` CLI flag ships later.

**4. Worktree Isolation as Security Model**
Git worktrees are not a convenience — they are the **primary isolation and safety boundary**. The PRD validation report confirmed this was intentionally pulled into MVP (upgraded from "Out of MVP" in the brief). Each story executes in its own worktree. Worktree operations must be atomic and recoverable — if `git worktree add` fails mid-operation, cleanup logic must restore consistent state. This is a founding architectural decision.

**5. Design for 5 Dependency Layers (Implement 2)**
The brainstorming session defined a 5-layer dependency stack: phase ordering → existence checks → status gates → assignee locks → hash staleness. MVP implements layers 1-2. However, the data structures, state model, and artifact references must **accommodate all 5 layers from day one** — or Growth-phase additions will require painful state model retrofits. This means `ArtifactRef` types, frontmatter schemas, and LangGraph state fields should have extension points for layers 3-5 even if unused in MVP.

### Technical Constraints & Dependencies

- **LangGraph StateGraph** as the execution runtime — all workflow state transitions are graph edges, all agent invocations are graph nodes
- **Claude Code SDK** (Python async generator) as the sole agent invocation interface — stateless, one session per story
- **Git 2.25+** for worktree operations — must handle atomic create/delete with failure recovery
- **Python 3.11+** — LangGraph requirement
- **File-system-oriented artifact model** — BMAD artifacts are markdown files in conventional directory structures; `.arcwright-ai/` is a file-based database with its own integrity guarantees
- **Two-tier config** with env var override — Pydantic validation at startup, not mid-run
- **MVP is sequential** — single agent, single story at a time. Architecture must not preclude Growth-phase parallel execution (N=5)
- **`arcwright-ai init`** bootstraps the entire product state model — it is the entry point for the `.arcwright-ai/` subsystem and must be idempotent

### Cross-Cutting Concerns Identified

1. **Cost tracking** — every SDK invocation must be instrumented; aggregated per-story and per-run; token ceiling enforcement halts before next invocation
2. **Idempotency** — resume, cleanup, init, and all re-runnable operations must produce identical state on repeated execution (NFR19)
3. **Decision provenance** — generated for every story execution (success, failure, halt); attached to PRs; written to `.arcwright-ai/runs/<run-id>/provenance/`
4. **Error handling cascade** — validation failure → retry (up to budget) → halt → structured report → resume point. No silent failures at any stage.
5. **Configuration validation** — all config errors surfaced at startup/validation, never mid-run. Unknown keys warn, missing required keys error.
6. **Observability instrumentation** — task lifecycle states tracked in LangGraph state; run summaries always generated; hooks exposed for Growth-phase observe mode
7. **Path safety** — application-level enforcement preventing agent file operations outside project base directory (agent sandbox subsystem)

### PRD Scoping Notes with Architectural Impact

The PRD validation report identified 4 scoping changes from the product brief. Two have direct architectural implications:

| Change | Brief → PRD | Architectural Impact |
|--------|-------------|---------------------|
| Observe mode | MVP → Growth | Architecture must be **instrumentable** in MVP — hooks, event emission, dry-run capability designed in from day one |
| Git worktree isolation | Out of MVP → IN MVP | Worktrees are the **founding isolation model** — not deferrable, not optional. Atomic operations with recovery required. |

## Starter Template Evaluation

### Primary Technology Domain

**Python CLI tool + orchestration engine platform** — installed via PyPI, invoked via terminal, runs LangGraph state machines that invoke Claude Code SDK async generators.

### Starter Options Considered

| Option | Description | Verdict |
|--------|-------------|---------|
| **Cookiecutter-pypackage** | Classic Python package template. Provides setup.py/pyproject.toml, Sphinx docs, tox, Makefiles. | Dated — still generates setup.py by default, doesn't align with modern tooling. |
| **Copier Python template** | Modern Copier-based template with pyproject.toml, GitHub Actions, pre-commit. | Viable but generic — no CLI structure, no async patterns, significant customization needed. |
| **python-project-template (fpgmaas)** | Modern template with pyproject.toml, mkdocs, pytest, GitHub Actions, pre-commit, Docker. | Closest to our needs but still a generic library template — no Typer, no LangGraph patterns. |
| **Custom scaffold** | Hand-built project structure tailored to Arcwright AI's subsystem map, async-first patterns, and LangGraph integration. | **Selected.** No existing template matches our orchestration engine + CLI + LangGraph + SDK stack. |

### Selected Approach: Custom Scaffold

**Rationale:** No existing Python project template provides LangGraph StateGraph structure, Typer CLI with async internals, Claude Code SDK integration patterns, or the `.arcwright-ai/` file-based state management. The subsystem map from Step 2 gives us a clear package structure. Using a generic template would require gutting 60%+ of it and adding all domain-specific structure anyway.

**Initialization:**

```bash
mkdir arcwright-ai && cd arcwright-ai
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
```

### Architectural Decisions Established by Scaffold

**Language & Runtime:**
- Python 3.11+ (LangGraph minimum)
- Async-first — all orchestration nodes, SDK calls, and internal APIs are async. CLI entry points wrap with `asyncio.run()`
- Type hints throughout — enforced by mypy or pyright

**CLI Framework:**
- Typer (built on Click) — type-hint-driven command definitions, auto-completion, rich help text
- Thin wrapper pattern — every CLI command delegates to the Python API; CLI is a surface, not the core

**Package & Dependency Management:**
- `pyproject.toml` (PEP 621) — single source of truth for metadata, dependencies, build config
- `pip install -e ".[dev]"` for development; `pip install arcwright-ai` for users

**Testing:**
- pytest with `pytest-asyncio` for async-first test support
- Test structure mirrors source structure
- Dedicated `tests/fixtures/` directory for shared test infrastructure:
  - Mock SDK client (predictable async generator responses for success, failure, rate limit, malformed scenarios)
  - Synthetic BMAD project fixtures: known-good (passes all V6), known-bad (fails specific checks), partial (for resume testing)
  - `tmp_project` conftest fixture that scaffolds minimal `.arcwright-ai/` + `_spec/` directory for integration tests
- SCM tests marked `@pytest.mark.slow` (real git operations with `tmp_path`)

**Code Quality:**
- Ruff for linting + formatting (replaces flake8, isort, black — single tool)
- mypy or pyright for type checking
- pre-commit hooks for CI consistency

**Build & Distribution:**
- `pyproject.toml` with `hatchling` or `setuptools` backend
- PyPI: `pip install arcwright-ai`
- Development: `pip install -e ".[dev]"`

### Project Structure

8 packages aligned to subsystem map — consolidated from initial 10 per pragmatism review. Packages split when any single file exceeds ~300 lines.

```
arcwright-ai/
├── pyproject.toml
├── README.md
├── LICENSE
├── src/
│   └── arcwright_ai/
│       ├── __init__.py
│       ├── cli/                    # [Subsystem 10] Typer CLI surface
│       │   ├── __init__.py
│       │   ├── app.py              # Typer app, command registration
│       │   ├── dispatch.py         # dispatch commands
│       │   └── status.py           # status, validate-setup, cleanup
│       ├── engine/                 # [Subsystem 1] Orchestration Engine
│       │   ├── __init__.py
│       │   ├── graph.py            # LangGraph StateGraph definition
│       │   ├── state.py            # Pydantic state models (ProjectState, StoryState)
│       │   └── nodes.py            # All graph nodes (flat — split at ~300 LOC)
│       ├── validation/             # [Subsystem 2] Validation Framework
│       │   ├── __init__.py
│       │   ├── v3_reflexion.py     # V3 reflexion validation
│       │   ├── v6_invariant.py     # V6 invariant checks
│       │   └── pipeline.py         # Artifact-specific pipeline routing
│       ├── agent/                  # [Subsystems 3+4] Agent Invoker + Sandbox
│       │   ├── __init__.py
│       │   ├── invoker.py          # Claude Code SDK async integration
│       │   ├── sandbox.py          # Path validation (zero coupling to invoker —
│       │   │                       #   passed as validator via dependency inversion)
│       │   └── prompt.py           # Prompt construction helpers
│       ├── context/                # [Subsystem 5] Context Injector / Answerer
│       │   ├── __init__.py
│       │   ├── injector.py         # BMAD artifact reading, context assembly
│       │   └── answerer.py         # Static rule lookup engine
│       ├── output/                 # [Subsystems 6+9] Provenance + Run State
│       │   ├── __init__.py
│       │   ├── provenance.py       # Decision logging + markdown generation
│       │   ├── run_manager.py      # .arcwright-ai/ directory management
│       │   └── summary.py          # Run summary + halt report generation
│       ├── scm/                    # [Subsystem 7] SCM Manager
│       │   ├── __init__.py
│       │   ├── worktree.py         # Git worktree lifecycle (atomic create/delete + recovery)
│       │   ├── branch.py           # Branch naming, management
│       │   └── pr.py               # PR generation with provenance attachment
│       └── core/                   # Shared infrastructure
│           ├── __init__.py
│           ├── types.py            # ArtifactRef (with extension fields for dep layers 3-5),
│           │                       #   StoryId, EpicId, RunId
│           ├── lifecycle.py        # Task lifecycle enum + transition rules
│           ├── config.py           # Pydantic config models + two-tier loader
│           ├── constants.py        # Dir names, defaults, exit codes (0-5), retry limits
│           ├── exceptions.py       # HaltError, ConfigError, SandboxViolation, etc.
│           └── events.py           # Observe mode hooks — emit interface, no-op default handler
├── tests/
│   ├── conftest.py                 # tmp_project fixture, mock SDK client, shared helpers
│   ├── fixtures/
│   │   ├── mock_sdk.py             # Predictable async generator for SDK scenarios
│   │   └── projects/               # Synthetic BMAD project directories
│   │       ├── valid_project/      # Passes all V6 checks
│   │       ├── invalid_project/    # Fails specific V6 checks
│   │       └── partial_project/    # For resume/halt testing
│   ├── test_cli/
│   ├── test_engine/
│   ├── test_validation/
│   ├── test_agent/
│   ├── test_context/
│   ├── test_output/
│   ├── test_scm/                   # @pytest.mark.slow — real git operations
│   └── test_core/
└── .github/
    └── workflows/
        └── ci.yml                  # pytest + ruff + mypy
```

### Design Principles Embedded in Structure

- **`core/events.py`** — observe mode hook infrastructure from day one (Constraint #3). Every subsystem calls `emit()`, MVP default is no-op/log.
- **`core/lifecycle.py`** — task lifecycle enum is the architectural backbone (Constraint #1). Imported by every subsystem.
- **`core/types.py`** — `ArtifactRef` designed with optional extension fields for dependency layers 3-5 (Constraint #5), unused in MVP.
- **`core/constants.py`** — all magic strings centralized. Directory names, exit codes, retry defaults.
- **`agent/sandbox.py`** — zero coupling to invoker. Sandbox is a pure validator function, passed to invoker via dependency inversion.
- **`engine/nodes.py`** — flat file for MVP. Split into `nodes/` directory when exceeding ~300 LOC.
- **`output/`** — unified package for all `.arcwright-ai/` file writes (provenance, run state, summaries).
- **Project scaffold is the first implementation story.**

## Core Architectural Decisions

### Decision 1: LangGraph State Model — Hybrid

**Choice:** Hybrid approach — preflight assembles context payload, downstream nodes consume it, source refs preserved for tracing.

**Detail:** The LangGraph StateGraph carries a Pydantic state object through every node. The `preflight` graph node is the context assembly point — it invokes `context/injector.py` to resolve references, build the context bundle, and store the result in LangGraph state. Downstream nodes (agent dispatch, validation) consume the assembled payload from state without re-resolving.

**Integration note (D1↔D4 binding):** The `preflight` node IS the dispatch-time context assembly described in Decision 4. These are the same architectural moment — not two separate mechanisms. The preflight node calls the context resolver; the result lives in LangGraph state for the graph's lifetime and is checkpointed to the run directory at the state transition boundary.

**Source refs:** Every context payload entry carries a source reference (file path + line range or section anchor) so provenance can trace exactly which document sections informed the agent.

---

### Decision 2: Retry & Halt Strategy

**Choices:**
- **Retry scope:** Validation-only retries — only V3 reflexion failures trigger retry. Agent crashes, SDK errors, and sandbox violations are immediate halts.
- **Budget model:** Dual budget — both invocation count ceiling AND cost ceiling. Whichever is hit first triggers halt.
- **Halt scope (MVP):** Halt the entire epic. No partial continuation, no story skipping. Resume picks up from the halted story.

**Halt output requirements (story AC):** When halt occurs, the CLI must output: which stories completed successfully, which story caused the halt, the halt reason (validation fail count exhausted vs. budget exceeded vs. agent error), current budget consumption, and the exact `arcwright resume <run-id>` command to continue. This is a required acceptance criterion for the halt implementation story.

---

### Decision 3: Provenance Format

**Choice:** One markdown file per story, validation history included, collapsible `<details>` blocks for PR embedding.

**Format:**
```markdown
# Provenance: <story-title>

## Agent Decisions
- [timestamp] Decision description (source: FR-N, architecture §section)

## Validation History
| Attempt | Result | Failures | Duration |
|---------|--------|----------|----------|

## Context Provided
- List of resolved references with source paths

<details>
<summary>Full validation details</summary>
... detailed validation output ...
</details>
```

**File path contract (D3↔D5 binding):** Provenance files live at `.arcwright-ai/runs/<run-id>/stories/<story-slug>/validation.md`. The `scm/pr.py` module reads from this known path to assemble PR bodies. This path is a stable contract between the provenance writer (`output/provenance.py`) and the PR generator.

---

### Decision 4: Context Injection Strategy — Dispatch-Time Assembly (Option D)

**Choice:** Stories stay in standard BMAD format — no workflow changes. Arcwright's `context/` package resolves references at dispatch time.

**Pipeline:**
1. **Story parser** reads the story file, extracts natural references — FR IDs, architecture section anchors, acceptance criteria
2. **Context resolver** maps references to source document sections (PRD → FR definition, architecture.md → relevant decisions/patterns)
3. **Bundle builder** assembles focused context payload: story text + resolved requirement snippets + relevant architecture excerpts + project conventions
4. **Checkpoint** — assembled bundle written to `.arcwright-ai/runs/<run-id>/stories/<story-slug>/context-bundle.md` for provenance

**Reference resolution — strict mode (MVP constraint):**
- FR/NFR IDs → regex match `FR-\d+`, `NFR-\d+` against PRD headings
- Architecture refs → section anchors in architecture.md
- **No fuzzy matching in MVP** — natural language references like "see the dispatch section" are NOT resolved
- Unresolved refs → logged as `context.unresolved` event (Decision 8), agent proceeds with available context
- No LLM fallback — pure pattern matching only

**Answerer strategy:** Regex pattern matching + resolver functions. Unmatched patterns return "no answer available" signal, logged as provenance note. Agent treats unanswered questions as a validation flag (story may be underspecified).

---

### Decision 5: Run Directory Schema

**Structure:**
```
.arcwright-ai/
  runs/
    <run-id>/                    # Format: YYYYMMDD-HHMMSS-<short-uuid>
      run.yaml                   # Run metadata: start time, config snapshot, status, budget consumed
      stories/
        <story-slug>/
          story.md               # Copy of input story (frozen at dispatch time)
          context-bundle.md      # Assembled context payload the agent received
          agent-output.md        # Raw agent response
          validation.md          # Validation results + provenance (see Decision 3)
          files/                 # Files the agent produced (before commit)
      log.jsonl                  # Structured event log (append-only)
```

**Key choices:**
- `run.yaml` — human-readable, editable, consistent with BMAD artifacts
- Story slug as directory name — readable in `ls`, derived from story title
- Run ID format: `YYYYMMDD-HHMMSS-<short-uuid>` (e.g., `20260227-143052-a7f3`) — sortable, human-scannable, collision-safe

**Write policy (LangGraph state vs. run directory):** LangGraph state is the authority during graph execution. Run directory files are written as **checkpoints at state transitions only**: after preflight → write `context-bundle.md`, after agent response → write `agent-output.md`, after validation → write `validation.md`. No subsystem should read run directory files during active graph execution — they may be stale. Run directory is the persistence layer for post-execution inspection, provenance, and resume.

---

### Decision 6: Error Handling Taxonomy

**Exception hierarchy:**
```
ArcwrightError (base)
├── ConfigError              # Invalid/missing config, bad YAML
├── ProjectError             # Not a valid project, missing PRD/stories
├── ContextError             # Failed to resolve references, missing docs
├── AgentError               # Claude Code SDK failures
│   ├── AgentTimeoutError    # Session exceeded time budget
│   └── AgentBudgetError     # Cost/count budget exhausted
├── ValidationError          # Story output failed validation criteria
├── ScmError                 # Git/worktree operation failures
│   ├── WorktreeError        # Worktree create/cleanup failures
│   └── BranchError          # Branch conflicts, checkout failures
└── RunError                 # Run directory I/O, state corruption
```

**Exit code mapping:**

| Code | Meaning | Exception(s) |
|------|---------|---------------|
| 0 | Success | — |
| 1 | Validation failure | `ValidationError` |
| 2 | Agent failure | `AgentError`, `AgentTimeoutError`, `AgentBudgetError` |
| 3 | Configuration / project / context error | `ConfigError`, `ProjectError`, `ContextError` |
| 4 | SCM/Git error | `ScmError`, `WorktreeError`, `BranchError` |
| 5 | Internal/unexpected | `RunError`, unhandled exceptions |

**Note:** `ContextError` maps to exit code 3 (not 5) because context resolution failures are user-fixable project setup issues — missing docs, invalid FR references, misconfigured project structure. Exit 5 is reserved for truly unexpected internal failures.

**Conventions:**
- All exceptions carry `message` (human-readable) and optional `details` dict (structured data for logging)
- CLI layer catches `ArcwrightError` subclasses → maps to exit code + formatted message
- Unhandled exceptions → exit 5, full traceback to `log.jsonl`, sanitized message to stderr
- No exception swallowing — every caught exception is either re-raised or logged
- `AgentBudgetError` triggers run halt + provenance entry recording budget state at halt

---

### Decision 7: Git Operations Strategy

**Approach:** Shell out to `git` CLI — no Python Git library. All calls wrapped through `scm/git.py`.

**Subprocess wrapper:**
```python
async def git(*args: str, cwd: Path | None = None) -> GitResult:
    """Run git command, return GitResult(stdout, stderr, returncode).
    Logs full command + result to structured logger.
    Raises ScmError on non-zero return code."""
```

**Worktree lifecycle:**
1. `git worktree add .arcwright-ai/worktrees/<story-slug> -b arcwright/<story-slug> <base-ref>`
2. Agent executes in worktree directory (sandbox boundary)
3. Validation passes → `git add` + `git commit` (inside worktree) → `git worktree remove`
4. Validation fails → worktree preserved for inspection, logged in provenance
5. Halt/budget-exceeded → all active worktrees preserved, run marked incomplete

**Conventions:**
- Base ref: defaults to current HEAD; configurable via `--base-ref`
- Branch naming: `arcwright/<story-slug>` — namespaced, predictable, greppable
- Commit message: `[arcwright] <story-title>\n\nStory: <story-file-path>\nRun: <run-id>`
- No force operations — no `--force`, no `reset --hard`, no rebase. Existing branch → error out
- No push in MVP — all operations local only (FR-25 is Growth phase)
- All git commands run with `cwd=worktree_path` except worktree add/remove (project root)
- Atomic guarantee: worktree creation failure → no partial state, story skipped and logged

**Cleanup command:** `arcwright clean` with flags:
- Default: removes completed worktrees + merged branches
- `--all`: removes ALL arcwright worktrees and branches (including failed/stale)
- Never automatic — cleanup is always user-initiated

---

### Decision 8: Logging & Observability

**Two distinct output channels:**

| Channel | Format | Audience | Destination |
|---------|--------|----------|-------------|
| User output | Formatted text (Rich/Typer) | Human at terminal | stderr |
| Structured log | JSONL | Machine/debugging | `.arcwright-ai/runs/<run-id>/log.jsonl` |

**User output tiers:**
- Default: story start/complete, validation pass/fail, run summary, errors
- `--verbose`: + context resolution details, git commands, agent session timing
- `--quiet`: errors only + final exit code

**Structured log event envelope:**
```json
{
  "ts": "2026-02-27T14:30:52.123Z",
  "event": "agent.dispatch",
  "story": "setup-project-scaffold",
  "level": "info",
  "data": { ... }
}
```

**Event types:**
- `run.start`, `run.complete`, `run.halt` — run lifecycle
- `story.start`, `story.complete`, `story.skip` — story lifecycle
- `context.resolve`, `context.unresolved` — context assembly
- `agent.dispatch`, `agent.response`, `agent.timeout`, `agent.budget` — agent interactions
- `validation.start`, `validation.pass`, `validation.fail` — validation results
- `git.command`, `git.worktree.create`, `git.worktree.remove`, `git.commit` — SCM ops
- `budget.check` — budget consumption snapshots

**Python logging integration:**
- Standard `logging` module with custom JSONL handler writing to `log.jsonl`
- No root logger modification — only `arcwright.*` logger namespace configured
- Logger hierarchy mirrors packages: `arcwright.engine`, `arcwright.agent`, `arcwright.scm`, etc.
- No external telemetry in MVP — JSONL file is the observability surface

---

### Decision 9: Role-Based Model Registry

**Choice:** Role-based model registry — each pipeline consumption point declares a model role; roles resolve to model specs through a registry with fallback.

**Motivation:** The execution pipeline has two fundamentally different LLM consumers: code generation (`agent_dispatch_node`) and code review (V3 reflexion in `validate_node`). Using the same model for both loses the adversarial benefit of independent review. Different models also have different cost/capability profiles — a fast, cheap model for generation paired with a thorough, expensive model for review optimizes both speed and quality. The architecture must support this split without proliferating per-consumer config fields.

**Design principle:** *Design for N model roles, implement 2.* This mirrors the existing Constraint #5 ("Design for 5 dependency layers, implement 2") — the registry pattern accommodates future roles (planning, summarization, triage, observe-mode analysis) without config model changes.

**Model roles (initial set):**

| Role | Consumer | Default Model | Purpose |
|------|----------|---------------|---------|
| `generate` | `agent_dispatch_node` → `invoke_agent()` | `claude-sonnet-4-20250514` | Code generation — fast, cost-effective |
| `review` | `validate_node` → V3 reflexion → `invoke_agent()` | `claude-opus-4-5` | Code review — thorough, adversarial |

**Future roles (designed for, not implemented):**

| Role | Likely Consumer | Rationale |
|------|----------------|-----------|
| `plan` | Epic-level planning, story decomposition | Growth-phase orchestrator intelligence |
| `summarize` | Run summary, PR body generation | Cheap model for structured text output |
| `triage` | Pre-validation quick-check | Fast gate before expensive V3 reflexion |
| `observe` | Observe mode analysis (PRD deferred) | Already architecturally planned |

**Configuration model:**

```python
class ModelRole(StrEnum):
    """Well-known model roles in the execution pipeline."""
    GENERATE = "generate"
    REVIEW = "review"

class ModelSpec(ArcwrightModel):
    """A model specification bound to a role."""
    model_config = ConfigDict(frozen=True, extra="ignore")
    version: str
    pricing: ModelPricing = Field(default_factory=ModelPricing)

class ModelRegistry(ArcwrightModel):
    """Role-based model selection registry.
    
    Each role maps to a ModelSpec. If a role is not explicitly configured,
    it falls back to the 'generate' role (which must always be present).
    """
    model_config = ConfigDict(frozen=True, extra="ignore")
    roles: dict[str, ModelSpec]
    
    def get(self, role: ModelRole | str) -> ModelSpec:
        """Resolve model spec for a role, with fallback to 'generate'."""
        key = role.value if isinstance(role, ModelRole) else role
        if key in self.roles:
            return self.roles[key]
        if ModelRole.GENERATE.value in self.roles:
            return self.roles[ModelRole.GENERATE.value]
        raise ConfigError(f"No model configured for role '{key}' and no 'generate' fallback")
```

**RunConfig integration:**

```python
class RunConfig(ArcwrightModel):
    api: ApiConfig
    models: ModelRegistry      # replaces model: ModelConfig
    limits: LimitsConfig
    methodology: MethodologyConfig
    scm: ScmConfig
    reproducibility: ReproducibilityConfig
```

**Config YAML format:**

```yaml
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
```

**Minimal config (backward-compatible spirit):**

```yaml
models:
  generate:
    version: claude-sonnet-4-20250514
# review falls back to generate automatically
```

**Backward compatibility migration:**
1. If `models` key exists in config → use new registry format
2. If `model` (singular) key exists → migrate to `models.generate`, emit deprecation warning
3. If neither → use defaults (`generate` role with `claude-sonnet-4-20250514`)

**Environment variable pattern:**

Role-templated env vars replace per-field constants:

| Env Var | Effect |
|---------|--------|
| `ARCWRIGHT_AI_MODEL_GENERATE_VERSION` | Override generate role model version |
| `ARCWRIGHT_AI_MODEL_REVIEW_VERSION` | Override review role model version |
| `ARCWRIGHT_AI_MODEL_GENERATE_PRICING_INPUT_RATE` | Override generate role input pricing |
| `ARCWRIGHT_AI_MODEL_REVIEW_PRICING_INPUT_RATE` | Override review role input pricing |

The env var override logic scans for `ARCWRIGHT_AI_MODEL_{ROLE}_*` patterns and merges into the corresponding registry entry. One scanning pattern covers all roles — no per-role constant declarations needed. The existing `ARCWRIGHT_AI_MODEL_VERSION` env var is treated as an alias for `ARCWRIGHT_AI_MODEL_GENERATE_VERSION` with a deprecation warning.

**Node wiring:**

```python
# agent_dispatch_node
spec = state.config.models.get(ModelRole.GENERATE)
result = await invoke_agent(prompt, model=spec.version, ...)
cost = calculate_invocation_cost(tokens_in, tokens_out, spec.pricing)

# validate_node (V3 reflexion)
spec = state.config.models.get(ModelRole.REVIEW)
result = await run_validation_pipeline(..., model=spec.version, ...)
cost = calculate_invocation_cost(tokens_in, tokens_out, spec.pricing)
```

**Cost tracking implications:**
- Each node resolves its own `ModelSpec` and applies the correct pricing
- Run summaries can report cost breakdown by role: "generation cost: $X, review cost: $Y"
- `BudgetState` aggregation is unchanged — per-story and per-run totals still accumulate, but source pricing varies by role
- Budget ceiling enforcement still operates on aggregate cost — no per-role ceilings in this iteration

**Integration note (D9↔D2 binding):** Budget check node evaluates aggregate cost regardless of which model role incurred the cost. A story that fails V3 review and retries will accumulate both generation costs (from `generate` role) and review costs (from `review` role) toward the same dual ceiling.

**Integration note (D9↔D8 binding):** Structured log events for `agent.dispatch` and `validation.pipeline.start` include the resolved model role and version:
```json
{"event": "agent.dispatch", "data": {"model_role": "generate", "model_version": "claude-sonnet-4-20250514", ...}}
{"event": "validation.v3.start", "data": {"model_role": "review", "model_version": "claude-opus-4-5", ...}}
```

---

### Party Mode Enhancements Applied (Round 3)

1. **D1↔D4 binding documented** — preflight graph node explicitly identified as the context assembly moment
2. **Write policy added to D5** — LangGraph state is authority during execution; run directory files are transition checkpoints only
3. **`arcwright clean --all` added to D7** — covers stale branches from failed runs
4. **Strict-mode regex stated as explicit constraint in D4** — no fuzzy matching in MVP
5. **`ContextError` moved to exit code 3 in D6** — user-fixable, not internal
6. **Provenance file path contract documented in D3** — explicit coupling between D3 format and D5 directory
7. **Halt output requirements noted in D2** — story AC for halt implementation
## Implementation Patterns & Consistency Rules

### Package Dependency DAG (Mandatory)

```
cli → engine → {validation, agent, context, output, scm} → core
```

- **`core`** depends on nothing (stdlib + Pydantic only)
- **`scm`, `context`, `output`, `validation`, `agent`** depend only on `core`
- **`engine`** depends on all domain packages + `core`
- **`cli`** depends on `engine` + `core`
- **Cross-domain imports are forbidden** — `scm` must never import from `agent`, `context` must never import from `output`, etc.
- If two domain packages need to communicate, the `engine` mediates via graph nodes
- Violation of this DAG is a blocking code review finding

### Python Code Style Patterns

**Naming conventions:**
- `snake_case` for all functions, methods, variables, modules
- `PascalCase` for classes and Pydantic models only
- `UPPER_SNAKE_CASE` for constants (in `core/constants.py` only)
- Private members: single underscore prefix `_internal_method`
- No double-underscore name mangling unless absolutely required

**Module `__all__` convention:**
- Every `__init__.py` must explicitly define `__all__` listing the public API
- No logic in `__init__.py` files — re-exports only
- Agents import from the package level (`from arcwright_ai.core import TaskState`), not deep module paths

**Import ordering (enforced by Ruff):**
```python
# 1. stdlib
import asyncio
from pathlib import Path

# 2. third-party
from pydantic import BaseModel
from langgraph.graph import StateGraph

# 3. local
from arcwright_ai.core.types import StoryId
from arcwright_ai.core.lifecycle import TaskState
```

**String formatting:** f-strings everywhere. No `.format()`, no `%` formatting.

**Type hints:** Required on all public function signatures. `from __future__ import annotations` at top of every module for PEP 604 union syntax (`X | None` not `Optional[X]`).

**Docstrings:** Google style, required on all public classes and functions:
```python
def resolve_references(story_path: Path, project_root: Path) -> ContextBundle:
    """Resolve FR/NFR references from a story file into a context bundle.

    Args:
        story_path: Path to the BMAD story markdown file.
        project_root: Root directory containing _spec/ and docs/.

    Returns:
        Assembled context bundle with resolved references.

    Raises:
        ContextError: If story file is missing or unreadable.
    """
```

### Async Patterns

**Rule: All I/O is async.** No synchronous file reads, subprocess calls, or network operations in the core packages.

**Async file I/O:** Use `asyncio.to_thread()` wrapping `pathlib.Path` operations (not `aiofiles` — one fewer dependency):
```python
content = await asyncio.to_thread(path.read_text, encoding="utf-8")
```

**Anti-pattern — sync I/O in async functions (explicitly forbidden):**
```python
# WRONG — blocks the event loop
async def load_story(path: Path) -> str:
    return path.read_text()  # synchronous!

# RIGHT
async def load_story(path: Path) -> str:
    return await asyncio.to_thread(path.read_text, encoding="utf-8")
```

**Subprocess (git):** `asyncio.create_subprocess_exec` — never `subprocess.run`:
```python
proc = await asyncio.create_subprocess_exec(
    "git", *args,
    cwd=str(cwd),
    stdout=asyncio.subprocess.PIPE,
    stderr=asyncio.subprocess.PIPE,
)
stdout, stderr = await proc.communicate()
```

**CLI entry points:** `asyncio.run()` wraps the async core:
```python
@app.command()
def dispatch(epic: str) -> None:
    """Dispatch an epic for execution."""
    asyncio.run(_dispatch_async(epic))
```

**No `async with` for simple operations.** Context managers only when managing lifecycle (e.g., agent sessions with cleanup).

**Graph node return type pattern:** All LangGraph graph nodes return the full `StoryState` object (not partial dicts). Use Pydantic's `.model_copy(update={...})` for immutable-style updates within the mutable state model:
```python
async def preflight_node(state: StoryState) -> StoryState:
    bundle = await resolve_references(state.story_path, state.project_root)
    return state.model_copy(update={"context_bundle": bundle, "status": TaskState.RUNNING})
```

### Pydantic Model Patterns

**Base model configuration:**
```python
from pydantic import BaseModel, ConfigDict

class ArcwrightModel(BaseModel):
    model_config = ConfigDict(
        frozen=True,          # Immutable by default
        extra="forbid",       # No unknown fields
        str_strip_whitespace=True,
    )
```

**Mutable state models** (LangGraph state) use `frozen=False` explicitly:
```python
class StoryState(BaseModel):
    model_config = ConfigDict(frozen=False, extra="forbid")
```

**Enum pattern:** String enums for all categorical fields:
```python
from enum import StrEnum

class TaskState(StrEnum):
    QUEUED = "queued"
    PREFLIGHT = "preflight"
    RUNNING = "running"
    VALIDATING = "validating"
    SUCCESS = "success"
    RETRY = "retry"
    ESCALATED = "escalated"
```

**Validation:** Pydantic validators for domain rules, not standalone validation functions:
```python
from pydantic import field_validator

class RunConfig(ArcwrightModel):
    max_retries: int = 3

    @field_validator("max_retries")
    @classmethod
    def validate_max_retries(cls, v: int) -> int:
        if v < 0:
            raise ValueError("max_retries must be non-negative")
        return v
```

### Error Handling Patterns

**Raising:** Always use the exception hierarchy from Decision 6. Never raise bare `Exception` or `ValueError` from application code:
```python
# Good
raise ConfigError("Missing required field 'model'", details={"file": str(config_path)})

# Bad
raise ValueError("Missing required field 'model'")
```

**Catching:** Catch specific exceptions, never bare `except:`:
```python
try:
    result = await git("worktree", "add", worktree_path, "-b", branch_name)
except ScmError as e:
    logger.error("worktree_create_failed", extra={"data": {"error": str(e), "story": story_slug}})
    raise  # Let the engine handle halt logic
```

**Logging vs re-raising:** Log at the point of maximum context, re-raise for flow control. Don't log AND handle — pick one level to own it:
```python
# In scm/worktree.py — log details, re-raise
except ScmError as e:
    logger.error("worktree_failed", extra={"data": {"branch": branch_name, "stderr": e.details.get("stderr")}})
    raise

# In engine/nodes.py — catch, don't re-log, handle
except ScmError:
    state.status = TaskState.ESCALATED
    return state
```

### File & Path Patterns

**Always `pathlib.Path`** — never string concatenation for paths:
```python
# Good
run_dir = project_root / ".arcwright-ai" / "runs" / run_id
# Bad
run_dir = os.path.join(str(project_root), ".arcwright-ai", "runs", run_id)
```

**Encoding:** Always explicit `encoding="utf-8"` on all file reads/writes.

**Directory creation:** `path.mkdir(parents=True, exist_ok=True)` — always idempotent.

**YAML I/O:** PyYAML (`yaml.safe_load` / `yaml.safe_dump`) — simplest option, no round-trip formatting needed for MVP. Single function pair in `core/` for all YAML reads/writes:
```python
# core/io.py
import yaml

def load_yaml(path: Path) -> dict[str, Any]:
    """Load YAML file. Raises ConfigError on parse failure."""
    ...

def save_yaml(path: Path, data: dict[str, Any]) -> None:
    """Write YAML file with consistent formatting."""
    ...
```

**Markdown I/O:** Read as text, write as text. No markdown parsing library in MVP — regex for reference extraction.

### Structured Logging Patterns

Agents must emit structured log events using the JSONL format from Decision 8, not human-readable strings:

```python
import logging

logger = logging.getLogger(__name__)

# Structured event — data dict becomes the JSONL 'data' field
logger.info("context.resolve", extra={"data": {"story": story_slug, "refs_found": 5, "refs_unresolved": 1}})

# Error with details
logger.error("git.command", extra={"data": {"args": ["worktree", "add"], "stderr": stderr, "returncode": rc}})
```

**Anti-pattern (forbidden):**
```python
# WRONG — human-readable but not machine-parseable
logger.info(f"Resolved {n} references for story {story_slug}")

# RIGHT — structured event
logger.info("context.resolve", extra={"data": {"story": story_slug, "refs_found": n}})
```

### Testing Patterns

**Test naming:** `test_<function_name>_<scenario>`:
```python
def test_resolve_references_returns_empty_bundle_for_no_refs(): ...
def test_resolve_references_raises_context_error_for_missing_prd(): ...
async def test_git_worktree_add_creates_branch(): ...
```

**Test isolation:** Tests must not depend on execution order. Each test creates its own state via fixtures. No shared mutable state between tests. No test should read from or write to the actual filesystem outside `tmp_path`.

**Assertion style:** Plain `assert` + `pytest.raises` only. No assertion libraries:
```python
# Good
assert result.status == TaskState.SUCCESS
assert len(result.stories) == 3

with pytest.raises(ConfigError, match="Missing required field"):
    load_config(bad_path)

# Bad — no assertion libraries
assertThat(result.status).is_equal_to(TaskState.SUCCESS)
```

**Fixture usage:** Shared fixtures in `conftest.py`, scenario-specific fixtures in test files:
```python
# tests/conftest.py
@pytest.fixture
def tmp_project(tmp_path: Path) -> Path:
    """Scaffold minimal .arcwright-ai/ + _spec/ for integration tests."""
    ...
```

**Async tests:** Use `pytest.mark.asyncio` decorator:
```python
@pytest.mark.asyncio
async def test_dispatch_story_invokes_agent():
    ...
```

**Mock SDK pattern:** Always use the `mock_sdk` fixture from `tests/fixtures/mock_sdk.py` — never create ad-hoc mocks:
```python
async def test_agent_dispatch(mock_sdk):
    mock_sdk.configure(response="# Implementation\n...")
    result = await invoke_agent(story_context, sdk=mock_sdk)
    assert result.output == "# Implementation\n..."
```

**SCM tests:** Marked `@pytest.mark.slow`, use real git operations with `tmp_path`:
```python
@pytest.mark.slow
async def test_worktree_lifecycle(tmp_path):
    # Actually creates git repo, worktree, commits
    ...
```

### Enforcement Guidelines

**All AI agents (story implementations) MUST:**
1. Run `ruff check` and `ruff format` — zero violations before commit
2. Run `mypy --strict` on changed files — zero errors
3. Follow the import ordering, naming conventions, and `__all__` exports above
4. Use the exception hierarchy — never bare exceptions
5. Use `pathlib.Path` — never `os.path` string operations
6. Write tests matching the naming, isolation, and fixture patterns
7. Use `asyncio.to_thread()` for file I/O — never sync reads in async functions
8. Respect the package dependency DAG — no cross-domain imports
9. Return full `StoryState` from graph nodes — no partial dicts
10. Emit structured log events — no unstructured string messages

**Anti-patterns (explicitly forbidden):**
- `import *` — never
- Mutable default arguments — never
- `print()` for output — always use logger or Typer echo
- `os.system()` or `subprocess.run()` — always async subprocess
- Catching `Exception` without re-raising — always catch specific types
- Hardcoded paths — always derive from `project_root` or constants
- Cross-domain package imports — always mediate through `engine`

### Party Mode Enhancements Applied (Round 4)

1. **`__all__` convention added** — every `__init__.py` explicitly defines public API, no logic in init files
2. **Sync I/O anti-pattern example added** — explicit wrong/right for `asyncio.to_thread` in async functions
3. **Graph node return type pattern defined** — full `StoryState` + `model_copy(update={...})`, no partial dicts
4. **Package dependency DAG stated as mandatory rule** — cross-domain imports forbidden, engine mediates
5. **PyYAML named as YAML library** — `yaml.safe_load` / `yaml.safe_dump`, single wrapper pair
6. **Test isolation rule added** — no shared state, `tmp_path` only, no execution order dependence
7. **Assertion style standardized** — plain `assert` + `pytest.raises`, no assertion libraries
8. **Structured logging emit pattern added** — concrete examples of correct event emission vs. forbidden string logging

## Project Structure & Boundaries

### Requirements → Structure Mapping

#### Core Execution Chain (FR1→3→8→9→4→5)

| Requirement | File(s) | Role |
|-------------|---------|------|
| FR1 (dispatch epic) | `cli/dispatch.py` → `engine/graph.py` | CLI parses args, engine builds and runs the StateGraph |
| FR3 (sequential execution) | `engine/graph.py`, `engine/nodes.py` | Graph edges enforce story ordering; nodes execute one at a time |
| FR8 (V3 evaluation) | `validation/v3_reflexion.py`, `validation/pipeline.py` | Pipeline routes to V3; reflexion validates agent output |
| FR9 (retry on failure) | `engine/nodes.py`, `engine/state.py` | Validation node checks retry count in state, re-dispatches or escalates |
| FR4 (halt on max retries) | `engine/nodes.py`, `core/constants.py` | Node reads `MAX_RETRIES` from constants, transitions to ESCALATED |
| FR5 (resume from halt) | `cli/dispatch.py`, `output/run_manager.py`, `engine/graph.py` | CLI reads run state, engine rebuilds graph from last incomplete story |

#### Provenance Chain (FR12→13→14→15)

| Requirement | File(s) | Role |
|-------------|---------|------|
| FR12 (log decisions) | `output/provenance.py` | Appends decision entries during agent execution |
| FR13 (structured entries) | `output/provenance.py`, `core/types.py` | `ProvenanceEntry` Pydantic model defines structure |
| FR14 (write to runs/) | `output/run_manager.py` | Writes `validation.md` at story completion |
| FR15 (attach to PRs) | `scm/pr.py` | Reads `validation.md` from run dir, builds PR body with `<details>` |

#### Context Chain (FR16→17→18→19)

| Requirement | File(s) | Role |
|-------------|---------|------|
| FR16 (read BMAD artifacts) | `context/injector.py` | Reads `_spec/` markdown files, parses headings/anchors |
| FR17 (answerer rule lookup) | `context/answerer.py` | Regex-based pattern matcher against indexed document sections |
| FR18 (resolve dependencies) | `context/injector.py` | Maps FR-N references to PRD sections, builds bundle |
| FR19 (invoke SDK) | `agent/invoker.py`, `agent/prompt.py` | Prompt builder assembles context bundle + story into SDK input |

#### Safety Chain (FR6→20→21→36)

| Requirement | File(s) | Role |
|-------------|---------|------|
| FR6 (worktree isolation) | `scm/worktree.py` | Creates/removes worktrees with atomic guarantees |
| FR20 (path traversal prevention) | `agent/sandbox.py` | Validates all agent file operations stay within worktree |
| FR21 (temp file containment) | `agent/sandbox.py` | Ensures temp files written to `.arcwright-ai/` not project root |
| FR36 (worktree lifecycle) | `scm/worktree.py`, `engine/nodes.py` | Engine node triggers worktree create/remove at state transitions |

#### Remaining FR Mapping (File-Level Precision)

| FR | Description | Primary File | Notes |
|----|-------------|-------------|-------|
| FR22 | Agent session config | `agent/invoker.py` | Session timeout, model resolved via `ModelRegistry.get(GENERATE)` from `RunConfig` |
| FR23 | Token tracking | `core/types.py` + `engine/nodes.py` | `BudgetState` fields + budget_check node accumulates |
| FR24 | Cost ceiling enforcement | `engine/nodes.py` | budget_check conditional edge before agent dispatch |
| FR25 | Push to remote | `scm/git.py` | **NOT IN MVP** — file location reserved for Growth phase |
| FR26 | Init command | `cli/status.py` | `arcwright init` bootstraps `.arcwright-ai/` |
| FR27 | Config loading | `core/config.py` | Two-tier loader (file + env) with Pydantic validation |
| FR28 | Validate-setup | `cli/status.py` + `core/config.py` | Validates project structure + config completeness |
| FR29 | Config schema | `core/config.py` | Pydantic model IS the schema — self-documenting |
| FR30 | Env var override | `core/config.py` | Two-tier loader reads env vars with `ARCWRIGHT_` prefix |
| FR31 | Run status | `output/run_manager.py` | Reads `run.yaml` status field |
| FR32 | Run listing | `output/run_manager.py` | Scans `.arcwright-ai/runs/` directory |
| FR33 | Run summary | `output/summary.py` | Generates human-readable run report |
| FR34 | Branch creation | `scm/branch.py` | `arcwright/<story-slug>` naming convention |
| FR35 | Commit story | `scm/worktree.py` | `git add` + `git commit` inside worktree |

### Architectural Boundaries

**Boundary 1: CLI ↔ Engine**
- CLI calls a single async function per command (e.g., `dispatch_epic(epic_path, config)`)
- CLI never accesses engine internals (no StateGraph, no node functions)
- All user output (Rich/Typer formatting) stays in `cli/` — engine returns data objects

**Boundary 2: Engine ↔ Domain Packages**
- Engine imports domain packages; domain packages never import engine
- Engine passes configuration/context as function arguments — no global state
- Domain functions are pure: `(input) → output` or `(input) → output + side_effect`

**Boundary 3: Agent Invoker ↔ Sandbox**
- Invoker receives sandbox as a validator function via dependency injection
- Sandbox has zero knowledge of Claude Code SDK — it validates `(path, operation) → allow/deny`
- Invoker calls sandbox before applying any file operation from agent output

**Boundary 4: Application ↔ File System**
- All `.arcwright-ai/` writes go through `output/run_manager.py` — no direct file writes from other packages
- All `_spec/` reads go through `context/injector.py` — no direct reads from engine
- All git operations go through `scm/git.py` — no subprocess calls from other packages
- `core/io.py` provides YAML/text I/O primitives used by the above
- **`core/io.py` scope:** Primitive file I/O wrappers ONLY — YAML pair + async text pair. JSONL formatting belongs in the logging handler. Markdown regex extraction belongs in `context/injector.py`. No domain logic in `core/io.py`.

### Data Flow

```
[CLI] → dispatch(epic_path, config)
  │
  ▼
[Engine: graph.py] builds StateGraph
  │
  ├─── For each story ──────────────────────────────────────┐
  │                                                          │
  ▼                                                          │
[Node: preflight]                                            │
  ├── context/injector.py → resolve refs → ContextBundle     │
  ├── scm/worktree.py → create worktree                     │
  ├── output/run_manager.py → write context-bundle.md        │
  └── state.status = RUNNING                                 │
  │                                                          │
  ▼                                                          │
[Node: budget_check]                                         │
  ├── Reads BudgetState from state (count + cost)            │
  ├── If budget OK → route to agent_dispatch                 │
  └── If budget exceeded → route to ESCALATED (halt)         │
  │                                                          │
  ▼                                                          │
[Node: agent_dispatch]                                       │
  ├── agent/prompt.py → build prompt from ContextBundle      │
  ├── models.get(GENERATE) → resolve model spec              │
  ├── agent/invoker.py → SDK async generator                 │
  ├── agent/sandbox.py → validate each file operation        │
  ├── output/run_manager.py → write agent-output.md          │
  ├── Update BudgetState (tokens consumed, cost via spec)    │
  └── state.status = VALIDATING                              │
  │                                                          │
  ▼                                                          │
[Node: validate]                                             │
  ├── models.get(REVIEW) → resolve model spec               │
  ├── validation/pipeline.py → route to V3/V6               │
  ├── output/provenance.py → record validation results       │
  ├── output/run_manager.py → write validation.md            │
  ├── Update BudgetState (validation cost via review spec)   │
  └── state.status = SUCCESS | RETRY | ESCALATED             │
  │                                                          │
  ├── if RETRY → back to budget_check (within budget)        │
  ├── if ESCALATED → halt epic, preserve worktree            │
  └── if SUCCESS ─────────────────────────────────────┐      │
                                                      │      │
  ▼                                                   │      │
[Node: commit]                                        │      │
  ├── scm/worktree.py → git add + commit              │      │
  ├── scm/worktree.py → remove worktree               │      │
  └── state.status = SUCCESS                          │      │
  │                                                   │      │
  └──────────────────── next story ───────────────────┘      │
  │                                                          │
  ▼                                                          │
[Node: run_complete]                                         │
  ├── output/summary.py → generate run summary               │
  └── return final ProjectState to CLI                       │
```

### NFR → Structure Mapping

| NFR | Enforced By | Mechanism |
|-----|-------------|-----------|
| NFR1 (zero silent failures) | `core/lifecycle.py`, `engine/nodes.py` | Every state transition is explicit; no default/fallthrough paths |
| NFR2 (progress recovery) | `output/run_manager.py` | `run.yaml` tracks last completed story; resume reads this |
| NFR4 (worktree isolation) | `scm/worktree.py`, `agent/sandbox.py` | Worktree per story + path validation on every file op |
| NFR5 (config validation) | `core/config.py` | Pydantic validates all config at startup, never mid-run |
| NFR7 (path safety) | `agent/sandbox.py` | Application-level enforcement, independent of SDK |
| NFR8 (state integrity) | `output/run_manager.py` | Atomic writes, idempotent operations |
| NFR9-12 (cost/performance) | `core/types.py` (BudgetState), `engine/nodes.py` | Budget checked before each agent invocation via budget_check node |
| NFR16-18 (observability) | `core/events.py`, structured logging | Event hooks + JSONL per Decision 8 |
| NFR19 (idempotency) | All modules | `exist_ok=True`, resume safety, re-runnable operations |

### Complete Project Tree

```
arcwright-ai/
├── pyproject.toml               # PEP 621 metadata, deps, [dev] extras, ruff/mypy config
├── README.md
├── LICENSE
├── .gitignore
├── .pre-commit-config.yaml      # ruff + mypy hooks
├── src/
│   └── arcwright_ai/
│       ├── __init__.py          # __all__ = ["__version__"]
│       ├── py.typed             # PEP 561 marker (zero-byte)
│       ├── cli/
│       │   ├── __init__.py      # __all__ = ["app"]
│       │   ├── app.py           # Typer app, command registration
│       │   ├── dispatch.py      # arcwright dispatch, arcwright resume
│       │   └── status.py        # arcwright init, status, validate-setup, clean
│       ├── engine/
│       │   ├── __init__.py      # __all__ = ["build_graph", "run_epic"]
│       │   ├── graph.py         # StateGraph construction, edge routing
│       │   ├── state.py         # ProjectState, StoryState, BudgetState Pydantic models
│       │   └── nodes.py         # Node functions:
│       │                        #   preflight(StoryState) → StoryState
│       │                        #   budget_check(StoryState) → StoryState
│       │                        #   agent_dispatch(StoryState) → StoryState
│       │                        #   validate(StoryState) → StoryState
│       │                        #   commit(StoryState) → StoryState
│       │                        #   run_complete(ProjectState) → ProjectState
│       ├── validation/
│       │   ├── __init__.py      # __all__ = ["validate_story_output"]
│       │   ├── v3_reflexion.py  # V3 reflexion: LLM-as-judge on acceptance criteria
│       │   ├── v6_invariant.py  # V6 invariant: deterministic rule checks
│       │   └── pipeline.py      # Routes artifacts to V3/V6 based on type
│       ├── agent/
│       │   ├── __init__.py      # __all__ = ["invoke_agent"]
│       │   ├── invoker.py       # Claude Code SDK async integration
│       │   ├── sandbox.py       # Path validator: (path, op) → allow/deny
│       │   └── prompt.py        # ContextBundle → SDK prompt string
│       ├── context/
│       │   ├── __init__.py      # __all__ = ["resolve_context", "lookup_answer"]
│       │   ├── injector.py      # Story parser + reference resolver + bundle builder
│       │   └── answerer.py      # Regex pattern matcher for agent questions
│       ├── output/
│       │   ├── __init__.py      # __all__ = ["RunManager", "write_provenance", "generate_summary"]
│       │   ├── provenance.py    # ProvenanceEntry model, markdown generator
│       │   ├── run_manager.py   # .arcwright-ai/runs/ CRUD, run.yaml, status tracking
│       │   └── summary.py       # Run summary + halt report generation
│       ├── scm/
│       │   ├── __init__.py      # __all__ = ["create_worktree", "remove_worktree", "commit_story"]
│       │   ├── git.py           # async git() subprocess wrapper
│       │   ├── worktree.py      # Worktree lifecycle (create/remove/cleanup)
│       │   ├── branch.py        # Branch naming, existence checks
│       │   └── pr.py            # PR body generation with provenance <details>
│       └── core/
│           ├── __init__.py      # __all__ = ["TaskState", "ArcwrightModel", "ArcwrightError", ...]
│           ├── types.py         # StoryId, EpicId, RunId, ArtifactRef, ContextBundle,
│           │                    #   BudgetState, ProvenanceEntry, ModelRole (StrEnum)
│           ├── lifecycle.py     # TaskState enum + transition validation
│           ├── config.py        # RunConfig, ModelRegistry, ModelSpec, ModelRole +
│           │                    #   two-tier loader (file + env) with role-templated env vars
│           ├── constants.py     # DIR_ARCWRIGHT, DIR_SPEC, EXIT_*, MAX_RETRIES, BRANCH_PREFIX
│           ├── exceptions.py    # Full hierarchy: ArcwrightError → Config/Project/Context/Agent/...
│           ├── events.py        # EventEmitter protocol, NoOpEmitter default, event types
│           └── io.py            # PRIMITIVES ONLY: load_yaml(), save_yaml(),
│                                #   read_text_async(), write_text_async()
│                                #   No JSONL, no markdown parsing, no domain logic
├── tests/
│   ├── conftest.py              # tmp_project, mock_sdk, shared fixtures
│   ├── fixtures/
│   │   ├── mock_sdk.py          # MockSDKClient: configurable async generator
│   │   └── projects/
│   │       ├── README.md        # Documents what each fixture contains and exercises
│   │       ├── valid_project/   # Complete _spec/ + .arcwright-ai/ — passes V6
│   │       │   └── README.md    # Stories included, FRs exercised, expected outcomes
│   │       ├── invalid_project/ # Missing/malformed artifacts — fails V6
│   │       │   └── README.md    # Specific failure modes and expected error types
│   │       └── partial_project/ # Halted mid-run — for resume testing
│   │           └── README.md    # Run state, halt point, expected resume behavior
│   ├── integration/             # Cross-package flow tests
│   │   ├── test_dispatch_flow.py    # Full story dispatch with mock SDK
│   │   ├── test_resume_flow.py      # Halt + resume cycle
│   │   └── test_budget_halt_flow.py # Budget exceeded mid-epic
│   ├── test_cli/
│   │   ├── test_dispatch.py
│   │   └── test_status.py
│   ├── test_engine/
│   │   ├── test_graph.py
│   │   ├── test_state.py
│   │   └── test_nodes.py
│   ├── test_validation/
│   │   ├── test_v3_reflexion.py
│   │   ├── test_v6_invariant.py
│   │   └── test_pipeline.py
│   ├── test_agent/
│   │   ├── test_invoker.py
│   │   ├── test_sandbox.py
│   │   └── test_prompt.py
│   ├── test_context/
│   │   ├── test_injector.py
│   │   └── test_answerer.py
│   ├── test_output/
│   │   ├── test_provenance.py
│   │   ├── test_run_manager.py
│   │   └── test_summary.py
│   ├── test_scm/               # @pytest.mark.slow — real git operations
│   │   ├── test_git.py
│   │   ├── test_worktree.py
│   │   ├── test_branch.py
│   │   └── test_pr.py
│   └── test_core/
│       ├── test_types.py
│       ├── test_lifecycle.py
│       ├── test_config.py
│       ├── test_exceptions.py
│       └── test_io.py
└── .github/
    └── workflows/
        └── ci.yml              # pytest + ruff check + ruff format --check + mypy --strict
```

### Party Mode Enhancements Applied (Round 5)

1. **`budget_check` node added to data flow** — explicit conditional edge before agent dispatch; retries route through budget_check
2. **`core/io.py` scope note added** — primitives only, no JSONL/markdown/domain logic
3. **Node function signatures documented in tree** — canonical `(StoryState) → StoryState` per node, `run_complete` operates on `ProjectState`
4. **`py.typed` marker file added** — PEP 561 for mypy strict compliance
5. **README.md added to each fixture project** — documents stories, FRs exercised, expected outcomes
6. **`tests/integration/` directory added** — cross-package flow tests for dispatch, resume, budget halt
7. **Remaining FR mapping expanded to file-level precision** — FR22-35 each mapped to primary file with notes

## Architecture Validation Results

### Coherence Validation ✅

**Decision Compatibility:**
All 9 decisions validated pairwise — no contradictions found. Key bindings explicitly documented through Party Mode reviews:
- D1↔D4: preflight node = context assembly (bound in Round 3)
- D3↔D5: provenance file path contract (bound in Round 3)
- D2↔D8: halt output requirements as story AC (bound in Round 3)
- D5 write policy: LangGraph state is authority, run dir files are transition checkpoints (Round 3)
- D7↔D2: failed worktrees preserved on halt, `arcwright clean --all` for cleanup (Round 3)
- D9↔D2: budget check aggregates across model roles — no per-role ceilings (Amendment 2026-03-11)
- D9↔D8: structured log events include model_role and model_version (Amendment 2026-03-11)

**Pattern Consistency:**
All implementation patterns align with architectural decisions:
- Error handling patterns use D6 exception hierarchy consistently
- File I/O patterns use `pathlib.Path` + `asyncio.to_thread()` aligned with D7 async subprocess
- Naming patterns (`snake_case`, `arcwright/<slug>`) consistent across code, branches, and run IDs
- State transitions use `TaskState` enum from D1 throughout data flow and node signatures
- Logging patterns emit structured JSONL events per D8 specification

**Structure Alignment:**
Project structure directly implements the package dependency DAG. 8 packages map to 10 subsystems. All boundaries enforce the DAG via import rules.

### Requirements Coverage Validation ✅

**Functional Requirements — all 36 FRs mapped to specific files:**

| FR Range | Status | Coverage |
|----------|--------|----------|
| FR1-5 (Orchestration) | COMPLETE | Core Execution Chain → engine/ |
| FR6-7 (Isolation, SCM) | COMPLETE | Safety Chain → scm/worktree.py |
| FR8-11 (Validation) | COMPLETE | validation/ package |
| FR12-15 (Provenance) | COMPLETE | Provenance Chain → output/, scm/pr.py |
| FR16-18 (Context) | COMPLETE | Context Chain → context/ |
| FR19-22 (Agent) | COMPLETE | agent/ package |
| FR23-25 (Cost) | COMPLETE | core/types.py + engine/nodes.py (FR25 deferred to Growth) |
| FR26-30 (Config) | COMPLETE | cli/status.py + core/config.py |
| FR31-33 (Visibility) | COMPLETE | output/run_manager.py + output/summary.py |
| FR34-36 (SCM) | COMPLETE | scm/ package |

**Non-Functional Requirements — all 20 NFRs mapped to enforcement mechanisms:**

| NFR Range | Status | Enforcement |
|-----------|--------|-------------|
| NFR1-5 (Reliability) | COMPLETE | Lifecycle enum, run_manager, exception hierarchy, config validation |
| NFR6-8 (Security) | COMPLETE | Sandbox, path validation, atomic state writes |
| NFR9-12 (Cost/Perf) | COMPLETE | BudgetState, budget_check node, dual ceiling |
| NFR13-15 (Integration) | COMPLETE | BMAD artifact reading, Git CLI, file-based state |
| NFR16-18 (Observability) | COMPLETE | events.py hooks, JSONL logging, structured events |
| NFR19-20 (Quality) | COMPLETE | Idempotency patterns, ruff+mypy enforcement |

### Implementation Readiness Validation ✅

| Dimension | Status | Evidence |
|-----------|--------|----------|
| Technology versions specified | PASS | Python 3.11+, Git 2.25+, LangGraph, Claude Code SDK, Typer, Pydantic, PyYAML |
| Package structure complete | PASS | 8 packages, 27 source files, all with `__all__` exports, `py.typed` marker |
| Test structure complete | PASS | Unit (per-package), integration (3 flow tests), fixtures (3 projects + READMEs), slow markers |
| Dependency DAG documented | PASS | Mandatory rule: core → domain → engine → cli, cross-domain forbidden |
| Error handling complete | PASS | 6-class hierarchy, exit codes 0-5, catch/re-raise conventions |
| Patterns with examples | PASS | 6 pattern categories with code examples + anti-patterns |
| Data flow documented | PASS | Full graph node flow with budget_check, retry loop, checkpoint writes |
| Boundary contracts explicit | PASS | 4 boundaries with specific interface rules |

### Gap Analysis

**Critical Gaps:** None.

**Important Gaps (non-blocking, addressable during implementation):**

1. **`.arcwright-ai/` init schema** — exact files created by `arcwright init` not enumerated. Recommend: `config.yaml` + `runs/` + `worktrees/` (empty). Story-level detail.
2. ~~**V3 validation budget tracking** — V3 reflexion invokes SDK (costs tokens). MVP: track against same BudgetState. Growth refinement: separate validation budget.~~ **RESOLVED by Decision 9:** Each model role carries its own `ModelPricing`; validate_node applies review model pricing while agent_dispatch applies generate model pricing. Budget ceiling remains aggregate.
3. **`prompt.py` template structure** — prompt engineering is an implementation concern. Flagged as high-priority story needing experimentation.

**Nice-to-Have Gaps:**

4. Architecture Mermaid diagram (ASCII data flow serves same purpose for now)
5. Dependency version pinning strategy (ranges in pyproject.toml, `pip freeze` in CI)

### Architecture Completeness Checklist

**✅ Requirements Analysis**
- [x] Project context thoroughly analyzed (36 FRs, 20 NFRs, 4 FR chains)
- [x] Scale and complexity assessed (10 subsystems, high complexity)
- [x] Technical constraints identified (LangGraph, SDK, Git 2.25+, Python 3.11+)
- [x] Cross-cutting concerns mapped (7 concerns documented)
- [x] 5 first-class architectural constraints established

**✅ Architectural Decisions**
- [x] 9 critical decisions documented with rationale and trade-offs (D1-D8 original, D9 post-MVP amendment)
- [x] Technology stack fully specified with versions
- [x] Integration patterns defined (file-based state, CLI boundaries, SDK contract)
- [x] All inter-decision bindings explicitly documented

**✅ Implementation Patterns**
- [x] Python code style (naming, imports, docstrings, `__all__`)
- [x] Async patterns (to_thread, subprocess, graph nodes)
- [x] Pydantic model patterns (frozen default, mutable state, StrEnum)
- [x] Error handling patterns (hierarchy, catch/re-raise rules)
- [x] File & path patterns (pathlib, encoding, YAML I/O)
- [x] Structured logging patterns (event emit, anti-patterns)
- [x] Testing patterns (naming, isolation, fixtures, assertions, slow markers)
- [x] Package dependency DAG as mandatory rule

**✅ Project Structure**
- [x] Complete directory structure (27 source files, 20 test files, 3 integration tests)
- [x] Component boundaries established (4 explicit boundaries)
- [x] All 36 FRs mapped to specific files
- [x] All 20 NFRs mapped to enforcement mechanisms
- [x] Data flow documented with all graph nodes and state transitions
- [x] Node function signatures documented

### Architecture Readiness Assessment

**Overall Status:** READY FOR IMPLEMENTATION

**Confidence Level:** High — all FRs/NFRs covered, no critical gaps, 5 rounds of Party Mode review producing 28 enhancements, post-MVP amendment (Decision 9) adding role-based model registry.

**Key Strengths:**
- Every FR maps to a specific file — agents know exactly where to implement
- Package dependency DAG prevents circular imports and architectural drift
- 5 Party Mode rounds caught material issues (budget_check node, ContextError exit code, D1↔D4 binding, dependency DAG, test isolation)
- Patterns are concrete and copy-pasteable with working code examples
- Error handling, state lifecycle, and boundary contracts are explicit — no implicit success paths
- Decision 9 (Role-Based Model Registry) enables adversarial code generation/review split and cost optimization per model role

**Areas for Future Enhancement:**
- Prompt engineering templates (high-priority implementation story)
- ~~V3 validation budget split (Growth phase)~~ — resolved by Decision 9 role-based pricing
- Architecture Mermaid diagram
- `.arcwright-ai/` init schema enumeration (first implementation story)
- Dependency version pinning strategy
- Per-role budget ceilings (future refinement — current design aggregates across roles)