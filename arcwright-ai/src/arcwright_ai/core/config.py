"""Core config — Two-tier configuration loading and validation."""

from __future__ import annotations

import os
import warnings
from decimal import Decimal
from enum import StrEnum
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from pydantic import ConfigDict, Field, model_validator
from pydantic import ValidationError as PydanticValidationError

from arcwright_ai.core.constants import (
    CONFIG_FILENAME,
    DIR_ARCWRIGHT,
    ENV_API_CLAUDE_API_KEY,
    ENV_LIMITS_COST_PER_RUN,
    ENV_LIMITS_RETRY_BUDGET,
    ENV_LIMITS_TIMEOUT_PER_STORY,
    ENV_LIMITS_TOKENS_PER_STORY,
    ENV_METHODOLOGY_ARTIFACTS_PATH,
    ENV_METHODOLOGY_TYPE,
    ENV_MODEL_GENERATE_PRICING_INPUT_RATE,
    ENV_MODEL_GENERATE_PRICING_OUTPUT_RATE,
    ENV_MODEL_GENERATE_VERSION,
    ENV_MODEL_PRICING_INPUT_RATE,
    ENV_MODEL_PRICING_OUTPUT_RATE,
    ENV_MODEL_REVIEW_PRICING_INPUT_RATE,
    ENV_MODEL_REVIEW_PRICING_OUTPUT_RATE,
    ENV_MODEL_REVIEW_VERSION,
    ENV_MODEL_VERSION,
    ENV_REPRODUCIBILITY_ENABLED,
    ENV_REPRODUCIBILITY_RETENTION,
    ENV_SCM_BRANCH_TEMPLATE,
    GLOBAL_CONFIG_DIR,
)
from arcwright_ai.core.exceptions import ConfigError
from arcwright_ai.core.io import load_yaml
from arcwright_ai.core.types import ArcwrightModel

__all__: list[str] = [
    "ApiConfig",
    "LimitsConfig",
    "MethodologyConfig",
    "ModelConfig",
    "ModelPricing",
    "ModelRegistry",
    "ModelRole",
    "ModelSpec",
    "ReproducibilityConfig",
    "RunConfig",
    "ScmConfig",
    "load_config",
]

# ---------------------------------------------------------------------------
# Config sub-models — override extra="ignore" for forward-compatible unknown keys
# ---------------------------------------------------------------------------


class ApiConfig(ArcwrightModel):
    """API credentials configuration.

    Attributes:
        claude_api_key: Anthropic Claude API key. Required — no default.
    """

    model_config = ConfigDict(frozen=True, extra="ignore", str_strip_whitespace=True)

    claude_api_key: str


class ModelPricing(ArcwrightModel):
    """Per-model token pricing configuration.

    Rates are expressed as USD per 1 million tokens.  Defaults match
    Claude Opus 4.5 pricing.

    Attributes:
        input_rate: Cost per 1M input tokens (USD).
        output_rate: Cost per 1M output tokens (USD).
    """

    model_config = ConfigDict(frozen=True, extra="ignore", str_strip_whitespace=True)

    input_rate: Decimal = Decimal("15.00")
    output_rate: Decimal = Decimal("75.00")


class ModelRole(StrEnum):
    """Enumeration of model roles within the pipeline.

    Attributes:
        GENERATE: Model used for code generation (agent invocation).
        REVIEW: Model used for reflexion-based validation review.
    """

    GENERATE = "generate"
    REVIEW = "review"


class ModelSpec(ArcwrightModel):
    """Per-role model specification.

    Attributes:
        version: Claude model version identifier.
        pricing: Per-model token pricing.
    """

    model_config = ConfigDict(frozen=True, extra="ignore", str_strip_whitespace=True)

    version: str = "claude-sonnet-4-20250514"
    pricing: ModelPricing = Field(default_factory=ModelPricing)


class ModelRegistry(ArcwrightModel):
    """Registry mapping pipeline roles to model specifications.

    Attributes:
        roles: Mapping from role name to model specification.
    """

    model_config = ConfigDict(frozen=True, extra="ignore", str_strip_whitespace=True)

    roles: dict[str, ModelSpec]

    @model_validator(mode="after")
    def _require_generate_role(self) -> ModelRegistry:
        """Validate that at least a 'generate' role is configured.

        Returns:
            Self after validation.

        Raises:
            ValueError: If roles is empty or missing the 'generate' role.
        """
        if not self.roles or ModelRole.GENERATE.value not in self.roles:
            raise ValueError("ModelRegistry requires at least a 'generate' role")
        return self

    def get(self, role: ModelRole | str) -> ModelSpec:
        """Return the ModelSpec for the requested role with generate fallback.

        Args:
            role: The pipeline role to look up.

        Returns:
            ModelSpec for the role, or the generate fallback if not configured.

        Raises:
            ConfigError: If the role is not found and no 'generate' fallback exists.
        """
        from arcwright_ai.core.exceptions import ConfigError

        key = role.value if isinstance(role, ModelRole) else role
        if key in self.roles:
            return self.roles[key]
        generate_key = ModelRole.GENERATE.value
        if generate_key in self.roles:
            return self.roles[generate_key]
        raise ConfigError(
            f"No model configured for role '{key}' and no 'generate' fallback",
            details={"role": key, "available_roles": list(self.roles.keys())},
        )


class ModelConfig(ArcwrightModel):
    """Model selection and pricing configuration.

    Deprecated:
        Use :class:`ModelSpec` and :class:`ModelRegistry` via ``RunConfig.models``.
        Retained for backward-compatibility migration logic only.

    Attributes:
        version: Claude model version identifier.
        pricing: Per-model token pricing.
    """

    model_config = ConfigDict(frozen=True, extra="ignore", str_strip_whitespace=True)

    version: str = "claude-opus-4-5"
    pricing: ModelPricing = Field(default_factory=ModelPricing)


class LimitsConfig(ArcwrightModel):
    """Resource limits configuration.

    Attributes:
        tokens_per_story: Maximum tokens per story execution.
        cost_per_run: Maximum allowed cost per epic run in USD.
        retry_budget: Number of validation retry attempts before halting.
        timeout_per_story: Maximum seconds per story execution.
    """

    model_config = ConfigDict(frozen=True, extra="ignore", str_strip_whitespace=True)

    tokens_per_story: int = 200_000
    cost_per_run: float = 10.0
    retry_budget: int = 3
    timeout_per_story: int = 300


class MethodologyConfig(ArcwrightModel):
    """BMAD methodology configuration.

    Attributes:
        artifacts_path: Relative path to spec/artifact directory.
        type: Methodology type identifier.
    """

    model_config = ConfigDict(frozen=True, extra="ignore", str_strip_whitespace=True)

    artifacts_path: str = "_spec"
    type: str = "bmad"


class ScmConfig(ArcwrightModel):
    """Source control configuration.

    Attributes:
        branch_template: Git branch name template string.
        remote: Default git remote name for push/PR operations.
        default_branch: Override for the repository default branch.
            Empty string (the default) means auto-detect via the
            ``git remote show`` / ``gh repo view`` / ``origin/HEAD`` cascade.
        auto_merge: When ``True``, automatically merge the PR after creation.
            Defaults to ``False`` (manual merge).  The actual merge call is
            wired in Story 9.3; this field only stores the preference.
    """

    model_config = ConfigDict(frozen=True, extra="ignore", str_strip_whitespace=True)

    branch_template: str = "arcwright-ai/{story_slug}"
    remote: str = "origin"
    default_branch: str = ""
    auto_merge: bool = False


class ReproducibilityConfig(ArcwrightModel):
    """Run reproducibility configuration.

    Attributes:
        enabled: Whether to capture full reproducibility artifacts.
        retention: Days to retain run artifacts.
    """

    model_config = ConfigDict(frozen=True, extra="ignore", str_strip_whitespace=True)

    enabled: bool = False
    retention: int = 30


class RunConfig(ArcwrightModel):
    """Top-level Arcwright AI run configuration.

    Composes all configuration sub-models.  Loaded at startup via
    :func:`load_config` and validated before any run begins.

    Attributes:
        api: API credentials.
        models: Role-based model registry (generate and optional review roles).
        limits: Resource limits.
        methodology: BMAD methodology settings.
        scm: Source control settings.
        reproducibility: Reproducibility capture settings.
    """

    model_config = ConfigDict(frozen=True, extra="ignore", str_strip_whitespace=True)

    api: ApiConfig
    models: ModelRegistry = Field(
        default_factory=lambda: ModelRegistry(roles={"generate": ModelSpec(version="claude-sonnet-4-20250514")})
    )
    limits: LimitsConfig = Field(default_factory=LimitsConfig)
    methodology: MethodologyConfig = Field(default_factory=MethodologyConfig)
    scm: ScmConfig = Field(default_factory=ScmConfig)
    reproducibility: ReproducibilityConfig = Field(default_factory=ReproducibilityConfig)


# ---------------------------------------------------------------------------
# Known-key sets for unknown-key detection (populated after class definitions)
# ---------------------------------------------------------------------------

# Include the legacy "model" key so old YAML doesn't trigger an unknown-key warning
# before the migration block in load_config() has run.
_KNOWN_TOP_LEVEL: frozenset[str] = frozenset(RunConfig.model_fields.keys()) | frozenset({"model"})

_KNOWN_SECTION_FIELDS: dict[str, frozenset[str]] = {
    "api": frozenset(ApiConfig.model_fields.keys()),
    "model": frozenset(ModelConfig.model_fields.keys()),  # legacy; mapped by migration
    "models": frozenset({"roles", ModelRole.GENERATE.value, ModelRole.REVIEW.value}),
    "limits": frozenset(LimitsConfig.model_fields.keys()),
    "methodology": frozenset(MethodologyConfig.model_fields.keys()),
    "scm": frozenset(ScmConfig.model_fields.keys()),
    "reproducibility": frozenset(ReproducibilityConfig.model_fields.keys()),
}

# Nested sub-section known keys for deeper warning detection
_KNOWN_SUBSECTION_FIELDS: dict[str, dict[str, frozenset[str]]] = {
    "model": {
        "pricing": frozenset(ModelPricing.model_fields.keys()),
    },
    "models": {
        ModelRole.GENERATE.value: frozenset(ModelSpec.model_fields.keys()),
        ModelRole.REVIEW.value: frozenset(ModelSpec.model_fields.keys()),
    },
}


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------


def _warn_unknown_keys_recursive(data: dict[str, Any]) -> None:
    """Emit UserWarning for any unrecognized config keys before Pydantic sees the data.

    Args:
        data: Raw config dict loaded from a YAML tier.
    """
    _warn_unknown_keys(data, section_name="", known_keys=set(_KNOWN_TOP_LEVEL))

    for key in data:
        if isinstance(data[key], dict) and key in _KNOWN_SECTION_FIELDS:
            _warn_unknown_keys(
                data[key],
                section_name=key,
                known_keys=set(_KNOWN_SECTION_FIELDS[key]),
            )
            # Handle models.{role}.{field} nesting
            if key == "models":
                models_data = data[key]
                role_section_name = "models"
                role_map = models_data

                # Support wrapped form: models.roles.{role} (accepted by Pydantic)
                if isinstance(models_data.get("roles"), dict):
                    role_section_name = "models.roles"
                    role_map = models_data["roles"]

                for role_key, role_data in role_map.items():
                    if isinstance(role_data, dict):
                        role_known = _KNOWN_SUBSECTION_FIELDS.get("models", {}).get(
                            role_key, frozenset(ModelSpec.model_fields.keys())
                        )
                        _warn_unknown_keys(
                            role_data,
                            section_name=f"{role_section_name}.{role_key}",
                            known_keys=set(role_known),
                        )

                        pricing_data = role_data.get("pricing")
                        if isinstance(pricing_data, dict):
                            _warn_unknown_keys(
                                pricing_data,
                                section_name=f"{role_section_name}.{role_key}.pricing",
                                known_keys=set(ModelPricing.model_fields.keys()),
                            )


def _warn_unknown_keys(data: dict[str, Any], section_name: str, known_keys: set[str]) -> None:
    """Emit UserWarning for unknown keys in a config section.

    Args:
        data: Mapping containing keys to validate.
        section_name: Dot-prefixed section name. Use empty string for root keys.
        known_keys: Allowed key names for the section.
    """
    for key in data:
        if key in known_keys:
            continue

        qualified_key = key if section_name == "" else f"{section_name}.{key}"
        warnings.warn(
            f"Unknown config key '{qualified_key}' will be ignored",
            UserWarning,
            stacklevel=4,
        )


def _expected_type_for_error(error_type: str) -> str:
    """Map Pydantic error types to user-facing type names.

    Args:
        error_type: Pydantic error type code.

    Returns:
        Friendly expected type label for error messaging.
    """
    if "int" in error_type:
        return "int"
    if "float" in error_type:
        return "float"
    if "bool" in error_type:
        return "bool"
    if "str" in error_type or "string" in error_type:
        return "str"
    return error_type


def _deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    """Recursively merge ``override`` into ``base``.

    Nested dicts are merged; scalar values are overridden.  Neither input is
    mutated.

    Args:
        base: Base dictionary (lower precedence).
        override: Override dictionary (higher precedence).

    Returns:
        New merged dictionary.
    """
    result = dict(base)
    for key, value in override.items():
        if key in result and isinstance(result[key], dict) and isinstance(value, dict):
            result[key] = _deep_merge(result[key], value)
        else:
            result[key] = value
    return result


def _check_no_api_keys_in_project(data: dict[str, Any], project_config_path: Path) -> None:
    """Raise ConfigError if the project-level config contains an ``api`` section.

    Args:
        data: Raw config dict loaded from the project config file.
        project_config_path: Path to the project config file (for error details).

    Raises:
        ConfigError: If an ``api`` section is present in the project config.
    """
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


def _env_set_str(merged: dict[str, Any], section: str, field: str, env_var: str) -> None:
    """Apply a string env var override to ``merged[section][field]``.

    Args:
        merged: Accumulated config dict (mutated in place).
        section: Top-level section name (e.g. ``"api"``).
        field: Field name within the section.
        env_var: Environment variable name to read.
    """
    value = os.environ.get(env_var)
    if value is not None:
        merged.setdefault(section, {})[field] = value


def _env_set_int(merged: dict[str, Any], section: str, field: str, env_var: str) -> None:
    """Apply an integer env var override to ``merged[section][field]``.

    Args:
        merged: Accumulated config dict (mutated in place).
        section: Top-level section name.
        field: Field name within the section.
        env_var: Environment variable name to read.

    Raises:
        ConfigError: If the env var value cannot be coerced to ``int``.
    """
    raw = os.environ.get(env_var)
    if raw is not None:
        try:
            merged.setdefault(section, {})[field] = int(raw)
        except ValueError as err:
            raise ConfigError(
                f"Invalid type for {section}.{field}: expected int, got str {raw!r}",
                details={"env_var": env_var, "value": raw},
            ) from err


def _env_set_float(merged: dict[str, Any], section: str, field: str, env_var: str) -> None:
    """Apply a float env var override to ``merged[section][field]``.

    Args:
        merged: Accumulated config dict (mutated in place).
        section: Top-level section name.
        field: Field name within the section.
        env_var: Environment variable name to read.

    Raises:
        ConfigError: If the env var value cannot be coerced to ``float``.
    """
    raw = os.environ.get(env_var)
    if raw is not None:
        try:
            merged.setdefault(section, {})[field] = float(raw)
        except ValueError as err:
            raise ConfigError(
                f"Invalid type for {section}.{field}: expected float, got str {raw!r}",
                details={"env_var": env_var, "value": raw},
            ) from err


def _env_set_bool(merged: dict[str, Any], section: str, field: str, env_var: str) -> None:
    """Apply a boolean env var override to ``merged[section][field]``.

    Truthy strings: ``"true"``, ``"1"``, ``"yes"`` (case-insensitive).
    Everything else is ``False``.

    Args:
        merged: Accumulated config dict (mutated in place).
        section: Top-level section name.
        field: Field name within the section.
        env_var: Environment variable name to read.
    """
    raw = os.environ.get(env_var)
    if raw is not None:
        merged.setdefault(section, {})[field] = raw.lower() in {"true", "1", "yes"}


def _env_set_decimal(
    merged: dict[str, Any],
    section: str,
    subsection: str,
    field: str,
    env_var: str,
) -> None:
    """Apply a Decimal env var override to ``merged[section][subsection][field]``.

    Args:
        merged: Accumulated config dict (mutated in place).
        section: Top-level section name (e.g. ``"model"``).
        subsection: Nested section name (e.g. ``"pricing"``).
        field: Field name within the subsection.
        env_var: Environment variable name to read.

    Raises:
        ConfigError: If the env var value cannot be coerced to ``Decimal``.
    """
    raw = os.environ.get(env_var)
    if raw is not None:
        try:
            Decimal(raw)  # validate parseable
        except Exception as err:
            raise ConfigError(
                f"Invalid type for {section}.{subsection}.{field}: expected decimal, got str {raw!r}",
                details={"env_var": env_var, "value": raw},
            ) from err
        merged.setdefault(section, {}).setdefault(subsection, {})[field] = raw


def _apply_env_overrides(merged: dict[str, Any]) -> None:
    """Apply all ``ARCWRIGHT_*`` env var overrides to ``merged`` (mutates in place).

    Args:
        merged: Accumulated config dict to apply overrides to.
    """
    _env_set_str(merged, "api", "claude_api_key", ENV_API_CLAUDE_API_KEY)
    _env_set_int(merged, "limits", "tokens_per_story", ENV_LIMITS_TOKENS_PER_STORY)
    _env_set_float(merged, "limits", "cost_per_run", ENV_LIMITS_COST_PER_RUN)
    _env_set_int(merged, "limits", "retry_budget", ENV_LIMITS_RETRY_BUDGET)
    _env_set_int(merged, "limits", "timeout_per_story", ENV_LIMITS_TIMEOUT_PER_STORY)
    _env_set_str(merged, "methodology", "artifacts_path", ENV_METHODOLOGY_ARTIFACTS_PATH)
    _env_set_str(merged, "methodology", "type", ENV_METHODOLOGY_TYPE)
    _env_set_str(merged, "scm", "branch_template", ENV_SCM_BRANCH_TEMPLATE)
    _env_set_bool(merged, "reproducibility", "enabled", ENV_REPRODUCIBILITY_ENABLED)
    _env_set_int(merged, "reproducibility", "retention", ENV_REPRODUCIBILITY_RETENTION)

    # Role-based model env var overrides (new pattern: ARCWRIGHT_AI_MODEL_{ROLE}_{FIELD})
    _role_version_env: list[tuple[str, str]] = [
        (ModelRole.GENERATE.value, ENV_MODEL_GENERATE_VERSION),
        (ModelRole.REVIEW.value, ENV_MODEL_REVIEW_VERSION),
    ]
    for role, env_var in _role_version_env:
        raw = os.environ.get(env_var)
        if raw is not None:
            (merged.setdefault("models", {}).setdefault("roles", {}).setdefault(role, {}))["version"] = raw

    _role_pricing_env: list[tuple[str, str, str]] = [
        (ModelRole.GENERATE.value, ENV_MODEL_GENERATE_PRICING_INPUT_RATE, "input_rate"),
        (ModelRole.GENERATE.value, ENV_MODEL_GENERATE_PRICING_OUTPUT_RATE, "output_rate"),
        (ModelRole.REVIEW.value, ENV_MODEL_REVIEW_PRICING_INPUT_RATE, "input_rate"),
        (ModelRole.REVIEW.value, ENV_MODEL_REVIEW_PRICING_OUTPUT_RATE, "output_rate"),
    ]
    for role, env_var, field in _role_pricing_env:
        raw = os.environ.get(env_var)
        if raw is not None:
            try:
                Decimal(raw)  # validate parseable
            except Exception as err:
                raise ConfigError(
                    f"Invalid type for models.{role}.pricing.{field}: expected decimal, got str {raw!r}",
                    details={"env_var": env_var, "value": raw},
                ) from err
            (merged.setdefault("models", {}).setdefault("roles", {}).setdefault(role, {}).setdefault("pricing", {}))[
                field
            ] = raw

    # Legacy env var alias: ARCWRIGHT_MODEL_VERSION → generate.version
    # Applied only when the new ARCWRIGHT_AI_MODEL_GENERATE_VERSION is NOT also set.
    legacy_version = os.environ.get(ENV_MODEL_VERSION)
    if legacy_version is not None and os.environ.get(ENV_MODEL_GENERATE_VERSION) is None:
        warnings.warn(
            "Environment variable 'ARCWRIGHT_MODEL_VERSION' is deprecated. "
            "Use 'ARCWRIGHT_AI_MODEL_GENERATE_VERSION' instead.",
            DeprecationWarning,
            stacklevel=2,
        )
        (merged.setdefault("models", {}).setdefault("roles", {}).setdefault(ModelRole.GENERATE.value, {}))[
            "version"
        ] = legacy_version

    # Legacy pricing env var aliases → generate role
    # Applied only when the new-style env var for the same field is NOT also set.
    _legacy_pricing_env: list[tuple[str, str, str]] = [
        (ENV_MODEL_PRICING_INPUT_RATE, ENV_MODEL_GENERATE_PRICING_INPUT_RATE, "input_rate"),
        (ENV_MODEL_PRICING_OUTPUT_RATE, ENV_MODEL_GENERATE_PRICING_OUTPUT_RATE, "output_rate"),
    ]
    for legacy_var, new_var, field in _legacy_pricing_env:
        legacy_raw = os.environ.get(legacy_var)
        if legacy_raw is not None and os.environ.get(new_var) is None:
            try:
                Decimal(legacy_raw)  # validate parseable
            except Exception as err:
                raise ConfigError(
                    f"Invalid type for models.generate.pricing.{field}: expected decimal, got str {legacy_raw!r}",
                    details={"env_var": legacy_var, "value": legacy_raw},
                ) from err
            (
                merged.setdefault("models", {})
                .setdefault("roles", {})
                .setdefault(ModelRole.GENERATE.value, {})
                .setdefault("pricing", {})
            )[field] = legacy_raw

    # Guard: if env vars partially populated models.roles, ensure the generate role
    # entry exists (even if empty) so that ModelRegistry validation passes.  The
    # ModelSpec default version covers the empty-dict case.
    if "models" in merged and "roles" in merged.get("models", {}):
        merged["models"]["roles"].setdefault(ModelRole.GENERATE.value, {})


def _translate_pydantic_error(exc: PydanticValidationError) -> None:
    """Translate a PydanticValidationError into a ConfigError.

    Always raises ConfigError.  Only the first error is reported to keep the
    message actionable.

    Args:
        exc: The Pydantic validation exception to translate.

    Raises:
        ConfigError: Always raised with a user-actionable message.
    """
    errors = exc.errors()
    if not errors:
        raise ConfigError("Configuration validation failed", details={"errors": []})

    first = errors[0]
    loc = ".".join(str(part) for part in first["loc"])
    error_type = first.get("type", "")

    if error_type == "missing":
        # When the entire "api" section is absent from the merged dict, Pydantic
        # reports loc=("api",); when the section is present but claude_api_key is
        # missing, loc=("api", "claude_api_key").  Both mean the same thing to
        # the user.
        if loc in ("api", "api.claude_api_key"):
            canonical_loc = "api.claude_api_key"
            raise ConfigError(
                f"Missing required field: {canonical_loc}",
                details={
                    "field": canonical_loc,
                    "fix": (
                        "Set ARCWRIGHT_API_CLAUDE_API_KEY environment variable "
                        "or add claude_api_key to ~/.arcwright-ai/config.yaml"
                    ),
                },
            )
        raise ConfigError(
            f"Missing required field: {loc}",
            details={"field": loc, "fix": f"Provide a value for {loc} in config or env"},
        )

    # Type / value error
    input_val = first.get("input")
    input_type = type(input_val).__name__
    expected_type = _expected_type_for_error(error_type)
    raise ConfigError(
        f"Invalid type for {loc}: expected {expected_type}, got {input_type} {input_val!r}",
        details={"errors": errors},
    )


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def load_config(project_root: Path | None = None) -> RunConfig:
    """Load, merge, and validate Arcwright AI configuration.

    Config tiers (lowest to highest precedence):

    1. Built-in defaults (Pydantic field defaults)
    2. Global config: ``~/.arcwright-ai/config.yaml``
    3. Project config: ``<project_root>/.arcwright-ai/config.yaml``
    4. Backward-compatible migration (``model:`` → ``models.generate``)
    5. Environment variables: ``ARCWRIGHT_*``

    Args:
        project_root: Optional path to the project root.  When provided, the
            project-level config file is loaded if it exists.

    Returns:
        Fully validated :class:`RunConfig` instance.

    Raises:
        ConfigError: If a required field is missing, a field has the wrong
            type, or the project config contains an ``api`` section.
    """
    merged: dict[str, Any] = {}

    # Tier 0: load .env file (project root, then cwd) so env vars are
    # available for the override layer below.  Existing env vars are NOT
    # overwritten ("first wins").
    if project_root is not None:
        load_dotenv(project_root / ".env")
    load_dotenv()  # cwd fallback — no-op if already loaded above

    # Tier 1: global config (~/.arcwright-ai/config.yaml)
    global_cfg = Path.home() / GLOBAL_CONFIG_DIR / CONFIG_FILENAME
    if global_cfg.exists():
        global_data = load_yaml(global_cfg)
        _warn_unknown_keys_recursive(global_data)
        merged = _deep_merge(merged, global_data)

    # Tier 2: project config (.arcwright-ai/config.yaml)
    if project_root is not None:
        project_cfg = project_root / DIR_ARCWRIGHT / CONFIG_FILENAME
        if project_cfg.exists():
            project_data = load_yaml(project_cfg)
            _check_no_api_keys_in_project(project_data, project_cfg)
            _warn_unknown_keys_recursive(project_data)
            merged = _deep_merge(merged, project_data)

    # Tier 3: backward-compatible model config migration
    # Must run after deep merge and before env overrides so that env vars can
    # target the migrated models.roles.{role}.* structure.
    if "models" in merged:
        models_data = merged["models"]
        if isinstance(models_data, dict) and "roles" not in models_data:
            # Flat YAML format { generate: {...}, review: {...} } → wrap in "roles"
            merged["models"] = {"roles": models_data}
    elif "model" in merged:
        # Old singular "model:" key → migrate to models.generate with deprecation warning.
        # Preserve whatever version was configured (or fall back to the old ModelConfig
        # default of "claude-opus-4-5" if version was absent) so existing users are not
        # silently downgraded.
        model_data: dict[str, Any] = dict(merged.pop("model"))
        if "version" not in model_data:
            model_data["version"] = ModelConfig().version
        warnings.warn(
            "Config key 'model' is deprecated. Replace with 'models: { generate: ... }' in your config",
            DeprecationWarning,
            stacklevel=2,
        )
        merged["models"] = {"roles": {"generate": model_data}}

    # Tier 4: env var overrides
    _apply_env_overrides(merged)

    # Tier 5: Pydantic validation
    try:
        return RunConfig.model_validate(merged)
    except PydanticValidationError as exc:
        _translate_pydantic_error(exc)
        # _translate_pydantic_error always raises; this is unreachable but
        # satisfies mypy's control-flow analysis.
        raise  # pragma: no cover
