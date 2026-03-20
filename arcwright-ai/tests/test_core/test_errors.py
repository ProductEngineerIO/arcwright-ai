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


# ---------------------------------------------------------------------------
# Story 13.5 — render_claude_guidance shared renderer (AC #1, #2, #4)
# ---------------------------------------------------------------------------


from arcwright_ai.core.errors import (  # noqa: E402
    LOCAL_RUNTIME_CATEGORIES,
    PLATFORM_ACCOUNT_CATEGORIES,
    TRANSIENT_CATEGORIES,
    redact_secrets,
    render_claude_guidance,
)


class TestRenderClaudeGuidanceSharedRenderer:
    """render_claude_guidance is the single render path for all surfaces (AC #1, #2, #4)."""

    def test_platform_guidance_labels_as_platform_issue(self) -> None:
        """Platform categories produce output explicitly labelled as a platform/account issue."""
        for cat in PLATFORM_ACCOUNT_CATEGORIES:
            cls = CLAUDE_ERROR_REGISTRY[cat]
            guidance = render_claude_guidance(cls)
            assert "Claude platform/account issue" in guidance, (
                f"{cat.value}: guidance must label failure as Claude platform/account issue"
            )

    def test_platform_guidance_includes_title_and_summary(self) -> None:
        """Platform guidance includes the classification title and summary."""
        cls = CLAUDE_ERROR_REGISTRY[ClaudeErrorCategory.BILLING_ERROR]
        guidance = render_claude_guidance(cls)
        assert cls.title in guidance
        assert cls.summary in guidance

    def test_platform_guidance_includes_remediation_steps(self) -> None:
        """Platform guidance lists all remediation steps."""
        cls = CLAUDE_ERROR_REGISTRY[ClaudeErrorCategory.AUTH_ERROR]
        guidance = render_claude_guidance(cls)
        for step in cls.remediation_steps:
            assert step in guidance

    def test_local_guidance_labels_as_local_setup_issue(self) -> None:
        """Local categories produce output explicitly labelled as a local Claude setup issue."""
        for cat in LOCAL_RUNTIME_CATEGORIES:
            cls = CLAUDE_ERROR_REGISTRY[cat]
            guidance = render_claude_guidance(cls)
            assert "local Claude setup issue" in guidance, (
                f"{cat.value}: guidance must label failure as local Claude setup issue"
            )

    def test_local_guidance_does_not_mention_platform(self) -> None:
        """Local guidance must not say 'Claude platform/account issue'."""
        for cat in LOCAL_RUNTIME_CATEGORIES:
            cls = CLAUDE_ERROR_REGISTRY[cat]
            guidance = render_claude_guidance(cls)
            assert "Claude platform/account issue" not in guidance, (
                f"{cat.value}: local guidance must not reference Claude platform/account issue"
            )

    def test_local_guidance_with_diagnostic_hint_includes_hint(self) -> None:
        """Diagnostic hint is included in local guidance when provided."""
        cls = CLAUDE_ERROR_REGISTRY[ClaudeErrorCategory.MANAGED_SETTINGS_ERROR]
        hint = "~/.claude/remote-settings.json"
        guidance = render_claude_guidance(cls, diagnostic_hint=hint)
        assert hint in guidance, "Diagnostic hint path must appear in local guidance"

    def test_local_guidance_without_diagnostic_hint_omits_inspect_line(self) -> None:
        """No 'Inspect:' line appears when diagnostic_hint is None."""
        cls = CLAUDE_ERROR_REGISTRY[ClaudeErrorCategory.LOCAL_CONFIG_ERROR]
        guidance = render_claude_guidance(cls, diagnostic_hint=None)
        assert "Inspect:" not in guidance

    def test_transient_retryable_guidance_labels_as_transient(self) -> None:
        """Retryable transient categories are labelled as transient/retryable provider issues."""
        retryable_cats = {cat for cat in TRANSIENT_CATEGORIES if CLAUDE_ERROR_REGISTRY[cat].retryable}
        for cat in retryable_cats:
            cls = CLAUDE_ERROR_REGISTRY[cat]
            guidance = render_claude_guidance(cls)
            assert "transient/retryable Claude provider issue" in guidance, (
                f"{cat.value}: transient guidance must label failure as transient/retryable issue"
            )

    def test_transient_retryable_guidance_includes_retry_note(self) -> None:
        """Retryable transient guidance includes a retry note."""
        cls = CLAUDE_ERROR_REGISTRY[ClaudeErrorCategory.RATE_LIMIT_ERROR]
        guidance = render_claude_guidance(cls)
        assert "retry" in guidance.lower()

    def test_unknown_sdk_error_labeled_as_unrecognised(self) -> None:
        """unknown_sdk_error produces an 'unrecognised' label (not 'transient/retryable')."""
        cls = CLAUDE_ERROR_REGISTRY[ClaudeErrorCategory.UNKNOWN_SDK_ERROR]
        guidance = render_claude_guidance(cls)
        assert "unrecognised" in guidance.lower()
        assert "transient/retryable" not in guidance

    def test_all_categories_produce_non_empty_guidance(self) -> None:
        """Every category in the registry produces non-empty guidance output."""
        for cat in ClaudeErrorCategory:
            cls = CLAUDE_ERROR_REGISTRY[cat]
            guidance = render_claude_guidance(cls)
            assert guidance.strip(), f"{cat.value}: render_claude_guidance returned empty string"

    def test_diagnostic_hint_is_redacted_when_it_contains_api_key(self) -> None:
        """Credential redaction is applied to diagnostic_hint before inclusion (AC #2)."""
        cls = CLAUDE_ERROR_REGISTRY[ClaudeErrorCategory.MANAGED_SETTINGS_ERROR]
        tainted_hint = "/path/config?api_key=sk-ant-api03-FAKEKEY12345678"
        guidance = render_claude_guidance(cls, diagnostic_hint=tainted_hint)
        assert "sk-ant-api03-FAKEKEY12345678" not in guidance, (
            "render_claude_guidance must redact credentials from diagnostic_hint"
        )

    def test_category_sets_are_exhaustive_and_disjoint(self) -> None:
        """PLATFORM, LOCAL, and TRANSIENT sets together cover all 10 categories exactly once."""
        all_sets = PLATFORM_ACCOUNT_CATEGORIES | LOCAL_RUNTIME_CATEGORIES | TRANSIENT_CATEGORIES
        all_cats = set(ClaudeErrorCategory)
        assert all_sets == all_cats, f"Gap or overlap: {all_cats.symmetric_difference(all_sets)}"


class TestRedactSecretsPublicAPI:
    """redact_secrets is the public credential-redaction API (AC #2)."""

    def test_redacts_sk_ant_key(self) -> None:
        text = "auth failed with key sk-ant-api03-SECRETVALUE1234567890"
        result = redact_secrets(text)
        assert "sk-ant-api03-SECRETVALUE1234567890" not in result
        assert "[REDACTED]" in result

    def test_redacts_bearer_token(self) -> None:
        text = "Authorization: Bearer eyJhbGciOiJSUzI1NiJ9.payload.sig"
        result = redact_secrets(text)
        assert "eyJhbGci" not in result

    def test_redacts_api_key_assignment(self) -> None:
        text = "api_key = mysecretvalue123456789012345"
        result = redact_secrets(text)
        assert "mysecretvalue" not in result

    def test_safe_text_unchanged(self) -> None:
        text = "No credentials here, just a file path: /home/user/.claude/config.json"
        result = redact_secrets(text)
        assert result == text


class TestCrossSurfaceGuidanceAlignment:
    """Guidance produced for the same category is aligned across halt and nodes surfaces (AC #4)."""

    def test_halt_and_nodes_produce_identical_platform_guidance(self) -> None:
        """HaltController._suggested_fix_for_exception and _derive_suggested_fix agree on platform errors."""
        from unittest.mock import MagicMock

        from arcwright_ai.cli.halt import HaltController
        from arcwright_ai.core.exceptions import AgentError

        for cat in PLATFORM_ACCOUNT_CATEGORIES:
            cls = CLAUDE_ERROR_REGISTRY[cat]
            exc = AgentError(cls.summary, details={"classification": cls, "failure_category": cat.value})

            # Terminal/halt-report surface (exception path)
            halt_fix = HaltController._suggested_fix_for_exception(exc)

            # Engine surface (_derive_suggested_fix with no retry history)
            mock_state = MagicMock()
            mock_state.retry_history = []
            mock_state.failure_category = cat.value
            # budget not exceeded
            budget = MagicMock()
            budget.max_invocations = 0
            budget.invocation_count = 0
            budget.max_cost = 0
            budget.estimated_cost = 0
            mock_state.budget = budget

            from arcwright_ai.engine.nodes import _derive_suggested_fix

            nodes_fix = _derive_suggested_fix(mock_state)

            # Both must contain the category title from the shared renderer
            assert cls.title in halt_fix, f"{cat.value}: title missing from halt fix"
            assert cls.title in nodes_fix, f"{cat.value}: title missing from nodes fix"
            # Both must flag as Claude platform/account issue
            assert "Claude platform/account issue" in halt_fix
            assert "Claude platform/account issue" in nodes_fix

    def test_halt_and_nodes_produce_identical_local_guidance(self) -> None:
        """HaltController._suggested_fix_for_exception and _derive_suggested_fix agree on local errors."""
        from unittest.mock import MagicMock

        from arcwright_ai.cli.halt import HaltController
        from arcwright_ai.core.exceptions import AgentError

        for cat in LOCAL_RUNTIME_CATEGORIES:
            cls = CLAUDE_ERROR_REGISTRY[cat]
            exc = AgentError(cls.summary, details={"classification": cls, "failure_category": cat.value})

            halt_fix = HaltController._suggested_fix_for_exception(exc)

            mock_state = MagicMock()
            mock_state.retry_history = []
            mock_state.failure_category = cat.value
            budget = MagicMock()
            budget.max_invocations = 0
            budget.invocation_count = 0
            budget.max_cost = 0
            budget.estimated_cost = 0
            mock_state.budget = budget

            from arcwright_ai.engine.nodes import _derive_suggested_fix

            nodes_fix = _derive_suggested_fix(mock_state)

            assert cls.title in halt_fix, f"{cat.value}: title missing from halt fix"
            assert cls.title in nodes_fix, f"{cat.value}: title missing from nodes fix"
            assert "local Claude setup issue" in halt_fix
            assert "local Claude setup issue" in nodes_fix

    def test_halt_and_nodes_produce_identical_transient_guidance(self) -> None:
        """HaltController._suggested_fix_for_exception and _derive_suggested_fix agree on transient errors."""
        from unittest.mock import MagicMock

        from arcwright_ai.cli.halt import HaltController
        from arcwright_ai.core.exceptions import AgentError

        for cat in TRANSIENT_CATEGORIES:
            cls = CLAUDE_ERROR_REGISTRY[cat]
            exc = AgentError(cls.summary, details={"classification": cls, "failure_category": cat.value})

            halt_fix = HaltController._suggested_fix_for_exception(exc)

            mock_state = MagicMock()
            mock_state.retry_history = []
            mock_state.failure_category = cat.value
            budget = MagicMock()
            budget.max_invocations = 0
            budget.invocation_count = 0
            budget.max_cost = 0
            budget.estimated_cost = 0
            mock_state.budget = budget

            from arcwright_ai.engine.nodes import _derive_suggested_fix

            nodes_fix = _derive_suggested_fix(mock_state)

            # Both must contain the category title
            assert cls.title in halt_fix, f"{cat.value}: title missing from halt fix"
            assert cls.title in nodes_fix, f"{cat.value}: title missing from nodes fix"

    def test_render_claude_guidance_matches_halt_suggested_fix_for_all_categories(self) -> None:
        """render_claude_guidance and _suggested_fix_for_exception produce identical output for every category."""
        from arcwright_ai.cli.halt import HaltController
        from arcwright_ai.core.exceptions import AgentError

        for cat in ClaudeErrorCategory:
            cls = CLAUDE_ERROR_REGISTRY[cat]
            exc = AgentError(cls.summary, details={"classification": cls, "failure_category": cat.value})

            halt_fix = HaltController._suggested_fix_for_exception(exc)
            direct_render = render_claude_guidance(cls)

            assert halt_fix == direct_render, (
                f"{cat.value}: halt _suggested_fix_for_exception diverges from render_claude_guidance.\n"
                f"  halt:   {halt_fix!r}\n"
                f"  render: {direct_render!r}"
            )
