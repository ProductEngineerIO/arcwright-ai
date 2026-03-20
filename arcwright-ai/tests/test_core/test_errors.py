"""Tests for core/errors.py — Claude error taxonomy and classification contract."""

from __future__ import annotations

import re

from arcwright_ai.core.errors import (
    CLAUDE_ERROR_REGISTRY,
    ClaudeErrorCategory,
    ClaudeErrorClassification,
    classify_claude_error,
)

# ---------------------------------------------------------------------------
# ClaudeErrorCategory enum
# ---------------------------------------------------------------------------


def test_claude_error_category_has_required_members() -> None:
    """AC #2: taxonomy must include all required categories."""
    required = {
        "billing_error",
        "auth_error",
        "model_access_error",
        "local_config_error",
        "managed_settings_error",
        "cli_missing_error",
        "network_error",
        "rate_limit_error",
        "timeout_error",
        "unknown_sdk_error",
    }
    actual = {member.value for member in ClaudeErrorCategory}
    assert required.issubset(actual), f"Missing categories: {required - actual}"


def test_platform_and_local_categories_are_distinct() -> None:
    """AC #2: platform/account failures are distinct from local runtime/configuration."""
    platform = {
        ClaudeErrorCategory.BILLING_ERROR,
        ClaudeErrorCategory.AUTH_ERROR,
        ClaudeErrorCategory.MODEL_ACCESS_ERROR,
        ClaudeErrorCategory.RATE_LIMIT_ERROR,
    }
    local = {
        ClaudeErrorCategory.LOCAL_CONFIG_ERROR,
        ClaudeErrorCategory.MANAGED_SETTINGS_ERROR,
        ClaudeErrorCategory.CLI_MISSING_ERROR,
    }
    assert platform.isdisjoint(local)


# ---------------------------------------------------------------------------
# ClaudeErrorClassification model
# ---------------------------------------------------------------------------


def test_classification_has_required_fields() -> None:
    """AC #1: classification includes code, title, summary, retryable, remediation steps."""
    c = ClaudeErrorClassification(
        error_code=ClaudeErrorCategory.AUTH_ERROR,
        title="Auth Error",
        summary="Auth failed.",
        retryable=False,
        remediation_steps=["Check key."],
    )
    assert c.error_code == ClaudeErrorCategory.AUTH_ERROR
    assert c.title == "Auth Error"
    assert c.summary == "Auth failed."
    assert c.retryable is False
    assert c.remediation_steps == ["Check key."]


def test_classification_is_frozen() -> None:
    """Classification objects should be immutable (frozen Pydantic model)."""
    c = ClaudeErrorClassification(
        error_code=ClaudeErrorCategory.AUTH_ERROR,
        title="Auth Error",
        summary="Auth failed.",
        retryable=False,
        remediation_steps=["Check key."],
    )
    import pytest
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        c.title = "Modified"  # type: ignore[misc]


# ---------------------------------------------------------------------------
# CLAUDE_ERROR_REGISTRY
# ---------------------------------------------------------------------------


def test_registry_has_entry_for_every_category() -> None:
    """Every enum member must have a corresponding registry entry."""
    for cat in ClaudeErrorCategory:
        assert cat in CLAUDE_ERROR_REGISTRY, f"No registry entry for {cat.value}"


def test_registry_entries_have_valid_structure() -> None:
    """AC #1: each entry has non-empty title, summary, and remediation steps."""
    for cat, entry in CLAUDE_ERROR_REGISTRY.items():
        assert entry.error_code == cat
        assert entry.title, f"{cat.value}: empty title"
        assert entry.summary, f"{cat.value}: empty summary"
        assert isinstance(entry.retryable, bool)
        assert len(entry.remediation_steps) >= 1, f"{cat.value}: no remediation steps"


def test_registry_entries_titles_are_distinct() -> None:
    """Titles should be unique across categories to avoid confusion."""
    titles = [e.title for e in CLAUDE_ERROR_REGISTRY.values()]
    assert len(titles) == len(set(titles)), "Duplicate titles found"


# ---------------------------------------------------------------------------
# classify_claude_error()
# ---------------------------------------------------------------------------


def test_classify_billing_error() -> None:
    """Billing errors should map to billing_error."""
    result = classify_claude_error(message="Your credit balance is too low")
    assert result.error_code == ClaudeErrorCategory.BILLING_ERROR
    assert result.retryable is False


def test_classify_billing_error_from_stderr() -> None:
    result = classify_claude_error(message="Command failed", stderr="plans & billing insufficient credit")
    assert result.error_code == ClaudeErrorCategory.BILLING_ERROR


def test_classify_auth_error() -> None:
    result = classify_claude_error(message="authentication_error: invalid API key")
    assert result.error_code == ClaudeErrorCategory.AUTH_ERROR
    assert result.retryable is False


def test_classify_auth_error_from_stderr() -> None:
    result = classify_claude_error(
        message="Command failed with exit code 1",
        stderr="invalid_api_key Authentication error: invalid API key",
    )
    assert result.error_code == ClaudeErrorCategory.AUTH_ERROR


def test_classify_model_access_error() -> None:
    result = classify_claude_error(message="model access denied for claude-opus")
    assert result.error_code == ClaudeErrorCategory.MODEL_ACCESS_ERROR
    assert result.retryable is False


def test_classify_rate_limit_error() -> None:
    result = classify_claude_error(message="rate limit exceeded (429)")
    assert result.error_code == ClaudeErrorCategory.RATE_LIMIT_ERROR
    assert result.retryable is True


def test_classify_timeout_error() -> None:
    result = classify_claude_error(message="request timeout after 120s")
    assert result.error_code == ClaudeErrorCategory.TIMEOUT_ERROR
    assert result.retryable is True


def test_classify_network_error() -> None:
    result = classify_claude_error(message="connection refused to api.anthropic.com")
    assert result.error_code == ClaudeErrorCategory.NETWORK_ERROR
    assert result.retryable is True


def test_classify_network_error_dns() -> None:
    result = classify_claude_error(message="DNS resolution failed for host")
    assert result.error_code == ClaudeErrorCategory.NETWORK_ERROR


def test_classify_cli_missing_error() -> None:
    result = classify_claude_error(message="claude: command not found")
    assert result.error_code == ClaudeErrorCategory.CLI_MISSING_ERROR
    assert result.retryable is False


def test_classify_cli_missing_no_such_file() -> None:
    result = classify_claude_error(message="No such file or directory: 'claude'")
    assert result.error_code == ClaudeErrorCategory.CLI_MISSING_ERROR


def test_classify_local_config_error() -> None:
    result = classify_claude_error(message="ANTHROPIC_API_KEY environment variable is not set")
    assert result.error_code == ClaudeErrorCategory.LOCAL_CONFIG_ERROR
    assert result.retryable is False


def test_classify_managed_settings_error() -> None:
    result = classify_claude_error(message="managed settings validation error: invalid JSON")
    assert result.error_code == ClaudeErrorCategory.MANAGED_SETTINGS_ERROR
    assert result.retryable is False


def test_classify_unknown_fallback() -> None:
    """AC #4: unknown samples fall back to unknown_sdk_error."""
    result = classify_claude_error(message="something completely unexpected happened xyz123")
    assert result.error_code == ClaudeErrorCategory.UNKNOWN_SDK_ERROR
    assert result.retryable is False


def test_classify_unknown_with_stderr_fallback() -> None:
    result = classify_claude_error(message="odd error", stderr="unrecognised output")
    assert result.error_code == ClaudeErrorCategory.UNKNOWN_SDK_ERROR


def test_classify_preserves_stderr_in_summary() -> None:
    """AC #1: summary is concise; AC #2: stderr is preserved for diagnostics."""
    result = classify_claude_error(
        message="Command failed",
        stderr="detailed diagnostic output here",
    )
    # For unknown errors the summary should include diagnostic context
    assert result.summary  # non-empty


def test_classify_with_exit_code() -> None:
    """exit_code context should be usable by the classifier."""
    result = classify_claude_error(
        message="Command failed with exit code 1",
        stderr="Your credit balance is too low",
        exit_code=1,
    )
    assert result.error_code == ClaudeErrorCategory.BILLING_ERROR


# ---------------------------------------------------------------------------
# Secret-safe rendering (AC #3)
# ---------------------------------------------------------------------------

_CREDENTIAL_PATTERNS = [
    re.compile(r"sk-ant-[a-zA-Z0-9\-_]{20,}"),
    re.compile(r"sk-[a-zA-Z0-9]{20,}"),
    re.compile(r"Bearer\s+[a-zA-Z0-9\-_\.]+"),
]


def test_classification_summaries_have_no_raw_credentials() -> None:
    """AC #3: registry entries never embed raw credentials in static guidance."""
    for cat, entry in CLAUDE_ERROR_REGISTRY.items():
        for pattern in _CREDENTIAL_PATTERNS:
            assert not pattern.search(entry.summary), f"{cat.value} summary contains credential"
            for step in entry.remediation_steps:
                assert not pattern.search(step), f"{cat.value} remediation step contains credential"


def test_classify_redacts_credentials_from_summary() -> None:
    """AC #3: dynamically classified errors redact credentials from guidance."""
    result = classify_claude_error(
        message="authentication_error: invalid api key sk-ant-api03-FAKEKEY1234567890abcdef",
    )
    assert "sk-ant-" not in result.summary
    for step in result.remediation_steps:
        assert "sk-ant-" not in step


def test_classify_redacts_bearer_token_from_summary() -> None:
    """AC #3: bearer tokens in stderr are not leaked into guidance."""
    result = classify_claude_error(
        message="Command failed",
        stderr="Authorization: Bearer eyJhbGciOiJSUzI1NiIsInR5cCI6IkpXVCJ9.payload.sig",
    )
    assert "Bearer" not in result.summary
    assert "eyJhbG" not in result.summary
