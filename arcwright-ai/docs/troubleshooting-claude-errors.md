# Troubleshooting Claude Errors in Arcwright AI

When Arcwright AI halts with a Claude-related error, this guide helps you diagnose the cause
and take the right action.  Errors are grouped into four categories.  For each category the
table below lists the error code, what it means, where you action it, and the recommended
remediation steps.

---

## Error Categories at a Glance

| Category | Error codes | Where to act |
|---|---|---|
| [Platform / Account](#platform--account-failures) | `billing_error`, `auth_error`, `model_access_error` | Claude platform (console.anthropic.com) |
| [Local Runtime / Configuration](#local-runtime--configuration-failures) | `cli_missing_error`, `local_config_error`, `managed_settings_error` | Local machine |
| [Transient Provider Failures](#transient-provider-failures) | `rate_limit_error`, `network_error`, `timeout_error` | Wait and retry (handled automatically) |
| [Unknown / Fallback](#unknown-sdk-error) | `unknown_sdk_error` | Check logs; file issue if reproducible |

---

## Platform / Account Failures

These errors originate from the Anthropic API or your account configuration.  They are **not**
story code defects.  Arcwright AI cannot resolve them; you must act on the Claude platform.

### `billing_error` — API Billing Error

**Symptom:** "credit balance is too low" or "billing_error" in Claude output.

**Cause:** The configured Anthropic API key has insufficient credit balance.

**Actions (Claude platform — console.anthropic.com):**
1. Check your Anthropic billing dashboard for remaining credits.
2. Add credits or upgrade your plan at console.anthropic.com.
3. If using an API key override, remove it so Claude Code can use CLI/OAuth auth.

---

### `auth_error` — API Authentication Error

**Symptom:** "authentication_error", "invalid API key", "401 Unauthorized".

**Cause:** The configured Anthropic API key was rejected.

**Actions (Claude platform):**
1. Verify the `ANTHROPIC_API_KEY` value is correct and not expired.
2. Regenerate the key at console.anthropic.com if needed.
3. Remove the Arcwright API-key override to use CLI/OAuth auth instead.

---

### `model_access_error` — Model Access Denied

**Symptom:** "model access denied", "not authorized to use model".

**Cause:** The configured account or API key does not have access to the requested model.

**Actions (Claude platform):**
1. Check which models your API key is authorised for.
2. Update your Arcwright AI configuration (for example, in `.arcwright-ai/config.yaml` or the `arcwright-ai` section of `pyproject.toml`) to use a model your account can access.
3. Upgrade your Anthropic plan if the model requires a higher tier.

---

## Local Runtime / Configuration Failures

These errors are caused by a missing or misconfigured local installation.  They are **not**
billing or Claude platform issues.  Fix them on your local machine.

### `cli_missing_error` — Claude CLI Not Found

**Symptom:** "command not found: claude", "ENOENT … claude".

**Cause:** The `claude` command-line tool is not installed or not on `PATH`.

**Actions (local machine):**
1. Install Claude Code CLI: `npm install -g @anthropic-ai/claude-code`
2. Verify `claude` is on your `PATH` by running `which claude`.
3. If installed via a version manager, ensure the correct Node environment is active.

---

### `local_config_error` — Local Configuration Error

**Symptom:** "ANTHROPIC_API_KEY not set", "missing api_key", "config not found".

**Cause:** A required local configuration value is missing or invalid.

**Actions (local machine):**
1. Ensure `ANTHROPIC_API_KEY` is set in your environment or `.env` file.
2. Run `arcwright-ai init` to regenerate configuration if needed.
3. Check the Arcwright config file for missing or malformed values.

---

### `managed_settings_error` — Managed Settings Error

**Symptom:** "managed.settings", "remote-settings.json" in error output.

**Cause:** Claude managed settings file is invalid or could not be loaded.

**Actions (local machine):**
1. Check `~/.claude/remote-settings.json` for valid JSON syntax.
2. Delete the file and let Arcwright recreate it on next run.
3. Verify file permissions allow read/write access.

---

## Transient Provider Failures

These errors are temporary and often resolve on their own.  Arcwright AI applies exponential
backoff automatically for retryable conditions.

### `rate_limit_error` — Rate Limit Exceeded

**Symptom:** "rate_limit", "429 Too Many Requests".

**Cause:** Anthropic API rate limit reached.

**Actions:**
1. Wait and retry — Arcwright applies exponential backoff automatically.
2. If persistent, check your Anthropic rate-limit tier and usage.
3. Consider reducing concurrency or request frequency.

---

### `network_error` — Network Connectivity Error

**Symptom:** "connection refused", "ECONNREFUSED", "no route to host", DNS resolution failures.

**Cause:** Cannot reach Anthropic API servers.

**Actions:**
1. Verify internet connectivity and DNS resolution.
2. Check if `api.anthropic.com` is reachable from your network.
3. Check proxy/firewall settings if operating behind a corporate network.

---

### `timeout_error` — Request Timeout

**Symptom:** "timeout", "timed out" in error output.

**Cause:** The Claude API request timed out before completing.

**Actions:**
1. Retry — transient network congestion may have caused the timeout.
2. If persistent, check network latency to Anthropic endpoints.
3. Consider increasing the timeout configuration if available.

---

## Unknown SDK Error

### `unknown_sdk_error` — Unrecognised Claude SDK/CLI Error

**Symptom:** An error that doesn't match any of the categories above.

**Cause:** An unrecognised Claude SDK or CLI error occurred.

**Actions:**
1. Check the full error output in the Arcwright run log for details.
2. Search the Anthropic status page (status.anthropic.com) for incidents.
3. If reproducible, file an issue with the full error log attached.

---

## Reading Halt Reports

When Arcwright AI halts, it writes a `halt-report.md` to the run directory under
`.arcwright-ai/runs/<run-id>/`.  The `## Suggested Fix` section contains the same structured
guidance as the terminal output, rendered by the shared `render_claude_guidance` function for
consistency across all surfaces.

Use `arcwright-ai dispatch --epic <EPIC> --resume` to resume after fixing the root cause.

---

## Credential Safety

All operator-facing guidance artifacts — terminal output, halt reports, and run summaries —
pass through the centralised credential redaction layer (`redact_secrets`) before display.
API keys, bearer tokens, and `api_key = ...` values are replaced with `[REDACTED]` before they
can appear in these artifacts.
