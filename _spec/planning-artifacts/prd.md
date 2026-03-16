---
stepsCompleted: ['step-01-init', 'step-02-discovery', 'step-02b-vision', 'step-02c-executive-summary', 'step-03-success', 'step-04-journeys', 'step-05-domain', 'step-06-innovation', 'step-07-project-type', 'step-08-scoping', 'step-09-functional', 'step-10-nonfunctional', 'step-11-polish']
inputDocuments:
  - '_spec/planning-artifacts/product-brief-arcwright-ai-2026-02-26.md'
  - '_spec/brainstorming/brainstorming-session-2026-02-26.md'
workflowType: 'prd'
documentCounts:
  briefs: 1
  research: 0
  brainstorming: 1
  projectDocs: 0
date: 2026-02-26
author: Ed
classification:
  projectType: Developer Tool (platform architecture — orchestration engine, validation framework, process runtime, SCM integration behind one CLI)
  domain: Developer Infrastructure — AI Agent Orchestration
  complexity: High (technical novelty + category creation + ecosystem dynamics)
  projectContext: greenfield
---

# Product Requirements Document - Arcwright AI

**Author:** Ed
**Date:** 2026-02-26

## Executive Summary

Arcwright AI is the third and final piece of the agentic coding stack — a deterministic orchestration shell around non-deterministic AI agents. Capable AI coding agents exist. BMAD solves context management — structured methodology that produces comprehensive planning artifacts. What's missing is **autonomous execution at velocity**: a system that takes a fully planned project, executes overnight across multiple epics and stories, validates its own output, and halts loudly on failure — so the developer can move on to the next project in their portfolio.

Arcwright AI is a LangGraph-based orchestration engine. Developers design collaboratively during the day (brainstorming, PRDs, architecture, story planning) and dispatch autonomous overnight runs that execute, validate, and produce decision-auditable output by morning. The developer controls scope down to individual story granularity — `arcwright-ai dispatch --epic EPIC-45` or `arcwright-ai dispatch --story STORY-123`. The system earns trust through transparency, not by demanding it upfront.

The platform ships as a Python CLI (`pip install arcwright-ai`) with four internal subsystems behind one entry point: an orchestration engine (LangGraph StateGraph for workflow DAG execution), a validation framework (six artifact-specific validation patterns with retry budgets), a process runtime (Claude Code SDK for stateless agent invocation), and SCM integration (git worktree isolation for parallel agent execution). BMAD is the reference methodology implementation, but the orchestration engine is methodology-agnostic — any development process can be encoded as an executable workflow definition. The long-term vision is an open-source community where every methodology trapped in someone's head or wiki becomes an executable workflow.

**Why now:** Claude Code SDK and LangGraph now provide the programmatic foundation that didn't exist 12 months ago. Each piece of the agentic coding stack was blocked until the previous piece existed — agents came first, then BMAD for context, and now the SDK and graph runtime make autonomous orchestration viable for the first time.

**Target user:** Developers running multiple projects with extensive roadmaps who need overnight execution across their portfolio — not just one project at a time. They refuse to be the manual orchestration layer between a finished plan and working code. Zero LangGraph knowledge required — LangGraph is an implementation detail, not a user-facing dependency.

### What Makes This Special

**Decision provenance as the trust mechanism.** When a developer reviews overnight results, the question isn't "did it work?" — it's "did it think correctly?" Every execution produces a complete reasoning trail: what was decided, what was rejected, and why. This is fundamentally different from black-box autonomous agents that demand trust upfront. Arcwright AI's decision logs make overnight runs *auditable*, which makes them *trustable*, which makes them *repeatable*.

**The three-piece puzzle.** Agents (capability) + BMAD (context) + Arcwright AI (velocity). Each piece was blocked until the previous piece existed. The stack is now complete. Developers with all three pieces stop babysitting agent conversations and start multiplexing their attention across their project portfolio.

**Fail loud, fail visible.** The system halts an epic on unrecoverable failure — no silent breakage, no partial work masquerading as complete. The halt summary reports what succeeded, what failed, why, and exactly where to resume. Failure handling *deepens* trust rather than eroding it.

**Methodology-agnostic platform with ecosystem dynamics.** BMAD is the reference implementation. But the community becomes the methodology library — every non-BMAD workflow definition contributed deepens the ecosystem moat and validates the platform promise.

## Project Classification

| Dimension | Classification |
|-----------|---------------|
| **Project Type** | Developer Tool — platform architecture internally (orchestration engine, validation framework, process runtime, SCM integration behind one CLI entry point) |
| **Domain** | Developer Infrastructure — AI Agent Orchestration |
| **Complexity** | High — technical novelty at the intersection of distributed systems, workflow orchestration, and non-deterministic AI; category creation with no direct precedent; ecosystem dynamics requiring platform extensibility |
| **Project Context** | Greenfield |

## Success Criteria

### User Success

**Portfolio Freedom (primary user success metric):** The number of distinct projects with active Arcwright AI dispatches and successful story completions without a halt, per week. This measures what the product ultimately delivers: the ability to parallelize a developer's attention across their project portfolio rather than being the manual orchestration layer for one project at a time.

- **Early adoption:** 1 project with active dispatches per week
- **Integrated usage:** 2-3 projects with active dispatches per week
- **Power usage:** 4+ projects with concurrent overnight execution

**Overnight Throughput:** Stories completed per autonomous run — the headline metric measuring whether plans convert to working code without human bottlenecks.

- **Target (v1):** 5+ stories completed per overnight run for a well-planned epic
- **Stretch:** Full epic completion (8-12 stories) in a single overnight dispatch

**Trust Ramp — Observe-to-Autonomous Ratio:** The ratio of observe mode runs to autonomous runs over time. Decreasing ratio indicates growing trust.

- **Week 1:** Mostly observe mode
- **Month 1:** Primarily autonomous with occasional observe for new project types
- **Month 3+:** Observe mode only for new methodology configurations

**The "Aha!" Moment:** Waking up to completed, validated stories with clean PRs — and a decision provenance trail that answers "did it think correctly?" without needing to re-read every file changed.

### Business Success

**3-Month Gate (pass/fail):** Complete 3 real-world epics (not demos) using Arcwright AI end-to-end, with >70% validation pass rate and <30 min average failure recovery time. All critical v1 features functional and reliable. Ed is using Arcwright AI across multiple projects as the standard execution layer.

**12-Month Milestone — Community Adoption:**
- Active GitHub community with external contributors (10+ non-maintainer PRs merged)
- Non-BMAD workflow definitions submitted by community members (3+ target)
- 100+ GitHub stars, recognition in AI development tooling discussions
- Ed established as a recognized expert in AI-augmented development methodology

**24-Month Gate — Commercial Viability (pass/fail):** 5+ teams or organizations have expressed willingness to pay for hosted execution, team management, or enterprise-grade observability features.

**Strategic Ecosystem Metric:** Community workflow definitions — the single most important long-term signal. When someone builds a workflow definition for a methodology that wasn't on the roadmap, the platform has taken on a life of its own.

### Technical Success

**Validation Pass Rate:** 80%+ stories passing the full validation pipeline without human intervention. Below 60% indicates methodology artifacts or validation pipeline issues.

**False Positive Rate:** 90%+ of halts are legitimate failures. Below 80% means the pipeline is crying wolf and users will start ignoring validators.

**Cost Per Story:** API spend per completed story including validation retries. Tracked and visible per run. Target TBD after v1 benchmarking, <$2 aspirational target.

**Dispatch Frequency:** Autonomous runs per week — increasing frequency indicates the tool is becoming part of the developer's workflow. Target: daily dispatches by month 3.

### Measurable Outcomes

| KPI | Measurement | 3-Month Target | 12-Month Target |
|-----|-------------|----------------|------------------|
| **Portfolio Freedom** | Distinct projects with active dispatches/week | 2-3 (personal) | 10+ (community) |
| **Portfolio Health Score** | Avg validation pass rate weighted across all active projects | >70% across all | >80% across all |
| **Stories/Night** | Avg stories completed per autonomous run | 5+ | 8-12 (full epics) |
| **Validation Pass Rate** | % stories passing without human intervention | 70%+ | 80%+ |
| **False Positive Rate** | % of halts that were legitimate | 80%+ | 90%+ |
| **Cost per Story** | Avg API spend per completed story incl. retries | Benchmark established | Tracked and optimized |
| **Setup-to-First-Run** | Time from install to first successful run | <30 min | <20 min |
| **Failure Recovery Time** | Time from halt to successful re-dispatch | <15 min | <10 min |
| **Community Workflow Defs** | Non-BMAD methodology definitions contributed | — | 3+ |
| **External Contributors** | Non-maintainer PRs merged | — | 10+ |

## Product Scope

### MVP — Minimum Viable Product

The MVP proves the core thesis: **a single developer can dispatch a scoped unit of work to an autonomous agent pipeline that executes overnight, validates its own output, and halts loudly on failure — ready for human review by morning.**

| # | Capability | Description |
|---|-----------|-------------|
| 1 | **Orchestration engine** | LangGraph StateGraph — deterministic shell around agent execution |
| 2 | **Sequential pipeline** | Stories execute one at a time in dependency order |
| 3 | **V3 reflexion validation** | Agent self-evaluates against acceptance criteria, retries on failure |
| 4 | **V6 invariant validation** | Static checks (file exists, schema valid, naming conventions) |
| 5 | **Decision provenance** | Structured logging of every significant implementation choice as markdown files in `.arcwright-ai/runs/<run-id>/provenance/` |
| 6 | **Halt-and-notify** | System halts on max retry failure with structured failure report. Never silently produces bad output. |
| 7 | **Claude Code SDK integration** | Stateless agent invocation — SDK called per story, no persistent agent state |
| 8 | **Git worktree isolation** | Each story gets its own worktree; primary safety boundary |
| 9 | **BMAD context injection** | Answerer reads BMAD artifacts (PRD, architecture, story ACs) and injects context into agent prompts |
| 10 | **`--resume` on epic dispatch** | Re-dispatch a halted epic, skipping completed stories |
| 11 | **Cost tracking** | Per-story and per-run cost embedded in `arcwright-ai status` output and run summary files. Tracking only — no enforcement in MVP. |

**MVP Exit Criteria:**
- 3 real-world BMAD epics dispatched and completed overnight
- V3 reflexion + V6 invariant validation passing on all 3
- Decision provenance logs produced for all 3 epics and used by the developer to assess correctness without re-reading every changed file
- At least 1 halt scenario producing actionable failure report
- Cost per story logged and within acceptable range
- Setup-to-first-run under 30 minutes

**Open Spikes (must resolve during MVP):**

| Spike | Timebox | Question | Resolution Criteria |
|-------|---------|----------|---------------------|
| **LangGraph Checkpointing** | 1 week | Can we resume a failed pipeline from the last successful step? | Prototype demonstrates resume from checkpoint |
| **Abstraction Layer Feasibility** | 1 week | Can the orchestration engine accept a non-BMAD methodology definition? | Pass/fail: a second workflow definition format plugs into the engine without modifying core orchestration code |
| **Validate-Setup Spec** | Resolved | Resolved into FR27 | FR27 defines the setup-validation contract: API key, project structure, artifact presence, config validity with pass/fail per check |

### Growth Features (Post-MVP)

| Feature | Target | Rationale |
|---------|--------|----------|
| Observe mode | v1.1 | Trust ramp for adoption beyond the creator; architecture supports it from MVP |
| Full deterministic replay + request/response logging | v1.1 | Replay engine and logging ship together; decision provenance provides MVP debugging |
| Test harness (regression suite) | v1.1 | Synthetic BMAD project fixture with known-bad scenarios; deferred from MVP to focus on core loop |
| Cost enforcement (caps, graceful halt, retry budget) | v1.1 | Cost *tracking* in MVP; cost *enforcement* in Growth |
| Abstraction layer (methodology decoupling) | v1.1 | Validated by spike; enables non-BMAD workflows |
| LLM-based answerer fallback | v1.1 | Static rules first; LLM handles edge cases |
| V2 LLM-as-Judge validation | v1.1 | Adds depth beyond V3 + V6 |
| Resume-from-checkpoint (auto) | v1.1 | Depends on checkpointing spike |
| Multi-agent parallel execution | v1.2 | Sequential sufficient for MVP thesis |
| Parallel worktree management | v1.2 | Required only for parallel agents |
| V1 BMAD native validators + V5 ensemble | v1.2 | Full validation pipeline depth |

### Vision (Future)

| Feature | Target | Rationale |
|---------|--------|----------|
| Web UI / dashboard | v2.0 | CLI sufficient for solo dev; UI for teams |
| Multi-methodology marketplace | v2.0+ | Community-contributed workflow definitions |
| Team coordination features | v2.0+ | Multi-user dispatch, shared observability |
| Commercial hosted execution | v2.0+ | Enterprise SLA-backed infrastructure |
| Dynamic graph topology | v3.0+ | Upgrade from static DAG when patterns emerge |

> **Section relationship:** Product Scope defines *what* ships in each phase. [Project Scoping & Phased Development](#project-scoping--phased-development) defines *how* and *why* features were phased — including solo-developer constraints, timeline, risk mitigation, and the authoritative MVP CLI command list.

## User Journeys

### Journey 1: Marcus — The Overnight Dispatcher (MVP, Happy Path)

Marcus is a senior developer running three projects simultaneously. He spent Monday and Tuesday using BMAD to plan Epic 3 of his SaaS analytics platform — PRD reviewed, architecture locked, 8 stories broken out with acceptance criteria. It's Wednesday evening, 6 PM. He's tired of manually shepherding Claude through one story at a time.

He opens his terminal:

```bash
arcwright-ai dispatch --epic EPIC-3
```

The scope selector resolves all 8 stories, confirms dependencies are satisfied, and shows the execution plan. Marcus scans it — stories 3.1 through 3.8, sequential pipeline, V3 reflexion + V6 invariant validation on each. Estimated cost: ~$12. He hits enter.

He closes his laptop and goes to dinner.

At 7 AM Thursday, he opens the run summary — a generated markdown file at `.arcwright-ai/runs/RUN-2026-02-26/summary.md`. **7 of 8 stories completed.** Story 3.5 required 2 reflexion retries but passed on the third attempt. He opens the decision provenance log at `.arcwright-ai/runs/RUN-2026-02-26/provenance/story-3.5.md` — the agent chose to implement a caching layer using Redis rather than in-memory LRU. The log shows why: the acceptance criteria mentioned "persistent across restarts." The agent considered LRU, rejected it (rationale: "doesn't survive process restart"), chose Redis. Marcus reads this in 30 seconds and agrees with the reasoning.

Story 3.8 is marked complete with all validations green. He runs `arcwright-ai cost --run RUN-2026-02-26` — $9.40 total, $1.17 per story average.

He opens the PRs. Each one has the decision provenance attached. He reviews and merges in 45 minutes — faster than it would have taken him to *implement* a single story manually. By 9 AM, he's already dispatching Epic 2 of his second project.

**This journey reveals requirements for:** scope selection, sequential pipeline, V3 reflexion with retry, decision provenance logging as generated markdown files, cost tracking, CLI interface (`dispatch`, `status`, `cost`), run summary as generated markdown, PR generation with provenance attachment, `.arcwright-ai/runs/` directory structure.

---

### Journey 2: Marcus — The Halt (MVP, Failure Path)

Same Marcus, different night. He dispatches Epic 4 — 6 stories. At 7 AM he opens `.arcwright-ai/runs/RUN-2026-02-27/summary.md` and sees red: **4 stories completed, story 4.5 HALTED after 3 retries.**

The halt summary reports:

**Completed:** Stories 4.1, 4.2, 4.3, 4.4 — all validated, PRs ready for review.
**Halted:** Story 4.5 — V3 reflexion failed 3 times. The agent couldn't satisfy acceptance criterion AC-3: "API response time under 200ms for paginated queries." Each retry's reflexion log shows the agent recognized the performance issue but couldn't resolve it within the story's scope — the underlying data model needs an index that wasn't specified in the architecture.
**Not started:** Story 4.6 (depends on 4.5).
**Resume point:** Story 4.5, pre-implementation.

Marcus reads the retry history in `.arcwright-ai/runs/RUN-2026-02-27/provenance/story-4.5.md`. Retry 1: naive query, 450ms. Retry 2: added query optimization, 280ms. Retry 3: restructured join, 240ms. Still over 200ms. The agent's final reflexion note: "Performance constraint requires schema-level change (composite index on `user_id, created_at`) that is outside this story's scope."

Marcus adds the index to the architecture doc, updates story 4.5's context, and re-dispatches the epic from the failure point:

```bash
arcwright-ai dispatch --epic EPIC-4 --resume
```

The system picks up at story 4.5, skipping the 4 already-completed stories. 9 minutes later, story 4.5 passes validation at 85ms response time. Story 4.6 follows. By 10 AM, the epic is complete. Total failure recovery time: 22 minutes.

He didn't lose the 4 completed stories. He didn't re-run anything that already passed. The system told him *exactly* what went wrong and *exactly* what to fix. His trust in Arcwright AI increased — not because it succeeded, but because it failed well.

**This journey reveals requirements for:** halt-and-notify with structured failure report as generated markdown, retry history preservation in provenance logs, `--resume` flag on epic dispatch (skips completed stories), dependency-aware execution (4.6 blocked by 4.5), partial progress preservation, resume semantics (epic-level, not implicit from story dispatch).

---

### Journey 3: Marcus — The Evaluator (Growth, Trust Ramp)

Marcus has heard about Arcwright AI. He's intrigued but skeptical — he's been burned by autonomous tools that produce garbage and call it done. He installs:

```bash
pip install arcwright-ai
```

He configures `.arcwright-ai/config.yaml` with his Claude API key and points it at his existing BMAD `_spec/` directory. He runs `arcwright-ai validate-setup`:

```
✅ Claude API key: valid
✅ BMAD project structure: detected at ./_spec/
✅ Planning artifacts: PRD, architecture, epics found
✅ Story artifacts: 12 stories with acceptance criteria
✅ Arcwright AI config: valid
Ready for dispatch.
```

Setup took 12 minutes.

**But what if setup fails?** Marcus misconfigured the `_spec/` path. `validate-setup` returns:

```
❌ BMAD project structure: NOT FOUND at ./specs/
   Expected: ./_spec/ (check config.yaml -> methodology.artifacts_path)
   Found: ./specs/ directory exists but contains no BMAD artifacts
   Fix: Update .arcwright-ai/config.yaml artifacts_path or move artifacts to ./_spec/
✅ Claude API key: valid
⚠️ Cannot validate remaining checks without project structure
```

Clear error. Specific fix. He corrects the path, re-runs, gets green. Fail loud, fail visible — even in onboarding.

He picks a small scope — 2 stories from Epic 1 that he's already implemented manually. He knows what correct looks like. He runs in observe mode:

```bash
arcwright-ai dispatch --story STORY-1.1 --observe
```

He watches the orchestrator work in real time. The scope selector resolves story 1.1's artifact dependencies. The SDK invocation fires. He sees the answerer handle 3 BMAD prompts using static rules — file lookups for the architecture doc, config reads for naming conventions. V6 invariant checks run: file exists ✅, schema valid ✅, naming convention ✅. V3 reflexion evaluates against acceptance criteria — all 4 ACs pass.

The observe output shows exactly what *would* have been written to disk: 3 new files, 1 modified file. Marcus compares against his own implementation. The agent made different implementation choices (used a factory pattern where he used a builder), but both satisfy the acceptance criteria. The decision provenance explains why: "Factory pattern selected for extensibility — story AC-2 mentions 'support additional providers in future.'"

He runs observe mode on story 1.2. Same experience — transparent, explainable, correct. Marcus is now ready for his first real autonomous run. He picks 3 stories from Epic 2 that he hasn't implemented yet, drops the `--observe` flag, and dispatches overnight.

He's crossed the trust threshold — not because someone told him to trust it, but because he watched it think.

**This journey reveals requirements for:** `validate-setup` command with clear pass/fail per check, actionable error messages with specific fix instructions on setup failure, observe mode (full pipeline, no file writes), real-time execution output, SDK invocation visibility, answerer transparency, validation step-by-step output, file diff preview in observe mode.

---

### Journey 4: Priya — The BMAD Workflow Customizer (Growth — Post-MVP)

> **Note:** This journey validates the *need* for workflow extensibility. The actual workflow definition format and extension mechanism are first-class architecture concerns to be resolved during the architecture phase. The abstraction layer feasibility spike (timeboxed to 1 week during MVP) will validate whether this journey is technically achievable.

Priya is a BMAD power user. She's been using the standard BMAD workflows for 6 months but her team has a specific code review process: every PR must include a security checklist, and stories touching authentication must have an additional validation step that checks OWASP Top 10 compliance.

She looks at Arcwright AI's workflow definition format. The BMAD reference implementation maps BMAD's phases and steps to LangGraph nodes. She doesn't need to create a new methodology — she needs to *extend* the existing BMAD pipeline with custom validation nodes.

She copies the BMAD workflow definition and adds a new V6 invariant check: "If story tags include `auth`, run OWASP checklist validator." She adds a post-implementation step that generates the security checklist from the story's acceptance criteria.

She tests with observe mode on a single auth story. The custom validator fires, checks 8 OWASP items, flags 2 that need attention. The reflexion retry addresses both. She's satisfied.

She pushes her customized workflow definition to her team's repo. Now every overnight dispatch on their project includes the security validation automatically. The customization took an afternoon — not because the system was hard, but because she wanted to get the OWASP checklist right.

**This journey reveals requirements for:** workflow definition format that supports extension/customization, custom V6 invariant definitions, story-tag-based conditional logic, workflow definition validation (does the custom definition parse and execute correctly?), observe mode for testing customizations.

---

### Journey 5: Carlos — The Code Reviewer (MVP, Team Context)

Carlos is on Marcus's team. He doesn't operate Arcwright AI directly — Marcus dispatches the runs. But every morning, Carlos's GitHub notifications have 3-5 PRs from overnight runs.

These are not ordinary PRs. Each one has a **Decision Provenance** section: a structured log of every significant implementation choice the agent made, with alternatives considered and rationale. Carlos doesn't need to reverse-engineer *why* the code looks the way it does — the reasoning is right there.

He opens PR #147 — story 3.3, implementing a notification service. The provenance log shows 4 decisions:
1. **Transport:** Chose WebSocket over polling (rationale: "real-time requirement in AC-1")
2. **Queue:** Chose in-process queue over Redis (rationale: "MVP scope, single-instance deployment specified in architecture")
3. **Retry strategy:** Exponential backoff with 3 retries (rationale: "architecture doc specifies retry policy")
4. **Error handling:** Silent drop after retry exhaustion (rationale: "AC-4 says 'best-effort delivery'")

Carlos disagrees with decision #4 — he thinks failed notifications should be logged, not silently dropped. He leaves a PR comment referencing the provenance log: "Decision #4 — I'd prefer we log dropped notifications even if delivery is best-effort. Can we add a warn-level log line?"

The review takes 15 minutes instead of 45. The provenance didn't just explain the code — it focused the review on the decisions that matter rather than line-by-line reading.

**This journey reveals requirements for:** PR generation with decision provenance embedded, structured provenance format readable in GitHub PR view, provenance organized by decisions (not by code lines), provenance that references acceptance criteria and architecture docs by ID.

---

### Journey Requirements Summary

| Journey | Scope | Key Capabilities Revealed |
|---------|-------|---------------------------|
| **Marcus — Dispatcher** | MVP | Scope selection, sequential pipeline, V3+V6 validation, decision provenance as markdown files, cost tracking, CLI commands, run summary, PR generation |
| **Marcus — Halt** | MVP | Halt-and-notify, retry history, `--resume` flag on epic dispatch, dependency-aware execution, partial progress preservation, structured failure reports |
| **Marcus — Evaluator** | MVP | `validate-setup` with actionable errors, observe mode, real-time output, answerer transparency, file diff preview, setup failure experience |
| **Priya — Customizer** | Growth | Extensible workflow definitions, custom validators, conditional logic, workflow validation (format TBD in architecture) |
| **Carlos — Reviewer** | MVP | PR with decision provenance, structured provenance in GitHub format, decision-centric review, AC/architecture cross-references |

**Cross-cutting requirements surfaced by all journeys:**
- **Decision provenance** is the connective tissue across every journey — the trust artifact for the dispatcher, the debugging tool for the failure path, the transparency mechanism for the evaluator, and the review accelerator for the code reviewer
- **Morning review UX** — all run artifacts (summary, provenance, cost) are generated as markdown files in `.arcwright-ai/runs/<run-id>/`, not terminal output. Files are versionable, shareable, and reviewable.
- **Observe mode** appears in 3 of 5 journeys — it's the trust ramp that enables adoption
- The **CLI interface** is the sole interaction surface — it must be comprehensive and self-documenting
- **Fail loud, fail visible** extends from runtime failure (journey 2) all the way to setup failure (journey 3)

## Domain-Specific Requirements

> **Domain:** Developer Infrastructure — AI Agent Orchestration | **Complexity:** High (technical novelty, not regulatory)

### LLM Reliability & Model Constraints

| Constraint | Requirement | Configurability |
|-----------|-------------|------------------|
| **Model version pinning** | User specifies model version in project or run config; prevents mid-run behavior drift | `.arcwright-ai/config.yaml` → `model.version` |
| **Per-story token ceiling** | Soft ceiling with hard accounting — story halts before the *next* SDK invocation if cumulative token usage exceeds ceiling. Current in-flight invocation completes (may overshoot by one invocation). Fail loud, not truncate. | `.arcwright-ai/config.yaml` → `limits.tokens_per_story` |
| **Rate limit awareness** | Orchestrator implements backoff/queuing when API rate limits hit; transparent to user, logged in run output. Default: exponential backoff with jitter, starting at 1s, capping at 60s. | Built-in behavior, backoff strategy configurable |
| **Full deterministic replay** | Every LLM request/response cached in `.arcwright-ai/runs/<run-id>/replay/`. Model version + prompt hash + full response stored. Enables exact replay for debugging, regression testing, and **cost-free testing of limit enforcement and validation logic**. Replay mode serves double duty as debugging tool and test harness. | `.arcwright-ai/config.yaml` → `reproducibility` section |
| **Replay cache retention** | Replay cache has a retention policy to prevent unbounded growth of `.arcwright-ai/runs/`. Options: keep last N runs, TTL-based expiry, or manual `arcwright-ai replay --prune`. | `.arcwright-ai/config.yaml` → `reproducibility.retention` |

### Agent Sandboxing & Safety

| Constraint | Requirement |
|-----------|-------------|
| **File write boundary** | Agent CANNOT modify files outside the project's base directory. **Application-level enforcement** — all file paths validated before write. MVP does not promise OS-level isolation (chroot/container). |
| **Arcwright AI-directed vs SDK-internal ops** | Sandboxing applies to **Arcwright AI-directed file operations** (story implementation, validation artifacts). SDK-internal operations (e.g., reading `~/.config/` for Claude SDK config) are allowed and not controllable by Arcwright AI. This distinction must be explicit in implementation. |
| **Temp file handling** | Temporary files written to `.arcwright-ai/tmp/`, auto-added to `.gitignore`. **Cleaned up at story completion** (success or halt). Temp files are inspectable in the worktree before worktree disposal for debugging purposes. Temp files never survive past worktree disposal. |
| **Worktree isolation** | Each story executes in its own git worktree; worktree provides the primary isolation boundary |
| **Validation failure → disposable worktree** | If validation fails after max retries, worktree is abandoned. Can be recreated from clean state on `--resume` |
| **No external access** | Agent has no Arcwright AI-directed access to files outside the project base directory — no `~/.ssh`, no `/etc`, no sibling projects |

### SCM Integration

| Concern | Requirement |
|---------|-------------|
| **Merge conflict strategy (Growth)** | Sequential merge ordering — stories execute in parallel worktrees but merge one at a time in dependency order. Each merge triggers rebase of remaining worktrees + post-rebase re-validation (V3 + V6). **Post-rebase re-validation incurs additional API cost** — this is an expected overhead of parallel execution and should be reflected in cost estimates for Growth-phase runs. Directional choice, revisitable in architecture. |
| **Worktree cleanup** | Triple-trigger: `arcwright-ai cleanup` command (manual), automatic on next dispatch (lazy), post-merge hook (eager). **All triggers must be idempotent** — cleanup of an already-cleaned worktree is a no-op, not an error. |
| **Branch naming** | Configurable template (e.g., `arcwright-ai/epic-3/story-3.1`) via `.arcwright-ai/config.yaml` → `scm.branch_template` |

### Cost Economics

| Constraint | Requirement | Configurability |
|-----------|-------------|------------------|
| **Per-run cost cap** | Hard ceiling per run; system halts gracefully when reached (completes current story, then stops) | `.arcwright-ai/config.yaml` → `limits.cost_per_run` |
| **Retry budget** | Separate budget for V3 reflexion retries, independent of overall run budget; prevents retry amplification from silently consuming the full budget | `.arcwright-ai/config.yaml` → `limits.retry_budget` |
| **Pre-dispatch estimate** | Ballpark cost estimate shown before dispatch confirmation; not a hard commitment. Growth-phase parallel estimates should account for post-rebase re-validation overhead. | Derived from story count × average cost |

## Innovation & Novel Patterns

### Detected Innovation Areas

Arcwright AI exhibits four distinct innovation patterns, ranging from category-defining to exploratory:

#### 1. Decision Provenance as Trust Artifact (Category-Defining)

**Innovation type:** Category-defining — expected to become table stakes for agentic coding tools.

No existing AI coding tool captures the agent's decision-making process as a first-class, reviewable artifact. Current tools produce code; Arcwright AI produces code *plus the structured reasoning chain that explains every significant implementation choice, alternatives considered, and rationale linked to acceptance criteria and architecture docs*.

This is not a feature — it's the foundational trust mechanism that makes autonomous overnight execution viable. Without decision provenance, code review of AI-generated PRs devolves into line-by-line reading with no visibility into *why*. With it, review becomes decision-centric: "Do I agree with the choices the agent made?"

**Competitive implication:** As the agentic coding space matures, decision provenance will become expected. Arcwright AI's first-mover advantage is in defining the format, the granularity, and the integration patterns (PR embedding, cross-referencing to specs) that become the de facto standard.

**Growth-phase strategic opportunity:** Open-source the decision provenance *format specification* (not the implementation) to drive ecosystem adoption. If Arcwright AI's provenance format becomes the standard, it creates network effects — code review tools integrate with it, team knowledge bases index it, compliance tooling references it for audit trails of AI-generated code. This is the Docker playbook: open the standard, own the tooling.

#### 2. Deterministic Shell Pattern (Architectural Contribution)

**Innovation type:** Publishable architectural pattern — ecosystem contribution, not proprietary advantage.

The insight that non-deterministic AI agents can be wrapped in a deterministic state machine that guarantees behavioral contracts:
- **Halt guarantee:** If the agent can't satisfy acceptance criteria after N retries, the system halts — never silently produces bad output
- **Validation contracts:** V3 reflexion + V6 invariant checks are state machine transitions, not optional post-processing
- **Retry semantics:** Reflexion retries are graph edges, not loops — each retry is a distinct state with its own provenance

This pattern is generalizable beyond Arcwright AI. Any system that wraps AI agents in structured workflows faces the same trust problem. The deterministic shell is an architectural answer to "how do you trust autonomous AI?"

**Pattern layer vs product layer:** The architecture phase must define a clean boundary between the **pattern layer** (the generalizable deterministic shell concept, publishable, expressible without referencing LangGraph/Claude/BMAD) and the **product layer** (Arcwright AI-specific orchestration, proprietary). If the pattern can't be described without naming the stack, it's not a pattern yet — it's just architecture.

**Publication intent:** The deterministic shell pattern will be published as a standalone architectural contribution (blog post, technical paper, or open-source pattern library). The pattern description must be stack-agnostic.

#### 3. Portfolio Multiplexer (Product Innovation)

**Innovation type:** Product-level innovation — unique operational model.

"Design by day, execute by night" — treating a developer's multiple projects as a portfolio managed by a single orchestration tool. Context switching is handled by the system (each project has its own `.arcwright-ai/` config and artifact path), not by the developer. A solo developer or small team can maintain velocity across 3-5 projects simultaneously, with Arcwright AI handling the execution queue.

No existing tool frames autonomous coding as a portfolio operation. Task runners work per-project. CI/CD works per-repo. Arcwright AI works per-developer, across projects.

#### 4. Methodology-Agnostic Orchestration (Exploratory — Unvalidated)

**Innovation type:** Exploratory upside option — feasibility unknown.

The hypothesis: if the orchestration pattern works for BMAD, it can be abstracted to work for any structured software development methodology. The BMAD reference implementation proves the pattern; an abstraction layer would export it.

**Base case:** Arcwright AI ships as a BMAD-native orchestration engine — a complete, shippable product for the BMAD ecosystem. This is not a fallback; this is the default product.

**Upside case:** If the abstraction layer spike reveals clean methodology seams, the addressable market expands to any structured methodology.

**Current confidence:** Low. The abstraction layer feasibility spike (timeboxed to 1 week during MVP) will determine whether BMAD-specific assumptions are separable from the orchestration logic. Key unknowns:
- Where are the BMAD-specific seams in the context injection layer?
- Can the "answerer" (static rule engine for methodology questions) be generalized to other methodologies?
- Is the artifact structure (PRD → Architecture → Epics → Stories) BMAD-specific or universal?

**If spike doesn't produce clean seams in 1 week: park, don't abandon.** The seams may become visible after months of BMAD-native usage reveals which parts are truly BMAD-specific vs. generic. Don't close the door — just don't hold it open.

### Validation Approach

| Innovation | Validation Method | Work Type | Timeline |
|-----------|-------------------|-----------|----------|
| Decision provenance | User testing with Carlos-type reviewers — does provenance actually accelerate review? Measure review time with/without provenance. | `user-test` | MVP (requires usable CLI) |
| Deterministic shell | Functional: prove halt guarantees hold across 50+ story executions. Pattern: can someone implement this with a different stack (e.g., Temporal + GPT-4 + Scrum artifacts) and get the same trust properties? | `automated-test` (functional), `external-feedback` (pattern) | MVP (functional), Growth (pattern publication) |
| Portfolio multiplexer | Marcus-type users running 2+ projects — does portfolio management feel natural? Measure context-switch overhead. | `user-test` | MVP (requires multi-project support) |
| Methodology-agnostic | Abstraction layer spike — can we swap BMAD artifacts for a generic artifact structure without breaking the orchestrator? | `spike` | MVP spike (1 week, timeboxed) |

### Risk Mitigation

| Innovation | Risk | Mitigation |
|-----------|------|------------|
| Decision provenance | Provenance too verbose — reviewers skip it | Tiered provenance: summary (default) + detailed (expand on demand) |
| Deterministic shell | State machine too rigid — can't handle edge cases | Escape hatches for human override at any state transition |
| Portfolio multiplexer | Cross-project resource contention (API rate limits shared across projects) | Per-project rate limit budgets, queue priority |
| Methodology-agnostic | Abstraction adds latency/complexity for no user benefit | Hard timebox — if spike doesn't produce clean seams in 1 week, park and revisit after BMAD-native usage reveals natural seams |

## Developer Tool & CLI Specific Requirements

### Project-Type Overview

Arcwright AI is a hybrid **developer tool + CLI tool**: a Python package installed via `pip` that exposes both a comprehensive CLI interface and a programmatic Python API. The CLI is the primary interaction surface for users; the Python API enables programmatic and scripted orchestration.

### Command Structure

#### MVP Commands

| Command | Purpose |
|---------|--------|
| `arcwright-ai init` | Scaffold `.arcwright-ai/` directory, generate default config, add `.arcwright-ai/tmp/` and `.arcwright-ai/runs/` to `.gitignore`, detect BMAD artifacts |
| `arcwright-ai dispatch --epic EPIC-N` | Dispatch full epic execution |
| `arcwright-ai dispatch --epic EPIC-N --resume` | Resume halted epic from failure point |
| `arcwright-ai dispatch --story STORY-N.N` | Dispatch single story |
| `arcwright-ai validate-setup` | Validate config, API key, project structure |
| `arcwright-ai status [--run RUN-ID]` | Current/last run status (or specific run), includes cost summary |
| `arcwright-ai cleanup` | Manual worktree cleanup |

#### Growth Commands

| Command | Purpose |
|---------|--------|
| `arcwright-ai dispatch ... --observe` | Observe mode — full pipeline, no file writes |
| `arcwright-ai cost --run RUN-ID` | Standalone cost breakdown for a run |
| `arcwright-ai replay --run RUN-ID` | Replay a cached run (deterministic) |
| `arcwright-ai replay --prune` | Prune old replay caches per retention policy |
| `... --format json` | Machine-readable output for all informational commands |

**Exit codes:**
- `0` — success
- `1` — general error
- `2` — validation failure (story failed after max retries)
- `3` — cost cap reached (graceful halt)
- `4` — configuration error
- `5` — timeout (story exceeded time limit)

All commands composable in shell scripts: `arcwright-ai dispatch --epic EPIC-3 && notify-slack "done"`

**Story timeout:** Token ceiling serves as the primary implicit timeout (a story that burns tokens without converging will hit the ceiling). Additionally, an explicit per-story wall-clock timeout is configurable (`.arcwright-ai/config.yaml` → `limits.timeout_per_story`). When either limit is hit, the story halts with exit code 5 and is marked as timed out in the run summary.

### Output Formats

| Context | Default Format | Alternative |
|---------|---------------|-------------|
| **Run artifacts** (summary, provenance, cost) | Generated markdown files in `.arcwright-ai/runs/<run-id>/` | N/A — always files |
| **CLI command output** (`status`, `cost`, `validate-setup`) | Human-readable plain text | `--format json` for machine-readable output |
| **Observe mode output** | Real-time streaming text to terminal | `--format json` for structured event stream |

The `--format` flag supports: `text` (default), `json`. Scriptability requires predictable JSON output for all informational commands.

### Configuration Schema

**Two-tier configuration with env var override:**

**Precedence chain:** env var > project config > global config > defaults

| Level | Path | Purpose |
|-------|------|----------|
| **Environment variables** | `ARCWRIGHT_AI_API_KEY`, `ARCWRIGHT_AI_MODEL_VERSION`, etc. | CI/CD pipelines, shared team keys, ephemeral overrides |
| **Global** | `~/.arcwright-ai/config.yaml` | API keys, default model version, global limits, cross-project defaults |
| **Project** | `.arcwright-ai/config.yaml` | Project-specific overrides: methodology artifacts path, branch template, per-story token ceiling, cost caps, reproducibility settings |

**Merge semantics:** Env vars override project config, which overrides global config, which overrides built-in defaults. API keys accepted via env var (`ARCWRIGHT_AI_API_KEY`) or global config (never committed to repo). Project config is committable and shareable.

**Config validation behavior:**
- Unknown key → **warning** (not error — forward compatibility for config fields added in future versions)
- Missing required key → **error** with specific "missing field: X" message and fix instruction
- Invalid value type → **error** with expected vs actual type

**Config sections:**
```yaml
# ~/.arcwright-ai/config.yaml (global)
api:
  claude_api_key: "sk-..."    # or set ARCWRIGHT_AI_API_KEY env var
model:
  version: "claude-sonnet-4-20250514"
limits:
  tokens_per_story: 100000    # global default
  cost_per_run: 50.00         # global default
  timeout_per_story: 1800     # 30 minutes, global default

# .arcwright-ai/config.yaml (project)
methodology:
  artifacts_path: "./_spec"
  type: "bmad"                # reference implementation
scm:
  branch_template: "arcwright-ai/{epic}/{story}"
  default_branch: ""              # empty = auto-detect; set to "main", "develop", etc. to override
  auto_merge: false               # set true for unattended overnight dispatch → merge chain
limits:
  tokens_per_story: 80000     # project override
  cost_per_run: 25.00         # project override
  retry_budget: 10.00
  timeout_per_story: 3600     # 1 hour for complex stories
reproducibility:
  enabled: true
  retention: "last-10-runs"
```

### Shell Completion

Ships with completion scripts for **bash**, **zsh**, and **fish**. Installed automatically via `pip install arcwright-ai` using standard Python packaging hooks (e.g., `argcomplete` or Click's built-in completion). Completes commands, flags, and dynamic values (epic IDs, run IDs) where feasible.

### Python API Surface

Programmatic API for scripted and integrated use:

```python
from arcwright_ai import Orchestrator

o = Orchestrator()  # loads config from env vars + .arcwright-ai/ + ~/.arcwright-ai/
o.dispatch(epic="EPIC-3")
o.dispatch(story="STORY-3.1", observe=True)
o.status(run_id="RUN-2026-02-26")
o.cost(run_id="RUN-2026-02-26")
o.cleanup()
```

**Constructor failure behavior:** `Orchestrator()` raises `ConfigurationError` with an actionable message if no config is found, required fields are missing, or the API key is not set. Error messages match the specificity of `validate-setup` output.

**MVP scope:** Python API mirrors CLI commands 1:1. No additional programmatic-only features. CLI is a thin wrapper around the Python API (not the other way around — the API is the real interface, CLI is the surface).

**Async API (Growth-phase extensibility point):** MVP ships both sync and async interfaces (`Orchestrator` and `AsyncOrchestrator`), but only the sync CLI path is actively tested and documented. The async API is supported but not promoted in MVP — it becomes the extensibility point for Growth-phase integrations (CI/CD pipelines, Jupyter notebooks, custom dashboards).

### Installation & Distribution

| Method | Command | Scope |
|--------|---------|-------|
| PyPI | `pip install arcwright-ai` | MVP |
| Development | `pip install -e .` | MVP |
| pipx (isolated) | `pipx install arcwright-ai` | MVP (supported, not primary) |

**Python version:** 3.11+ (LangGraph requirement)

### Documentation Strategy

Generated documentation site (e.g., MkDocs or Sphinx) covering:
- CLI command reference (auto-generated from Click/argparse definitions)
- Python API reference (auto-generated from docstrings)
- Getting started guide
- Configuration reference
- User journeys as tutorials

Hosted on GitHub Pages or ReadTheDocs. `arcwright-ai --help` provides inline help for all commands (not a substitute for the docs site).

### Implementation Considerations

- **CLI framework:** Click or Typer (Python CLI frameworks with built-in completion support)
- **Architecture:** Python API is the core; CLI is a thin wrapper. This ensures programmatic and CLI use are always in sync.
- **Config parsing:** Pydantic models for config validation — fail loud on invalid config with actionable error messages
- **Async support:** Dispatch commands are inherently long-running. CLI blocks with progress output; Python API supports `async/await` for non-blocking dispatch. Async is Growth-phase extensibility — only sync path actively tested in MVP.

## Project Scoping & Phased Development

### MVP Strategy & Philosophy

**MVP Approach:** Platform MVP — prove the full deterministic orchestration loop works end-to-end with the minimum viable surface area.

**Team:** Solo developer. Every feature shipped is a feature maintained alone. Ruthless prioritization.

**MVP target:** 12-16 weeks from architecture completion.

**MVP thesis:** If one developer can dispatch an epic overnight and wake up to completed stories with decision provenance that makes review fast — the product works. Everything else is polish.

**Dogfooding checkpoint:** By week 8, Arcwright AI can dispatch a single story against its own codebase. This is both a technical milestone (core loop works) and a motivation milestone (you're using what you're building).

### MVP Feature Set (Phase 1)

**Core User Journey Supported:** Marcus — The Overnight Dispatcher (happy path + halt path)

#### Must-Have Capabilities

| # | Capability | Description |
|---|-----------|-------------|
| 1 | **Orchestration engine** | LangGraph StateGraph — deterministic shell around agent execution |
| 2 | **Sequential pipeline** | Stories execute one at a time in dependency order |
| 3 | **V3 reflexion validation** | Agent self-evaluates against acceptance criteria, retries on failure |
| 4 | **V6 invariant validation** | Static checks (file exists, schema valid, naming conventions) |
| 5 | **Decision provenance** | Structured logging of every significant implementation choice as markdown files in `.arcwright-ai/runs/<run-id>/provenance/` |
| 6 | **Halt-and-notify** | System halts on max retry failure with structured failure report. Never silently produces bad output. |
| 7 | **Claude Code SDK integration** | Stateless agent invocation — SDK called per story, no persistent agent state |
| 8 | **Git worktree isolation** | Each story gets its own worktree; primary safety boundary |
| 9 | **BMAD context injection** | Answerer reads BMAD artifacts (PRD, architecture, story ACs) and injects context into agent prompts |
| 10 | **`--resume` on epic dispatch** | Re-dispatch a halted epic, skipping completed stories |
| 11 | **Cost tracking** | Per-story and per-run cost embedded in `arcwright-ai status` output and run summary files. Tracking only — no enforcement in MVP. |

#### MVP CLI Commands

| Command | Purpose |
|---------|----------|
| `arcwright-ai init` | Scaffold `.arcwright-ai/`, generate default config, detect BMAD artifacts |
| `arcwright-ai dispatch --epic EPIC-N` | Dispatch epic execution |
| `arcwright-ai dispatch --epic EPIC-N --resume` | Resume from halt point |
| `arcwright-ai dispatch --story STORY-N.N` | Dispatch single story |
| `arcwright-ai validate-setup` | Validate config, API key, project structure |
| `arcwright-ai status` | Current/last run status with cost summary |
| `arcwright-ai cleanup` | Manual worktree cleanup |

**MVP does NOT include:** observe mode\*, `--format json`, shell completions, `arcwright-ai cost` (embedded in status), `arcwright-ai replay`, request/response logging\*, public Python API\*, async API, generated docs site, cost enforcement (caps/halt), separate retry budget, test harness (regression suite)\*.

\* **Architectural notes for deferred features:**
- **Observe mode:** The execution pipeline must be architecturally instrumentable in MVP (Growth adds the CLI flag and streaming output, not the plumbing)
- **Request/response logging:** Deferred with the replay engine. Decision provenance + halt reports provide MVP debugging visibility.
- **Python API:** Exists as the internal architecture layer in MVP — CLI is a thin wrapper around it. Not documented, tested, or promoted as a public interface until Growth.
- **Test harness:** Manual testing of known-bad scenarios during MVP development. Formalized regression suite ships in Growth with replay engine support.

**MVP output:** Plain text CLI output. Run artifacts as markdown files. README as sole documentation.

### Deferred to Growth (Phase 2)

| Feature | Rationale for Deferral |
|---------|------------------------|
| **Observe mode** | Trust ramp for new users — not needed when sole user is the creator. Essential for adoption beyond the creator. Architecture supports it from MVP. |
| **Full deterministic replay** | Replay engine (cached re-execution) built on request/response logging. Both ship together in Growth. |
| **Request/response logging** | Infrastructure for replay engine. Decision provenance provides MVP debugging. Ships with replay. |
| **`--format json`** | Scriptability is Growth — MVP users interact manually |
| **Shell completions** | Polish, not function |
| **Cost enforcement** (caps, graceful halt, retry budget) | Cost *tracking* in MVP; cost *enforcement* in Growth |
| **Public Python API** | Internal architecture in MVP; documented and tested public surface in Growth |
| **Async API** | No consumer in MVP; Growth extensibility point for CI/CD, Jupyter, dashboards |
| **Generated docs site** | README sufficient for MVP; MkDocs/Sphinx in Growth |
| **`arcwright-ai replay` command** | Ships with replay engine in Growth |
| **Parallel execution** | Sequential pipeline in MVP; parallel with merge ordering in Growth |
| **Test harness (regression suite)** | Synthetic BMAD project fixture; deferred to focus on core dispatch loop. Manual testing sufficient for MVP. |
| **Priya's customizer journey** | Workflow extensibility — Growth after BMAD-native proves the pattern |

### Deferred to Vision (Phase 3)

| Feature | Rationale |
|---------|----------|
| **Methodology-agnostic orchestration** | Parked — seams emerge after BMAD-native usage. Upside option, not commitment. |
| **Open-source provenance format spec** | Requires ecosystem adoption work — after format stabilizes in MVP/Growth |
| **Deterministic shell pattern publication** | After pattern is proven across enough real-world usage |
| **Multi-user/team dispatch coordination** | Solo-focused MVP; team features in Vision |
| **Dynamic graph topology** | Upgrade from static DAG when patterns emerge |

### Abstraction Layer Spike (MVP — 1 Week Timebox)

**Scheduled last in MVP** — after the core orchestration loop is working. Don't explore until you can dispatch.

Remains in MVP as a learning exercise, not a shipping feature. The spike answers: "Are the BMAD-specific seams visible?" If yes, note them for Growth. If no, park and revisit. Zero expectation that the spike produces shippable code.

### Risk Mitigation Strategy

**Technical Risks:**

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| LangGraph StateGraph doesn't support required state transitions | Low | Critical | Spike early — build the state machine skeleton in week 1 |
| Claude Code SDK output quality too variable for automated validation | Medium | High | V3 reflexion + V6 invariants are the mitigation. If quality is consistently low, reduce scope to simpler stories. |
| Git worktree performance at scale | Low | Medium | MVP runs 1-8 stories per epic. Scale is a Growth problem. |
| BMAD artifact parsing fragility | Medium | Medium | Strict schema validation on artifact loading — fail loud if artifacts don't match expected structure |

**Market Risks:**

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| BMAD user base too small for traction | Medium | High | Arcwright AI validates the pattern; methodology-agnostic expansion is the Growth bet |
| Competing tools emerge with similar approach | Low (near term) | Medium | Decision provenance as first-mover advantage. Ship fast. |
| Users don't trust overnight autonomous execution | High | High | Decision provenance + halt guarantees are the direct mitigation. Observe mode in Growth completes the trust ramp. |

**Resource Risks (Solo Developer):**

| Risk | Mitigation |
|------|------------|
| Scope creep | This scoping exercise. Strict MVP boundaries. No Growth features pulled forward. |
| Burnout / motivation decay | Dogfooding checkpoint at week 8. Time-boxed spikes. Using Arcwright AI to build Arcwright AI sustains motivation. |
| Single point of failure | Open-source architecture. Good README, code comments, provenance pattern docs. Bus-factor mitigation through code quality. |
| Timeline overrun | 12-16 week target with buffer. If week 12 and core loop doesn't work, cut `--resume` and ship single-story dispatch only. |

## Functional Requirements

> **Capability Contract:** Every feature in the final product must trace to an FR below. Capabilities not listed here will not exist unless explicitly added. UX, architecture, and epic breakdown all derive from this list.

### Orchestration & Execution

- **FR1:** Developer can dispatch all stories in an epic for sequential autonomous execution
- **FR2:** Developer can dispatch a single story for autonomous execution
- **FR3:** System executes stories one at a time in dependency order within an epic
- **FR4:** System halts execution when a story fails validation after maximum retries, preserving all completed work
- **FR5:** Developer can resume a halted epic from the failure point, skipping previously completed stories
- **FR6:** System creates an isolated git worktree for each story execution
- **FR7:** System cleans up worktrees via manual command, automatic on next dispatch, or post-merge hook (all idempotent)

### Validation & Quality

- **FR8:** System evaluates each story's implementation against its acceptance criteria using reflexion (V3)
- **FR9:** System retries story implementation when reflexion identifies unmet acceptance criteria, up to a configurable maximum
- **FR10:** System performs invariant checks (V6) on each story — file existence, schema validity, naming conventions
- **FR11:** System generates a structured failure report when a story halts, including retry history and the specific unmet criteria

### Decision Provenance

- **FR12:** System logs every implementation decision where the agent chose between multiple alternatives, deviated from acceptance criteria, or selected a design pattern — each logged as a provenance entry during story execution
- **FR13:** Each provenance entry includes the decision, alternatives considered, rationale, and references to acceptance criteria or architecture docs
- **FR14:** Provenance is written as markdown files in `.arcwright-ai/runs/<run-id>/provenance/`
- **FR15:** Provenance is attached to generated pull requests for code review context

### Context Injection

- **FR16:** System reads BMAD planning artifacts and injects the story's acceptance criteria, the matching architecture section, and applicable domain requirements into each agent prompt
- **FR17:** System responds with the applicable BMAD rule when the agent queries about workflow steps, artifact formats, or naming conventions (answerer component, static rule lookup)
- **FR18:** System resolves story dependencies and artifact references before agent invocation

### Agent Invocation

- **FR19:** System invokes Claude Code SDK per story with no persistent agent state between stories
- **FR20:** System enforces that agent file operations cannot modify files outside the project base directory
- **FR21:** System writes temporary files to `.arcwright-ai/tmp/`, auto-added to `.gitignore`, cleaned up at story completion
- **FR22:** System implements backoff and queuing when API rate limits are hit

### Cost & Resource Tracking

- **FR23:** System tracks token consumption and estimated cost per story and per run
- **FR24:** Developer can view cost summary as part of run status output
- **FR25:** System enforces a per-story token ceiling — halts before the next SDK invocation if cumulative tokens exceed the configured limit

### Project Setup & Configuration

- **FR26:** Developer can initialize a new Arcwright AI project via `arcwright-ai init`, which scaffolds the `.arcwright-ai/` directory, generates a default config file, adds temp/run directories to `.gitignore`, and detects existing BMAD artifacts
- **FR27:** Developer can validate project setup via `arcwright-ai validate-setup`, which checks API key, project structure, artifact presence, and config validity with pass/fail per check and actionable fix instructions on failure
- **FR28:** System loads configuration with precedence: environment variables > project config > global config > defaults
- **FR29:** System warns on unknown config keys (forward compatibility) and errors on missing required keys or invalid value types with specific messages
- **FR30:** Developer can configure model version, token ceiling, branch naming template, cost limits, timeout, and reproducibility settings

### Run Visibility

- **FR31:** Developer can check current or last run status via CLI, including completion state and cost summary
- **FR32:** System generates a run summary as a markdown file in `.arcwright-ai/runs/<run-id>/summary.md` containing story completion status, validation results, cost, and provenance references
- **FR33:** System generates structured halt reports as markdown files when execution stops due to failure, cost, or timeout

### SCM Integration

- **FR34:** System creates git branches per story using a configurable naming template
- **FR35:** System generates pull requests for completed stories with decision provenance embedded
- **FR36:** System manages worktree lifecycle — creation before story execution, disposal after validation failure
- **FR37:** System supports a configurable default branch (`scm.default_branch`) with auto-detect fallback cascade (git remote show → gh repo view → origin/HEAD → fallback "main")
- **FR38:** System fetches and fast-forward merges the remote default branch before worktree creation, ensuring stories start from the latest upstream state
- **FR39:** System optionally auto-merges PRs via `gh pr merge --squash` after creation when `scm.auto_merge` is enabled in config

## Non-Functional Requirements

### Reliability

| NFR | Requirement | Measurable Criteria |
|-----|-------------|-------------------|
| **NFR1** | System never silently produces incorrect output — every story completion path passes through V3 or V6 validation. No validation bypass paths exist in the architecture. | 0% silent failures; architectural review confirms no bypass paths |
| **NFR2** | Partial epic completion is always recoverable — completed stories are preserved, `--resume` picks up where it left off | Resume after any halt recovers 100% of completed work |
| **NFR3** | System handles unexpected SDK errors (network timeout, API 500, malformed response) gracefully — retry or halt, never crash | 0 unhandled exceptions reaching the user |
| **NFR4** | Worktree isolation prevents any story execution from corrupting the main branch or other stories' worktrees | 0 cross-contamination incidents |
| **NFR5** | Config validation catches all invalid states at startup — never fails mid-run due to bad config | All config errors surfaced during `validate-setup` or `dispatch` initialization, not during story execution |

### Security

| NFR | Requirement | Measurable Criteria |
|-----|-------------|-------------------|
| **NFR6** | API keys never written to project-level files or committed to git | 0 key exposure in any committable file |
| **NFR7** | Agent file operations cannot escape the project base directory | Path traversal attempts (e.g., `../../etc/passwd`) rejected 100% of the time |
| **NFR8** | `.arcwright-ai/tmp/` and `.arcwright-ai/runs/` added to `.gitignore` automatically on init | 0 accidental commits of temp or run data |

### Performance & Cost Efficiency

| NFR | Requirement | Measurable Criteria |
|-----|-------------|-------------------|
| **NFR9** | Orchestration overhead (orchestration engine transitions, worktree operations, validation setup) is negligible relative to story execution | Orchestration overhead < 30 seconds per story (excluding agent invocation and validation) |
| **NFR10** | Token ceiling enforcement stops spending before the next invocation, not after | Overshoot limited to a single SDK invocation's token cost |
| **NFR11** | Retry cycles (V3 reflexion) converge or halt within configured limits — no infinite retry loops | Every story terminates within max_retries × timeout_per_story |
| **NFR12a** | Cost tracking captures every SDK invocation with no missed calls | 100% of SDK invocations reflected in cost tracking (automated, testable) |
| **NFR12b** | Tracked cost is accurate relative to actual API billing | Tracked cost vs. actual invoice ≤ 10% variance (operational metric, measured post-launch) |

### Integration

| NFR | Requirement | Measurable Criteria |
|-----|-------------|-------------------|
| **NFR13** | System works with AI agent SDK version pinned in project dependencies — no implicit dependency on latest SDK | Explicit SDK version in project dependency manifest; tested against pinned version |
| **NFR14** | Git operations (worktree create/delete, branch, commit, push) work with standard git 2.25+ | No dependency on git features introduced after 2.25 (Ubuntu 20.04 floor) |
| **NFR15** | Generated PRs conform to SCM platform API format and render correctly in the platform's pull request view | Provenance sections render as valid markdown in pull request view |

### Observability

| NFR | Requirement | Measurable Criteria |
|-----|-------------|-------------------|
| **NFR16** | Every run produces a complete summary file without requiring additional commands | `summary.md` generated for 100% of runs (success, halt, and timeout) |
| **NFR17** | Decision provenance is human-readable without tooling — plain markdown, clear structure | Each provenance entry uses only markdown headings, lists, and prose; no custom formats or binary data. Readability validated by a non-author reviewer completing a provenance review within 2× the time of a standard code-only PR review. |
| **NFR18** | Halt reports contain all required diagnostic fields: (1) failing AC ID, (2) retry count + history, (3) last agent output (truncated), (4) suggested fix. Missing any field = NFR violation. | 100% of halt reports contain all 4 required fields |

### System-Wide Quality Attributes

| NFR | Requirement | Measurable Criteria |
|-----|-------------|-------------------|
| **NFR19** | All operations that may be retried or re-invoked are idempotent — repeated execution produces the same result as single execution. Includes: `--resume`, `cleanup`, `init` on existing project. | Second invocation of any re-runnable command produces identical state to first |
| **NFR20** | System completes local operations (validation, provenance, worktree) even when external services (GitHub, git remote) are unavailable. External failures surfaced as warnings, not halts. | Local story completion succeeds with no network; PR creation failure = warning in summary |
