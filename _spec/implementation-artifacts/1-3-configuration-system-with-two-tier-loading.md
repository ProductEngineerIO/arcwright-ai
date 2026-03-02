# Story 1.3: Configuration System with Two-Tier Loading

Status: done

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

## Story

As a developer setting up Arcwright AI,
I want a configuration system that loads settings from environment variables, project config, and global config with proper precedence,
so that I can configure API keys, model versions, token ceilings, and project-specific settings with confidence that invalid config is caught at startup.

## Acceptance Criteria (BDD)

1. **Given** a `core/config.py` module **When** `RunConfig` is inspected **Then** it is a Pydantic model composing six sub-models: `ApiConfig` (field: `claude_api_key: str`), `ModelConfig` (field: `version: str`), `LimitsConfig` (fields: `tokens_per_story: int`, `cost_per_run: float`, `retry_budget: int`, `timeout_per_story: int`), `MethodologyConfig` (fields: `artifacts_path: str`, `type: str`), `ScmConfig` (field: `branch_template: str`), `ReproducibilityConfig` (fields: `enabled: bool`, `retention: int`).

2. **Given** `load_config()` is called with valid inputs **When** configs exist at all tiers **Then** the precedence chain is enforced: env vars (`ARCWRIGHT_*`) > project config (`.arcwright-ai/config.yaml`) > global config (`~/.arcwright-ai/config.yaml`) > built-in defaults — each tier fully overrides individual fields of any lower tier it specifies.

3. **Given** a YAML config file at either tier **When** it contains a key that is not a recognized field of `RunConfig` or its sub-models **Then** `load_config()` emits a `warnings.warn()` (category `UserWarning`) per unknown key and continues loading; no exception is raised, and the unknown key is stripped from the final config.

4. **Given** `load_config()` is called **When** a required field (`api.claude_api_key`) has no value in any tier **Then** `ConfigError` is raised with message `"Missing required field: api.claude_api_key"` and `details={"field": "api.claude_api_key", "fix": "Set ARCWRIGHT_API_CLAUDE_API_KEY environment variable or add claude_api_key to ~/.arcwright-ai/config.yaml"}`.

5. **Given** a YAML config file **When** it contains a field value of the wrong type (e.g., `limits.tokens_per_story: "not-a-number"`) **Then** `ConfigError` is raised with a message including the field path, the expected type, and the actual value (e.g., `"Invalid type for limits.tokens_per_story: expected int, got str 'not-a-number'"`).

6. **Given** a project-level config file (`.arcwright-ai/config.yaml`) **When** it contains the `api.claude_api_key` field (or any `api` section key) **Then** `ConfigError` is raised with message `"API keys must not be stored in project-level config files"` and `details={"file": str(project_config_path), "fix": "Move api.claude_api_key to ~/.arcwright-ai/config.yaml or set ARCWRIGHT_API_CLAUDE_API_KEY environment variable"}` before any merge is attempted.

7. **Given** `load_config()` is defined **When** its signature is inspected **Then** it is `load_config(project_root: Path | None = None) -> RunConfig`, accepts an optional `project_root` path, and returns a fully validated `RunConfig` instance.

8. **Given** unit tests for `core/config.py` **When** `pytest tests/test_core/test_config.py` is run **Then** all tests pass, covering: full precedence chain, env var override per field, missing required field (`ConfigError`), unknown keys (warning not error), invalid type (`ConfigError`), API key source restriction (`ConfigError` when in project config), missing config files (defaults used), global-only config (no project config), `load_config()` signature validation.

9. **Given** story implementation is complete **When** `ruff check .` is run **Then** zero violations.

10. **Given** story implementation is complete **When** `mypy --strict src/` (via `.venv/bin/python -m mypy --strict src/`) is run **Then** zero errors.

11. **Given** all public classes and functions **When** every docstring is inspected **Then** each conforms to Google-style (Args, Returns, Raises sections where appropriate).

## Tasks / Subtasks

- [x] Task 1: Implement sub-models in `core/config.py` (AC: #1, #11)
  - [x] 1.1: Define `ApiConfig` with field `claude_api_key: str` — no default (required), `model_config = ConfigDict(frozen=True, extra="ignore", str_strip_whitespace=True)` (override base to enable warning-based unknown-key handling)
  - [x] 1.2: Define `ModelConfig` with `version: str = "claude-opus-4-5"`, same `model_config` override
  - [x] 1.3: Define `LimitsConfig` with `tokens_per_story: int = 200_000`, `cost_per_run: float = 10.0`, `retry_budget: int = 3`, `timeout_per_story: int = 300` (seconds), same `model_config` override
  - [x] 1.4: Define `MethodologyConfig` with `artifacts_path: str = "_spec"`, `type: str = "bmad"`, same `model_config` override
  - [x] 1.5: Define `ScmConfig` with `branch_template: str = "arcwright/{story_slug}"`, same `model_config` override
  - [x] 1.6: Define `ReproducibilityConfig` with `enabled: bool = False`, `retention: int = 30`, same `model_config` override
  - [x] 1.7: Define `RunConfig` composing all sub-models: `api: ApiConfig`, `model: ModelConfig = Field(default_factory=ModelConfig.model_construct)` etc. — note that sub-models with required fields (ApiConfig) cannot have `default_factory`; `RunConfig` itself uses `model_config = ConfigDict(frozen=True, extra="ignore", str_strip_whitespace=True)`
  - [x] 1.8: Add `__all__` to `core/config.py` listing all public symbols

- [x] Task 2: Implement private helpers in `core/config.py` (AC: #2, #3, #5)
  - [x] 2.1: Implement `_warn_unknown_keys(data: dict[str, Any], section_name: str, known_keys: set[str]) -> None` — emits `warnings.warn(f"Unknown config key '{section_name}.{key}' will be ignored", UserWarning, stacklevel=4)` for each unrecognized key; called per section before merge
  - [x] 2.2: Implement `_deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]` — recursively merges `override` into `base`, where nested dicts are merged (not replaced), and scalar values are overridden; returns a new dict (does not mutate inputs)
  - [x] 2.3: Implement `_apply_env_overrides(merged: dict[str, Any]) -> None` — reads env vars per the `ENV_VAR_MAP` (see Task 4), applies type coercion (`int()`, `float()`, `bool` via `lower() in {"true","1","yes"}`), wraps type errors in `ConfigError` following AC #5 message format, mutates `merged` in place
  - [x] 2.4: Implement `_check_no_api_keys_in_project(data: dict[str, Any], project_config_path: Path) -> None` — checks if `data.get("api")` is a dict containing any keys; if so, raises `ConfigError` per AC #6

- [x] Task 3: Implement `load_config()` in `core/config.py` (AC: #2, #4, #6, #7)
  - [x] 3.1: Implement `load_config(project_root: Path | None = None) -> RunConfig` with exact signature from AC #7
  - [x] 3.2: Initialize `merged: dict[str, Any] = {}` as the accumulator
  - [x] 3.3: Load and merge global config — read `Path.home() / ".arcwright-ai" / "config.yaml"` if it exists using `load_yaml()` from `core.io`; call `_warn_unknown_keys()` per section; call `_deep_merge(merged, global_data)`
  - [x] 3.4: Load and merge project config — if `project_root` is not None and `.arcwright-ai/config.yaml` exists: call `_check_no_api_keys_in_project()` FIRST (before merge), then `_warn_unknown_keys()` per section, then `_deep_merge(merged, project_data)`
  - [x] 3.5: Apply env var overrides via `_apply_env_overrides(merged)`
  - [x] 3.6: Validate via Pydantic — wrap `RunConfig.model_validate(merged)` in a try/except for `pydantic.ValidationError` (imported as `PydanticValidationError`); translate to `ConfigError` with AC #4 message format for missing fields and AC #5 format for type errors
  - [x] 3.7: Return the validated `RunConfig` instance

- [x] Task 4: Add env var constants to `core/constants.py` (AC: #2)
  - [x] 4.1: Add `ENV_PREFIX: str = "ARCWRIGHT_"` and document the full env var → config field mapping as a constant comment block
  - [x] 4.2: Add individual env var name constants: `ENV_API_CLAUDE_API_KEY`, `ENV_MODEL_VERSION`, `ENV_LIMITS_TOKENS_PER_STORY`, `ENV_LIMITS_COST_PER_RUN`, `ENV_LIMITS_RETRY_BUDGET`, `ENV_LIMITS_TIMEOUT_PER_STORY`, `ENV_METHODOLOGY_ARTIFACTS_PATH`, `ENV_METHODOLOGY_TYPE`, `ENV_SCM_BRANCH_TEMPLATE`, `ENV_REPRODUCIBILITY_ENABLED`, `ENV_REPRODUCIBILITY_RETENTION`
  - [x] 4.3: Update `__all__` in `core/constants.py` with new constants (maintain alphabetical order per RUF022)
  - [x] 4.4: Add `CONFIG_FILENAME: str = "config.yaml"` and `GLOBAL_CONFIG_DIR: str = ".arcwright-ai"` constants for the config file paths

- [x] Task 5: Update `core/__init__.py` to export config symbols (AC: #1)
  - [x] 5.1: Add `from arcwright_ai.core.config import RunConfig, load_config` import
  - [x] 5.2: Add `"RunConfig"` and `"load_config"` to `__all__` in `core/__init__.py` (maintain alphabetical order)

- [x] Task 6: Write unit tests in `tests/test_core/test_config.py` (AC: #8)
  - [x] 6.1: Create `tests/test_core/test_config.py` with fixtures: `tmp_global_config` (writes a config YAML to `tmp_path/.arcwright-ai/config.yaml`), `tmp_project_config` (writes a project config to `tmp_path`), `mock_api_key_env` (sets `ARCWRIGHT_API_CLAUDE_API_KEY` via `monkeypatch`)
  - [x] 6.2: Test `test_load_config_full_precedence_chain`: set up global config with `model.version = "v-global"`, project config with `model.version = "v-project"`, env var `ARCWRIGHT_MODEL_VERSION = "v-env"` → assert final config has `v-env` (env wins)
  - [x] 6.3: Test `test_load_config_project_overrides_global`: global has `limits.retry_budget = 5`, project has `limits.retry_budget = 2`, no env var → assert `retry_budget == 2`
  - [x] 6.4: Test `test_load_config_uses_defaults_when_no_files`: no config files exist, API key set via env → assert default values for all fields (e.g., `model.version == "claude-opus-4-5"`, `limits.tokens_per_story == 200_000`)
  - [x] 6.5: Test `test_load_config_missing_api_key_raises_config_error`: no api key in any tier → `pytest.raises(ConfigError, match="Missing required field: api.claude_api_key")`
  - [x] 6.6: Test `test_load_config_unknown_key_warns`: global config YAML has extra key `foo: bar` → `pytest.warns(UserWarning, match="Unknown config key")`, no exception raised, returned config valid
  - [x] 6.7: Test `test_load_config_invalid_type_raises_config_error`: global config has `limits.tokens_per_story: "not-a-number"` → `pytest.raises(ConfigError, match="Invalid type for limits.tokens_per_story")`
  - [x] 6.8: Test `test_load_config_api_key_in_project_config_raises_config_error`: project config YAML contains `api: {claude_api_key: "sk-test"}` → `pytest.raises(ConfigError, match="API keys must not be stored in project-level config files")`
  - [x] 6.9: Test `test_load_config_global_only_no_project`: no project_root provided, global config has api key → valid RunConfig returned
  - [x] 6.10: Test `test_load_config_env_override_bool_parsing`: `ARCWRIGHT_REPRODUCIBILITY_ENABLED = "true"` → `reproducibility.enabled == True`; test with `"false"` → `False`; test with `"1"` → `True`

- [x] Task 7: Validate all quality gates (AC: #9, #10)
  - [x] 7.1: Run `ruff check .` — zero violations
  - [x] 7.2: Run `ruff format --check .` — no formatting diffs
  - [x] 7.3: Run `.venv/bin/python -m mypy --strict src/` — zero errors
  - [x] 7.4: Run `pytest tests/test_core/test_config.py -v` — all tests pass

## Dev Notes

### Critical Architecture Constraints

#### Package Dependency DAG — `core/` Must Stay Clean
```
cli → engine → {validation, agent, context, output, scm} → core
```
`core/config.py` depends on **nothing** except stdlib (`os`, `warnings`, `pathlib`, `typing`) and Pydantic, plus imports from within `core/` itself (`core.io.load_yaml`, `core.exceptions.ConfigError`). **No imports from `arcwright_ai.{cli,engine,validation,agent,context,output,scm}`** — ever. This is a blocking code review finding.

#### `from __future__ import annotations` — Required First Line
Every `.py` file must begin with `from __future__ import annotations`. This is enforced and was established in Story 1.1.

#### Pydantic ValidationError Name Collision
`arcwright_ai.core.exceptions.ValidationError` and `pydantic.ValidationError` have the same name. In `config.py`, import Pydantic's with an alias:
```python
from pydantic import ValidationError as PydanticValidationError
```
Never use the bare name `ValidationError` in config.py without one of them being aliased.

#### `extra="ignore"` Override on Config Sub-models
The `ArcwrightModel` base declares `extra="forbid"`. Config sub-models MUST override this with `extra="ignore"` because unknown-key detection is handled manually (with `warnings.warn()`) during the loading phase — before Pydantic sees the data. If you leave `extra="forbid"` on RunConfig or its sub-models, forward-compatible unknown keys will cause hard errors instead of warnings. The override pattern:
```python
from pydantic import ConfigDict

class ApiConfig(ArcwrightModel):
    model_config = ConfigDict(frozen=True, extra="ignore", str_strip_whitespace=True)
    claude_api_key: str
```

#### `__all__` Must Be Alphabetically Sorted (RUF022)
`ruff` enforces RUF022 — `__all__` lists must be in alphabetical order. This was a hard lesson from Story 1.2. Always sort.

#### `asyncio_mode = "auto"` — No `@pytest.mark.asyncio` Decorator
`pyproject.toml` sets `asyncio_mode = "auto"` — async test functions are discovered automatically. Do NOT add `@pytest.mark.asyncio`.

---

### Technical Specifications

#### `RunConfig` Sub-Model Hierarchy

```
RunConfig
├── api: ApiConfig
│   └── claude_api_key: str          # REQUIRED — no default
├── model: ModelConfig
│   └── version: str = "claude-opus-4-5"
├── limits: LimitsConfig
│   ├── tokens_per_story: int = 200_000
│   ├── cost_per_run: float = 10.0
│   ├── retry_budget: int = 3        # same as MAX_RETRIES default
│   └── timeout_per_story: int = 300 # seconds
├── methodology: MethodologyConfig
│   ├── artifacts_path: str = "_spec"
│   └── type: str = "bmad"
├── scm: ScmConfig
│   └── branch_template: str = "arcwright/{story_slug}"
└── reproducibility: ReproducibilityConfig
    ├── enabled: bool = False
    └── retention: int = 30          # days
```

#### YAML Config File Format

Both global (`~/.arcwright-ai/config.yaml`) and project (`.arcwright-ai/config.yaml`) use identical YAML structure:

```yaml
# Example ~/.arcwright-ai/config.yaml
api:
  claude_api_key: "sk-ant-..."  # Only allowed in global config (not project)

model:
  version: "claude-opus-4-5"

limits:
  tokens_per_story: 200000
  cost_per_run: 10.0
  retry_budget: 3
  timeout_per_story: 300

methodology:
  artifacts_path: "_spec"
  type: "bmad"

scm:
  branch_template: "arcwright/{story_slug}"

reproducibility:
  enabled: false
  retention: 30
```

#### Environment Variable Mapping

```python
# In core/constants.py — add these constants:
ENV_PREFIX: str = "ARCWRIGHT_"
ENV_API_CLAUDE_API_KEY: str = "ARCWRIGHT_API_CLAUDE_API_KEY"
ENV_MODEL_VERSION: str = "ARCWRIGHT_MODEL_VERSION"
ENV_LIMITS_TOKENS_PER_STORY: str = "ARCWRIGHT_LIMITS_TOKENS_PER_STORY"
ENV_LIMITS_COST_PER_RUN: str = "ARCWRIGHT_LIMITS_COST_PER_RUN"
ENV_LIMITS_RETRY_BUDGET: str = "ARCWRIGHT_LIMITS_RETRY_BUDGET"
ENV_LIMITS_TIMEOUT_PER_STORY: str = "ARCWRIGHT_LIMITS_TIMEOUT_PER_STORY"
ENV_METHODOLOGY_ARTIFACTS_PATH: str = "ARCWRIGHT_METHODOLOGY_ARTIFACTS_PATH"
ENV_METHODOLOGY_TYPE: str = "ARCWRIGHT_METHODOLOGY_TYPE"
ENV_SCM_BRANCH_TEMPLATE: str = "ARCWRIGHT_SCM_BRANCH_TEMPLATE"
ENV_REPRODUCIBILITY_ENABLED: str = "ARCWRIGHT_REPRODUCIBILITY_ENABLED"
ENV_REPRODUCIBILITY_RETENTION: str = "ARCWRIGHT_REPRODUCIBILITY_RETENTION"
```

The `_apply_env_overrides` function in `config.py` uses these constants from `core.constants` — no magic strings.

#### `load_config()` Algorithm (Step-by-Step)

```python
def load_config(project_root: Path | None = None) -> RunConfig:
    # Step 1: accumulator
    merged: dict[str, Any] = {}

    # Step 2: global config (~/.arcwright-ai/config.yaml)
    global_cfg = Path.home() / GLOBAL_CONFIG_DIR / CONFIG_FILENAME
    if global_cfg.exists():
        global_data = load_yaml(global_cfg)         # raises ConfigError on bad YAML
        _warn_unknown_keys_recursive(global_data, root=True)
        merged = _deep_merge(merged, global_data)

    # Step 3: project config (.arcwright-ai/config.yaml)
    if project_root is not None:
        project_cfg = project_root / DIR_ARCWRIGHT / CONFIG_FILENAME
        if project_cfg.exists():
            project_data = load_yaml(project_cfg)   # raises ConfigError on bad YAML
            _check_no_api_keys_in_project(project_data, project_cfg)  # raises ConfigError if api key found
            _warn_unknown_keys_recursive(project_data, root=True)
            merged = _deep_merge(merged, project_data)

    # Step 4: env var overrides
    _apply_env_overrides(merged)

    # Step 5: Pydantic validation
    try:
        return RunConfig.model_validate(merged)
    except PydanticValidationError as exc:
        _translate_pydantic_error(exc)              # always raises ConfigError
```

#### Unknown Key Detection Strategy

Pydantic `extra="ignore"` silently drops unknown keys. Config sub-models override `extra="ignore"` so Pydantic doesn't error, but we detect unknown keys BEFORE Pydantic sees the data via `_warn_unknown_keys_recursive`. Use each model's `model_fields` dict to know what keys are valid:

```python
import warnings

_KNOWN_TOP_LEVEL: frozenset[str] = frozenset(RunConfig.model_fields.keys())
_KNOWN_SECTION_FIELDS: dict[str, frozenset[str]] = {
    "api": frozenset(ApiConfig.model_fields.keys()),
    "model": frozenset(ModelConfig.model_fields.keys()),
    "limits": frozenset(LimitsConfig.model_fields.keys()),
    "methodology": frozenset(MethodologyConfig.model_fields.keys()),
    "scm": frozenset(ScmConfig.model_fields.keys()),
    "reproducibility": frozenset(ReproducibilityConfig.model_fields.keys()),
}

def _warn_unknown_keys_recursive(data: dict[str, Any], root: bool = False) -> None:
    for key in data:
        if key not in _KNOWN_TOP_LEVEL:
            warnings.warn(f"Unknown config key '{key}' will be ignored", UserWarning, stacklevel=4)
        elif isinstance(data[key], dict) and key in _KNOWN_SECTION_FIELDS:
            for subkey in data[key]:
                if subkey not in _KNOWN_SECTION_FIELDS[key]:
                    warnings.warn(
                        f"Unknown config key '{key}.{subkey}' will be ignored",
                        UserWarning, stacklevel=4,
                    )
```

#### Deep Merge Algorithm

```python
def _deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    """Recursively merge override into base. Nested dicts merged; scalars overridden."""
    result = dict(base)  # shallow copy of base
    for key, value in override.items():
        if key in result and isinstance(result[key], dict) and isinstance(value, dict):
            result[key] = _deep_merge(result[key], value)
        else:
            result[key] = value
    return result
```

#### env var `_apply_env_overrides` Implementation Pattern

```python
import os
from arcwright_ai.core.constants import (
    ENV_API_CLAUDE_API_KEY, ENV_MODEL_VERSION,
    ENV_LIMITS_TOKENS_PER_STORY, ENV_LIMITS_COST_PER_RUN,
    ENV_LIMITS_RETRY_BUDGET, ENV_LIMITS_TIMEOUT_PER_STORY,
    ENV_METHODOLOGY_ARTIFACTS_PATH, ENV_METHODOLOGY_TYPE,
    ENV_SCM_BRANCH_TEMPLATE, ENV_REPRODUCIBILITY_ENABLED,
    ENV_REPRODUCIBILITY_RETENTION,
)

def _apply_env_overrides(merged: dict[str, Any]) -> None:
    """Apply ARCWRIGHT_* env vars over the merged config dict (mutates in place)."""
    _env_set_str(merged, "api", "claude_api_key",       ENV_API_CLAUDE_API_KEY)
    _env_set_str(merged, "model", "version",             ENV_MODEL_VERSION)
    _env_set_int(merged, "limits", "tokens_per_story",   ENV_LIMITS_TOKENS_PER_STORY)
    _env_set_float(merged, "limits", "cost_per_run",     ENV_LIMITS_COST_PER_RUN)
    _env_set_int(merged, "limits", "retry_budget",       ENV_LIMITS_RETRY_BUDGET)
    _env_set_int(merged, "limits", "timeout_per_story",  ENV_LIMITS_TIMEOUT_PER_STORY)
    _env_set_str(merged, "methodology", "artifacts_path", ENV_METHODOLOGY_ARTIFACTS_PATH)
    _env_set_str(merged, "methodology", "type",           ENV_METHODOLOGY_TYPE)
    _env_set_str(merged, "scm", "branch_template",        ENV_SCM_BRANCH_TEMPLATE)
    _env_set_bool(merged, "reproducibility", "enabled",   ENV_REPRODUCIBILITY_ENABLED)
    _env_set_int(merged, "reproducibility", "retention",  ENV_REPRODUCIBILITY_RETENTION)
```

Helper functions `_env_set_str`, `_env_set_int`, `_env_set_float`, `_env_set_bool` check `os.environ.get(env_var_name)`, skip if not present, apply type coercion, and raise `ConfigError` if coercion fails. Use `merged.setdefault(section, {})[field] = value`.

#### `_translate_pydantic_error` — Error Message Formatting

Iterate over `exc.errors()` from `PydanticValidationError`. For each error:
- If `type == "missing"`: raise `ConfigError(f"Missing required field: {'.'.join(str(l) for l in error['loc'])}", details={"field": ..., "fix": ...})`
- Otherwise: raise `ConfigError(f"Invalid type for {'.'.join(...)}: expected {error['input']}", details={"errors": exc.errors()})` 

Always raise only the first error (or build a combined message). Keep it actionable.

#### NFR6: API Key Restriction Enforcement

```python
def _check_no_api_keys_in_project(data: dict[str, Any], project_config_path: Path) -> None:
    """Raise ConfigError if 'api' section appears in the project-level config."""
    if "api" in data:
        raise ConfigError(
            "API keys must not be stored in project-level config files",
            details={
                "file": str(project_config_path),
                "fix": (
                    "Move api.claude_api_key to ~/.arcwright-ai/config.yaml "
                    "or set ARCWRIGHT_API_CLAUDE_API_KEY environment variable"
                ),
            },
        )
```

Note: this checks for the presence of ANY `api` section (not just `claude_api_key`) in the project config. This is intentional — the entire `api` namespace is global-only.

---

### Previous Story Intelligence (Stories 1.1 and 1.2)

Key learnings from prior stories that directly affect this story:

1. **`__all__` sorted alphabetically** — `ruff` RUF022 enforces this. All `__all__` lists in every file must be in alphabetical order. This applies to `core/config.py` (new) and the additions to `core/constants.py` and `core/__init__.py`.

2. **All test subdirectories have `__init__.py`** — `tests/test_core/__init__.py` already exists from Story 1.1. No new directories are needed; `test_config.py` goes directly into the existing `tests/test_core/` directory.

3. **`asyncio_mode = "auto"`** — async test functions are auto-discovered. `test_config.py` does not use async tests (all I/O in config loading is sync), so this is informational only.

4. **`ArcwrightModel` is frozen** — `model_copy(update={...})` for any new instances. Config sub-models are read-only after construction.

5. **`from __future__ import annotations` as first line** — required for PEP 604 `X | None` syntax on Python 3.11.

6. **Import ordering: stdlib → third-party → local** — enforced by Ruff isort. In `config.py`, that means: `import os`, `import warnings`, `from pathlib import ...`, `from typing import ...` → `from pydantic import ...` → `from arcwright_ai.core.*`.

7. **`load_yaml` already exists in `core.io`** — reuse it for reading config YAML. It already raises `ConfigError` on bad YAML, so no duplicate error handling needed.

8. **Constants already defined in `core/constants.py`**: `DIR_ARCWRIGHT = ".arcwright-ai"` and `DIR_SPEC = "_spec"` — import and use these. `CONFIG_FILENAME` and `GLOBAL_CONFIG_DIR` will be new additions from Task 4.

9. **`types-PyYAML` in dev deps** — added in Story 1.2. No action needed; already present in `pyproject.toml`.

10. **Pydantic `ValidationError` name collision** — `arcwright_ai.core.exceptions.ValidationError` already exists. In `config.py`, alias Pydantic's via `from pydantic import ValidationError as PydanticValidationError`. This is critical — forgetting this causes a `NameError` or silently uses the wrong class at runtime.

---

### Architecture Compliance Notes

1. **`core/` depends on nothing except stdlib and Pydantic** — `config.py` may only import: `os`, `warnings`, `pathlib.Path`, `typing.*`, `pydantic.*`, and siblings within `arcwright_ai.core.*` (specifically `core.io.load_yaml`, `core.exceptions.ConfigError`, `core.constants.*`). Any import from `arcwright_ai.{cli,engine,validation,agent,context,output,scm}` is a hard violation.

2. **`load_config()` is synchronous** — Config loading happens at startup once (NFR5: "all config errors surfaced at startup/validation, never mid-run"). It uses `load_yaml()` from `core.io` which is also synchronous. Do NOT wrap in `asyncio.to_thread()` — config loading is intentionally synchronous because it must run before the event loop starts.

3. **`RunConfig` from `core/config.py` will be referenced by `engine/state.py` (Story 2.1)** — the `StoryState` model carries a `config: RunConfig` reference per the architecture. The `RunConfig` model must be importable and stable after this story. Do not introduce any circular dependency patterns.

4. **`extra="ignore"` vs `extra="forbid"` explanation** — `ArcwrightModel` base uses `extra="forbid"` as its default for all domain models (strict contract). Config models specifically override to `extra="ignore"` because the loading function manually handles unknown keys with warnings (for forward compatibility per FR29). Both behaviors are intentional and serve different contract requirements.

5. **Pydantic `model_validate()` vs constructor** — always use `RunConfig.model_validate(dict)` (not `RunConfig(**dict)`) for loading from raw YAML/dict data, as it applies validators and coercions properly.

---

### Testing Architecture Notes

File to create: `tests/test_core/test_config.py`

`tests/test_core/__init__.py` already exists from Story 1.1. Directory is ready.

**Recommended test fixture pattern using `monkeypatch` and `tmp_path`:**

```python
import os
import warnings
from pathlib import Path
import pytest
from arcwright_ai.core.config import load_config
from arcwright_ai.core.exceptions import ConfigError

@pytest.fixture
def api_key_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Ensure ARCWRIGHT_API_CLAUDE_API_KEY is set for tests that don't test missing key."""
    monkeypatch.setenv("ARCWRIGHT_API_CLAUDE_API_KEY", "test-api-key")

@pytest.fixture
def global_config_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Redirect Path.home() to tmp_path for isolation."""
    home = tmp_path / "home"
    home.mkdir()
    (home / ".arcwright-ai").mkdir()
    monkeypatch.setattr(Path, "home", staticmethod(lambda: home))
    return home / ".arcwright-ai"
```

**Key test scenarios (coverage targets):**

```python
def test_load_config_full_precedence_chain(api_key_env, global_config_dir, tmp_path, monkeypatch):
    # global sets model.version = "v-global"
    # project config sets model.version = "v-project"
    # env var sets ARCWRIGHT_MODEL_VERSION = "v-env"
    # assert config.model.version == "v-env"  (env wins)
    ...

def test_load_config_unknown_key_warns(api_key_env, global_config_dir):
    # global config YAML has top-level key "foo: bar"
    # assert warnings.warn called with UserWarning about "foo"
    # assert no exception raised
    with pytest.warns(UserWarning, match="Unknown config key 'foo'"):
        cfg = load_config()
    assert cfg.model.version  # rest of config is valid

def test_load_config_missing_api_key_raises(global_config_dir):
    # no env var, no api key anywhere
    with pytest.raises(ConfigError, match="Missing required field: api.claude_api_key"):
        load_config()

def test_load_config_api_key_in_project_config_raises(api_key_env, global_config_dir, tmp_path):
    # project .arcwright-ai/config.yaml has "api: {claude_api_key: sk-test}"
    project_root = tmp_path / "project"
    project_root.mkdir()
    (project_root / ".arcwright-ai").mkdir()
    # write project config with api section
    ...
    with pytest.raises(ConfigError, match="API keys must not be stored in project-level config files"):
        load_config(project_root=project_root)

def test_load_config_invalid_type_raises(api_key_env, global_config_dir):
    # global config has limits.tokens_per_story: "not-a-number"
    with pytest.raises(ConfigError, match="Invalid type for limits.tokens_per_story"):
        load_config()
```

**Critical test isolation rule**: every test that calls `load_config()` must either mock `Path.home()` (to avoid reading the real `~/.arcwright-ai/config.yaml`) or clear env vars that could bleed over. Use `monkeypatch.setenv`/`monkeypatch.delenv` for env vars, and redirect `Path.home()` for file system isolation. Failure to do this will cause test-order-dependent flakiness.

---

### Project Structure Notes

Files to create or modify:
- `arcwright-ai/src/arcwright_ai/core/config.py` — **replace placeholder stub** with full implementation
- `arcwright-ai/src/arcwright_ai/core/constants.py` — **update** to add env var name constants and `CONFIG_FILENAME`/`GLOBAL_CONFIG_DIR`
- `arcwright-ai/src/arcwright_ai/core/__init__.py` — **update** to re-export `RunConfig` and `load_config`
- `arcwright-ai/tests/test_core/test_config.py` — **new file**

No new directories needed. `tests/test_core/` already exists with `__init__.py`.

Working directory for all commands: `arcwright-ai/`

### References

- [Source: _spec/planning-artifacts/epics.md#Story-1.3] — story requirements and acceptance criteria
- [Source: _spec/planning-artifacts/architecture.md#Architectural-Subsystem-Map] — Subsystem #8: Configuration System (FR26-30, NFR5)
- [Source: _spec/planning-artifacts/architecture.md#Cross-Cutting-Concerns] — Cross-cutting concern #5: configuration validation at startup
- [Source: _spec/planning-artifacts/architecture.md#Package-Dependency-DAG] — `core` depends on nothing; mandatory rule
- [Source: _spec/planning-artifacts/architecture.md#Pydantic-Model-Patterns] — `ArcwrightModel` base, `model_validate()`, `model_copy()`
- [Source: _spec/planning-artifacts/architecture.md#Python-Code-Style-Patterns] — naming, `__all__`, docstrings, import ordering
- [Source: _spec/planning-artifacts/architecture.md#Testing-Patterns] — naming, isolation, `tmp_path`, `pytest.raises`, no assertion libraries
- [Source: _spec/planning-artifacts/architecture.md#Boundary-4-Application-–-File-System] — all YAML I/O through `core/io.py`
- [Source: _spec/planning-artifacts/prd.md#FR28] — precedence: env > project > global > defaults
- [Source: _spec/planning-artifacts/prd.md#FR29] — unknown keys warn, missing required error, invalid type error
- [Source: _spec/planning-artifacts/prd.md#FR30] — configurable fields: model version, token ceiling, branch naming, cost limits, timeout, reproducibility
- [Source: _spec/planning-artifacts/prd.md#NFR5] — all config errors at startup, never mid-run
- [Source: _spec/planning-artifacts/prd.md#NFR6] — API keys never written to project-level files
- [Source: _spec/implementation-artifacts/1-2-core-types-lifecycle-and-exception-hierarchy.md#Dev-Notes] — Story 1.2 patterns: `__all__` sorting, `asyncio_mode = "auto"`, import aliasing for `PydanticValidationError`
- [Source: arcwright-ai/src/arcwright_ai/core/constants.py] — existing constants to import (`DIR_ARCWRIGHT`, `DIR_SPEC`)
- [Source: arcwright-ai/src/arcwright_ai/core/io.py] — `load_yaml()` and `save_yaml()` primitives
- [Source: arcwright-ai/src/arcwright_ai/core/exceptions.py] — `ConfigError` hierarchy
- [Source: arcwright-ai/src/arcwright_ai/core/types.py] — `ArcwrightModel` base class

## Dev Agent Record

### Agent Model Used

Claude Sonnet 4.6 (GitHub Copilot)

### Debug Log References

- Fixture ordering bug: `clean_env` must run before `api_key_env` to avoid deleting the key set by `api_key_env`. Fixed by making `api_key_env` fixture depend on `clean_env`.
- Pydantic reports `loc=("api",)` (not `("api","claude_api_key")`) when the entire `api` dict is absent from `merged`. `_translate_pydantic_error` special-cases both `"api"` and `"api.claude_api_key"` to produce the canonical `"Missing required field: api.claude_api_key"` message.
- `ruff` RUF022 and I001 violations auto-fixed via `ruff --fix --unsafe-fixes`; B904 violations (exception chaining) required manual `raise ... from err` additions.

### Completion Notes List

- Implemented full `core/config.py` with six Pydantic sub-models (`ApiConfig`, `ModelConfig`, `LimitsConfig`, `MethodologyConfig`, `ScmConfig`, `ReproducibilityConfig`) all using `extra="ignore"` override on `ArcwrightModel` base.
- `RunConfig` composes all sub-models; `api: ApiConfig` is required (no default); all others use `Field(default_factory=...)`.
- `_warn_unknown_keys_recursive` detects unknown top-level and section-level keys before Pydantic validation, emitting `UserWarning` for each.
- `_deep_merge` performs non-mutating recursive dict merge.
- `_apply_env_overrides` uses typed helpers (`_env_set_str/int/float/bool`) with proper B904 exception chaining.
- `_translate_pydantic_error` maps Pydantic's `ValidationError` to `ConfigError` with actionable messages, including the `loc=("api",)` edge case.
- Added 14 env var constants + `CONFIG_FILENAME` + `GLOBAL_CONFIG_DIR` to `core/constants.py`; updated `__all__` alphabetically.
- Updated `core/__init__.py` to re-export `RunConfig` and `load_config`.
- 21 unit tests in `tests/test_core/test_config.py` — all passing; full regression suite 144/144.
- Quality gates: `ruff check` ✅ | `ruff format` ✅ | `mypy --strict` ✅ | `pytest` 144/144 ✅
- Code review follow-up fixes applied: normalized AC #5 type error messaging to user-friendly expected types (e.g., `int`), added explicit `_warn_unknown_keys(...)` helper to match story task contract, and synced story/sprint tracking metadata.

### File List

- arcwright-ai/src/arcwright_ai/core/config.py (replaced stub with full implementation)
- arcwright-ai/src/arcwright_ai/core/constants.py (added env var constants, CONFIG_FILENAME, GLOBAL_CONFIG_DIR)
- arcwright-ai/src/arcwright_ai/core/__init__.py (added RunConfig, load_config exports)
- arcwright-ai/tests/test_core/test_config.py (new file — 21 unit tests)
- arcwright-ai/tests/test_core/test_constants.py (updated expected set to include new constants)
- _spec/implementation-artifacts/1-3-configuration-system-with-two-tier-loading.md (updated review outcome and records)
- _spec/implementation-artifacts/sprint-status.yaml (synced story status to done)

## Senior Developer Review (AI)

### Reviewer

Ed (AI-assisted code review)

### Date

2026-03-02

### Outcome

Changes Requested → Addressed (all High/Medium findings fixed)

### Findings Addressed

- High: AC #5 error message used Pydantic internal type code (`int_parsing`) instead of user-facing expected type (`int`).
    - Fix: Added expected-type normalization in `_translate_pydantic_error`.
- Medium: Task 2.1 required `_warn_unknown_keys(...)` helper but implementation only had `_warn_unknown_keys_recursive(...)`.
    - Fix: Added `_warn_unknown_keys(data, section_name, known_keys)` and wired recursive scanner through it.
- Medium: Story File List omitted a changed tracked file.
    - Fix: Updated File List to include `_spec/implementation-artifacts/sprint-status.yaml`.

### Validation Evidence

- `ruff check src/arcwright_ai/core/config.py tests/test_core/test_config.py` ✅
- `.venv/bin/python -m mypy --strict src/arcwright_ai/core/config.py` ✅
- `pytest tests/test_core/test_config.py -q` ✅ (21 passed)
- Manual runtime probe confirms message format: `Invalid type for limits.tokens_per_story: expected int, got str 'not-a-number'` ✅

## Change Log

- 2026-03-02: Story created by SM (create-story workflow) — comprehensive context engine analysis completed. Status → ready-for-dev.
- 2026-03-02: Story implemented by Dev (dev-story workflow, Claude Sonnet 4.6). All 7 tasks complete. 21 unit tests, 144 total tests passing. ruff/mypy/pytest quality gates green. Status → review.
- 2026-03-02: Code review fixes applied (auto-fix path): AC #5 error message normalization, Task 2.1 helper alignment, File List/sprint tracking synchronization. Status → done.
