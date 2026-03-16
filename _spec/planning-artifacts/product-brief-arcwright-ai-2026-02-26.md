---
stepsCompleted: [1, 2, 3, 4, 5]
inputDocuments:
  - '_spec/brainstorming/brainstorming-session-2026-02-26.md'
date: 2026-02-26
author: Ed
---

# Product Brief: Arcwright AI

<!-- Content will be appended sequentially through collaborative workflow steps -->

## Executive Summary

> **Design by day, execute by night.**

Arcwright AI is a methodology-agnostic agent orchestration platform that automates multi-stage software development workflows, enforces deterministic validation gates around non-deterministic AI agent output, and provides full observability and traceability via LangGraph. It ships with the BMAD Method as its reference implementation — but any team can encode their own development methodology as executable workflows.

The core insight: AI-assisted development has solved the context problem, but not the throughput problem. Today, developers manually shepherd AI agents through workflows one conversation at a time — a process that is sequential, unvalidated, and unobservable. Arcwright AI wraps a deterministic orchestration shell around non-deterministic agents, enabling developers to design collaboratively during the day and dispatch automated execution overnight across multiple epics and stories — waking up to completed, validated, traceable work.

Arcwright AI is built on the principle that **automation earns trust through transparency, not by asking for it upfront.** Every decision is logged. Every output is validated. Every workflow step is observable. Developers choose exactly which epics and stories to execute — down to individual story granularity — and the system halts loudly on unrecoverable failure. Fail loud, fail visible is a deliberate design choice, not a limitation.

This is an open-source, practitioner-built platform. BMAD is the reference implementation, but **every methodology trapped in someone's head or a wiki can become an executable workflow.** The community becomes the methodology library.

---

## Core Vision

### Problem Statement

AI coding agents have become remarkably capable at executing individual tasks when given proper context. The BMAD Method solved the context problem — providing structured workflows that produce comprehensive, consistent planning artifacts that give AI agents everything they need to implement correctly.

But execution remains a manual bottleneck. A developer using BMAD today must:
- Initiate each workflow conversation individually
- Monitor agent progress and answer prompts in real-time
- Manually validate outputs before proceeding to the next phase
- Execute stories sequentially, one at a time, one conversation at a time
- Maintain mental state about what's been completed, what's next, and what depends on what

The ceiling isn't agent intelligence — it's human throughput as the orchestration layer.

### Problem Impact

For solo developers, this means carefully planned epics and stories execute at the speed of human attention — typically 2-4 stories per working day. For teams, coordination overhead multiplies: who's working on which story, are dependencies satisfied, did the last output pass review?

The planning phase produces a complete implementation roadmap. The implementation phase then ignores that completeness by executing one manual step at a time. The automation gap between "fully planned" and "fully executed" is where developer hours go to die.

### Why Existing Solutions Fall Short

The market has autonomous coding agents and workflow orchestration platforms, but nothing that combines methodology-driven planning with validated automated execution:

- **Autonomous coding agents** (Devin, Factory Droids, and similar) operate as black boxes — no methodology, no structured validation pipeline, no user-controlled workflow. Developers don't trust them because they demand trust upfront rather than earning it through transparency.
- **CI/CD and workflow engines** (Airflow, Temporal) orchestrate deterministic tasks. They have no model for wrapping non-deterministic AI agent output in validation gates.
- **AI coding assistants** (Copilot, Cursor, Claude Code) augment individual developer sessions but provide no multi-agent coordination, no automated workflow sequencing, and no overnight execution model.

Every existing tool has serious gaps, requires too many manual steps along the way, or is simply too difficult to use for real-world multi-epic execution.

### Proposed Solution

Arcwright AI provides a LangGraph-based orchestration engine with a methodology-agnostic workflow definition interface — a first-class abstraction layer that is fully decoupled from any specific methodology's conventions. It:

1. **Declares** development workflows as a directed acyclic graph — nodes are methodology steps, edges are dependencies and validation gates
2. **Invokes** AI agents via Claude Code SDK with stateless, context-controlled sessions — one fresh session per command, orchestrator owns all context
3. **Validates** every output through artifact-specific pipelines using six validation patterns (from lightweight invariant checks to multi-perspective ensemble review), with a 5-retry budget before halting the epic
4. **Coordinates** parallel agent execution via centralized state with git worktree isolation — up to N=5 agents working concurrently on independent stories
5. **Provides** full observability and traceability through LangGraph's telemetry hooks — every node lifecycle (queued → running → validating → success/failed), every decision logged, every artifact tracked. LangGraph Studio is one consumer of this data; the architecture exposes telemetry any dashboard can consume.

Developers control execution scope with precision: "run epics 2, 3, and 5" or "just stories 2.1 through 2.4." The system halts an epic on unrecoverable failure — **fail loud, fail visible** — preserving all progress and decision history for human review.

### Key Differentiators

- **Methodology-agnostic platform**: The orchestration engine accepts any workflow definition through a first-class abstraction layer. BMAD ships as the reference implementation, but teams encode their own processes. The community becomes the methodology library.
- **Deterministic shell around non-deterministic agents**: LangGraph provides ordering, retry, and state guarantees. AI agents provide the creative work. Artifact-specific validation pipelines bridge the gap.
- **Design by day, execute by night**: The manual collaborative planning process feeds directly into automated execution. No translation layer, no re-specification. Plan your epics, select your scope, dispatch overnight.
- **Trust through transparency**: Unlike black-box autonomous agents, every decision is logged, every output is validated, every workflow step is observable. Developers choose exactly what work to dispatch — down to individual stories.
- **Fail loud, fail visible**: A deliberate design choice. The system halts an epic on unrecoverable failure rather than silently producing broken work. All progress and decision history is preserved for human review.
- **Open source, practitioner-built**: Built by developers solving their own problems. Every methodology trapped in a wiki can become an executable workflow.

## Target Users

### Primary Users

#### Job-to-be-Done

> **"When I've finished planning a project, I want to convert that plan into working code without being the execution bottleneck, so I can ship faster while maintaining quality and control."**

#### The Arcwright AI Developer

The primary user is any developer or technical lead who has completed structured project planning and wants automated, validated execution of that plan. The role matters less than the situation: they have a methodology-driven plan with actionable epics and stories, and they refuse to be the bottleneck between "fully planned" and "fully implemented."

**Profile:** Mid-to-senior developer, comfortable with CLI tools and Python environments. They value transparency, control, and observable systems over black-box magic. Zero LangGraph knowledge required — LangGraph is an implementation detail, not a user-facing dependency.

**How they get the job done — three modes:**

**Mode 1 — The Planner (Day)**
Collaboratively designs and refines project artifacts using HITL methodology workflows. This is the creative, high-judgment work: brainstorming, writing PRDs, defining architecture, breaking requirements into epics and stories. This mode is manual by design — human insight drives the planning.

**Mode 2 — The Dispatcher (Night)**
Selects specific epics and/or stories from the completed plan, configures scope, and launches Arcwright AI for automated execution. Reviews results the next morning — validated outputs, decision logs, and any failures that need attention. This mode is autonomous by design — the system earns trust through transparency.

**Mode 3 — The Methodology Author (Anytime)**
Encodes development processes as executable workflow definitions. For BMAD users, this is already done. For teams with custom processes, this mode enables them to plug their own methodology into Arcwright AI's orchestration engine. This mode may also describe open-source contributors who share workflow definitions with the community.

**Motivations:**
- Multiply implementation velocity without sacrificing quality or methodology rigor
- Sleep while validated code gets written
- Maintain full control over what work gets dispatched and full visibility into what happened

**Pain Points Today:**
- Manually babysitting each AI agent conversation through every workflow step
- Sequential execution when stories could run in parallel
- No observability into what the AI decided or why
- No validation beyond manual review — "completed" doesn't mean "completed correctly"

**What Makes Them Say "This Is Exactly What I Needed":**
Waking up to see that 6 stories across 2 epics were implemented, validated, and merged overnight — with a clear trail of every decision, every validation result, and every file changed.

### Secondary Users

#### Team Members and Reviewers

In team settings, secondary users interact with Arcwright AI's outputs rather than operating it directly:

- **Code reviewers** who review PRs generated by overnight runs. These are not ordinary PRs — each includes decision provenance logs explaining *why* every implementation choice was made, validation results confirming quality, and full execution traces. The review experience is fundamentally richer than reviewing human-generated PRs.
- **Tech leads** who monitor sprint velocity and use observability dashboards to assess automated execution quality
- **Engineering managers** who evaluate Arcwright AI's impact on team throughput and process compliance

These users benefit from Arcwright AI's transparency — decision provenance, validation results, and full execution traces — without needing to configure or dispatch runs themselves.

### Key Product Concepts

#### Dry Run / Observe Mode

Before trusting Arcwright AI with overnight execution, users can run in **observe mode** — a supervised, real-time execution where the user watches the orchestrator invoke agents, validate outputs, and track state transitions as they happen. This is not just a debugging tool; it is the **trust ramp** — the explicit product mechanism by which users build confidence before committing to autonomous execution.

Observe mode is a first-class product concept, not an afterthought.

#### Scope Selection

Scope selection is a **first-class interaction pattern**. Users specify exactly which epics and/or individual stories to execute — "run epics 2, 3, and 5" or "just stories 2.1 through 2.4." The specific UX for scope selection (CLI flags, YAML config, TUI, or other) is a design concern to be resolved during architecture and UX planning. The brief commits to the principle: **granular, user-controlled scope is non-negotiable.**

#### Failure Experience

When Arcwright AI halts an epic after exhausting retry budget, the user's experience of that failure is a deliberate design concern:

- **Halt summary:** A clear report of what succeeded (completed stories, merged PRs), what failed (story ID, failure reason, retry history), and where execution stopped
- **Decision trail preserved:** Every decision log, validation result, and state transition from the run is retained — nothing is lost
- **Resume point:** The system identifies exactly where to resume, so the user can address the failure and re-dispatch without re-executing completed work
- **Fail loud, fail visible:** The halt is unambiguous. No silent failures, no partial work masquerading as complete. The user knows exactly what happened and why.

### User Journey

**Discovery:** Bottom-up, grassroots adoption. A developer discovers Arcwright AI through open-source channels (GitHub, dev communities, word-of-mouth). The "design by day, execute by night" tagline and the promise of methodology-agnostic orchestration piques curiosity.

**Evaluation:** Before committing, the developer assesses fit. Their job at this stage is distinct: *"Help me see if this thing works on a small, low-risk scope before I trust it with real work."* They install Arcwright AI, point it at a small existing project or a test scope, and run in **observe mode** to watch the system work without committing to autonomous execution. The evaluation gate: does the system produce valid, observable, explainable output?

**Onboarding (10-20 minutes):**
1. `pip install arcwright-ai`
2. Configure `.arcwright-ai/config.yaml` with SDK keys and methodology path
3. Point at existing planning artifacts (e.g., BMAD `_spec/` directory)
4. Run `arcwright-ai validate-setup` to confirm dependencies and configuration

Zero LangGraph knowledge required. The user needs no understanding of graph internals to dispatch and monitor runs.

**First Autonomous Run:** The developer selects a small scope — perhaps 2-3 stories from one epic — and dispatches an overnight run. They check the observe mode output from their evaluation run, confirm trust, and let it go.

**The "Aha!" Moment:** The first time they wake up and see completed, validated stories with clean PRs ready for review. The execution trace shows exactly what happened. The decision logs explain every choice. The validation reports confirm quality. *They can't go back to manual execution after this.*

**Failure as Trust-Builder:** Inevitably, a run halts. The user opens the halt summary: 4 stories completed, 1 failed after 5 retries, clear error and retry history, resume point identified. They fix the issue, re-dispatch from the failure point. The system's handling of failure — transparent, recoverable, no lost work — deepens trust rather than eroding it.

**Long-term Integration:** Arcwright AI becomes the standard execution layer for their development process. Planning remains collaborative and manual (the "day" side). Implementation becomes automated and observable (the "night" side). For teams, it becomes shared infrastructure — dispatch runs, review enriched PRs with decision provenance, iterate.

## Success Metrics

### User Success Metrics

**Primary Success Indicator — Overnight Throughput:**
Stories completed per autonomous run. This is the headline metric that directly measures whether Arcwright AI is delivering on its core promise: converting plans into working code without human bottlenecks.
- **Target (v1):** 5+ stories completed per overnight run for a well-planned epic
- **Stretch:** Full epic completion (8-12 stories) in a single overnight dispatch

**Quality Gate — Validation Pass Rate:**
Percentage of stories that pass the full validation pipeline without requiring human intervention. This metric is only meaningful in the context of validation pipeline depth (see KPIs).
- **Target:** 80%+ first-pass validation success rate against active validation patterns
- **Signal of concern:** Below 60% indicates methodology artifacts or validation pipeline issues

**Quality Integrity — False Positive Rate:**
Percentage of halts that were legitimate failures (not false alarms from overly aggressive validators). If the validation pipeline halts valid work, it destroys trust faster than missed issues.
- **Target:** 90%+ of halts are legitimate failures
- **Signal of concern:** Below 80% means the pipeline is crying wolf and users will start ignoring or disabling validators

**Adoption Signal — Dispatch Frequency:**
How often users dispatch autonomous runs. Increasing frequency indicates trust is building and the tool is becoming part of the user's workflow.
- **Early adoption:** 1-2 dispatches per week (evaluating)
- **Integrated usage:** 3-5 dispatches per week (standard workflow)
- **Power usage:** Daily dispatches with increasing scope

**Trust Ramp — Observe Mode to Autonomous Ratio:**
The ratio of observe mode runs to autonomous runs over time. A decreasing ratio indicates growing trust.
- **Week 1:** Mostly observe mode
- **Month 1:** Primarily autonomous with occasional observe for new project types
- **Month 3+:** Observe mode only for new methodology configurations

**Cost Awareness — Cost per Story:**
API spend (Claude SDK tokens) per completed story, including validation retries. Parallel agents multiplied by retry attempts can produce meaningful costs. Users will ask "what does an overnight run cost me?" — this metric must be tracked and visible.
- **Target:** TBD after v1 benchmarking. The system should report cost per run and cost per story in execution summaries.

### Business Objectives

**3-Month Gate — Personal Validation (pass/fail):**
Complete 3 real-world epics (not demos) using Arcwright AI end-to-end, with >70% validation pass rate and <30 min average failure recovery time. All critical v1 features (scope selection, validation pipeline, observe mode, failure experience) are functional and reliable. Ed is using Arcwright AI across multiple projects as the standard execution layer.

**12-Month Milestone — Community Adoption:**
Arcwright AI has established itself within the BMAD community and is attracting users from the broader AI-assisted development space.
- Active GitHub community with external contributors
- Non-BMAD workflow definitions submitted by community members
- Recognition as a credible tool in AI development tooling discussions
- Ed established as a recognized expert in AI-augmented development methodology

**24-Month Gate — Commercial Viability (pass/fail):**
The open-core model is validated when: **5+ teams or organizations have expressed willingness to pay for hosted execution, team management, or enterprise-grade observability features.** This can be measured through waitlist signups, direct conversations, or letter-of-intent equivalents. The open-source Arcwright AI remains genuinely useful and free; the commercial layer targets problems that are expensive for teams to self-host (multi-user coordination, managed infrastructure, SLA-backed execution, compliance reporting).

### Strategic Ecosystem Metric — Community Workflow Definitions

This is the single most important long-term metric for Arcwright AI's success as a platform. Every non-BMAD methodology encoded as an executable workflow definition deepens the ecosystem moat, makes Arcwright AI harder to replace, and validates the methodology-agnostic promise.

- **12-Month Target:** 3+ community-contributed workflow definitions for non-BMAD methodologies
- **The Signal That Matters Most:** When someone builds a workflow definition *you didn't expect* — for a methodology, domain, or use case that wasn't on the roadmap. That's when the platform takes on a life of its own.
- **Leading Indicators:** Documentation quality for workflow authoring, number of "how do I create a workflow for X?" issues, community discussion around methodology encoding

Stars and forks measure awareness. Workflow definitions measure *commitment.* Prioritize the latter.

### Key Performance Indicators

| KPI | Measurement | 3-Month Target | 12-Month Target |
|-----|-------------|----------------|------------------|
| **Stories/Night** | Avg stories completed per autonomous run | 5+ | 8-12 (full epics) |
| **Validation Pass Rate** | % stories passing validation without human intervention | 70%+ | 80%+ |
| **Validation Pipeline Depth** | # of active validation patterns (V1-V6) per artifact type | V6 minimum (invariant checks) | V1+V2+V5 on docs, V3+V6+tests on code |
| **False Positive Rate** | % of halts that were legitimate failures | 80%+ | 90%+ |
| **Dispatch Frequency** | Autonomous runs per week (personal usage) | 3+ | Daily |
| **Cost per Story** | Avg API spend per completed story incl. retries | Benchmark established | Tracked and optimized |
| **Projects Using Arcwright AI** | Distinct projects with active Arcwright AI execution | 2-3 (personal) | 10+ (community) |
| **GitHub Stars** | Community interest signal | 100+ | 500+ |
| **External Contributors** | Non-maintainer PRs merged | — | 10+ |
| **Community Workflow Defs** | Non-BMAD methodology definitions contributed | — | 3+ |
| **Setup-to-First-Run** | Time from install to first successful autonomous run | <30 min | <20 min |
| **Failure Recovery Time** | Time from halt notification to successful re-dispatch | <15 min | <10 min |
| **Commercial Interest** | Teams expressing willingness to pay for premium features | — | 5+ (24-month gate) |

---

## 5. MVP Scope & Boundaries

### MVP Definition

The MVP is the minimum surface area required to prove the core thesis: **a single developer can dispatch a scoped unit of work (epic or story) to an autonomous agent pipeline that executes overnight, validates its own output, and halts loudly on failure — ready for human review by morning.**

### Architectural Risk Ranking

Features are ordered by architectural risk and dependency. The PRD **must** prioritize implementation in this sequence:

1. **Claude Code SDK + Answerer integration** — highest risk; validates that the invocation model and deterministic rule engine work end-to-end before anything else is built on top
2. **V3 Reflexion validation pipeline** — second-highest risk; proves the self-correction loop is viable
3. **Resume-from-failure** — third-highest risk; requires LangGraph checkpointing spike to validate feasibility

### Core MVP Features

| # | Feature | Description | Validation |
|---|---------|-------------|------------|
| 1 | **Scope Selector** | User selects epic or story as the dispatch unit; system resolves the artifact graph for that scope | Static: scope maps to correct artifact set |
| 2 | **Claude Code SDK Invocation** | Stateless async agent calls via Python SDK; streaming token output | Unit: invoke returns structured output |
| 3 | **Answerer (Static Rules)** | Deterministic rule engine that answers agent questions without LLM calls — file lookups, config reads, artifact references | Unit: rules resolve correctly; no LLM fallback in MVP |
| 4 | **Sequential Pipeline** | Single-agent, single-step-at-a-time execution through the methodology workflow | Integration: steps execute in correct order |
| 5 | **V3 Reflexion Validation** | Agent self-evaluates output against story acceptance criteria; up to 3 retry loops before escalation | V3 evaluates against AC from the story artifact |
| 6 | **V6 Invariant Checks** | Static rule-based checks (file exists, schema valid, naming conventions) run after each step | Unit: invariants catch known-bad output |
| 7 | **Halt & Notify on Failure** | Pipeline stops on validation failure; writes structured failure report; notifies user via CLI output + optional webhook | Integration: halt produces actionable report |
| 8 | **Observe Mode** | Dry-run flag that executes the full pipeline but writes no files; outputs what *would* happen | All dispatch commands accept `--observe` flag |
| 9 | **Test Harness** | Synthetic BMAD project fixture for automated regression; known-good and known-bad scenarios exercise the full pipeline without live LLM calls where possible | CI: harness runs on every PR; known-bad scenarios trigger expected halts |
| 10 | **Cost Tracking** | Per-run token usage and estimated cost logged to run metadata | Each run log includes input/output tokens + cost estimate |
| 11 | **LangGraph State & Observability** | Full execution trace via LangGraph; replayable from any checkpoint | LangGraph Studio shows complete run graph |

### Explicitly Out of MVP

| Feature | Rationale | Target |
|---------|-----------|--------|
| Abstraction layer (methodology decoupling) | Adds complexity before core loop is proven | v1.1 |
| Multi-agent parallel execution | Sequential is sufficient to prove thesis | v1.2 |
| Git worktree isolation | Needed only for parallel agents | v1.2 |
| Web UI / dashboard | CLI is sufficient for solo dev | v2.0 |
| LLM-based answerer fallback | Static rules first; LLM fallback adds ambiguity | v1.1 |
| V2 (LLM-as-Judge) validation | V3 + V6 sufficient for MVP | v1.1 |
| Multi-methodology support | BMAD is reference impl; others after abstraction layer | v1.1+ |
| Resume-from-checkpoint (auto) | Needs LangGraph checkpointing spike first | v1.1 (spike in MVP) |

### MVP Exit Criteria

- **3 real-world BMAD epics** dispatched and autonomously completed overnight across different project types
- All 3 produce artifacts that pass V3 reflexion + V6 invariant validation
- At least 1 epic triggers a halt scenario that produces an actionable failure report
- Observe mode successfully previews a full run without writing files
- Test harness passes CI with both known-good and known-bad synthetic scenarios
- Cost per story-equivalent is logged and within acceptable range (<$2 target)
- Setup-to-first-run time is under 30 minutes for a developer with an existing BMAD project

### Open Spikes (Must Resolve During MVP)

| Spike | Question | Resolution Criteria |
|-------|----------|--------------------|
| **LangGraph Checkpointing** | Can we resume a failed pipeline from the last successful step? | Prototype demonstrates resume from checkpoint in LangGraph |
| **Validate-Setup Spec** | What does the setup-validation contract look like for a new project? | Written spec defining minimum project structure, config files, and methodology artifacts required before first dispatch |

### CLI Interface (MVP)

```bash
# Dispatch a story
arcwright-ai dispatch --story STORY-123

# Dispatch an epic
arcwright-ai dispatch --epic EPIC-45

# Observe mode (dry run)
arcwright-ai dispatch --story STORY-123 --observe

# Check run status
arcwright-ai status --run <run-id>

# View cost summary
arcwright-ai cost --run <run-id>
```
