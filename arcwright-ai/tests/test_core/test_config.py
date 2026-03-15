"""Unit tests for arcwright_ai.core.config — two-tier configuration loading."""

from __future__ import annotations

import inspect
import warnings
from pathlib import Path

import pytest

from arcwright_ai.core.config import ModelRegistry, ModelRole, ModelSpec, load_config
from arcwright_ai.core.exceptions import ConfigError

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def global_config_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Redirect Path.home() to tmp_path for isolation."""
    home = tmp_path / "home"
    home.mkdir()
    (home / ".arcwright-ai").mkdir()
    monkeypatch.setattr(Path, "home", staticmethod(lambda: home))
    return home / ".arcwright-ai"


@pytest.fixture
def clean_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Remove all ARCWRIGHT_ env vars that may bleed in from the real environment."""
    arcwright_vars = [
        "ARCWRIGHT_API_CLAUDE_API_KEY",
        "ARCWRIGHT_MODEL_VERSION",
        "ARCWRIGHT_MODEL_PRICING_INPUT_RATE",
        "ARCWRIGHT_MODEL_PRICING_OUTPUT_RATE",
        "ARCWRIGHT_AI_MODEL_GENERATE_VERSION",
        "ARCWRIGHT_AI_MODEL_REVIEW_VERSION",
        "ARCWRIGHT_AI_MODEL_GENERATE_PRICING_INPUT_RATE",
        "ARCWRIGHT_AI_MODEL_GENERATE_PRICING_OUTPUT_RATE",
        "ARCWRIGHT_AI_MODEL_REVIEW_PRICING_INPUT_RATE",
        "ARCWRIGHT_AI_MODEL_REVIEW_PRICING_OUTPUT_RATE",
        "ARCWRIGHT_LIMITS_TOKENS_PER_STORY",
        "ARCWRIGHT_LIMITS_COST_PER_RUN",
        "ARCWRIGHT_LIMITS_RETRY_BUDGET",
        "ARCWRIGHT_LIMITS_TIMEOUT_PER_STORY",
        "ARCWRIGHT_METHODOLOGY_ARTIFACTS_PATH",
        "ARCWRIGHT_METHODOLOGY_TYPE",
        "ARCWRIGHT_SCM_BRANCH_TEMPLATE",
        "ARCWRIGHT_REPRODUCIBILITY_ENABLED",
        "ARCWRIGHT_REPRODUCIBILITY_RETENTION",
    ]
    for var in arcwright_vars:
        monkeypatch.delenv(var, raising=False)


@pytest.fixture
def api_key_env(clean_env: None, monkeypatch: pytest.MonkeyPatch) -> None:
    """Ensure ARCWRIGHT_API_CLAUDE_API_KEY is set for tests that don't test missing key.

    Depends on clean_env to run first, then sets the API key.
    """
    monkeypatch.setenv("ARCWRIGHT_API_CLAUDE_API_KEY", "test-api-key")


def _write_yaml(path: Path, content: str) -> None:
    """Write a YAML config file to disk."""
    path.write_text(content, encoding="utf-8")


# ---------------------------------------------------------------------------
# AC #1 — RunConfig sub-model structure
# ---------------------------------------------------------------------------


def test_run_config_model_fields(api_key_env: None, global_config_dir: Path, clean_env: None) -> None:
    """RunConfig is a Pydantic model composing the expected sub-models."""
    cfg = load_config()
    assert hasattr(cfg, "api")
    assert hasattr(cfg, "models")
    assert hasattr(cfg, "limits")
    assert hasattr(cfg, "methodology")
    assert hasattr(cfg, "scm")
    assert hasattr(cfg, "reproducibility")
    # spot-check sub-model fields via ModelRegistry
    assert hasattr(cfg.api, "claude_api_key")
    assert hasattr(cfg.models.get(ModelRole.GENERATE), "version")
    assert hasattr(cfg.limits, "tokens_per_story")
    assert hasattr(cfg.limits, "cost_per_run")
    assert hasattr(cfg.limits, "retry_budget")
    assert hasattr(cfg.limits, "timeout_per_story")
    assert hasattr(cfg.methodology, "artifacts_path")
    assert hasattr(cfg.methodology, "type")
    assert hasattr(cfg.scm, "branch_template")
    assert hasattr(cfg.reproducibility, "enabled")
    assert hasattr(cfg.reproducibility, "retention")


# ---------------------------------------------------------------------------
# AC #2 — Precedence chain: env > project > global > defaults
# ---------------------------------------------------------------------------


def test_load_config_full_precedence_chain(
    global_config_dir: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, clean_env: None
) -> None:
    """Env var wins over project config which wins over global config."""
    # Global config sets models.generate.version = "v-global"
    _write_yaml(
        global_config_dir / "config.yaml",
        "models:\n  generate:\n    version: v-global\n",
    )
    # Project config sets models.generate.version = "v-project"
    project_root = tmp_path / "project"
    project_root.mkdir()
    (project_root / ".arcwright-ai").mkdir()
    _write_yaml(
        project_root / ".arcwright-ai" / "config.yaml",
        "models:\n  generate:\n    version: v-project\n",
    )
    # Env var sets ARCWRIGHT_AI_MODEL_GENERATE_VERSION = "v-env"
    monkeypatch.setenv("ARCWRIGHT_API_CLAUDE_API_KEY", "test-api-key")
    monkeypatch.setenv("ARCWRIGHT_AI_MODEL_GENERATE_VERSION", "v-env")

    cfg = load_config(project_root=project_root)
    assert cfg.models.get(ModelRole.GENERATE).version == "v-env"


def test_load_config_project_overrides_global(
    global_config_dir: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, clean_env: None
) -> None:
    """Project config wins over global when no env var is set."""
    _write_yaml(
        global_config_dir / "config.yaml",
        "limits:\n  retry_budget: 5\n",
    )
    project_root = tmp_path / "project"
    project_root.mkdir()
    (project_root / ".arcwright-ai").mkdir()
    _write_yaml(
        project_root / ".arcwright-ai" / "config.yaml",
        "limits:\n  retry_budget: 2\n",
    )
    monkeypatch.setenv("ARCWRIGHT_API_CLAUDE_API_KEY", "test-api-key")

    cfg = load_config(project_root=project_root)
    assert cfg.limits.retry_budget == 2


def test_load_config_global_overrides_defaults(
    global_config_dir: Path, monkeypatch: pytest.MonkeyPatch, clean_env: None
) -> None:
    """Global config wins over built-in defaults."""
    _write_yaml(
        global_config_dir / "config.yaml",
        "api:\n  claude_api_key: sk-global\nmodels:\n  generate:\n    version: v-global\n",
    )

    cfg = load_config()
    assert cfg.models.get(ModelRole.GENERATE).version == "v-global"
    assert cfg.api.claude_api_key == "sk-global"


# ---------------------------------------------------------------------------
# AC #3 — Unknown keys: warn, not error
# ---------------------------------------------------------------------------


def test_load_config_unknown_top_level_key_warns(global_config_dir: Path, api_key_env: None, clean_env: None) -> None:
    """Unknown top-level YAML key emits UserWarning and does not raise."""
    _write_yaml(
        global_config_dir / "config.yaml",
        "foo: bar\n",
    )
    with pytest.warns(UserWarning, match="Unknown config key 'foo'"):
        cfg = load_config()
    # rest of config is valid with defaults
    assert cfg.models.get(ModelRole.GENERATE).version == "claude-sonnet-4-20250514"


def test_load_config_unknown_section_key_warns(global_config_dir: Path, api_key_env: None, clean_env: None) -> None:
    """Unknown sub-section YAML key emits UserWarning and does not raise."""
    _write_yaml(
        global_config_dir / "config.yaml",
        "model:\n  version: claude-opus-4-5\n  unknown_field: xyzzy\n",
    )
    with pytest.warns(UserWarning, match="Unknown config key 'model.unknown_field'"):
        cfg = load_config()
    assert cfg.models.get(ModelRole.GENERATE).version == "claude-opus-4-5"


# ---------------------------------------------------------------------------
# AC #4 — Missing required field raises ConfigError
# ---------------------------------------------------------------------------


def test_load_config_missing_api_key_raises_config_error(global_config_dir: Path, clean_env: None) -> None:
    """Missing api.claude_api_key in all tiers raises ConfigError with expected message."""
    with pytest.raises(ConfigError, match=r"Missing required field: api\.claude_api_key"):
        load_config()


def test_load_config_missing_api_key_has_helpful_details(global_config_dir: Path, clean_env: None) -> None:
    """ConfigError for missing api key has details with fix hint."""
    with pytest.raises(ConfigError) as exc_info:
        load_config()
    assert exc_info.value.details is not None
    assert "field" in exc_info.value.details
    assert "fix" in exc_info.value.details


# ---------------------------------------------------------------------------
# AC #5 — Invalid type raises ConfigError
# ---------------------------------------------------------------------------


def test_load_config_invalid_type_raises_config_error(
    global_config_dir: Path, api_key_env: None, clean_env: None
) -> None:
    """Wrong type for limits.tokens_per_story raises ConfigError with field path."""
    _write_yaml(
        global_config_dir / "config.yaml",
        "limits:\n  tokens_per_story: 'not-a-number'\n",
    )
    with pytest.raises(ConfigError, match=r"Invalid type for limits\.tokens_per_story"):
        load_config()


# ---------------------------------------------------------------------------
# AC #6 — API key in project config raises ConfigError
# ---------------------------------------------------------------------------


def test_load_config_api_key_in_project_config_raises_config_error(
    global_config_dir: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, clean_env: None
) -> None:
    """Project config containing api section raises ConfigError before merge."""
    monkeypatch.setenv("ARCWRIGHT_API_CLAUDE_API_KEY", "test-api-key")
    project_root = tmp_path / "project"
    project_root.mkdir()
    (project_root / ".arcwright-ai").mkdir()
    _write_yaml(
        project_root / ".arcwright-ai" / "config.yaml",
        "api:\n  claude_api_key: sk-test\n",
    )
    with pytest.raises(ConfigError, match="API keys must not be stored in project-level config files"):
        load_config(project_root=project_root)


def test_load_config_api_key_in_project_config_has_details(
    global_config_dir: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, clean_env: None
) -> None:
    """ConfigError for api key in project config has details with file and fix."""
    monkeypatch.setenv("ARCWRIGHT_API_CLAUDE_API_KEY", "test-api-key")
    project_root = tmp_path / "project"
    project_root.mkdir()
    (project_root / ".arcwright-ai").mkdir()
    _write_yaml(
        project_root / ".arcwright-ai" / "config.yaml",
        "api:\n  claude_api_key: sk-bad\n",
    )
    with pytest.raises(ConfigError) as exc_info:
        load_config(project_root=project_root)
    assert exc_info.value.details is not None
    assert "file" in exc_info.value.details
    assert "fix" in exc_info.value.details


# ---------------------------------------------------------------------------
# AC #7 — load_config() signature
# ---------------------------------------------------------------------------


def test_load_config_signature() -> None:
    """load_config() accepts optional project_root Path and returns RunConfig."""
    from arcwright_ai.core.config import RunConfig

    sig = inspect.signature(load_config)
    params = sig.parameters
    assert "project_root" in params
    annotation = sig.return_annotation
    assert annotation is RunConfig or str(annotation) in (
        "RunConfig",
        "arcwright_ai.core.config.RunConfig",
    )
    # default value is None
    assert params["project_root"].default is None


# ---------------------------------------------------------------------------
# AC #8 coverage — Defaults, global-only, env overrides
# ---------------------------------------------------------------------------


def test_load_config_uses_defaults_when_no_files(
    global_config_dir: Path, monkeypatch: pytest.MonkeyPatch, clean_env: None
) -> None:
    """All fields use built-in defaults when no config files and only api key env is set."""
    monkeypatch.setenv("ARCWRIGHT_API_CLAUDE_API_KEY", "test-api-key")

    cfg = load_config()
    assert cfg.models.get(ModelRole.GENERATE).version == "claude-sonnet-4-20250514"
    assert cfg.limits.tokens_per_story == 200_000
    assert cfg.limits.cost_per_run == 10.0
    assert cfg.limits.retry_budget == 3
    assert cfg.limits.timeout_per_story == 300
    assert cfg.methodology.artifacts_path == "_spec"
    assert cfg.methodology.type == "bmad"
    assert cfg.scm.branch_template == "arcwright-ai/{story_slug}"
    assert cfg.reproducibility.enabled is False
    assert cfg.reproducibility.retention == 30


def test_load_config_global_only_no_project(global_config_dir: Path, clean_env: None) -> None:
    """No project_root provided: global config with api key returns valid RunConfig."""
    _write_yaml(
        global_config_dir / "config.yaml",
        "api:\n  claude_api_key: sk-global-test\n",
    )
    cfg = load_config()
    assert cfg.api.claude_api_key == "sk-global-test"


def test_load_config_env_override_bool_parsing_true(
    global_config_dir: Path, monkeypatch: pytest.MonkeyPatch, clean_env: None
) -> None:
    """'true' string env var for boolean field parses to True."""
    monkeypatch.setenv("ARCWRIGHT_API_CLAUDE_API_KEY", "test-api-key")
    monkeypatch.setenv("ARCWRIGHT_REPRODUCIBILITY_ENABLED", "true")
    cfg = load_config()
    assert cfg.reproducibility.enabled is True


def test_load_config_env_override_bool_parsing_false(
    global_config_dir: Path, monkeypatch: pytest.MonkeyPatch, clean_env: None
) -> None:
    """'false' string env var for boolean field parses to False."""
    monkeypatch.setenv("ARCWRIGHT_API_CLAUDE_API_KEY", "test-api-key")
    monkeypatch.setenv("ARCWRIGHT_REPRODUCIBILITY_ENABLED", "false")
    cfg = load_config()
    assert cfg.reproducibility.enabled is False


def test_load_config_env_override_bool_parsing_one(
    global_config_dir: Path, monkeypatch: pytest.MonkeyPatch, clean_env: None
) -> None:
    """'1' string env var for boolean field parses to True."""
    monkeypatch.setenv("ARCWRIGHT_API_CLAUDE_API_KEY", "test-api-key")
    monkeypatch.setenv("ARCWRIGHT_REPRODUCIBILITY_ENABLED", "1")
    cfg = load_config()
    assert cfg.reproducibility.enabled is True


def test_load_config_env_override_int_field(
    global_config_dir: Path, monkeypatch: pytest.MonkeyPatch, clean_env: None
) -> None:
    """Env var for int field is coerced correctly."""
    monkeypatch.setenv("ARCWRIGHT_API_CLAUDE_API_KEY", "test-api-key")
    monkeypatch.setenv("ARCWRIGHT_LIMITS_TOKENS_PER_STORY", "100000")
    cfg = load_config()
    assert cfg.limits.tokens_per_story == 100_000


def test_load_config_env_override_float_field(
    global_config_dir: Path, monkeypatch: pytest.MonkeyPatch, clean_env: None
) -> None:
    """Env var for float field is coerced correctly."""
    monkeypatch.setenv("ARCWRIGHT_API_CLAUDE_API_KEY", "test-api-key")
    monkeypatch.setenv("ARCWRIGHT_LIMITS_COST_PER_RUN", "5.5")
    cfg = load_config()
    assert cfg.limits.cost_per_run == 5.5


def test_load_config_missing_global_config_file_uses_defaults(
    global_config_dir: Path, monkeypatch: pytest.MonkeyPatch, clean_env: None
) -> None:
    """No config file at all (global dir exists but no config.yaml) uses defaults."""
    monkeypatch.setenv("ARCWRIGHT_API_CLAUDE_API_KEY", "test-api-key")
    # global_config_dir exists but no config.yaml file written
    cfg = load_config()
    assert cfg.models.get(ModelRole.GENERATE).version == "claude-sonnet-4-20250514"


def test_load_config_no_project_config_file_uses_global(
    global_config_dir: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, clean_env: None
) -> None:
    """project_root provided but no project config file: falls back to global."""
    _write_yaml(
        global_config_dir / "config.yaml",
        "api:\n  claude_api_key: sk-global\nmodels:\n  generate:\n    version: v-global\n",
    )
    project_root = tmp_path / "project"
    project_root.mkdir()
    # No .arcwright-ai directory in project_root
    cfg = load_config(project_root=project_root)
    assert cfg.models.get(ModelRole.GENERATE).version == "v-global"


# ---------------------------------------------------------------------------
# ModelPricing — sub-model defaults, YAML override, env override
# ---------------------------------------------------------------------------


def test_model_pricing_defaults(api_key_env: None, global_config_dir: Path, clean_env: None) -> None:
    """ModelPricing has sensible Opus 4.5 defaults without explicit config."""
    from decimal import Decimal

    cfg = load_config()
    assert cfg.models.get(ModelRole.GENERATE).pricing.input_rate == Decimal("15.00")
    assert cfg.models.get(ModelRole.GENERATE).pricing.output_rate == Decimal("75.00")


def test_model_pricing_env_override_input_rate(
    api_key_env: None,
    global_config_dir: Path,
    clean_env: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """ARCWRIGHT_AI_MODEL_GENERATE_PRICING_INPUT_RATE overrides the default input rate."""
    from decimal import Decimal

    monkeypatch.setenv("ARCWRIGHT_AI_MODEL_GENERATE_PRICING_INPUT_RATE", "3.00")
    cfg = load_config()
    assert cfg.models.get(ModelRole.GENERATE).pricing.input_rate == Decimal("3.00")
    # output_rate should still be default
    assert cfg.models.get(ModelRole.GENERATE).pricing.output_rate == Decimal("75.00")


def test_model_pricing_env_override_output_rate(
    api_key_env: None,
    global_config_dir: Path,
    clean_env: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """ARCWRIGHT_AI_MODEL_GENERATE_PRICING_OUTPUT_RATE overrides the default output rate."""
    from decimal import Decimal

    monkeypatch.setenv("ARCWRIGHT_AI_MODEL_GENERATE_PRICING_OUTPUT_RATE", "60.00")
    cfg = load_config()
    assert cfg.models.get(ModelRole.GENERATE).pricing.output_rate == Decimal("60.00")
    assert cfg.models.get(ModelRole.GENERATE).pricing.input_rate == Decimal("15.00")


def test_model_pricing_invalid_env_raises_config_error(
    api_key_env: None,
    global_config_dir: Path,
    clean_env: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Non-numeric ARCWRIGHT_AI_MODEL_GENERATE_PRICING_INPUT_RATE raises ConfigError."""
    monkeypatch.setenv("ARCWRIGHT_AI_MODEL_GENERATE_PRICING_INPUT_RATE", "not-a-number")
    with pytest.raises(ConfigError, match=r"Invalid type.*pricing"):
        load_config()


# ---------------------------------------------------------------------------
# AC #15a-g — New role-based model registry tests
# ---------------------------------------------------------------------------


def test_models_new_format_loads_both_roles(
    api_key_env: None,
    global_config_dir: Path,
    clean_env: None,
) -> None:
    """New models: format with generate and review roles loads both roles correctly."""
    _write_yaml(
        global_config_dir / "config.yaml",
        ("models:\n  generate:\n    version: claude-sonnet-4-20250514\n  review:\n    version: claude-haiku-3-7\n"),
    )
    cfg = load_config()
    assert cfg.models.get(ModelRole.GENERATE).version == "claude-sonnet-4-20250514"
    assert cfg.models.get(ModelRole.REVIEW).version == "claude-haiku-3-7"


def test_model_singular_key_migrates_with_deprecation_warning(
    api_key_env: None,
    global_config_dir: Path,
    clean_env: None,
) -> None:
    """Old model: YAML key auto-migrates to models.generate with DeprecationWarning."""
    from decimal import Decimal

    _write_yaml(
        global_config_dir / "config.yaml",
        "model:\n  version: legacy-model\n  pricing:\n    input_rate: '5.00'\n",
    )
    with pytest.warns(DeprecationWarning, match="Config key 'model' is deprecated"):
        cfg = load_config()
    assert cfg.models.get(ModelRole.GENERATE).version == "legacy-model"
    assert cfg.models.get(ModelRole.GENERATE).pricing.input_rate == Decimal("5.00")
    assert "generate" in cfg.models.roles


def test_no_model_or_models_uses_defaults(
    api_key_env: None,
    global_config_dir: Path,
    clean_env: None,
) -> None:
    """Config with neither model nor models key uses generate default claude-sonnet-4-20250514."""
    cfg = load_config()
    assert cfg.models.get(ModelRole.GENERATE).version == "claude-sonnet-4-20250514"
    assert "generate" in cfg.models.roles


def test_env_var_override_generate_version(
    api_key_env: None,
    global_config_dir: Path,
    clean_env: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """ARCWRIGHT_AI_MODEL_GENERATE_VERSION sets the generate role version."""
    monkeypatch.setenv("ARCWRIGHT_AI_MODEL_GENERATE_VERSION", "test-generate-model")
    cfg = load_config()
    assert cfg.models.get(ModelRole.GENERATE).version == "test-generate-model"


def test_env_var_override_review_version(
    api_key_env: None,
    global_config_dir: Path,
    clean_env: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """ARCWRIGHT_AI_MODEL_REVIEW_VERSION creates and configures the review role."""
    monkeypatch.setenv("ARCWRIGHT_AI_MODEL_REVIEW_VERSION", "review-model")
    cfg = load_config()
    assert cfg.models.get(ModelRole.REVIEW).version == "review-model"


def test_env_var_override_role_pricing(
    api_key_env: None,
    global_config_dir: Path,
    clean_env: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """ARCWRIGHT_AI_MODEL_GENERATE_PRICING_INPUT_RATE overrides generate pricing."""
    from decimal import Decimal

    monkeypatch.setenv("ARCWRIGHT_AI_MODEL_GENERATE_PRICING_INPUT_RATE", "1.50")
    cfg = load_config()
    assert cfg.models.get(ModelRole.GENERATE).pricing.input_rate == Decimal("1.50")
    assert cfg.models.get(ModelRole.GENERATE).pricing.output_rate == Decimal("75.00")


def test_legacy_env_var_maps_to_generate_with_deprecation(
    api_key_env: None,
    global_config_dir: Path,
    clean_env: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """ARCWRIGHT_MODEL_VERSION maps to generate role version with DeprecationWarning."""
    monkeypatch.setenv("ARCWRIGHT_MODEL_VERSION", "legacy-generate-model")
    with pytest.warns(DeprecationWarning, match="ARCWRIGHT_MODEL_VERSION.*deprecated"):
        cfg = load_config()
    assert cfg.models.get(ModelRole.GENERATE).version == "legacy-generate-model"


def test_new_env_var_takes_precedence_over_legacy(
    api_key_env: None,
    global_config_dir: Path,
    clean_env: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """When both ARCWRIGHT_MODEL_VERSION and ARCWRIGHT_AI_MODEL_GENERATE_VERSION are set, new wins."""
    monkeypatch.setenv("ARCWRIGHT_MODEL_VERSION", "old-model")
    monkeypatch.setenv("ARCWRIGHT_AI_MODEL_GENERATE_VERSION", "new-model")
    cfg = load_config()
    assert cfg.models.get(ModelRole.GENERATE).version == "new-model"


def test_get_review_falls_back_to_generate_when_not_configured(
    api_key_env: None,
    global_config_dir: Path,
    clean_env: None,
) -> None:
    """Requesting review role falls back to generate when review is not configured."""
    cfg = load_config()
    # Only generate is configured; review should fall back to generate spec
    generate_spec = cfg.models.get(ModelRole.GENERATE)
    review_spec = cfg.models.get(ModelRole.REVIEW)
    assert review_spec is generate_spec


def test_get_raises_config_error_when_generate_missing() -> None:
    """ModelRegistry.get raises ConfigError when role not found and generate not configured."""
    from arcwright_ai.core.config import ModelPricing

    # Bypass the @model_validator by directly constructing with a non-generate role
    # Using model_construct to skip validation for this edge-case test
    registry = ModelRegistry.model_construct(roles={"custom": ModelSpec(version="some-model", pricing=ModelPricing())})
    with pytest.raises(ConfigError, match="No model configured for role 'missing'"):
        registry.get("missing")


def test_model_registry_empty_roles_raises() -> None:
    """ModelRegistry with empty roles dict raises ValueError at construction."""
    with pytest.raises(ValueError, match="requires at least a 'generate' role"):
        ModelRegistry(roles={})


def test_known_keys_warns_on_unknown_models_subkey(
    api_key_env: None,
    global_config_dir: Path,
    clean_env: None,
) -> None:
    """Unknown role name inside models: section emits UserWarning."""
    _write_yaml(
        global_config_dir / "config.yaml",
        "models:\n  generate:\n    version: v1\n  unknown_role:\n    version: v2\n",
    )
    with pytest.warns(UserWarning, match="Unknown config key 'models.unknown_role'"):
        cfg = load_config()
    # generate is still loaded correctly
    assert cfg.models.get(ModelRole.GENERATE).version == "v1"


def test_models_roles_wrapped_format_does_not_warn_unknown_keys(
    api_key_env: None,
    global_config_dir: Path,
    clean_env: None,
) -> None:
    """Accepted wrapped form models.roles should not emit unknown-key warnings."""
    _write_yaml(
        global_config_dir / "config.yaml",
        "models:\n  roles:\n    generate:\n      version: v1\n",
    )
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        cfg = load_config()
    assert cfg.models.get(ModelRole.GENERATE).version == "v1"
    unknown_warnings = [
        str(w.message) for w in caught if isinstance(w.message, UserWarning) and "Unknown config key" in str(w.message)
    ]
    assert unknown_warnings == []


def test_known_keys_warns_on_unknown_models_pricing_subkey(
    api_key_env: None,
    global_config_dir: Path,
    clean_env: None,
) -> None:
    """Unknown nested pricing key under models role emits UserWarning."""
    _write_yaml(
        global_config_dir / "config.yaml",
        ("models:\n  generate:\n    version: v1\n    pricing:\n      input_rate: '1.00'\n      unknown_field: 'x'\n"),
    )
    with pytest.warns(UserWarning, match="Unknown config key 'models.generate.pricing.unknown_field'"):
        cfg = load_config()
    assert cfg.models.get(ModelRole.GENERATE).version == "v1"


# ---------------------------------------------------------------------------
# Story 9.1 — ScmConfig default_branch and auto_merge fields
# ---------------------------------------------------------------------------


def test_scm_default_branch_empty_default(api_key_env: None, global_config_dir: Path, clean_env: None) -> None:
    """ScmConfig.default_branch defaults to empty string (auto-detect)."""
    cfg = load_config()
    assert cfg.scm.default_branch == ""


def test_scm_default_branch_round_trips(
    api_key_env: None, global_config_dir: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, clean_env: None
) -> None:
    """ScmConfig loads default_branch from YAML and round-trips correctly."""
    project_root = tmp_path / "project"
    project_root.mkdir()
    (project_root / ".arcwright-ai").mkdir()
    _write_yaml(
        project_root / ".arcwright-ai" / "config.yaml",
        "scm:\n  default_branch: develop\n",
    )
    monkeypatch.setenv("ARCWRIGHT_API_CLAUDE_API_KEY", "test-api-key")
    cfg = load_config(project_root=project_root)
    assert cfg.scm.default_branch == "develop"


def test_scm_auto_merge_default_false(api_key_env: None, global_config_dir: Path, clean_env: None) -> None:
    """ScmConfig.auto_merge defaults to False."""
    cfg = load_config()
    assert cfg.scm.auto_merge is False


def test_scm_auto_merge_round_trips(
    api_key_env: None, global_config_dir: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, clean_env: None
) -> None:
    """ScmConfig loads auto_merge from YAML and round-trips correctly."""
    project_root = tmp_path / "project"
    project_root.mkdir()
    (project_root / ".arcwright-ai").mkdir()
    _write_yaml(
        project_root / ".arcwright-ai" / "config.yaml",
        "scm:\n  auto_merge: true\n",
    )
    monkeypatch.setenv("ARCWRIGHT_API_CLAUDE_API_KEY", "test-api-key")
    cfg = load_config(project_root=project_root)
    assert cfg.scm.auto_merge is True


def test_scm_unknown_key_warning_still_works(api_key_env: None, global_config_dir: Path, clean_env: None) -> None:
    """Unknown key in scm section triggers UserWarning even with new fields present."""
    _write_yaml(
        global_config_dir / "config.yaml",
        "scm:\n  branch_template: 'test/{story_slug}'\n  default_branch: main\n  auto_merge: false\n  bogus_key: 42\n",
    )
    with pytest.warns(UserWarning, match="Unknown config key 'scm.bogus_key'"):
        cfg = load_config()
    assert cfg.scm.branch_template == "test/{story_slug}"
    assert cfg.scm.default_branch == "main"
    assert cfg.scm.auto_merge is False
