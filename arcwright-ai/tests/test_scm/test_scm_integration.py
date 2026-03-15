"""End-to-end integration tests for SCM enhancements (Stories 9.1-9.3).

All tests are marked ``@pytest.mark.slow`` and require a real git binary.
Run with ``pytest -m slow`` to include them.
"""

from __future__ import annotations

import shutil
from typing import TYPE_CHECKING

import pytest

from arcwright_ai.core.exceptions import ScmError
from arcwright_ai.scm.branch import commit_story, fetch_and_sync, push_branch
from arcwright_ai.scm.git import git
from arcwright_ai.scm.worktree import create_worktree, remove_worktree

if TYPE_CHECKING:
    from pathlib import Path

pytestmark = [pytest.mark.slow, pytest.mark.asyncio]


# ---------------------------------------------------------------------------
# Scenario 1 — Single story full chain with auto-merge (AC: #1, #7, #8)
# ---------------------------------------------------------------------------


async def test_single_story_full_chain_auto_merge(
    bare_remote_and_clone: tuple[Path, Path, Path],
) -> None:
    """Verify fetch → worktree → commit → push → merge → verify forms unbroken chain (AC: #1).

    Args:
        bare_remote_and_clone: Shared fixture providing (bare, clone, scratch) paths.
    """
    _bare, clone, scratch = bare_remote_and_clone

    # Fetch latest SHA from remote
    sha = await fetch_and_sync("main", "origin", project_root=clone)
    assert sha, "fetch_and_sync should return a non-empty SHA"

    # Create worktree from fetched SHA
    wt_path = await create_worktree("single-story", sha, project_root=clone)
    assert wt_path.exists()

    # Write a feature file in the worktree
    (wt_path / "feature.py").write_text("def hello(): pass\n")

    # Commit the changes
    commit_hash = await commit_story(
        "single-story",
        "Single Story",
        "_spec/single-story.md",
        "run-001",
        worktree_path=wt_path,
    )
    assert commit_hash, "commit_story should return a non-empty hash"

    # Push the branch
    pushed = await push_branch(
        "arcwright-ai/single-story",
        project_root=clone,
        remote="origin",
        worktree_path=wt_path,
    )
    assert pushed is True

    # Verify remote branch exists
    branches_result = await git("branch", "-r", cwd=clone)
    assert "origin/arcwright-ai/single-story" in branches_result.stdout

    # Simulate auto-merge via scratch: fetch → merge → push to main
    await git("fetch", "origin", cwd=scratch)
    await git(
        "merge",
        "origin/arcwright-ai/single-story",
        "--no-ff",
        "-m",
        "Merge PR #1",
        cwd=scratch,
    )
    await git("push", "origin", "HEAD:main", cwd=scratch)

    # Simulate branch deletion (--delete-branch)
    await git("push", "origin", "--delete", "arcwright-ai/single-story", cwd=scratch)

    # Verify changes on default branch
    await git("fetch", "--prune", "origin", cwd=clone)
    log_result = await git("log", "--oneline", "origin/main", cwd=clone)
    assert "Merge PR" in log_result.stdout or "Single Story" in log_result.stdout

    # Verify remote branch was deleted
    branches_after = await git("branch", "-r", cwd=clone)
    assert "origin/arcwright-ai/single-story" not in branches_after.stdout

    # Cleanup
    await remove_worktree("single-story", project_root=clone, delete_branch=True)


# ---------------------------------------------------------------------------
# Scenario 2 — Epic chain: story 2 starts from story 1's merged commit (AC: #2)
# ---------------------------------------------------------------------------


async def test_epic_chain_two_stories_auto_merge(
    bare_remote_and_clone: tuple[Path, Path, Path],
) -> None:
    """Verify story 2's worktree contains story 1's merged output (AC: #2).

    Ensures ``fetch_and_sync`` after story 1 merges returns a new SHA so that
    story 2's worktree is based on post-merge state.

    Args:
        bare_remote_and_clone: Shared fixture providing (bare, clone, scratch) paths.
    """
    _bare, clone, scratch = bare_remote_and_clone

    # --- Story 1 ---
    initial_sha = await fetch_and_sync("main", "origin", project_root=clone)

    wt1_path = await create_worktree("chain-story-1", initial_sha, project_root=clone)
    (wt1_path / "chain1.py").write_text("# Story 1 output\n")
    await commit_story(
        "chain-story-1",
        "Chain Story 1",
        "_spec/chain-story-1.md",
        "run-chain-1",
        worktree_path=wt1_path,
    )
    await push_branch(
        "arcwright-ai/chain-story-1",
        project_root=clone,
        remote="origin",
        worktree_path=wt1_path,
    )

    # Simulate story 1 merge via scratch
    await git("fetch", "origin", cwd=scratch)
    await git(
        "merge",
        "origin/arcwright-ai/chain-story-1",
        "--no-ff",
        "-m",
        "Merge Story 1",
        cwd=scratch,
    )
    await git("push", "origin", "HEAD:main", cwd=scratch)
    await git("push", "origin", "--delete", "arcwright-ai/chain-story-1", cwd=scratch)

    # Cleanup story 1 worktree
    await remove_worktree("chain-story-1", project_root=clone, delete_branch=True)

    # --- Story 2 ---
    # Fetch again — should return a NEW sha (post-merge)
    new_sha = await fetch_and_sync("main", "origin", project_root=clone)
    assert new_sha != initial_sha, "SHA must advance after story 1 merges"

    wt2_path = await create_worktree("chain-story-2", new_sha, project_root=clone)

    # Key assertion: story 1's file must be present in story 2's worktree
    assert (wt2_path / "chain1.py").exists(), "chain1.py from story 1 must be present in story 2's worktree"

    # Complete story 2
    (wt2_path / "chain2.py").write_text("# Story 2 output\n")
    await commit_story(
        "chain-story-2",
        "Chain Story 2",
        "_spec/chain-story-2.md",
        "run-chain-2",
        worktree_path=wt2_path,
    )
    await push_branch(
        "arcwright-ai/chain-story-2",
        project_root=clone,
        remote="origin",
        worktree_path=wt2_path,
    )

    # Verify story 2 branch is on remote
    branches_result = await git("branch", "-r", cwd=clone)
    assert "origin/arcwright-ai/chain-story-2" in branches_result.stdout

    # Cleanup
    await remove_worktree("chain-story-2", project_root=clone, delete_branch=True)
    # Delete remote story 2 branch
    await git("push", "origin", "--delete", "arcwright-ai/chain-story-2", cwd=clone)


# ---------------------------------------------------------------------------
# Scenario 3 — Auto-merge disabled: PR stays open, branch remains (AC: #3)
# ---------------------------------------------------------------------------


async def test_full_chain_auto_merge_disabled(
    bare_remote_and_clone: tuple[Path, Path, Path],
) -> None:
    """Verify that when auto-merge is disabled, push succeeds but branch is not merged (AC: #3).

    The test simulates the case where the system stops at push — no merge step.

    Args:
        bare_remote_and_clone: Shared fixture providing (bare, clone, scratch) paths.
    """
    _bare, clone, _scratch = bare_remote_and_clone

    sha = await fetch_and_sync("main", "origin", project_root=clone)
    wt_path = await create_worktree("no-merge-story", sha, project_root=clone)
    (wt_path / "no_merge_feature.py").write_text("# No merge feature\n")
    await commit_story(
        "no-merge-story",
        "No Merge Story",
        "_spec/no-merge-story.md",
        "run-no-merge",
        worktree_path=wt_path,
    )
    await push_branch(
        "arcwright-ai/no-merge-story",
        project_root=clone,
        remote="origin",
        worktree_path=wt_path,
    )

    # Verify branch exists on remote — no merge was performed
    branches_result = await git("branch", "-r", cwd=clone)
    assert "origin/arcwright-ai/no-merge-story" in branches_result.stdout

    # Verify changes are NOT on main (no merge step was executed)
    await git("fetch", "origin", cwd=clone)
    log_result = await git("log", "--oneline", "origin/main", cwd=clone)
    assert "No Merge Story" not in log_result.stdout

    # Cleanup: remove worktree and delete remote branch (test housekeeping only)
    await remove_worktree("no-merge-story", project_root=clone, delete_branch=True)
    await git("push", "origin", "--delete", "arcwright-ai/no-merge-story", cwd=clone)


# ---------------------------------------------------------------------------
# Scenario 4 — Configured default branch (AC: #4)
# ---------------------------------------------------------------------------


async def test_configured_default_branch(tmp_path: Path) -> None:
    """Verify all SCM operations target the configured default branch, not auto-detected one (AC: #4).

    Uses an inline fixture with ``develop`` as default branch instead of ``main``
    to validate that ``fetch_and_sync`` and subsequent operations target the
    configured branch.

    Args:
        tmp_path: pytest-provided temporary directory.
    """
    bare = tmp_path / "bare.git"
    clone = tmp_path / "clone"
    scratch = tmp_path / "scratch"

    # Set up bare repo with 'develop' as default instead of 'main'
    await git("init", "--bare", str(bare), cwd=tmp_path)

    scratch.mkdir()
    await git("init", cwd=scratch)
    await git("config", "user.email", "test@test.com", cwd=scratch)
    await git("config", "user.name", "Test", cwd=scratch)
    (scratch / "README.md").write_text("# Develop branch\n")
    await git("add", ".", cwd=scratch)
    await git("commit", "-m", "Initial commit on develop", cwd=scratch)
    await git("remote", "add", "origin", str(bare), cwd=scratch)
    await git("push", "origin", "HEAD:develop", cwd=scratch)

    # Clone with -b develop
    await git("clone", "-b", "develop", str(bare), str(clone), cwd=tmp_path)
    await git("config", "user.email", "test@test.com", cwd=clone)
    await git("config", "user.name", "Test", cwd=clone)
    (clone / ".arcwright-ai" / "worktrees").mkdir(parents=True)

    # Fetch targeting 'develop'
    sha = await fetch_and_sync("develop", "origin", project_root=clone)
    assert sha, "fetch_and_sync should return a non-empty SHA for develop"

    # Create worktree and push
    slug = "dev-branch-story"
    wt_path = await create_worktree(slug, sha, project_root=clone)
    (wt_path / "dev_feature.py").write_text("# Develop branch feature\n")
    await commit_story(
        slug,
        "Dev Branch Story",
        "_spec/dev-branch-story.md",
        "run-dev-branch",
        worktree_path=wt_path,
    )
    await push_branch(
        f"arcwright-ai/{slug}",
        project_root=clone,
        remote="origin",
        worktree_path=wt_path,
    )

    # Simulate merge into 'develop' via scratch
    await git("fetch", "origin", cwd=scratch)
    await git("checkout", "develop", cwd=scratch)
    await git(
        "merge",
        f"origin/arcwright-ai/{slug}",
        "--no-ff",
        "-m",
        "Merge Dev Branch Story",
        cwd=scratch,
    )
    await git("push", "origin", "HEAD:develop", cwd=scratch)

    # Verify changes are on 'develop'
    await git("fetch", "origin", cwd=clone)
    log_result = await git("log", "--oneline", "origin/develop", cwd=clone)
    assert "Merge Dev Branch Story" in log_result.stdout or "Dev Branch" in log_result.stdout

    # Verify 'main' does NOT exist on remote
    branches_result = await git("branch", "-r", cwd=clone)
    assert "origin/main" not in branches_result.stdout

    # Cleanup
    await remove_worktree(slug, project_root=clone, delete_branch=True)


# ---------------------------------------------------------------------------
# Scenario 5 — Network failure simulation (AC: #5)
# ---------------------------------------------------------------------------


async def test_fetch_failure_graceful_halt(
    bare_remote_and_clone: tuple[Path, Path, Path],
) -> None:
    """Verify fetch_and_sync raises ScmError when the remote is unreachable (AC: #5).

    Simulates a network failure by deleting the bare repo directory so that
    the remote URL points to a non-existent path.

    Args:
        bare_remote_and_clone: Shared fixture providing (bare, clone, scratch) paths.
    """
    bare, clone, _scratch = bare_remote_and_clone

    # Delete the bare repo to simulate an unreachable remote
    shutil.rmtree(bare)

    # fetch_and_sync must raise ScmError with the exact expected message
    with pytest.raises(ScmError, match=r"^Failed to fetch from remote — check network connectivity$"):
        await fetch_and_sync("main", "origin", project_root=clone)


async def test_fetch_failure_error_has_details(
    bare_remote_and_clone: tuple[Path, Path, Path],
) -> None:
    """Verify ScmError from fetch failure carries 'remote' and 'branch' in details (AC: #5).

    Args:
        bare_remote_and_clone: Shared fixture providing (bare, clone, scratch) paths.
    """
    bare_details, clone_details, _scratch_details = bare_remote_and_clone
    shutil.rmtree(bare_details)

    exc_info: pytest.ExceptionInfo[ScmError]
    with pytest.raises(ScmError) as exc_info:
        await fetch_and_sync("main", "origin", project_root=clone_details)

    assert exc_info.value.details is not None
    assert "remote" in exc_info.value.details
    assert "branch" in exc_info.value.details


# ---------------------------------------------------------------------------
# Scenario 6 — Merge conflict graceful failure (AC: #6)
# ---------------------------------------------------------------------------


async def test_merge_conflict_graceful_failure(
    bare_remote_and_clone: tuple[Path, Path, Path],
) -> None:
    """Verify auto-merge fails gracefully on conflict; branch pushed, story not broken (AC: #6).

    Simulates a real merge conflict by having both scratch and the story branch
    modify ``README.md``. Verifies that:

    - Push of the story branch succeeds (story marked SUCCESS)
    - The attempted merge raises ``ScmError``
    - ``origin/main`` remains unchanged (no merge happened)
    - Story branch is still on remote after failed merge

    Args:
        bare_remote_and_clone: Shared fixture providing (bare, clone, scratch) paths.
    """
    _bare, clone, scratch = bare_remote_and_clone
    slug = "conflict-story"

    # Fetch initial SHA BEFORE pushing conflicting change to main
    # This ensures the story branch diverges from the same ancestor as the
    # conflicting main commit, creating a true 3-way merge conflict.
    sha = await fetch_and_sync("main", "origin", project_root=clone)

    # Create worktree and write conflicting content to README.md
    # The worktree starts at the same initial SHA as main
    wt_path = await create_worktree(slug, sha, project_root=clone)
    (wt_path / "README.md").write_text("# Story content\n")

    # Commit the story's conflicting change
    await commit_story(
        slug,
        "Conflict Story",
        "_spec/conflict-story.md",
        "run-conflict",
        worktree_path=wt_path,
    )

    # Push should succeed (no conflict at this point)
    pushed = await push_branch(
        f"arcwright-ai/{slug}",
        project_root=clone,
        remote="origin",
        worktree_path=wt_path,
    )
    assert pushed is True, "push_branch must succeed even if a future merge will conflict"

    # NOW push a conflicting change to main from scratch (same README.md, different text)
    # Both the story branch and main have independently modified README.md from the
    # same initial commit — this creates a true merge conflict.
    (scratch / "README.md").write_text("# Conflicting content\n")
    await git("add", ".", cwd=scratch)
    await git("commit", "-m", "Conflicting main commit", cwd=scratch)
    await git("push", "origin", "HEAD:main", cwd=scratch)

    # Verify story branch is on remote
    await git("fetch", "origin", cwd=clone)
    branches_result = await git("branch", "-r", cwd=clone)
    assert f"origin/arcwright-ai/{slug}" in branches_result.stdout
    story_marked_success_before_merge = pushed and f"origin/arcwright-ai/{slug}" in branches_result.stdout
    assert story_marked_success_before_merge is True

    # Simulate merge attempt from scratch — this WILL conflict on README.md
    await git("fetch", "origin", cwd=scratch)
    with pytest.raises(ScmError):
        await git("merge", f"origin/arcwright-ai/{slug}", cwd=scratch)

    # Abort the failed merge to restore clean state
    await git("merge", "--abort", cwd=scratch)

    # Verify: story branch still on remote
    await git("fetch", "origin", cwd=clone)
    branches_after = await git("branch", "-r", cwd=clone)
    assert f"origin/arcwright-ai/{slug}" in branches_after.stdout
    story_marked_success_after_merge_conflict = pushed and f"origin/arcwright-ai/{slug}" in branches_after.stdout
    assert story_marked_success_after_merge_conflict is True

    # Verify: main still has the conflicting commit, no merge
    log_result = await git("log", "--oneline", "origin/main", cwd=clone)
    assert "Conflicting main commit" in log_result.stdout
    assert "Merge Story" not in log_result.stdout
    assert "Merge PR" not in log_result.stdout

    # Cleanup
    await remove_worktree(slug, project_root=clone, delete_branch=True)
    await git("push", "origin", "--delete", f"arcwright-ai/{slug}", cwd=clone)
