# Pre-Upgrade Audit Report — BMAD 6.0.3 → 6.1

**Story:** 11.1 — Pre-Upgrade Audit & Backup  
**Audit Date:** 2026-03-15  
**Auditor:** Dev Agent (Amelia)  
**Audit Method:** SHA-256 hash comparison against `_bmad/_config/files-manifest.csv` + files-not-in-manifest scan

---

## Section 1: Custom Modifications

### Diff Strategy Used

Primary strategy: SHA-256 hash audit — every stock framework file was hashed and compared against the recorded hash in `_bmad/_config/files-manifest.csv`. Files in the manifest that match their recorded hash are **unmodified stock files**. Any mismatch indicates post-install modification.

Secondary scan: Walk the `_bmad/` directory tree (excluding `_memory/` and `.DS_Store`) to find files that exist on disk but are **not listed in the manifest** (extra/custom additions).

### Hash Mismatch Results (Modified Stock Files)

**2 stock framework files have been modified post-install:**

| File | Status |
|---|---|
| `_bmad/bmm/workflows/4-implementation/dev-story/checklist.md` | MODIFIED |
| `_bmad/bmm/workflows/4-implementation/dev-story/instructions.xml` | MODIFIED |

#### `checklist.md` — Nature of Change

The title was changed from the stock "Dev Story Definition of Done Checklist" to **"Enhanced Dev Story Definition of Done Checklist"**. The checklist structure has been expanded with emoji section headers (`📋`, `✅`, `🧪`, `📝`, `🔚`, `🎯`), additional validation items including a `File List` reconciliation requirement, review follow-up handling items, a `Final Validation Output` block with template variables, and a `Story Structure Compliance` item. This is a **deliberate customization** to the project's dev workflow quality gate.

#### `instructions.xml` — Nature of Change

The dev-story workflow instructions XML has been enhanced with additional workflow steps. Notable additions compared to stock:
- Step 3: Explicit "Detect review continuation and extract review context" step that checks for a "Senior Developer Review (AI)" section and "Review Follow-ups (AI)" subsection
- Step 8: Enhanced task completion validation with explicit review follow-up handling (`[AI-Review]` prefix tasks), cross-referencing the Senior Developer Review section, and a git diff audit that reconciles the File List against `git diff --name-only HEAD`
- Step 9: Git diff reconciliation table output with discrepancy detection (missing vs phantom entries), plus enhanced definition-of-done validation gate with full checklist
- Step 10: Expanded communication step with explanation offers and tip about using a different LLM for code review

These are **deliberate workflow enhancements** representing the project's evolved dev-story process. They must be preserved or re-applied after the 6.1 upgrade.

### Files Not in Manifest (Custom Additions)

**58 files** were found in `_bmad/` (excluding `_memory/`) that are not listed in the stock manifest. These fall into expected categories:

| Category | Count | Examples |
|---|---|---|
| `_config/agents/*.customize.yaml` | 20 | compiled agent customization overrides for all modules |
| `_config/bmad-help.csv` | 1 | generated help index |
| `_config/files-manifest.csv` | 1 | generated file integrity manifest |
| `_config/tool-manifest.csv` | 1 | generated tool manifest |
| `_config/ides/github-copilot.yaml` | 1 | IDE integration config |
| `bmb/agents/*.md` | 3 | compiled agent files (agent-builder, module-builder, workflow-builder) |
| `bmm/agents/*.md` | 10 | compiled agent files (analyst, architect, dev, pm, qa, qfsd, sm, tech-writer, ux-designer) |
| `bmm/workflows/4-implementation/dev-release-cycle/steps-c/*.md` | 4 | dev release cycle step files |
| Other generated workflow/data files | ~17 | various compiled workflow and data files |

### Evidence Basis for "Installer-Generated" Classification

Classification criteria used:
1. Path families align with BMAD-generated output locations (compiled agent markdown in module `agents/`, generated manifests in `_config/`, IDE integration config in `_config/ides/`).
2. Filenames follow expected generation conventions (`*.customize.yaml`, generated manifest CSVs, compiled agent mirrors) rather than ad-hoc custom naming.
3. No extra files were found in user-sidecar memory paths beyond expected `_memory/` inventory; user customizations are concentrated in known sidecar files and the 2 modified stock workflow files.
4. Install metadata and module inventory in `_bmad/_config/manifest.yaml` are consistent with the observed generated module surfaces.

**Assessment:** All 58 extra files are standard installer-generated artifacts (compiled agent files, customization overrides, IDE integration, generated manifests). None are hand-authored custom files outside the expected installer output pattern. The `_config/agents/*.customize.yaml` files may need to be re-applied after upgrade if the 6.1 installer replaces them.

### Missing Stock Files

**0 stock files are missing.** All files listed in `files-manifest.csv` are present on disk.

### Custom Modification Summary

| Assessment | Result |
|---|---|
| Modified stock files | **2** (dev-story checklist.md + instructions.xml — deliberate workflow enhancements) |
| Missing stock files | **0** |
| Extra non-manifest files | **58** (all standard installer artifacts) |
| Hand-authored customizations | **2 files** requiring preservation / re-application post-upgrade |

---

## Section 2: Sidecar Data Inventory

All files in `_bmad/_memory/` are user customizations that survive framework upgrades. The BMAD installer does **not** overwrite `_memory/` contents.

| File | Size (bytes) | Modified | Purpose |
|---|---|---|---|
| `_memory/config.yaml` | 259 | 2026-02-26T08:07:25 | User config: user_name (Ed), communication_language (English), document_output_language (English), output_folder ({project-root}/_spec) |
| `_memory/storyteller-sidecar/stories-told.md` | 206 | 2026-02-26T08:07:22 | Narrative history log (empty template — no stories recorded yet) |
| `_memory/storyteller-sidecar/story-preferences.md` | 217 | 2026-02-26T08:07:22 | User story preferences (empty template — no preferences recorded yet) |
| `_memory/tech-writer-sidecar/documentation-standards.md` | 5867 | 2026-02-26T08:07:21 | CommonMark standards, no-time-estimates rule, Mermaid diagram rules (5867 bytes — significant customization) |

**Total sidecar files:** 4 files across 3 subdirectories (config.yaml, 2 storyteller files, 1 tech-writer file)

**Key file:** `tech-writer-sidecar/documentation-standards.md` at 5867 bytes is the most significant sidecar file, containing project-specific documentation standards. Must be verified post-upgrade.

**Note on modification timestamps:** All sidecar files show modification timestamps of 2026-02-26 — the same day as the original install. None have been modified post-install, but the content of `documentation-standards.md` is a meaningful customization regardless of timestamp.

---

## Section 3: Copilot Instructions Baseline

**File:** `.github/copilot-instructions.md`  
**Hash (SHA-256):** `080248e6eee5d3f8c743f51a4861b5d64072541bced254aea5cc32e59d6fbc25`  
**Length:** 59 lines  
**Markers:** `<!-- BMAD:START -->` / `<!-- BMAD:END -->` wrapper

### Key Structural Elements

- **BMAD wrapper:** `<!-- BMAD:START -->` on line 1, `<!-- BMAD:END -->` on line 59
- **Project configuration block:** Project (Arcwright AI), User (Ed), Communication Language (English), Document Output Language (English), User Skill Level (expert), Output Folder, Planning Artifacts, Implementation Artifacts, Project Knowledge paths
- **BMAD runtime structure block:** Agent definitions, Workflow definitions, Core tasks, Core workflows, Workflow engine, Module/Core configuration, Agent manifest, Workflow manifest, Help manifest, Agent memory — all with file paths
- **Key conventions block:** 6 rules covering config loading, session variables, MD vs YAML workflow execution modes, step-based execution, save-after-each-step, project-root variable resolution
- **Agent table:** 10 agents

| Agent | Persona | Title |
|---|---|---|
| bmad-master | BMad Master | BMad Master Executor, Knowledge Custodian, and Workflow Orchestrator |
| analyst | Mary | Business Analyst |
| architect | Winston | Architect |
| dev | Amelia | Developer Agent |
| pm | John | Product Manager |
| qa | Quinn | QA Engineer |
| quick-flow-solo-dev | Barry | Quick Flow Solo Dev |
| sm | Bob | Scrum Master |
| tech-writer | Paige | Technical Writer |
| ux-designer | Sally | UX Designer |

- **Slash commands section:** "Type `/bmad-` in Copilot Chat to see all available BMAD workflows and agent activators. Agents are also available in the agents dropdown."

### Post-Upgrade Comparison Checklist

After 6.1 upgrade, verify `.github/copilot-instructions.md`:
- [ ] Still contains `<!-- BMAD:START -->` / `<!-- BMAD:END -->` markers
- [ ] Project configuration block (project name, user, languages, paths) is present and correct
- [ ] BMAD runtime structure block references updated paths (if any changed in 6.1)
- [ ] Agent table contains same 10 agents (or adds new 6.1 agents if applicable)
- [ ] Key conventions still valid (especially workflow execution mode rules)

---

## Section 4: Backup Verification

| Property | Value |
|---|---|
| Backup location | `_bmad-backup-6.0.3/` (project root) |
| Backup command | `cp -a _bmad/ _bmad-backup-6.0.3/` |
| Backup file count | **672 files** ✅ (matches baseline: 672 files) |
| Backup directory count | **150 directories** ✅ (matches baseline: 150 directories) |
| Gitignore exclusion | ✅ Confirmed — `_bmad-backup-*` pattern added to `.gitignore`; `git status` does not show backup as untracked |

### Spot-Check Results

| File | Present in Backup |
|---|---|
| `_bmad-backup-6.0.3/_config/manifest.yaml` | ✅ |
| `_bmad-backup-6.0.3/bmm/config.yaml` | ✅ |
| `_bmad-backup-6.0.3/_memory/tech-writer-sidecar/documentation-standards.md` | ✅ |
| `_bmad-backup-6.0.3/bmm/workflows/4-implementation/dev-story/checklist.md` | ✅ |
| `_bmad-backup-6.0.3/bmm/workflows/4-implementation/dev-story/instructions.xml` | ✅ |

### Rollback Instructions

If the 6.1 upgrade must be rolled back:

```bash
rm -rf _bmad && mv _bmad-backup-6.0.3 _bmad
```

This restores the complete 6.0.3 installation including all custom modifications and sidecar data.

---

## Section 5: Current Installation Metadata

| Property | Value |
|---|---|
| BMAD Version | 6.0.3 |
| Install Date | 2026-02-26T13:07:26.228Z |
| Last Updated | 2026-02-26T13:07:26.228Z |
| Total Files | 672 |
| Total Directories | 150 |
| Configured IDEs | github-copilot |

### Installed Modules

| Module | Version | Install Date | Source |
|---|---|---|---|
| core | 6.0.3 | 2026-02-26T13:07:25.557Z | built-in |
| bmm | 6.0.3 | 2026-02-26T13:07:21.505Z | built-in |
| bmb | 0.1.6 | 2026-02-26T13:07:22.396Z | external (bmad-builder) |
| cis | 0.1.8 | 2026-02-26T13:07:22.995Z | external (bmad-creative-intelligence-suite) |
| tea | 1.3.1 | 2026-02-26T13:07:23.742Z | external (bmad-method-test-architecture-enterprise) |

---

## Pre-Upgrade Readiness Checklist

- [x] Hash audit completed — 2 custom-modified stock files identified and documented
- [x] All stock files present — 0 missing
- [x] Sidecar data inventoried — 4 files, sizes and dates recorded
- [x] Copilot instructions baseline documented — 59 lines, 10 agents, structural elements recorded
- [x] Backup created at `_bmad-backup-6.0.3/` — 672 files, 150 dirs, matches baseline exactly
- [x] Backup gitignored — confirmed via `git status`
- [x] `.gitignore` updated with `_bmad-backup-*` pattern
- [x] Rollback instructions documented

**Upgrade Readiness: GO ✅** — Safe to proceed with Story 11.2 (Execute BMAD 6.1 Installation and Migration)

### Key Post-Upgrade Actions Required

1. **Re-apply dev-story checklist customization** — `_bmad/bmm/workflows/4-implementation/dev-story/checklist.md` must be re-patched with the enhanced checklist content if 6.1 overwrites it
2. **Re-apply dev-story instructions customization** — `_bmad/bmm/workflows/4-implementation/dev-story/instructions.xml` must be re-patched with enhanced review-continuation and git-diff-audit steps if 6.1 overwrites it
3. **Verify sidecar survival** — Confirm `_bmad/_memory/` contents are intact post-upgrade (especially `tech-writer-sidecar/documentation-standards.md`)
4. **Verify copilot-instructions.md** — Post-upgrade comparison against baseline documented in Section 3
