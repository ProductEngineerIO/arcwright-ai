# Story 9.1: ScmConfig Enhancements — Default Branch & Auto-Merge Configuration

Status: todo

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

## Story

As a developer configuring Arcwright AI for my project,
I want to specify the default branch and enable auto-merge in my project config,
so that SCM operations target the correct branch and PRs merge automatically when configured.

## Acceptance Criteria (BDD)

1. **Given** `core/config.py` `ScmConfig` Pydantic model **When** inspected **Then** it has two new optional fields: `default_branch: str = ""` (empty string means auto-detect) and `auto_merge: bool = False`.

2. **Given** `default_branch` is set to a non-empty string (e.g., `"main"`, `"develop"`) in `.arcwright-ai/config.yaml` **When** `_detect_default_branch()` in `scm/pr.py` is called **Then** it returns that configured value immediately without executing any git or gh commands.

3. **Given** `default_branch` is empty or unset in config **When** `_detect_default_branch()` in `scm/pr.py` is called **Then** the existing 3-step cascade is used: `git remote show origin` → `gh repo view --json defaultBranchRef` → `git rev-parse --abbrev-ref origin/HEAD` → fallback `"main"`.

4. **Given** `auto_merge` config field **When** it defaults **Then** its value is `False`. When set to `True` in YAML, it round-trips correctly through `load_config`.

5. **Given** `_KNOWN_SECTION_FIELDS["scm"]` **When** inspected **Then** it includes `"default_branch"` and `"auto_merge"` (because `ScmConfig.model_fields` is used to derive the frozenset, this happens automatically once the fields are added to `ScmConfig`).

6. **Given** the `arcwright-ai init` config template in `cli/status.py` **When** inspected **Then** the `scm:` section includes commented-out `default_branch` and `auto_merge` fields with inline explanatory comments.

7. **Given** `_detect_default_branch()` in `scm/pr.py` **When** the function signature is updated **Then** it accepts an optional `default_branch_override: str = ""` parameter. When non-empty, return it immediately. When empty, run the existing cascade.

8. **Given** `open_pull_request()` in `scm/pr.py` **When** called **Then** it accepts an optional `default_branch: str = ""` parameter and passes it to `_detect_default_branch()` as `default_branch_override`.

9. **Given** story implementation is complete **When** `ruff check .` is run against the FULL repository **Then** zero violations.

10. **Given** story implementation is complete **When** `.venv/bin/python -m mypy --strict src/` is run **Then** zero errors.

11. **Given** all public classes and functions **When** every docstring is inspected **Then** each conforms to Google-style (Args, Returns, Raises sections where appropriate).

12. **Given** any existing tests in the full test suite **When** this story is complete **Then** no existing tests break. All existing tests continue to pass.

13. **Given** new unit tests **When** the test suite runs **Then** tests cover:
    (a) `ScmConfig` with `default_branch=""` serializes and deserializes correctly;
    (b) `ScmConfig` with `default_branch="develop"` round-trips through YAML;
    (c) `ScmConfig` with `auto_merge=True` round-trips through YAML;
    (d) `ScmConfig` with `auto_merge=False` (default) requires no explicit YAML key;
    (e) `_detect_default_branch` with `default_branch_override="develop"` returns `"develop"` immediately (no git calls);
    (f) `_detect_default_branch` with `default_branch_override=""` runs the existing cascade;
    (g) `open_pull_request` passes `default_branch` through to `_detect_default_branch`;
    (h) Unknown key warnings still work for `scm` section with the new fields present.

## Tasks / Subtasks

- [ ] Task 1: Add `default_branch` and `auto_merge` fields to `ScmConfig` (AC: #1, #4, #5)
  - [ ] 1.1: Add `default_branch: str = ""` field to `ScmConfig` with docstring explaining empty-string = auto-detect.
  - [ ] 1.2: Add `auto_merge: bool = False` field to `ScmConfig` with docstring explaining False = manual merge.
  - [ ] 1.3: Update `ScmConfig` class docstring `Attributes:` section to include both new fields.
  - [ ] 1.4: Verify `_KNOWN_SECTION_FIELDS["scm"]` auto-updates (it uses `frozenset(ScmConfig.model_fields.keys())` so it picks up new fields automatically — just verify).

- [ ] Task 2: Update `_detect_default_branch()` signature (AC: #2, #3, #7)
  - [ ] 2.1: Add `default_branch_override: str = ""` parameter to `_detect_default_branch()`.
  - [ ] 2.2: At function entry, if `default_branch_override.strip()` is non-empty, log `scm.pr.default_branch_config` event and return it immediately.
  - [ ] 2.3: Otherwise, execute the existing 3-step cascade unchanged.
  - [ ] 2.4: Update function docstring to document the new parameter.

- [ ] Task 3: Update `open_pull_request()` to accept `default_branch` (AC: #8)
  - [ ] 3.1: Add `default_branch: str = ""` keyword-only parameter to `open_pull_request()`.
  - [ ] 3.2: Pass `default_branch_override=default_branch` to `_detect_default_branch()` call.
  - [ ] 3.3: Update function docstring to document the new parameter.

- [ ] Task 4: Update `__all__` exports if needed (AC: #1)
  - [ ] 4.1: `__all__` in `scm/pr.py` already exports `open_pull_request` — verify no changes needed.
  - [ ] 4.2: `__all__` in `core/config.py` already exports `ScmConfig` — verify no changes needed.

- [ ] Task 5: Update config template in `cli/status.py` (AC: #6)
  - [ ] 5.1: In `_DEFAULT_CONFIG_YAML`, expand the `scm:` section to include:
    ```yaml
    scm:
      branch_template: "arcwright-ai/{story_slug}"
      # default_branch: ""          # empty = auto-detect; set to "main", "develop", etc.
      # auto_merge: false            # set true for unattended overnight dispatch → merge chain
    ```

- [ ] Task 6: Create unit tests for ScmConfig fields (AC: #12, #13a-d, #13h)
  - [ ] 6.1: In `tests/test_core/test_config.py` add test `test_scm_default_branch_empty_default` — verify default is `""`.
  - [ ] 6.2: Test `test_scm_default_branch_round_trips` — YAML with `default_branch: "develop"` loads correctly.
  - [ ] 6.3: Test `test_scm_auto_merge_default_false` — verify default is `False`.
  - [ ] 6.4: Test `test_scm_auto_merge_round_trips` — YAML with `auto_merge: true` loads correctly.
  - [ ] 6.5: Test `test_scm_unknown_key_warning_still_works` — verify unknown key in `scm` section triggers `UserWarning`.

- [ ] Task 7: Create unit tests for `_detect_default_branch` override (AC: #12, #13e-g)
  - [ ] 7.1: In `tests/test_scm/test_pr.py` add test `test_detect_default_branch_config_override` — pass `default_branch_override="develop"`, verify no git calls made, returns `"develop"`.
  - [ ] 7.2: Test `test_detect_default_branch_empty_override_uses_cascade` — pass `default_branch_override=""`, verify git cascade runs.
  - [ ] 7.3: Test `test_open_pull_request_passes_default_branch` — verify `open_pull_request(default_branch="develop")` calls `_detect_default_branch` with override.

- [ ] Task 8: Run quality gates (AC: #9, #10, #11, #12)
  - [ ] 8.1: `ruff check .` — zero violations against FULL repository.
  - [ ] 8.2: `ruff format --check .` — zero formatting issues.
  - [ ] 8.3: `.venv/bin/python -m mypy --strict src/` — zero errors.
  - [ ] 8.4: `pytest` — all tests pass (existing + new).
  - [ ] 8.5: Verify Google-style docstrings on all modified functions.

## Dev Notes

### Architecture & Design Context

**Package Dependency DAG**: `cli → engine → {validation, agent, context, output, scm} → core`. This story touches `core/config.py` (adding fields), `scm/pr.py` (accepting config override), and `cli/status.py` (template). All are valid DAG paths: `scm → core` and `cli → engine → scm → core`. No DAG violations.

**Decision 7 — Git Operations Strategy (Updated)**: The architecture now specifies that the default branch is "auto-detected (git remote show → gh repo view → origin/HEAD → fallback "main"); overridable via `scm.default_branch` config". This story implements the config side of that decision.

### Current State Analysis — What Already Exists

1. **`core/config.py` `ScmConfig`** (line 219):
   ```python
   class ScmConfig(ArcwrightModel):
       model_config = ConfigDict(frozen=True, extra="ignore", str_strip_whitespace=True)
       branch_template: str = "arcwright-ai/{story_slug}"
       remote: str = "origin"
   ```
   Two fields exist. This story adds `default_branch` and `auto_merge`.

2. **`_KNOWN_SECTION_FIELDS["scm"]`** (line 288): Uses `frozenset(ScmConfig.model_fields.keys())`. Adding fields to `ScmConfig` auto-updates this frozenset. **No manual update needed**.

3. **`_KNOWN_SUBSECTION_FIELDS`** (line 293): Does NOT have an `"scm"` entry. `ScmConfig` has no nested sub-models, so no subsection entry is needed. **No changes needed here**.

4. **`scm/pr.py` `_detect_default_branch()`** (line 497):
   ```python
   async def _detect_default_branch(project_root: Path, story_slug: str) -> str:
   ```
   Current signature takes `project_root` and `story_slug`. 3-step cascade: `git remote show origin` → `gh repo view` → `git rev-parse --abbrev-ref origin/HEAD` → fallback `"main"`. This story adds `default_branch_override` param.

5. **`scm/pr.py` `open_pull_request()`** (line 600): Calls `_detect_default_branch` on line 625. This story adds `default_branch: str = ""` param and threads it through.

6. **`cli/status.py` `_DEFAULT_CONFIG_YAML`** (line 64): Contains the `scm:` section with `branch_template` only. This story adds commented-out fields.

7. **`tests/test_core/test_config.py`** (650 lines): Comprehensive config tests. ScmConfig is tested in existing tests that create full RunConfig. This story adds ScmConfig-specific field tests.

8. **`tests/test_scm/test_pr.py`** (773 lines): Has tests for `_detect_default_branch` and `open_pull_request`. This story adds override-specific tests.

### Existing Code to Reuse — DO NOT REINVENT

- **`ScmConfig(ArcwrightModel)`** — Pydantic model with `frozen=True, extra="ignore"`. Just add new fields.
- **`_detect_default_branch()`** — 3-step cascade. Just add an early-return path.
- **`open_pull_request()`** — Already calls `_detect_default_branch()`. Just thread the new param.
- **Test patterns in `test_config.py`** — Use `global_config_dir`, `clean_env`, `tmp_path` fixtures. Follow existing YAML write → `load_config()` → assert pattern.
- **Test patterns in `test_pr.py`** — Use `monkeypatch.setattr` for `git` mock, `shutil.which` mock, etc.

### CRITICAL: Backward Compatibility

- `default_branch=""` and `auto_merge=False` are the defaults. Existing configs without these fields work unchanged.
- `_detect_default_branch()` with `default_branch_override=""` (default) runs the exact same cascade as before.
- `open_pull_request()` with `default_branch=""` (default) behaves identically to current implementation.
- All existing callers of `open_pull_request()` and `_detect_default_branch()` pass no new args → backward compatible.

### CRITICAL: The `commit_node` Caller

`engine/nodes.py` `commit_node` calls `open_pull_request()` on line ~1438. Story 9.3 will update this caller to pass `default_branch=state.config.scm.default_branch`. For THIS story, the `commit_node` caller is NOT modified — it continues to pass no `default_branch` argument (defaults to `""`), which triggers the existing auto-detect cascade. The wiring happens in Story 9.3.

### Files Touched

| File | Changes |
|------|---------|
| `core/config.py` | Add `default_branch`, `auto_merge` to `ScmConfig` |
| `scm/pr.py` | Add `default_branch_override` param to `_detect_default_branch`, `default_branch` param to `open_pull_request` |
| `cli/status.py` | Expand `_DEFAULT_CONFIG_YAML` `scm:` section |
| `tests/test_core/test_config.py` | New ScmConfig field tests |
| `tests/test_scm/test_pr.py` | New override tests |
