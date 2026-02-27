---
stepsCompleted: [1, 2, 3, 4, 5]
inputDocuments: []
session_topic: 'Arcwright AI — Methodology-agnostic agent orchestration platform with LangGraph observability and multi-agent swarm scaling'
session_goals: 'Automated workflow execution, deterministic validation of non-deterministic agents, observability, swarm coordination, methodology-agnostic orchestration'
selected_approach: 'ai-recommended'
techniques_used: ['Question Storming', 'Morphological Analysis', 'Cross-Pollination']
ideas_generated: 40
context_file: '_bmad/bmm/data/project-context-template.md'
session_active: false
workflow_completed: true
---

# Brainstorming Session Results

**Facilitator:** Ed
**Date:** 2026-02-26

## Session Overview

**Topic:** Building Arcwright AI — a methodology-agnostic agent orchestration platform that automates multi-stage development workflows, enforces deterministic validation gates around non-deterministic AI agent output, provides observability and traceability via LangGraph, and enables multi-agent swarm collaboration on a single project. Ships with BMAD as the reference implementation.

**Goals:**
- Automated BMAD workflow execution across development phases
- Validation gates ensuring quality/compliance before progression
- LangGraph-powered observability into past and current workflow execution
- Multi-agent swarm coordination for parallel project work
- Features extending beyond native BMAD capabilities (state management, conflict resolution, agent coordination, artifact dependency tracking)

### Context Guidance

Project context template loaded with software/product development focus areas: user problems, feature ideas, technical approaches, UX, business model, market differentiation, technical risks, and success metrics.

### Session Setup

Expert-level session focusing on distributed systems architecture, workflow orchestration, and AI agent coordination. User has deep familiarity with BMAD internals and wants to scale from single-agent to multi-agent workflows.

## Technique Selection

**Approach:** AI-Recommended Techniques
**Analysis Context:** Orchestration layer over BMAD with focus on automated workflows, validation, observability, and swarm scaling

**Recommended Techniques:**

- **Question Storming (deep):** Map the unknown problem space — uncover hidden questions about coordination, state, failures, and API surface before jumping to solutions
- **Morphological Analysis (deep):** Decompose system into key design dimensions and systematically explore every architectural combination
- **Cross-Pollination (creative):** Transfer proven orchestration patterns from Kubernetes, Airflow, biological swarms, and other adjacent domains

**AI Rationale:** Challenge sits at intersection of distributed systems, workflow orchestration, and AI agent coordination — three rich domains with almost no precedent at their specific intersection. Techniques selected to properly scope the problem, systematically map the solution space, then pull proven patterns from adjacent domains.

## Technique Execution Results

### Technique 1: Question Storming (deep)

**Questions Explored:** 25+ across 5 domains
**Duration:** Extended deep-dive with answers producing architectural decisions

#### Domain 1: BMAD Interface & Execution
- **Q1: Can BMAD run without HITL?** → YES, proven by dev-release-cycle workflow. Steps auto-proceed; only CR Gate is a hard stop by design choice.
- **Q2: What is the interaction interface?** → Claude Code CLI / SDK. The `claude-code-sdk` Python package provides async generator with typed message objects and full tool control.
- **Q2a: How does LangGraph invoke Claude?** → SDK async generator, native Python async, fits LangGraph's async node model.
- **Q2b: How to capture structured output?** → SDK native JSON Schema enforcement → `ResultMessage.structured_output` → drops directly into Pydantic state fields. No parsing step.
- **Q2c: Does SDK load BMAD context?** → Isolated by default. Opt-in via `setting_sources=["project"]`. Auto-memory requires manual injection.
- **Q2d: How to feed answers to BMAD prompts?** → Two strategies: (1) Front-load known answers in the prompt, (2) Auto-answer loop via LangGraph "answerer" node that reads BMAD's question and generates contextual response.
- **Q2e: SDK signal for "waiting for input"?** → No special type — ResultMessage contains the question text. Detection is on the orchestrator side.

#### Domain 2: Orchestrator Design
- **Q3a: Can orchestrator pre-determine all answers?** → Not always. Hybrid approach: front-load what you know, catch the rest with answerer node.
- **Q3b: One node = one BMAD command?** → YES. Keep functionality focused and isolated.

#### Domain 3: Validation Architecture
- **Q4a: Validation patterns beyond checkboxes?** → Six distinct patterns mapped to LangGraph constructs:
  - **V1: BMAD Native Validators** — adversarial, cross-doc validation workflows as validator nodes
  - **V2: LLM-as-Judge** — separate model scores output against explicit criteria
  - **V3: Reflexion** — self-critique + revise loop for surface issues
  - **V4: Cross-Document Consistency** — validate artifact agreement (architecture ↔ PRD)
  - **V5: Multi-Perspective Ensemble** — parallel persona review, disagreement signals ambiguity
  - **V6: Property-Based / Invariant Checks** — "unit tests for documents," pure Python assertions
- **Q5: "Completed" vs "completed correctly"?** → Schema enforcement = completed. Validation pipeline = correctly. Different pipelines per artifact type.
- **Q5a: Different validation pipelines per artifact?** → YES. Artifact-specific pipelines are first-class design concern. PRD gets V1+V2+V5; code gets V3+V6+test execution.
- **Q5b: Retry budget?** → 5 attempts, then escalate to human/abort.

#### Domain 4: State, Artifacts & Dependencies
- **Q6: Branch detection / decision provenance?** → Structured decision log in frontmatter (Option B). Each workflow step appends `{topic, choice, rejected, rationale}` entries. Enables consistency enforcement, decision-aware validation, and surgical course correction.
- **Q12: How does orchestrator know what artifacts were produced?** → Convention-based top-level directory from config + file diff (snapshot before/after execution).
- **Q13: Complete vs partially written?** → "Next steps" prompt from BMAD = completion signal. Combined with structured output schema.
- **Q14: Workflow dependency expression?** → Two-tier model: Phase 4 uses explicit `input_file_patterns` in YAML; Phases 1-3 use convention-based glob discovery in init steps. No centralized DAG.
- **Q14a: Formal DAG vs phase ordering?** → Phase ordering + existence checks + three additive layers:
  - Layer 1: Phase ordering (have it)
  - Layer 2: Existence checks via glob (have it)
  - Layer 3: Status-aware existence (frontmatter `status: approved/draft`)
  - Layer 4: Assignee visibility (sprint-status.yaml assignee field)
  - Layer 5: Input hash staleness detection (content hashes in frontmatter, warn-don't-block)
- **Q14b: Stale dependency detection?** → Content hash tracking. Downstream artifacts record input hashes at creation time. Mismatch triggers warning + require explicit override. Warn-don't-block.

#### Domain 5: Swarm Architecture
- **Q15-18: Isolation strategy?** → Hybrid model:
  - **Code isolation:** Git worktrees (one per agent, separate branch)
  - **Coordination:** LangGraph state is single source of truth (sprint status, assignees, artifact hashes, decisions)
  - **Agent access:** Read-only coordination snapshots injected into prompts; full read/write within own worktree
  - **Merge:** PRs to develop, sequential or parallel with conflict detection
  - **Concurrent SDK:** Each agent is a separate `claude_code_sdk.run()` with `cwd` pointed to its worktree

### Key Breakthroughs from Question Storming

1. **BMAD is instructions, not software** — The "runtime" is an LLM with file/terminal access. Claude Code SDK bridges this to programmatic invocation.
2. **The 5-layer dependency stack** — Phase ordering → existence → status gates → assignee locks → hash staleness. Incrementally additive, no DAG required.
3. **Decision provenance via frontmatter** — Structured decision logs survive sessions, enable consistency enforcement and surgical course correction.
4. **Hybrid swarm isolation** — Worktrees for code, LangGraph state for coordination. Clean separation of concerns.
5. **Validation as a typed pipeline** — Six validation patterns ordered by cost, artifact-specific pipelines, 5-retry budget.

### Technique 2: Morphological Analysis (deep)

**Dimensions Explored:** 7 core design axes
**Combinations Tested:** 4 high-leverage pairings across all dimensions

#### The Morphological Matrix — Final Selections

| Dimension | Selection | Alternatives Considered |
|-----------|-----------|------------------------|
| **D1: Graph Topology** | DAG with parallel branches | Linear pipeline (too simple for swarm), Dynamic graph (premature complexity) |
| **D2: Invocation Model** | Stateless — one SDK session per command | Persistent per-phase (context bloat), Persistent per-persona (stale state risk) |
| **D3: Validation Scheduling** | Inline — validate immediately after each producer | Batched (late failure detection), Tiered cascade (optimization opportunity for later) |
| **D4: Answerer Strategy** | Hybrid — static rules first, LLM fallback for unknowns | Static-only (can't cover all prompts), LLM-only (expensive for predictable patterns) |
| **D5: Coordination Model** | Centralized — LangGraph state is sole authority | Federated (eliminated — conflicts with stateless D2), Event-driven (LangGraph already provides reactive behavior natively) |
| **D6: Swarm Parallelism** | Bounded parallel, N=5 agents max | Sequential (no swarm benefit), Elastic (operational complexity not justified initially) |
| **D7: Human Escalation** | Adaptive — autonomous by default, escalate on retry exhaustion | Never (too risky for production), Gates-only (too slow for autonomous operation) |

#### Key Synergies Discovered

1. **DAG + Bounded Parallel (D1×D6):** Stories within a sprint execute concurrently up to N=5, with dependencies respected via DAG edges. The primary swarm value proposition.
2. **Stateless + Hybrid Answerer (D2×D4):** Fresh invocations with no stale context. Orchestrator owns all context and injects exactly what each call needs. Static rules cover predictable BMAD prompts, LLM handles edge cases.
3. **Inline Validation + Adaptive Escalation (D3×D7):** Fast autonomous feedback loops. Most issues caught and retried without human involvement. Only retry budget exhaustion or low confidence triggers escalation.
4. **Centralized + Everything (D5×all):** LangGraph's state graph IS the coordination layer. Stateless agents require a central authority. Bounded parallel requires pool management. Adaptive escalation requires failure history. Centralized is the only option that doesn't fight other choices.

#### Conflicts Eliminated

- **Federated + Stateless:** Federated requires persistent local state, stateless agents can't maintain it. Eliminated.
- **Linear + Bounded Parallel:** Nothing to parallelize in a linear pipeline. Eliminated as wasteful.
- **Persistent sessions + Hybrid answerer:** Two sources of memory can contradict. Eliminated.

### Creative Facilitation Narrative

The session moved through two complementary techniques. Question Storming went deep — systematically traversing from "what is BMAD's API surface?" all the way to swarm isolation strategies. Ed's answers were remarkably well-reasoned, often arriving with multiple options already evaluated and a clear recommendation. The most generative moments came when answers revealed that existing BMAD patterns (dev-release-cycle, frontmatter, sprint-status.yaml) already contained the seeds of the orchestrator's design.

Morphological Analysis then formalized those discoveries into a 7-dimension design matrix. The combination testing was decisive — most dimensions had clear winners once tested against the locked choices. The centralized coordination model wasn't just the best option; it was the only one that didn't create conflicts with stateless invocation. The architecture emerged not from greenfield invention but from recognizing what was already there and formalizing it.

### Technique 3: Cross-Pollination (creative)

**Domains Explored:** 4 adjacent systems
**Patterns Extracted:** 4 proven patterns adapted to Arcwright AI

#### Pattern 1: Declarative Graph Definition (from CI/CD Pipelines)

**Source:** GitHub Actions, CircleCI pipeline-as-code
**What we're stealing:** The orchestration graph is declared as a configuration — nodes, dependencies (`needs:`), and artifact passing — not hardcoded. LangGraph's `StateGraph` is the execution engine; the graph definition maps cleanly to CI/CD's declarative pipeline model.

**Key adaptations:**
- Job isolation = git worktree isolation
- `needs:` = 5-layer dependency stack
- Artifacts between jobs = BMAD output documents
- Job matrix = bounded parallel (N=5)

**What doesn't translate:** BMAD workflows are conversational and non-deterministic, unlike idempotent CI jobs. The answerer node handles this gap.

#### Pattern 2: Desired State + Reconciliation (from Kubernetes)

**Source:** K8s controller reconciliation loops
**What we're stealing:** The orchestrator declares a desired project state ("PRD approved, architecture approved, all stories merged with passing tests") and continuously compares desired vs actual, taking corrective action on drift.

**Key adaptations:**
- Self-healing: validation failure → automatic retry (up to 5)
- Idempotent: re-running reconciler on complete project is a no-op. Safe to restart after crashes.
- Observable: desired vs actual diff IS the dashboard in LangGraph Studio
- Stale dependency detection: reconciler notices input hash changes (Layer 5)

**What doesn't translate:** K8s reconciles continuously (polling). Arcwright AI reconciles at discrete points (after each node completes). Desired state evolves as project progresses.

#### Pattern 3: Stigmergy — Environment-as-Coordination (from Ant Colonies)

**Source:** Biological swarm intelligence
**What we're stealing:** Agents coordinate indirectly through shared environment signals — sprint-status.yaml, artifact frontmatter (status, decisions, hashes), and git branch state. The orchestrator maintains the environment; agents read it for context.

**Key adaptations:**
- Secondary pattern layered on centralized control (D5-A)
- Decoupled scaling: new agents read the same environment, no re-wiring
- Fault tolerance: crashed agent's story stays "in-progress," recoverable
- Natural load balancing: agents claim unclaimed work from the queue

**What doesn't translate:** Pure stigmergy is decentralized. Arcwright AI uses it as environmental context, not primary coordination.

#### Pattern 4: Task Lifecycle State Machine + XCom (from Apache Airflow)

**Source:** Airflow DAG task scheduling
**What we're stealing:** Every node follows a formal lifecycle: `queued → preflight → running → validating → success/retry/escalated`. LangGraph state acts as the artifact bus (like Airflow XCom) — nodes push artifact references (paths + hashes), downstream nodes pull them.

**Key adaptations:**
- Task lifecycle = consistent status model across all graph nodes → excellent observability
- XCom = LangGraph `ProjectState` with typed `ArtifactRef` fields
- Airflow sensors = preflight dependency checks (Layers 2-5)

**What doesn't translate:** Airflow tasks are deterministic Python functions. BMAD tasks are non-deterministic LLM conversations. The validation pipeline compensates.

---

## Session Highlights

**Total Ideas/Decisions Generated:** 40+ across three techniques
**Techniques Used:** Question Storming, Morphological Analysis, Cross-Pollination
**Session Duration:** Extended deep-dive

### The Emergent Architecture Profile

**Arcwright AI** is a LangGraph-based orchestrator that:

1. **Declares** a DAG of BMAD workflows as a LangGraph StateGraph (CI/CD pattern)
2. **Invokes** each workflow via Claude Code SDK (stateless, one session per command)
3. **Validates** outputs through artifact-specific inline pipelines (6 validation patterns, 5-retry budget)
4. **Coordinates** via centralized LangGraph state with environmental signals (K8s reconciliation + stigmergy)
5. **Scales** to N=5 parallel agents via git worktrees (bounded parallel)
6. **Tracks** every node through a formal lifecycle: queued → preflight → running → validating → success/retry/escalated (Airflow pattern)
7. **Escalates** adaptively — autonomous by default, human involvement only when the system can't self-resolve

### Key Design Decisions Registry

| Decision | Choice | Rationale |
|----------|--------|-----------|
| LLM invocation | Claude Code SDK (async generator) | Native Python, typed messages, tool control, JSON Schema output |
| Structured output | SDK JSON Schema → Pydantic state | Zero parsing, direct state assignment |
| BMAD context loading | `setting_sources=["project"]` | Opt-in, orchestrator controls context per agent |
| Prompt answering | Hybrid (static rules + LLM fallback) | Covers predictable patterns cheaply, handles unknowns |
| Dependency management | 5-layer stack (phase → hash staleness) | Incrementally additive, no centralized DAG |
| Decision provenance | Structured frontmatter decision log | Survives sessions, enables consistency enforcement |
| Artifact tracking | File diff (before/after snapshots) | Leverages convention-based paths from BMAD config |
| Completion signal | "Next steps" prompt in ResultMessage | BMAD's native pattern |
| Swarm isolation | Git worktrees (code) + LangGraph state (coordination) | Full filesystem isolation with centralized authority |
| Validation | 6-pattern pipeline, artifact-specific, inline | Fast feedback, cost-tiered, avoids self-validation |
| Retry budget | 5 attempts, then adaptive escalation | Conservative but autonomous |
| Agent parallelism | Bounded, N=5 | Balances throughput with manageable complexity |

### What This Session Did NOT Cover (Future Exploration)

- Specific Pydantic state models for ProjectState
- LangGraph Studio dashboard configuration
- Cost estimation for parallel agent runs
- Testing strategy for the orchestrator itself
- Migration path from current BMAD usage to orchestrated mode
- Authentication and secrets management for Claude Code SDK sessions
- Monitoring and alerting beyond LangGraph Studio

## Idea Organization and Prioritization

### Thematic Organization

**Theme 1: Core Orchestration Engine**
_Focus: The fundamental mechanics of how LangGraph drives BMAD workflows_

- **Claude Code SDK as bridge layer** — async generator with typed messages, JSON Schema output, tool control
- **Stateless invocation model** — fresh SDK session per BMAD command, orchestrator owns all context
- **Declarative graph definition** — LangGraph StateGraph configured like CI/CD pipeline-as-code
- **Hybrid answerer** — static rules for predictable BMAD prompts, LLM fallback for unknowns
- **Task lifecycle state machine** — queued → preflight → running → validating → success/retry/escalated

**Theme 2: Validation & Quality Assurance**
_Focus: Ensuring BMAD agents do their job correctly_

- **Six validation patterns** (V1-V6) mapped to LangGraph constructs, ordered by cost
- **Artifact-specific validation pipelines** — different failure modes need different checks
- **Inline scheduling** — validate immediately after each producer for fast feedback
- **5-retry budget with adaptive escalation** — autonomous by default, human only when needed
- **Decision provenance** — structured frontmatter decision logs enable consistency-aware validation

**Theme 3: State Management & Dependencies**
_Focus: How the orchestrator tracks artifacts, dependencies, and project progress_

- **5-layer dependency stack** — phase ordering → existence → status gates → assignee locks → hash staleness
- **Content hash staleness detection** — warn-don't-block when inputs changed since artifact creation
- **File diff snapshots** — before/after directory snapshots to detect what workflows produced
- **Centralized LangGraph state** — single source of truth for sprint status, assignees, hashes, decisions
- **Desired state + reconciliation** — K8s-inspired pattern comparing actual vs intended project state

**Theme 4: Swarm Architecture**
_Focus: Enabling multiple AI agents to work on the same project concurrently_

- **Git worktrees for code isolation** — one worktree per agent, separate feature branches
- **Bounded parallelism (N=5)** — manageable concurrency with orchestrator-managed pool
- **Stigmergy/environment-as-coordination** — agents read shared signals (sprint-status, frontmatter, git state)
- **Read-only coordination snapshots** — agents get injected context, only orchestrator writes coordination state
- **PR-based merge** — standard git flow for integrating parallel agent work

**Theme 5: BMAD Integration Layer**
_Focus: Bridging BMAD's instruction-based model to programmatic orchestration_

- **BMAD is instructions, not software** — the LLM is the runtime, SDK is the invocation layer
- **`setting_sources=["project"]`** — opt-in BMAD context loading per agent
- **Two-tier dependency model** — BMAD's existing explicit (Phase 4) and convention-based (Phases 1-3) discovery
- **Front-loaded prompt answers** — pre-answer known questions, auto-answer loop for unknowns
- **Completion signal detection** — "next steps" prompt pattern indicates workflow finished

**Cross-Cutting Breakthrough Concepts:**

- **The orchestrator doesn't replace BMAD — it wraps it.** BMAD workflows run exactly as designed; the orchestrator manages sequencing, validation, and coordination around them.
- **The architecture already exists in BMAD primitives.** Sprint-status.yaml, frontmatter, dev-release-cycle's step pattern, and `_memory` sidecars are the building blocks — they just need formalization.
- **Deterministic shell around non-deterministic agents.** LangGraph provides the guarantees (ordering, retry, state); BMAD agents provide the creative work.

### Prioritization Results

**Top Priority — Foundation (must build first):**
1. Core orchestration engine with SDK integration and stateless invocation
2. Single-agent sequential pipeline (Phases 1-4, no parallelism)
3. Inline validation with V6 (invariant checks) as minimum viable validation

**Second Priority — Intelligence Layer:**
4. Hybrid answerer (static rules + LLM fallback)
5. Full validation pipeline (V1-V6) with artifact-specific routing
6. 5-layer dependency stack with hash staleness detection

**Third Priority — Swarm Scaling:**
7. Git worktree management and bounded parallel execution
8. Centralized coordination state with read-only agent snapshots
9. PR-based merge with conflict detection

**Future / Optional:**
10. Decision provenance in frontmatter
11. Multi-perspective ensemble validation (V5)
12. Dynamic graph topology (upgrade from static DAG)

### Action Plan

**Immediate Next Step:** Run BMAD's **Create Brief (CB)** workflow to produce a formal product brief from this brainstorming session. The session output provides all the raw material — CB will distill it into exec-level framing.

**Then:** **Create PRD (CP)** to formalize requirements, especially around the SDK integration boundary, validation pipeline specification, and swarm coordination rules.

**Then:** **Create Architecture (CA)** to lock the LangGraph graph structure, Pydantic state models, and worktree management approach.

**Then:** Standard BMAD flow — **Create Epics & Stories (CE)** → **Implementation Readiness (IR)** → **Sprint Planning (SP)** → **Dev (DS)**.

## Session Summary

**Key Achievements:**
- Mapped the complete problem space through 25+ answered architectural questions
- Produced a 7-dimension design matrix with all combinations tested and selections locked
- Adapted 4 proven patterns from CI/CD, Kubernetes, biological swarms, and Airflow
- Emerged with a coherent architecture profile and clear implementation roadmap

**Session Reflections:**
This brainstorming session was unusual — it produced architectural decisions, not just ideas. The Question Storming technique was the backbone: each answer constrained the solution space, and by the time we reached Morphological Analysis, most dimensions had obvious winners. The Cross-Pollination technique then grounded abstract decisions in proven real-world patterns. The result is a design that feels inevitable rather than invented — because it was systematically derived from BMAD's existing primitives, the SDK's capabilities, and LangGraph's native constructs.
