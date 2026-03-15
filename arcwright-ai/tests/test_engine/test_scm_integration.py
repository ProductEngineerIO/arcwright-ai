"""Integration tests for SCM integration with engine nodes — Real git operations.

Tests the full lifecycle: preflight (worktree created) → agent_dispatch (ran in
worktree) → validate (pass or fail) → commit (committed + worktree removed) →
finalize.

All tests are marked ``@pytest.mark.slow`` and require a real git binary.
Run with ``pytest -m slow`` to include them.
"""

from __future__ import annotations

from decimal import Decimal
from typing import TYPE_CHECKING
from unittest.mock import AsyncMock, MagicMock

import pytest

from arcwright_ai.agent.invoker import InvocationResult
from arcwright_ai.core.config import ApiConfig, LimitsConfig, RunConfig
from arcwright_ai.core.constants import BRANCH_PREFIX, DIR_ARCWRIGHT, DIR_WORKTREES
from arcwright_ai.core.lifecycle import TaskState
from arcwright_ai.core.types import EpicId, RunId, StoryId
from arcwright_ai.engine.nodes import agent_dispatch_node, commit_node, finalize_node, preflight_node, validate_node
from arcwright_ai.engine.state import StoryState
from arcwright_ai.scm.git import git
from arcwright_ai.validation.pipeline import PipelineOutcome, PipelineResult
from arcwright_ai.validation.v6_invariant import V6CheckResult, V6ValidationResult

if TYPE_CHECKING:
    from pathlib import Path

pytestmark = [pytest.mark.slow, pytest.mark.asyncio]


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
async def git_repo(tmp_path: Path) -> Path:
    """Create a real git repository with an initial commit and BMAD structure.

    Args:
        tmp_path: pytest-provided temporary directory.

    Returns:
        Path: Root of the initialised git repository.
    """
    await git("init", cwd=tmp_path)
    await git("config", "user.email", "test@test.com", cwd=tmp_path)
    await git("config", "user.name", "Test", cwd=tmp_path)
    (tmp_path / "README.md").write_text("# Test Repo")
    await git("add", ".", cwd=tmp_path)
    await git("commit", "-m", "Initial commit", cwd=tmp_path)
    (tmp_path / DIR_ARCWRIGHT / DIR_WORKTREES).mkdir(parents=True)
    return tmp_path


@pytest.fixture
def make_run_config() -> RunConfig:
    """Build a minimal RunConfig for integration tests."""
    return RunConfig(
        api=ApiConfig(claude_api_key="test-key-not-real"),
        limits=LimitsConfig(retry_budget=2),
    )


@pytest.fixture
def scm_story_state(git_repo: Path, make_run_config: RunConfig) -> StoryState:
    """StoryState backed by a real git repository for SCM integration tests."""
    story_path = git_repo / "_spec" / "implementation-artifacts" / "6-6-scm-integration.md"
    story_path.parent.mkdir(parents=True, exist_ok=True)
    story_path.write_text("# Story 6.6\n\n## Acceptance Criteria\n\n1. Test AC\n", encoding="utf-8")

    return StoryState(
        story_id=StoryId("6-6-scm-integration"),
        epic_id=EpicId("epic-6"),
        run_id=RunId("20260308-120000-test001"),
        story_path=story_path,
        project_root=git_repo,
        config=make_run_config,
    )


def _make_fail_v6_pipeline_result() -> PipelineResult:
    """Create a minimal FAIL_V6 PipelineResult."""
    v6 = V6ValidationResult(
        passed=False,
        results=[
            V6CheckResult(
                check_name="file_existence",
                passed=False,
                failure_detail="Required file missing",
            )
        ],
    )
    return PipelineResult(
        passed=False,
        outcome=PipelineOutcome.FAIL_V6,
        v6_result=v6,
        tokens_used=0,
        cost=Decimal("0"),
    )


# ---------------------------------------------------------------------------
# Test 7.2: Full story lifecycle — preflight → agent → validate(PASS) → commit → finalize
# ---------------------------------------------------------------------------


async def test_full_story_lifecycle_with_scm(
    scm_story_state: StoryState,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Full lifecycle: preflight creates worktree → agent runs in worktree
    → validation passes → commit commits and removes worktree → finalize writes summary.

    Verifies:
    - worktree directory is gone after commit_node
    - branch has the expected commit
    - commit message matches template format
    """
    story_id = str(scm_story_state.story_id)
    project_root = scm_story_state.project_root
    expected_worktree = project_root / DIR_ARCWRIGHT / DIR_WORKTREES / story_id

    # Patch context assembly to avoid needing full BMAD artifacts
    mock_bundle = MagicMock()
    mock_bundle.domain_requirements = "FR1"

    async def _mock_build_bundle(*args: object, **kwargs: object) -> MagicMock:
        return mock_bundle

    def _mock_serialize(bundle: object) -> str:
        return "# Context\n\nMock context bundle"

    monkeypatch.setattr("arcwright_ai.engine.nodes.build_context_bundle", _mock_build_bundle)
    monkeypatch.setattr("arcwright_ai.engine.nodes.serialize_bundle_to_markdown", _mock_serialize)
    monkeypatch.setattr("arcwright_ai.engine.nodes.write_text_async", AsyncMock())
    monkeypatch.setattr("arcwright_ai.engine.nodes.append_entry", AsyncMock())
    monkeypatch.setattr("arcwright_ai.engine.nodes.update_story_status", AsyncMock())
    monkeypatch.setattr("arcwright_ai.engine.nodes.update_run_status", AsyncMock())
    monkeypatch.setattr("arcwright_ai.engine.nodes.write_success_summary", AsyncMock())

    # Step 1: preflight — creates real worktree
    state_after_preflight = await preflight_node(scm_story_state)

    assert state_after_preflight.worktree_path is not None
    assert expected_worktree.exists(), "worktree directory must exist after preflight"
    assert state_after_preflight.status == TaskState.RUNNING

    # Step 2: agent_dispatch — write a real file into the worktree
    agent_output_text = "# SCM Integration\n\nImplemented story 6.6"

    async def _mock_invoke(prompt: str, *, model: str, cwd: Path, sandbox: object) -> InvocationResult:
        # Simulate agent writing a file in the worktree
        assert cwd == state_after_preflight.worktree_path, "agent must run in worktree"
        output_file = cwd / "output.md"
        output_file.write_text(agent_output_text, encoding="utf-8")
        return InvocationResult(
            output_text=agent_output_text,
            tokens_input=50,
            tokens_output=50,
            total_cost=Decimal("0.001"),
            duration_ms=100,
            session_id="test-session",
            num_turns=1,
            is_error=False,
        )

    monkeypatch.setattr("arcwright_ai.engine.nodes.invoke_agent", _mock_invoke)
    state_after_dispatch = await agent_dispatch_node(state_after_preflight)
    assert state_after_dispatch.status == TaskState.VALIDATING

    # Step 3: validate_node PASS — required lifecycle step before commit
    async def _mock_run_validation_pipeline(*args: object, **kwargs: object) -> PipelineResult:
        v6 = V6ValidationResult(
            passed=True,
            results=[V6CheckResult(check_name="file_existence", passed=True)],
        )
        return PipelineResult(
            passed=True,
            outcome=PipelineOutcome.PASS,
            v6_result=v6,
            tokens_used=0,
            cost=Decimal("0"),
        )

    monkeypatch.setattr("arcwright_ai.engine.nodes.run_validation_pipeline", _mock_run_validation_pipeline)
    state_after_validate = await validate_node(state_after_dispatch)
    assert state_after_validate.status == TaskState.SUCCESS

    # Step 4: commit_node — commits changes in worktree and removes it
    state_after_commit = await commit_node(state_after_validate)

    assert state_after_commit.status == TaskState.SUCCESS  # unchanged by commit_node
    assert not expected_worktree.exists(), "worktree directory must be gone after commit"

    # Verify branch has the expected commit
    branch_name = BRANCH_PREFIX + story_id
    branch_log = await git("log", "--oneline", branch_name, cwd=project_root)
    assert "[arcwright-ai]" in branch_log.stdout, "commit message should start with [arcwright-ai]"

    # Step 5: finalize_node with SUCCESS status
    result = await finalize_node(state_after_commit)
    assert result.status == TaskState.SUCCESS


# ---------------------------------------------------------------------------
# Test 7.3: ESCALATED path — worktree preserved on failure
# ---------------------------------------------------------------------------


async def test_escalated_preserves_worktree(
    scm_story_state: StoryState,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """ESCALATED path: preflight creates worktree → agent runs → validation FAIL_V6
    → finalize → worktree directory still exists.

    Verifies:
    - worktree directory still exists after finalize_node in ESCALATED state
    - branch still has the worktree (was not removed)
    """
    story_id = str(scm_story_state.story_id)
    project_root = scm_story_state.project_root
    expected_worktree = project_root / DIR_ARCWRIGHT / DIR_WORKTREES / story_id

    # Patch context assembly
    mock_bundle = MagicMock()
    mock_bundle.domain_requirements = "FR1"

    async def _mock_build_bundle(*args: object, **kwargs: object) -> MagicMock:
        return mock_bundle

    def _mock_serialize(bundle: object) -> str:
        return "# Context"

    monkeypatch.setattr("arcwright_ai.engine.nodes.build_context_bundle", _mock_build_bundle)
    monkeypatch.setattr("arcwright_ai.engine.nodes.serialize_bundle_to_markdown", _mock_serialize)
    monkeypatch.setattr("arcwright_ai.engine.nodes.write_text_async", AsyncMock())
    monkeypatch.setattr("arcwright_ai.engine.nodes.append_entry", AsyncMock())
    monkeypatch.setattr("arcwright_ai.engine.nodes.update_story_status", AsyncMock())
    monkeypatch.setattr("arcwright_ai.engine.nodes.update_run_status", AsyncMock())
    monkeypatch.setattr("arcwright_ai.engine.nodes.write_halt_report", AsyncMock())

    # preflight creates worktree
    state_after_preflight = await preflight_node(scm_story_state)
    assert expected_worktree.exists()

    # Simulate ESCALATED path — go directly to finalize with ESCALATED status
    # (bypassing agent and validation for simplicity; worktree_path is already set)
    escalated_state = state_after_preflight.model_copy(
        update={
            "status": TaskState.ESCALATED,
            "agent_output": "partial output",
            "retry_history": [_make_fail_v6_pipeline_result()],
            "retry_count": 1,
        }
    )

    result = await finalize_node(escalated_state)

    assert result.status == TaskState.ESCALATED
    # Worktree must still exist — ESCALATED preserves it for inspection
    assert expected_worktree.exists(), "worktree must be preserved on ESCALATED"

    # The branch should still have the worktree checked out
    branch_name = BRANCH_PREFIX + story_id
    branch_list = await git("branch", "--list", branch_name, cwd=project_root)
    assert branch_name in branch_list.stdout
