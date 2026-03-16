# Story 11.3: Post-Upgrade Verification & Development Workflow Smoke Test

Status: ready-for-dev

## Story

As the maintainer of Arcwright AI,
I want to verify that the 6.1 upgrade did not break any product functionality or development workflows,
So that I can confidently continue development using the new skills-based BMAD infrastructure.

## Acceptance Criteria (BDD)

1. **Given** BMAD 6.1 installation is complete (Story 11.2) **When** `ruff check` is executed across all source code **Then** it passes with zero issues

2. **Given** BMAD 6.1 installation is complete **When** `mypy --strict` is executed **Then** it passes with zero issues

3. **Given** BMAD 6.1 installation is complete **When** `pytest` full suite is run **Then** it passes with zero failures (confirming product code is unaffected by the `_bmad/` upgrade) — baseline: 921 passed, 544 warnings

4. **Given** BMAD 6.1 installation is complete **When** `arcwright-ai validate-setup` is run against the project **Then** it passes all checks (confirming the CLI still detects BMAD artifacts correctly)

5. **Given** BMAD 6.1 installation is complete **When** BMAD development workflows are tested under the new skills-based system **Then**:
   - `/bmad cs` (create-story) or equivalent skill can be invoked (skill entrypoint loads successfully, discovers workflow.md)
   - `/bmad ds` (dev-story) or equivalent skill can be invoked (skill entrypoint loads successfully, discovers workflow.md)
   - `/bmad cr` (code-review) or equivalent skill can be invoked (skill entrypoint loads successfully, discovers workflow.md)

6. **Given** BMAD 6.1 installation is complete **When** `_spec/` planning artifacts are inspected **Then** `prd.md`, `architecture.md`, and `epics.md` are unchanged and accessible

7. **Given** BMAD 6.1 installation is complete **When** `_spec/implementation-artifacts/sprint-status.yaml` is inspected **Then** it is unchanged (except for this story's own status update)

8. **Given** all verifications pass **When** cleanup is performed **Then** the backup directory `_bmad-backup-6.0.3/` is removed

9. **Given** this is an infrastructure-only story **When** all tasks are complete **Then** no product source code (`src/`, `tests/`) is modified

## Tasks / Subtasks

- [ ] Task 1: Product Code Quality Gate — Lint & Type Checks (AC: #1, #2)
  - [ ] 1.1: Run `cd arcwright-ai && uv run ruff check` — must report zero issues across all source files
  - [ ] 1.2: Run `cd arcwright-ai && uv run mypy --strict src/` — must report "Success: no issues found in 40 source files" (or current file count)
  - [ ] 1.3: Document exact command output for both checks as evidence

- [ ] Task 2: Product Code Quality Gate — Full Test Suite (AC: #3)
  - [ ] 2.1: Run `cd arcwright-ai && uv run pytest -q` — must report 921 passed (baseline from Story 11.2)
  - [ ] 2.2: If any test failures occur, investigate whether they are caused by `_bmad/` changes (they should NOT be — `_bmad/` is infrastructure, not imported by product code)
  - [ ] 2.3: Document exact test result line (e.g., "921 passed, 544 warnings in X.XXs")

- [ ] Task 3: CLI validate-setup Verification (AC: #4)
  - [ ] 3.1: Run `cd arcwright-ai && uv run arcwright-ai validate-setup` from the project root
  - [ ] 3.2: Verify all checks pass: BMAD project structure detection, planning artifacts presence, story artifacts presence, config schema validation
  - [ ] 3.3: The `validate-setup` command lives in `src/arcwright_ai/cli/status.py` (`validate_setup_command`) — it checks for BMAD project structure, planning artifacts (`_spec/planning-artifacts/`), story artifacts (`_spec/implementation-artifacts/`), and Arcwright AI config completeness
  - [ ] 3.4: If validate-setup reports warnings about planning artifacts or story artifacts, that's acceptable — the command uses heuristic checks on `_spec/` paths. Only hard failures (exit code ≠ 0) are blockers.
  - [ ] 3.5: Document full command output as evidence

- [ ] Task 4: BMAD Development Workflow Smoke Test (AC: #5)
  - [ ] 4.1: Verify `create-story` skill chain is functional:
    - `.github/skills/bmad-create-story/SKILL.md` exists and references `_bmad/bmm/workflows/4-implementation/create-story/workflow.md`
    - `_bmad/bmm/workflows/4-implementation/create-story/workflow.md` exists and is parseable (6.1 format)
    - `_bmad/bmm/workflows/4-implementation/create-story/template.md` exists
    - `_bmad/bmm/workflows/4-implementation/create-story/checklist.md` exists
  - [ ] 4.2: Verify `dev-story` skill chain is functional:
    - `.github/skills/bmad-dev-story/SKILL.md` exists and references `_bmad/bmm/workflows/4-implementation/dev-story/workflow.md`
    - `_bmad/bmm/workflows/4-implementation/dev-story/workflow.md` exists (6.1 format — replaces `instructions.xml`)
    - `_bmad/bmm/workflows/4-implementation/dev-story/checklist.md` exists (custom enhanced version preserved per Story 11.2)
    - Custom git diff reconciliation (Step 9 of workflow.md) is present (re-applied in Story 11.2)
  - [ ] 4.3: Verify `code-review` skill chain is functional:
    - `.github/skills/bmad-code-review/SKILL.md` exists and references `_bmad/bmm/workflows/4-implementation/code-review/workflow.md`
    - `_bmad/bmm/workflows/4-implementation/code-review/workflow.md` exists and is parseable
  - [ ] 4.4: Verify the new `edge-case-hunter` skill exists (6.1 capability):
    - `.github/skills/bmad-review-edge-case-hunter/SKILL.md` exists
  - [ ] 4.5: Document verification results for each skill chain (file existence + key content check)

- [ ] Task 5: Planning Artifacts Integrity Check (AC: #6)
  - [ ] 5.1: Verify `_spec/planning-artifacts/prd.md` exists and is non-empty
  - [ ] 5.2: Verify `_spec/planning-artifacts/architecture.md` exists and is non-empty
  - [ ] 5.3: Verify `_spec/planning-artifacts/epics.md` exists and is non-empty — confirm Epic 11 content is present (last section at line ~1398)
  - [ ] 5.4: Run `git diff -- _spec/planning-artifacts/prd.md _spec/planning-artifacts/architecture.md` — both should show zero diff against HEAD (no changes from the upgrade process). Note: `epics.md` has been modified (Epic 11 added via course correction) — this is expected and acceptable.

- [ ] Task 6: Sprint Status Integrity Check (AC: #7)
  - [ ] 6.1: Verify `_spec/implementation-artifacts/sprint-status.yaml` has not been corrupted — parse all development_status entries, confirm Epic 11 section is intact with stories 11-1 (done), 11-2 (done), 11-3 (ready-for-dev)
  - [ ] 6.2: Verify all status entries for Epics 1-10 are unchanged from before the upgrade

- [ ] Task 7: Backup Cleanup (AC: #8)
  - [ ] 7.1: Verify all prior verifications (Tasks 1-6) have passed successfully — DO NOT proceed with cleanup if any verification failed
  - [ ] 7.2: Remove backup directory: `rm -rf _bmad-backup-6.0.3/`
  - [ ] 7.3: Verify removal: `ls -d _bmad-backup-6.0.3/ 2>/dev/null || echo "CLEANUP_COMPLETE"`
  - [ ] 7.4: Remove `_bmad-backup-*` pattern from `.gitignore` (no longer needed)

- [ ] Task 8: Final No-Product-Code Verification (AC: #9)
  - [ ] 8.1: Run `git diff --stat HEAD -- src/ tests/` — must show zero changes
  - [ ] 8.2: Run `git diff --stat HEAD -- arcwright-ai/src/ arcwright-ai/tests/` — must show zero changes (alternate path check)
  - [ ] 8.3: Document the output as final evidence

## Dev Notes

### Architecture & NFR Compliance

- **NFR1 (No silent failures)**: Every verification check must produce explicit pass/fail output. Do NOT skip any check and assume it passed.
- **NFR5 (Config validation at startup)**: The `validate-setup` command (Task 3) exercises this NFR directly — it runs Pydantic validation on the project config at startup. If the BMAD upgrade somehow corrupted config paths or structure, this command will catch it.
- **No product code changes**: This story is verification-only. The only filesystem changes are: (1) removing `_bmad-backup-6.0.3/`, (2) updating `.gitignore` to remove the backup pattern, (3) updating `sprint-status.yaml` with this story's status.

### Quality Gate Baselines (From Story 11.2)

| Check | Baseline | Source |
|-------|----------|--------|
| `ruff check` | 0 issues | Story 11.2 Task 9.3 |
| `mypy --strict` | 0 issues, 40 source files | Story 11.2 Task 9.3 |
| `pytest -q` | 921 passed, 544 warnings | Story 11.2 Task 9.2 |
| `validate-setup` | All checks pass | Story 1.5 (original implementation) |

### BMAD 6.1 Architecture Change Summary

The 6.0.3 → 6.1.0 migration introduced these structural changes that the smoke test must verify:

| Aspect | 6.0.3 | 6.1.0 |
|--------|-------|-------|
| Workflow entrypoint | `workflow.yaml` + `instructions.xml` | `workflow.md` + `bmad-skill-manifest.yaml` |
| IDE integration | Monolithic `.github/copilot-instructions.md` | Per-skill `.github/skills/<name>/SKILL.md` (65 skills) |
| New capability | N/A | `bmad-review-edge-case-hunter` |
| Module versions | core 6.0.3, bmm 6.0.3, bmb 0.1.6, cis 0.1.8, tea 1.3.1 | core 6.1.0, bmm 6.1.0, bmb 0.1.6, cis 0.1.8, tea 1.7.0 |

### Custom Modifications Preserved (From Story 11.2)

Two custom modifications were tracked through the upgrade:
1. **`dev-story/checklist.md`** — Enhanced DoD checklist with emoji sections and File List reconciliation — **preserved by installer** (bit-for-bit intact)
2. **`dev-story/instructions.xml`** → **`dev-story/workflow.md`** — Format migrated from XML to markdown. Custom **git diff reconciliation** logic was manually re-applied to Step 9 of the new `workflow.md` in Story 11.2.

Task 4.2 must verify that the Step 9 git diff reconciliation is still present in the current `workflow.md`.

### Backup Removal Safety

The backup at `_bmad-backup-6.0.3/` should ONLY be removed after ALL verifications pass (Tasks 1-6). If any verification fails:
- **DO NOT remove the backup**
- **Document the failure** in this story file
- **Assess whether rollback is needed**: `rm -rf _bmad && mv _bmad-backup-6.0.3 _bmad`

### .gitignore Cleanup

The `_bmad-backup-*` pattern was added to `.gitignore` in Story 11.1 (line ~206). After backup removal, this pattern should be removed since it's no longer needed. However, this is a minor cleanup — if the line remains, it's harmless.

### Working Tree Context

Current uncommitted changes in the working tree (from prior stories):
- `.github/copilot-instructions.md` — DELETED (replaced by `.github/skills/` per 6.1)
- `.gitignore` — Modified (backup pattern added by 11.1, installer entries added by 11.2)
- `README.md`, `arcwright-ai/README.md` — Modified (installer + pre-existing)
- `_spec/implementation-artifacts/10-2-*`, `10-3-*` — Modified (carryover from Epic 10)
- `_spec/planning-artifacts/epics.md` — Modified (Epic 11 added via course correction)
- Various `_spec/implementation-artifacts/11-*` — New/untracked story files

None of these affect the verification tasks — they are all expected carryover from earlier stories.

### validate-setup Command Details

The `validate-setup` command is implemented at `arcwright-ai/src/arcwright_ai/cli/status.py` — function `validate_setup_command()` (line ~549). It checks:
1. BMAD project structure detection (presence of `_bmad/` or `_spec/` directories)
2. Planning artifacts (`_spec/planning-artifacts/`)
3. Story artifacts (`_spec/implementation-artifacts/`)
4. Arcwright AI config schema validation (requires API key — may show warning if not set)

Invoke with: `cd arcwright-ai && uv run arcwright-ai validate-setup`

### Project Structure Notes

- Product source code is isolated at `arcwright-ai/src/arcwright_ai/` — completely separate from `_bmad/`
- Product tests are at `arcwright-ai/tests/` — no dependency on `_bmad/` framework files
- The `_bmad/` directory is gitignored — no product code imports or references it
- All spec artifacts remain at `_spec/` — unchanged filesystem paths

### References

- [Source: _spec/planning-artifacts/epics.md — Epic 11, Story 11.3](_spec/planning-artifacts/epics.md)
- [Source: _spec/planning-artifacts/architecture.md — NFR1 (zero silent failures), NFR5 (config validation)](_spec/planning-artifacts/architecture.md)
- [Source: _spec/implementation-artifacts/11-1-pre-upgrade-audit-and-backup.md — Audit baseline and backup creation](_spec/implementation-artifacts/11-1-pre-upgrade-audit-and-backup.md)
- [Source: _spec/implementation-artifacts/11-2-execute-bmad-6-1-installation-and-migration.md — Upgrade execution and custom modification tracking](_spec/implementation-artifacts/11-2-execute-bmad-6-1-installation-and-migration.md)
- [Source: arcwright-ai/src/arcwright_ai/cli/status.py — validate-setup command implementation](arcwright-ai/src/arcwright_ai/cli/status.py)

## Previous Story Intelligence

### Story 11.2 Key Learnings

- **Installer failure recovery pattern**: Story 11.2 encountered multiple installer failures (bmb module unavailability, config.yaml deletions). The dev agent recovered by stripping external modules from the manifest before retry. Lesson: always have a rollback path ready.
- **Config values silently reset**: The installer reset `user_skill_level` to `intermediate` and `project_name` to `arcwright-ai` without warning. Both were restored manually. Lesson: always verify config values after any installer-driven change.
- **Manifest corruption**: After install, the bmb manifest entry showed `version: null, source: unknown`. Fixed manually. Lesson: verify manifest integrity holistically, not just the modules being upgraded.
- **Custom file fate**: `checklist.md` was preserved bit-for-bit (installer detected it as custom). `instructions.xml` was replaced by stock `workflow.md` (expected format migration). Git diff reconciliation had to be manually re-applied to the new format.
- **Architecture change was real**: The shift from `copilot-instructions.md` monolith to `.github/skills/` was a significant structural change — 65 individual skill directories replaced one file.

### Story 11.1 Key Learnings

- **Evidence rigor**: Code review caught placeholder SHA hashes and "in progress" test claims. Every verification must include actual command output.
- **Hash audit approach works**: SHA-256 comparison against `files-manifest.csv` identified exactly 2 modified stock files.
- **Backup verification pattern**: `cp -a` preserving timestamps + file count comparison + spot-check of key files.

### Git Intelligence

Recent commits (last 5):
- `d541583` chore(story): 10.3 → review status
- `36d07cd` fix(deps): upgrade langgraph 0.6.11→1.x — CVE remediation
- `9914ab4` chore(spec): mark story 10-2 review
- `0b90e5d` fix(deps): upgrade PyJWT 2.11.0→2.12.1 — CVE remediation
- `dbe0f41` Epic 10.1: hatch-vcs dynamic versioning

**Pattern**: Project is in stable maintenance phase. All recent commits are infrastructure/dependency work. No product feature changes since v0.1.0 tag. The test suite (921 tests) has been stable across all recent changes.

## Dev Agent Record

### Agent Model Used

{{agent_model_name_version}}

### Debug Log References

### Completion Notes List

### Change Log

### File List
