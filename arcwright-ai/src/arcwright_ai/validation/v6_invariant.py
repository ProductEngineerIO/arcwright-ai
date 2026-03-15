"""V6 invariant validation — Deterministic rule-based checks for story outputs."""

from __future__ import annotations

import ast
import asyncio
import logging
import re
from pathlib import Path
from typing import Protocol, runtime_checkable

import yaml
from pydantic import Field, computed_field

from arcwright_ai.core.constants import PYTHON_DIRNAME_PATTERN, PYTHON_FILENAME_PATTERN
from arcwright_ai.core.exceptions import ValidationError
from arcwright_ai.core.io import read_text_async
from arcwright_ai.core.types import ArcwrightModel

__all__: list[str] = [
    "V6Check",
    "V6CheckResult",
    "V6ValidationResult",
    "check_file_existence",
    "check_naming_conventions",
    "check_python_syntax",
    "check_yaml_validity",
    "register_v6_check",
    "run_v6_validation",
]

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Compiled regex patterns for agent output parsing
# ---------------------------------------------------------------------------

_HEADER_PATTERN: re.Pattern[str] = re.compile(
    r"^#{1,3}\s+(?:File:\s+)?(\S+\.(?:py|yaml|yml|json|toml|md|txt))",
    re.MULTILINE,
)
_FENCE_PATTERN: re.Pattern[str] = re.compile(
    r"^```[a-zA-Z]*:(\S+\.(?:py|yaml|yml|json|toml|md|txt))",
    re.MULTILINE,
)
_LIST_PATTERN: re.Pattern[str] = re.compile(
    r"^-\s+(?:Created|Modified|Updated|Added):\s+(\S+\.(?:py|yaml|yml|json|toml|md|txt))",
    re.MULTILINE,
)
_PYTHON_NAME_PATTERN: re.Pattern[str] = re.compile(PYTHON_FILENAME_PATTERN)
_PYTHON_DIR_PATTERN: re.Pattern[str] = re.compile(PYTHON_DIRNAME_PATTERN)
_IGNORED_DIR_COMPONENTS: set[str] = {
    "src",
    "test",
    "tests",
    "__pycache__",
}
_SCHEMA_REQUIRED_KEYS: dict[str, set[str]] = {
    "sprint-status.yaml": {"development_status", "generated", "project", "tracking_system"},
    "config.yaml": set(),
    "run.yaml": {"status"},
}


# ---------------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------------


class V6CheckResult(ArcwrightModel):
    """Result of a single V6 invariant check.

    Attributes:
        check_name: Name of the invariant check performed.
        passed: Whether the check passed.
        failure_detail: Optional description of what failed, if applicable.
    """

    check_name: str
    passed: bool
    failure_detail: str | None = None


class V6ValidationResult(ArcwrightModel):
    """Aggregated result of all V6 invariant checks.

    Attributes:
        passed: True if all checks passed, False if any check failed.
        results: Complete list of individual check results.
        failures: Computed list of only the failed checks (included in serialization).
    """

    passed: bool
    results: list[V6CheckResult] = Field(default_factory=list)

    @computed_field  # type: ignore[prop-decorator]
    @property
    def failures(self) -> list[V6CheckResult]:
        """Return failed checks filtered from results.

        Returns:
            List of V6CheckResult instances where passed is False.
        """
        return [r for r in self.results if not r.passed]


# ---------------------------------------------------------------------------
# Protocol
# ---------------------------------------------------------------------------


@runtime_checkable
class V6Check(Protocol):
    """Protocol for V6 invariant check callables.

    All checks registered in ``_CHECK_REGISTRY`` must conform to this protocol.
    Checks receive the raw agent output text, the project root path, and the
    story path, and return a structured ``V6CheckResult``.
    """

    async def __call__(
        self,
        agent_output: str,
        project_root: Path,
        story_path: Path,
    ) -> V6CheckResult:
        """Execute the invariant check.

        Args:
            agent_output: Raw agent output text to validate.
            project_root: Absolute path to the project root.
            story_path: Path to the story file being validated.

        Returns:
            V6CheckResult with check outcome and optional failure details.
        """
        ...


# ---------------------------------------------------------------------------
# Internal utilities
# ---------------------------------------------------------------------------


def _extract_file_paths(agent_output: str) -> list[str]:
    """Extract file paths referenced in agent output using multiple patterns.

    Parses agent output text for file path references using compiled regex
    patterns matching common markdown conventions: section headers, fenced
    code blocks with language specifiers, and explicit file action lists.
    Paths are deduplicated while preserving first-occurrence order.

    Args:
        agent_output: Raw agent output text (markdown).

    Returns:
        Deduplicated list of relative file paths found in the output.
    """
    paths: list[str] = []
    for pattern in (_HEADER_PATTERN, _FENCE_PATTERN, _LIST_PATTERN):
        for match in pattern.finditer(agent_output):
            candidate = match.group(1).strip().strip("`")
            if candidate:
                paths.append(candidate)

    seen: set[str] = set()
    result: list[str] = []
    for p in paths:
        if p not in seen:
            seen.add(p)
            result.append(p)
    return result


# ---------------------------------------------------------------------------
# Check implementations
# ---------------------------------------------------------------------------


async def check_file_existence(
    agent_output: str,
    project_root: Path,
    story_path: Path,
) -> V6CheckResult:
    """Check that all files referenced in agent output exist in the worktree.

    Extracts file paths from the agent output and verifies each one exists
    on disk relative to the project root. If no files are referenced, the
    check passes (nothing to verify).

    Args:
        agent_output: Raw agent output text referencing created/modified files.
        project_root: Absolute path to the project root.
        story_path: Path to the story file (part of V6Check protocol contract).

    Returns:
        V6CheckResult with passed=True if all referenced files exist or no
        files are referenced. passed=False with failure_detail listing missing
        paths otherwise.
    """
    paths = _extract_file_paths(agent_output)
    if not paths:
        return V6CheckResult(check_name="file_existence", passed=True)

    missing: list[str] = []
    for path_str in paths:
        full_path = project_root / path_str
        exists = await asyncio.to_thread(full_path.exists)
        if not exists:
            missing.append(path_str)

    if missing:
        return V6CheckResult(
            check_name="file_existence",
            passed=False,
            failure_detail=f"Missing files: {', '.join(missing)}",
        )
    return V6CheckResult(check_name="file_existence", passed=True)


async def check_naming_conventions(
    agent_output: str,
    project_root: Path,
    story_path: Path,
) -> V6CheckResult:
    """Check that referenced Python files follow project naming conventions.

    Validates that Python file names are snake_case (matching
    ``^[a-z][a-z0-9_]*\\.py$``), module directories are snake_case, and
    test files (inside test/tests directories) start with ``test_``.

    Args:
        agent_output: Raw agent output text referencing created/modified files.
        project_root: Absolute path to the project root (unused directly).
        story_path: Path to the story file (part of V6Check protocol contract).

    Returns:
        V6CheckResult with passed=True if all Python files meet naming
        conventions or no Python files are referenced. passed=False with
        failure_detail listing violations otherwise.
    """
    paths = _extract_file_paths(agent_output)
    python_paths = [p for p in paths if p.endswith(".py")]
    if not python_paths:
        return V6CheckResult(check_name="naming_conventions", passed=True)

    violations: list[str] = []
    for path_str in python_paths:
        path = Path(path_str)
        filename = path.name

        if not _PYTHON_NAME_PATTERN.match(filename) and filename != "__init__.py":
            violations.append(f"{path_str}: filename '{filename}' does not match snake_case (^[a-z][a-z0-9_]*\\.py$)")

        for part in path.parts[:-1]:
            if part in _IGNORED_DIR_COMPONENTS or part.startswith("."):
                continue
            if not _PYTHON_DIR_PATTERN.match(part):
                violations.append(f"{path_str}: directory component '{part}' must be snake_case")

        parts_lower = {p.lower() for p in path.parts[:-1]}
        if parts_lower & {"test", "tests"} and not filename.startswith("test_") and filename != "__init__.py":
            violations.append(f"{path_str}: test file '{filename}' must start with 'test_'")

    if violations:
        return V6CheckResult(
            check_name="naming_conventions",
            passed=False,
            failure_detail="; ".join(violations),
        )
    return V6CheckResult(check_name="naming_conventions", passed=True)


async def check_python_syntax(
    agent_output: str,
    project_root: Path,
    story_path: Path,
) -> V6CheckResult:
    """Check that existing Python files referenced in agent output have valid syntax.

    For each Python file path extracted from the agent output that exists on
    disk, reads the file content and attempts ``ast.parse``. CPU-bound parse
    work is dispatched via ``asyncio.to_thread``.

    Args:
        agent_output: Raw agent output text referencing created/modified files.
        project_root: Absolute path to the project root.
        story_path: Path to the story file (part of V6Check protocol contract).

    Returns:
        V6CheckResult with passed=True if all existing Python files parse
        successfully or no Python files are found on disk. passed=False with
        failure_detail listing syntax errors otherwise.
    """
    paths = _extract_file_paths(agent_output)
    python_paths = [p for p in paths if p.endswith(".py")]
    if not python_paths:
        return V6CheckResult(check_name="python_syntax", passed=True)

    errors: list[str] = []
    for path_str in python_paths:
        full_path = project_root / path_str
        exists = await asyncio.to_thread(full_path.exists)
        if not exists:
            continue
        content = await read_text_async(full_path)
        try:
            await asyncio.to_thread(ast.parse, content, path_str)
        except SyntaxError as exc:
            errors.append(f"{path_str}: SyntaxError at line {exc.lineno}: {exc.msg}")

    if errors:
        return V6CheckResult(
            check_name="python_syntax",
            passed=False,
            failure_detail="; ".join(errors),
        )
    return V6CheckResult(check_name="python_syntax", passed=True)


async def check_yaml_validity(
    agent_output: str,
    project_root: Path,
    story_path: Path,
) -> V6CheckResult:
    """Check schema-constrained artifacts referenced in agent output.

    Validates two schema-constrained artifact types:
    1) YAML files: parse validity + lightweight schema checks for known files.
    2) Python files containing Pydantic models: field declarations must be
       type-annotated (except allowed config/class attributes).

    I/O and parsing are wrapped in async operations and thread offloading.

    Args:
        agent_output: Raw agent output text referencing created/modified files.
        project_root: Absolute path to the project root.
        story_path: Path to the story file (part of V6Check protocol contract).

    Returns:
        V6CheckResult with passed=True if all detected schema-constrained
        artifacts validate successfully. passed=False with failure_detail
        listing violations otherwise.
    """
    paths = _extract_file_paths(agent_output)
    yaml_paths = [p for p in paths if p.endswith(".yaml") or p.endswith(".yml")]
    python_paths = [p for p in paths if p.endswith(".py")]
    if not yaml_paths and not python_paths:
        return V6CheckResult(check_name="yaml_validity", passed=True)

    errors: list[str] = []
    for path_str in yaml_paths:
        full_path = project_root / path_str
        exists = await asyncio.to_thread(full_path.exists)
        if not exists:
            continue
        content = await read_text_async(full_path)
        try:
            parsed = await asyncio.to_thread(yaml.safe_load, content)
        except yaml.YAMLError as exc:
            errors.append(f"{path_str}: YAMLError: {exc}")
            continue

        if parsed is not None and not isinstance(parsed, dict):
            errors.append(f"{path_str}: expected YAML mapping at top level")
            continue

        required_keys = _SCHEMA_REQUIRED_KEYS.get(Path(path_str).name)
        if required_keys is not None and isinstance(parsed, dict):
            missing_keys = sorted(required_keys - set(parsed.keys()))
            if missing_keys:
                errors.append(f"{path_str}: missing required keys: {', '.join(missing_keys)}")

    for path_str in python_paths:
        full_path = project_root / path_str
        exists = await asyncio.to_thread(full_path.exists)
        if not exists:
            continue
        content = await read_text_async(full_path)
        try:
            parsed_ast = await asyncio.to_thread(ast.parse, content, path_str)
        except SyntaxError:
            continue

        for node in ast.walk(parsed_ast):
            if not isinstance(node, ast.ClassDef):
                continue

            base_names: set[str] = set()
            for base in node.bases:
                if isinstance(base, ast.Name):
                    base_names.add(base.id)
                elif isinstance(base, ast.Attribute):
                    base_names.add(base.attr)

            if not (base_names & {"BaseModel", "ArcwrightModel"}):
                continue

            for statement in node.body:
                if not isinstance(statement, ast.Assign):
                    continue
                if len(statement.targets) != 1:
                    continue
                target = statement.targets[0]
                if not isinstance(target, ast.Name):
                    continue
                if target.id in {"model_config", "__slots__"} or target.id.startswith("_"):
                    continue
                errors.append(
                    f"{path_str}: Pydantic model '{node.name}' field '{target.id}' must use a type annotation"
                )

    if errors:
        return V6CheckResult(
            check_name="yaml_validity",
            passed=False,
            failure_detail="; ".join(errors),
        )
    return V6CheckResult(check_name="yaml_validity", passed=True)


# ---------------------------------------------------------------------------
# Check registry and orchestrator
# ---------------------------------------------------------------------------

_CHECK_REGISTRY: list[V6Check] = [
    check_file_existence,
    check_naming_conventions,
    check_python_syntax,
    check_yaml_validity,
]


def register_v6_check(check: V6Check) -> None:
    """Register a new V6 invariant check in the global check registry.

    Appends the check to the module-level ``_CHECK_REGISTRY`` so it will be
    executed in all future ``run_v6_validation`` calls. This supports the
    extensibility requirement (AC #5): new invariant checks can be added
    without modifying the core module.

    Args:
        check: A callable conforming to the ``V6Check`` Protocol.
    """
    _CHECK_REGISTRY.append(check)


async def run_v6_validation(
    agent_output: str,
    project_root: Path,
    story_path: Path,
) -> V6ValidationResult:
    """Run all registered V6 invariant checks and aggregate results.

    Executes each check in ``_CHECK_REGISTRY`` sequentially to maintain
    deterministic ordering and reproducible results. Emits structured log
    events at the start and completion of the validation run.

    Args:
        agent_output: Raw agent output text to validate.
        project_root: Absolute path to the project root.
        story_path: Path to the story file being validated.

    Returns:
        V6ValidationResult with overall passed status and complete list of
        individual check results. ``passed`` is True only if every check passes.

    Raises:
        ValidationError: If an unexpected error occurs during check execution
            (not for normal check failures — those are captured as results).
    """
    logger.info(
        "validation.v6.start",
        extra={
            "data": {
                "story_path": str(story_path),
                "checks": len(_CHECK_REGISTRY),
            }
        },
    )

    results: list[V6CheckResult] = []
    try:
        for check in _CHECK_REGISTRY:
            result = await check(agent_output, project_root, story_path)
            results.append(result)
    except Exception as exc:  # pragma: no cover - defensive contract guard
        raise ValidationError(
            "Unexpected V6 validation execution error",
            details={"story_path": str(story_path), "error": str(exc)},
        ) from exc

    passed = all(r.passed for r in results)
    validation_result = V6ValidationResult(passed=passed, results=results)

    logger.info(
        "validation.v6.complete",
        extra={
            "data": {
                "passed": validation_result.passed,
                "checks_run": len(results),
                "failures": len(validation_result.failures),
            }
        },
    )

    return validation_result
