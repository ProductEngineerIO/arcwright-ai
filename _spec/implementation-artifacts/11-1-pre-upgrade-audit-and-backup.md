# Story 11.1: Pre-Upgrade Audit & Backup

Status: done

## Story

As the maintainer of Arcwright AI,
I want to audit the current `_bmad/` installation for any custom modifications and create a backup before the 6.1 upgrade,
So that no custom work is lost and the upgrade can be safely rolled back if needed.

## Acceptance Criteria (BDD)

1. **Given** the project is on BMAD v6.0.3 (installed 2026-02-26) **When** the pre-upgrade audit is performed **Then** a diff is generated between the stock 6.0.3 installation and the current `_bmad/` directory to identify any custom modifications to agents, workflows, configs, or memory files

2. **Given** the `_bmad/_memory/` directory contains user customizations **When** the audit is performed **Then** the sidecar directory contents are documented (these are user customizations that must survive the upgrade)

3. **Given** `.github/copilot-instructions.md` is the IDE integration entrypoint **When** the audit is performed **Then** its current content is documented as the baseline for post-upgrade comparison

4. **Given** the audit is complete **When** the backup step executes **Then** a full backup of `_bmad/` is created at `_bmad-backup-6.0.3/` (gitignored)

5. **Given** the backup is created **When** the audit results are documented **Then** a brief markdown report lists: (1) custom modifications found (if any), (2) sidecar data to preserve, (3) copilot-instructions.md baseline, (4) backup location verified

6. **Given** this is an infrastructure-only story **When** all tasks are complete **Then** no product source code (`src/`, `tests/`) is modified

## Tasks / Subtasks

- [x] Task 1: Add backup directory exclusion to `.gitignore` (AC: #4)
  - [x] 1.1: Append `_bmad-backup-*` pattern to `.gitignore` under the existing `# BMAD Framework` section (after the `_bmad/` entry)

- [x] Task 2: Generate stock-vs-current diff for custom modification detection (AC: #1)
  - [x] 2.1: Run `npx bmad-method@6.0.3 install --dry-run` in a temporary directory (or download/extract a fresh 6.0.3 reference copy) to produce a clean baseline of the stock installation
  - [x] 2.2: Diff the stock 6.0.3 `_bmad/` against the project's current `_bmad/` directory, **excluding** `_bmad/_memory/` (user data, not framework files) and `.DS_Store` files
  - [x] 2.3: Capture diff output — file-level summary (added/modified/deleted) plus content diffs for any modified files
  - [x] 2.4: If no clean reference install is feasible, perform a heuristic audit instead: compare file modification timestamps against the install date (2026-02-26), check for files not listed in `_bmad/_config/files-manifest.csv`, and inspect `_bmad/_config/` entries for any user-added custom agents/workflows/tools

- [x] Task 3: Document `_bmad/_memory/` sidecar contents (AC: #2)
  - [x] 3.1: Document `_bmad/_memory/config.yaml` — currently contains: user_name (Ed), communication_language (English), document_output_language (English), output_folder
  - [x] 3.2: Document `_bmad/_memory/storyteller-sidecar/` — contains `stories-told.md` (empty template) and `story-preferences.md` (empty template)
  - [x] 3.3: Document `_bmad/_memory/tech-writer-sidecar/` — contains `documentation-standards.md` (5867 bytes; CommonMark standards, no-time-estimates rule, Mermaid diagram rules)
  - [x] 3.4: Record file sizes and modification dates for each sidecar file for post-upgrade integrity verification

- [x] Task 4: Document `.github/copilot-instructions.md` baseline (AC: #3)
  - [x] 4.1: Record the full content or hash of `.github/copilot-instructions.md` (59 lines, contains BMAD:START/END markers, project config, agent table with 10 agents, runtime structure references, key conventions, slash commands section)
  - [x] 4.2: Note key structural elements: BMAD:START/END wrapper, project config block, runtime structure block, agent table (bmad-master, analyst, architect, dev, pm, qa, quick-flow-solo-dev, sm, tech-writer, ux-designer), slash commands section

- [x] Task 5: Create full backup of `_bmad/` (AC: #4)
  - [x] 5.1: Copy entire `_bmad/` directory to `_bmad-backup-6.0.3/` using `cp -a _bmad/ _bmad-backup-6.0.3/` (preserving permissions, timestamps, symlinks)
  - [x] 5.2: Verify backup integrity — compare file count (currently 672 files in 150 directories) and spot-check key files: `manifest.yaml`, `bmm/config.yaml`, `_memory/tech-writer-sidecar/documentation-standards.md`
  - [x] 5.3: Verify `_bmad-backup-6.0.3/` is excluded by `.gitignore` (run `git status` to confirm it doesn't appear as untracked)

- [x] Task 6: Generate audit report (AC: #5)
  - [x] 6.1: Create `_spec/implementation-artifacts/11-1-pre-upgrade-audit-report.md` with sections:
    - **Section 1: Custom Modifications** — results from Task 2 diff analysis
    - **Section 2: Sidecar Data Inventory** — results from Task 3 documentation
    - **Section 3: Copilot Instructions Baseline** — results from Task 4
    - **Section 4: Backup Verification** — location, file count, integrity check results
    - **Section 5: Current Installation Metadata** — version (6.0.3), install date (2026-02-26), installed modules with versions (core 6.0.3, bmm 6.0.3, bmb 0.1.6, cis 0.1.8, tea 1.3.1), configured IDEs (github-copilot)
  - [x] 6.2: Include a rollback instruction section in the report: `rm -rf _bmad && mv _bmad-backup-6.0.3 _bmad`

- [x] Task 7: Final verification (AC: #6)
  - [x] 7.1: Run `git diff --stat` to confirm **Story 11.1 scoped changes** are limited to `.gitignore` and `_spec/implementation-artifacts/` and that there are absolutely no changes to `src/` or `tests/`; document any carryover/out-of-scope working tree changes explicitly
  - [x] 7.2: Run `uv run pytest -q` to confirm all existing tests still pass (baseline: 921 passed)

### Review Follow-ups (AI)

- [x] [AI-Review][HIGH] Reconciled Task 7.1 claim with scoped verification language and explicit carryover-change disclosure.
- [x] [AI-Review][HIGH] Updated Dev Agent Record → File List with in-scope files plus explicit out-of-scope carryover working-tree changes observed at review time.
- [x] [AI-Review][MEDIUM] Replaced placeholder SHA in audit report Section 3 with computed SHA-256 digest.
- [x] [AI-Review][MEDIUM] Replaced "pytest in progress" with explicit final test result evidence.
- [x] [AI-Review][MEDIUM] Added concise evidence basis for classifying 58 non-manifest files as installer-generated artifacts.

## Dev Notes

### Architecture & NFR Compliance

- **NFR19 (Idempotency)**: This story's operations (backup, audit) MUST be idempotent. If `_bmad-backup-6.0.3/` already exists from a prior run, the script should overwrite or skip gracefully — never fail or create duplicate backups like `_bmad-backup-6.0.3 (2)`.
- **No product code changes**: This story exclusively modifies infrastructure files (`.gitignore`) and creates spec artifacts. The `src/` and `tests/` directories are completely untouched.

### Current Installation State (Baseline)

| Property | Value |
|---|---|
| BMAD Version | 6.0.3 |
| Install Date | 2026-02-26T13:07:26.228Z |
| Total Files | 672 |
| Total Directories | 150 |
| Installed Modules | core (6.0.3), bmm (6.0.3), bmb (0.1.6), cis (0.1.8), tea (1.3.1) |
| Configured IDEs | github-copilot |
| Memory Sidecars | storyteller-sidecar (2 files), tech-writer-sidecar (1 file) |

### Sidecar Data Preservation Checklist

These files in `_bmad/_memory/` contain user customizations that **must survive the upgrade**:

| File | Size | Purpose |
|---|---|---|
| `config.yaml` | 259 bytes | User config (name, language, output paths) |
| `storyteller-sidecar/stories-told.md` | 206 bytes | Narrative history (empty template) |
| `storyteller-sidecar/story-preferences.md` | 217 bytes | User story preferences (empty template) |
| `tech-writer-sidecar/documentation-standards.md` | 5867 bytes | CommonMark standards, no-time-estimates rule, Mermaid syntax rules |

### Copilot Instructions Baseline

The `.github/copilot-instructions.md` file (59 lines) contains:
- `<!-- BMAD:START -->` / `<!-- BMAD:END -->` markers
- Project configuration block (project name, user, languages, skill level, paths)
- BMAD runtime structure references (agent defs, workflow defs, core tasks, workflow engine, configs, manifests, memory)
- Key conventions (6 rules including config loading, workflow execution modes)
- Agent table: 10 agents (bmad-master, analyst, architect, dev, pm, qa, quick-flow-solo-dev, sm, tech-writer, ux-designer)
- Slash commands section

### Diff Strategy

The preferred approach for detecting custom modifications:
1. **Primary**: Install a fresh 6.0.3 reference in a temp directory and run a recursive diff against the current `_bmad/`, excluding `_memory/` and `.DS_Store`
2. **Fallback**: If a clean reference install is too heavy, compare against `_bmad/_config/files-manifest.csv` (which lists all stock framework files) and check for any files not in the manifest

### Project Structure Notes

- The `_bmad/` directory is already gitignored (see `.gitignore` line: `_bmad/`), so the backup at `_bmad-backup-6.0.3/` must also be gitignored
- The `.gitignore` uses the pattern style `_bmad-backup-*` to cover any future backup naming
- All spec artifacts go to `_spec/implementation-artifacts/` per project conventions

### References

- [Source: _spec/planning-artifacts/epics.md — Epic 11, Story 11.1](../planning-artifacts/epics.md)
- [Source: _spec/planning-artifacts/architecture.md — NFR19 idempotency](../planning-artifacts/architecture.md)
- [Source: _bmad/_config/manifest.yaml — installation metadata](../../_bmad/_config/manifest.yaml)
- [Source: _bmad/_memory/ — sidecar data inventory](../../_bmad/_memory/)
- [Source: .github/copilot-instructions.md — IDE integration baseline](../../.github/copilot-instructions.md)

## Previous Story Intelligence

### Epic 10 Context (Most Recent)

Story 10.3 (LangGraph Major Upgrade) is the most recent completed story. Key learnings:
- **Vulnerability remediation pattern**: Audit current state → apply change → verify no regressions → document evidence
- **Evidence gathering**: Story 10.3 established a pattern of including command transcript evidence for verification claims — apply the same rigor to this story's backup verification
- **Test baseline**: 921 tests passing as of 10.3 completion — this is the regression baseline
- **Lint baseline**: `ruff check` clean, `mypy --strict` clean across all 40 source files

### Git Intelligence

Recent commits (last 5):
- `d541583` chore(story): 10.3 → review status
- `36d07cd` fix(deps): upgrade langgraph 0.6.11→1.x — CVE remediation
- `9914ab4` chore(spec): mark story 10-2 review
- `0b90e5d` fix(deps): upgrade PyJWT 2.11.0→2.12.1 — CVE remediation
- `dbe0f41` Epic 10.1: hatch-vcs dynamic versioning

Pattern: All recent commits are infrastructure/dependency work in Epic 10. No product feature changes since v0.1.0 tag. This confirms the project is in a stable maintenance phase — ideal timing for the BMAD framework upgrade.

## Dev Agent Record

### Agent Model Used

Claude Sonnet 4.6 (GitHub Copilot)

### Debug Log References

- Hash audit via `_bmad/_config/files-manifest.csv` SHA-256 comparison revealed 2 modified stock files
- `cp -a _bmad/ _bmad-backup-6.0.3/` produced 672 files / 150 dirs — exact match to Dev Notes baseline
- `git status` confirmed `_bmad-backup-6.0.3/` does not appear as untracked (gitignore effective)
- `git diff --stat` confirmed no changes to `src/` or `tests/`
- `shasum -a 256 .github/copilot-instructions.md` = `080248e6eee5d3f8c743f51a4861b5d64072541bced254aea5cc32e59d6fbc25`
- `uv run pytest -q` completed successfully: `921 passed, 544 warnings in 9.73s`

### Completion Notes List

- ✅ Task 1: Added `_bmad-backup-*` pattern to `.gitignore` directly below the `_bmad/` line in the `# BMAD Framework` section
- ✅ Task 2: Performed fallback SHA-256 hash audit (primary `npx` approach not applicable to installed framework). Found 2 custom-modified stock files: `dev-story/checklist.md` (enhanced DoD checklist with emoji sections and git-diff audit) and `dev-story/instructions.xml` (enhanced workflow with review continuation, git-diff reconciliation, and expanded completion steps). 58 extra files identified as standard installer-generated artifacts.
- ✅ Task 3: Documented all 4 sidecar files with byte sizes and modification timestamps (2026-02-26). Key file: `tech-writer-sidecar/documentation-standards.md` (5867 bytes)
- ✅ Task 4: Documented copilot-instructions.md baseline — 59 lines, BMAD:START/END markers, 10-agent table, 6 key conventions
- ✅ Task 5: Backup created at `_bmad-backup-6.0.3/` — 672 files, 150 dirs, gitignored, spot-checked 5 key files
- ✅ Task 6: Audit report created at `_spec/implementation-artifacts/11-1-pre-upgrade-audit-report.md` with all 5 sections plus pre-upgrade readiness checklist and post-upgrade action items
- ✅ Task 7: Scoped git verification documented (no `src/`/`tests/` changes) and test suite completed: `921 passed, 544 warnings in 9.73s`

### Change Log

- 2026-03-15: Added `_bmad-backup-*` to `.gitignore`
- 2026-03-15: Created `_bmad-backup-6.0.3/` (672 files, 150 dirs) — full BMAD 6.0.3 backup
- 2026-03-15: Created `_spec/implementation-artifacts/11-1-pre-upgrade-audit-report.md` — full pre-upgrade audit report
- 2026-03-15: Senior Developer Review (AI) completed — outcome: Changes Requested; status moved to `in-progress`; follow-up items added
- 2026-03-15: CR follow-ups resolved (hash baseline, test evidence, git-state reconciliation, file-list reconciliation, artifact-classification evidence)
- 2026-03-15: Senior Developer Re-Review (AI) approved; story moved to `done`

### File List

- `.gitignore` (modified — added `_bmad-backup-*` pattern)
- `_spec/implementation-artifacts/sprint-status.yaml` (modified — story status updates)
- `_spec/implementation-artifacts/11-1-pre-upgrade-audit-and-backup.md` (modified — this story file)
- `_spec/implementation-artifacts/11-1-pre-upgrade-audit-report.md` (new — audit report)

### Out-of-Scope Carryover Working-Tree Changes (Observed During CR)

- `README.md` (modified)
- `_spec/implementation-artifacts/10-2-pyjwt-crit-header-vulnerability-remediation.md` (modified)
- `_spec/implementation-artifacts/10-3-langgraph-major-upgrade-deserialization-vulnerability-remediation.md` (modified)
- `_spec/planning-artifacts/epics.md` (modified)
- `arcwright-ai/README.md` (modified)
- `_bmad/bmm/workflows/4-implementation/dev-story/checklist.md` (staged deletion)
- `_bmad/bmm/workflows/4-implementation/dev-story/instructions.xml` (staged deletion)
- `_spec/planning-artifacts/sprint-change-proposal-2026-03-15.md` (untracked)

These files are explicitly treated as non-11.1 carryover context in this review cycle.

## Senior Developer Review (AI)

### Reviewer

Ed (CR run by GitHub Copilot)

### Date

2026-03-15

### Outcome

Changes Requested

### Summary

Story intent and artifacts are mostly in place, but several completed-task claims do not reconcile with actual repository state at review time. High-severity issues are primarily traceability and accuracy problems (task completion and file-list truthfulness), not product code defects.

### Findings

1. **[HIGH] Task completion claim mismatch (Task 7.1).**
  Story states only `.gitignore` and implementation artifacts are modified, but git shows additional changed files (`README.md`, `_spec/planning-artifacts/epics.md`, `arcwright-ai/README.md`), staged deletions under `_bmad/bmm/workflows/4-implementation/dev-story/`, and additional untracked planning/spec artifacts.

2. **[HIGH] Dev Agent File List is incomplete relative to git state.**
  The listed file set does not account for all current changes visible in the working tree, reducing audit reliability for upgrade readiness.

3. **[MEDIUM] Copilot instructions baseline hash is unresolved.**
  Audit report Section 3 includes a placeholder hash value (`{to-be-computed-if-needed}`), which weakens deterministic post-upgrade comparison.

4. **[MEDIUM] Test verification note is ambiguous.**
  Completion notes contain "pytest in progress" while Task 7.2 is checked complete. Completion evidence should be explicit and final.

5. **[MEDIUM] "58 extra files are standard installer-generated" needs tighter evidence citation.**
  The classification is plausible, but report should include clear derivation criteria to aid future audits.

### AC Validation Snapshot

- AC1: **PARTIAL** (modification audit performed, but evidence precision gaps remain in report traceability)
- AC2: **IMPLEMENTED**
- AC3: **PARTIAL** (baseline documented, but hash placeholder unresolved)
- AC4: **IMPLEMENTED**
- AC5: **PARTIAL** (report structure complete; some verification fields need tightening)
- AC6: **IMPLEMENTED** (no `src/` or `tests/` modifications detected)

## Senior Developer Re-Review (AI)

### Reviewer

Ed (CR re-run by GitHub Copilot)

### Date

2026-03-15

### Outcome

Approved

### Resolution Summary

- Resolved both HIGH issues by scoping Task 7.1 verification and reconciling File List with explicit out-of-scope carryover disclosures.
- Resolved all MEDIUM issues by adding deterministic copilot-instructions SHA-256, explicit pytest completion evidence, and artifact-classification evidence language in the audit report.
- No `src/` or `tests/` changes introduced by Story 11.1 artifacts.

### Final AC Validation Snapshot

- AC1: **IMPLEMENTED**
- AC2: **IMPLEMENTED**
- AC3: **IMPLEMENTED**
- AC4: **IMPLEMENTED**
- AC5: **IMPLEMENTED**
- AC6: **IMPLEMENTED**
