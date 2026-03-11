"""Unit tests for arcwright_ai.core.config — two-tier configuration loading."""

from __future__ import annotations

import inspect
from pathlib import Path

import pytest

from arcwright_ai.core.config import load_config
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
    """RunConfig is a Pydantic model composing the expected six sub-models."""
    cfg = load_config()
    assert hasattr(cfg, "api")
    assert hasattr(cfg, "model")
    assert hasattr(cfg, "limits")
    assert hasattr(cfg, "methodology")
    assert hasattr(cfg, "scm")
    assert hasattr(cfg, "reproducibility")
    # spot-check sub-model fields
    assert hasattr(cfg.api, "claude_api_key")
    assert hasattr(cfg.model, "version")
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
    # Global config sets model.version = "v-global"
    _write_yaml(
        global_config_dir / "config.yaml",
        "model:\n  version: v-global\n",
    )
    # Project config sets model.version = "v-project"
    project_root = tmp_path / "project"
    project_root.mkdir()
    (project_root / ".arcwright-ai").mkdir()
    _write_yaml(
        project_root / ".arcwright-ai" / "config.yaml",
        "model:\n  version: v-project\n",
    )
    # Env var sets ARCWRIGHT_MODEL_VERSION = "v-env"
    monkeypatch.setenv("ARCWRIGHT_API_CLAUDE_API_KEY", "test-api-key")
    monkeypatch.setenv("ARCWRIGHT_MODEL_VERSION", "v-env")

    cfg = load_config(project_root=project_root)
    assert cfg.model.version == "v-env"


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
        "api:\n  claude_api_key: sk-global\nmodel:\n  version: v-global\n",
    )

    cfg = load_config()
    assert cfg.model.version == "v-global"
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
    assert cfg.model.version == "claude-opus-4-5"


def test_load_config_unknown_section_key_warns(global_config_dir: Path, api_key_env: None, clean_env: None) -> None:
    """Unknown sub-section YAML key emits UserWarning and does not raise."""
    _write_yaml(
        global_config_dir / "config.yaml",
        "model:\n  version: claude-opus-4-5\n  unknown_field: xyzzy\n",
    )
    with pytest.warns(UserWarning, match="Unknown config key 'model.unknown_field'"):
        cfg = load_config()
    assert cfg.model.version == "claude-opus-4-5"


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
    assert cfg.model.version == "claude-opus-4-5"
    assert cfg.limits.tokens_per_story == 200_000
    assert cfg.limits.cost_per_run == 10.0
    assert cfg.limits.retry_budget == 3
    assert cfg.limits.timeout_per_story == 300
    assert cfg.methodology.artifacts_path == "_spec"
    assert cfg.methodology.type == "bmad"
    assert cfg.scm.branch_template == "arcwright/{story_slug}"
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
    assert cfg.model.version == "claude-opus-4-5"


def test_load_config_no_project_config_file_uses_global(
    global_config_dir: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, clean_env: None
) -> None:
    """project_root provided but no project config file: falls back to global."""
    _write_yaml(
        global_config_dir / "config.yaml",
        "api:\n  claude_api_key: sk-global\nmodel:\n  version: v-global\n",
    )
    project_root = tmp_path / "project"
    project_root.mkdir()
    # No .arcwright-ai directory in project_root
    cfg = load_config(project_root=project_root)
    assert cfg.model.version == "v-global"


# ---------------------------------------------------------------------------
# ModelPricing — sub-model defaults, YAML override, env override
# ---------------------------------------------------------------------------


def test_model_pricing_defaults(api_key_env: None, global_config_dir: Path, clean_env: None) -> None:
    """ModelPricing has sensible Opus 4.5 defaults without explicit config."""
    from decimal import Decimal

    cfg = load_config()
    assert cfg.model.pricing.input_rate == Decimal("15.00")
    assert cfg.model.pricing.output_rate == Decimal("75.00")


def test_model_pricing_env_override_input_rate(
    api_key_env: None,
    global_config_dir: Path,
    clean_env: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """ARCWRIGHT_MODEL_PRICING_INPUT_RATE overrides the default input rate."""
    from decimal import Decimal

    monkeypatch.setenv("ARCWRIGHT_MODEL_PRICING_INPUT_RATE", "3.00")
    cfg = load_config()
    assert cfg.model.pricing.input_rate == Decimal("3.00")
    # output_rate should still be default
    assert cfg.model.pricing.output_rate == Decimal("75.00")


def test_model_pricing_env_override_output_rate(
    api_key_env: None,
    global_config_dir: Path,
    clean_env: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """ARCWRIGHT_MODEL_PRICING_OUTPUT_RATE overrides the default output rate."""
    from decimal import Decimal

    monkeypatch.setenv("ARCWRIGHT_MODEL_PRICING_OUTPUT_RATE", "60.00")
    cfg = load_config()
    assert cfg.model.pricing.output_rate == Decimal("60.00")
    assert cfg.model.pricing.input_rate == Decimal("15.00")


def test_model_pricing_invalid_env_raises_config_error(
    api_key_env: None,
    global_config_dir: Path,
    clean_env: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Non-numeric ARCWRIGHT_MODEL_PRICING_INPUT_RATE raises ConfigError."""
    monkeypatch.setenv("ARCWRIGHT_MODEL_PRICING_INPUT_RATE", "not-a-number")
    with pytest.raises(ConfigError, match=r"Invalid type.*pricing"):
        load_config()
