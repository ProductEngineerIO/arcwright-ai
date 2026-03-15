# Story 9.4: End-to-End SCM Enhancement Integration Tests

Status: todo

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

## Story

As a system maintainer,
I want integration tests that verify the full enhanced SCM flow end-to-end,
so that fetch → worktree → commit → push → PR → merge works as an unbroken chain.

## Acceptance Criteria (BDD)

1. **Given** a `bare_remote_and_clone` fixture **When** created **Then** it provides a bare git repository (acts as "remote"), a clone of it (acts as "local project"), and both are real git repos with an initial commit on the default branch.

2. **Given** test scenario 1 (single story, auto-merge enabled) **When** the test runs **Then** it executes: `fetch_and_sync(default_branch, remote, project_root)` → `create_worktree(slug, base_ref=sha, project_root)` → write a file in worktree → `commit_story()` → `push_branch()` → verify branch exists on bare remote → verify commit content matches.

3. **Given** test scenario 2 (fetch picks up remote changes) **When** story 2 runs after story 1 has been pushed to the remote **Then** `fetch_and_sync()` returns a SHA that includes story 1's changes **And** the worktree created from that SHA contains story 1's file.

4. **Given** test scenario 3 (configurable default branch) **When** `scm.default_branch` is set to a custom branch name (e.g., `"develop"`) **Then** `fetch_and_sync` fetches that branch instead of auto-detecting **And** the worktree is based on the correct branch tip.

5. **Given** test scenario 4 (fetch failure) **When** `git fetch` fails (mock the network error by removing the remote) **Then** `ScmError` is raised with a clear message containing "fetch" and "remote".

6. **Given** test scenario 5 (worktree from remote tip, not stale local) **When** a new commit is pushed directly to the bare remote after the local clone was made **Then** `fetch_and_sync()` returns the new commit SHA **And** `create_worktree()` with that SHA has the new commit's content.

7. **Given** all tests **When** executed **Then** they are marked `@pytest.mark.slow` and `@pytest.mark.asyncio` **And** use `tmp_path` fixture with real git repos (no mocks for git commands).

8. **Given** story implementation is complete **When** `ruff check .` is run against the FULL repository **Then** zero violations.

9. **Given** story implementation is complete **When** `.venv/bin/python -m mypy --strict src/` is run **Then** zero errors.

10. **Given** any existing tests in the full test suite **When** this story is complete **Then** no existing tests break. All existing tests continue to pass.

## Tasks / Subtasks

- [ ] Task 1: Create `bare_remote_and_clone` fixture (AC: #1)
  - [ ] 1.1: In `tests/test_scm/test_scm_integration.py` (new file), create an async-compatible fixture.
  - [ ] 1.2: Init a bare repo: `git init --bare bare.git` in `tmp_path / "remote"`.
  - [ ] 1.3: Clone it: `git clone bare.git local` in `tmp_path`.
  - [ ] 1.4: In the clone, create initial commit: write `README.md`, `git add .`, `git commit -m "initial"`.
  - [ ] 1.5: Push: `git push origin main` (or whatever `git init` defaults to).
  - [ ] 1.6: Return a named tuple or dataclass with `remote_path`, `local_path`, `default_branch`.
  - [ ] 1.7: All git commands via `subprocess.run` (not the async `git()` wrapper — fixtures use sync operations for simplicity).

- [ ] Task 2: Test scenario 1 — single story fetch + worktree + commit + push (AC: #2)
  - [ ] 2.1: Call `fetch_and_sync("main", "origin", project_root=local_path)` — verify returns a SHA string.
  - [ ] 2.2: Call `create_worktree("test-story-1", base_ref=sha, project_root=local_path)` — verify returns Path.
  - [ ] 2.3: Write a new file in the worktree, call `commit_story("test-story-1", "Test Story", "/path/to/story.md", "run-001", worktree_path=worktree_path)`.
  - [ ] 2.4: Call `push_branch("arcwright-ai/test-story-1", project_root=local_path)` — verify succeeds.
  - [ ] 2.5: Verify branch exists on the bare remote: `git branch --list "arcwright-ai/test-story-1"` against bare.git.
  - [ ] 2.6: Verify the pushed commit contains the expected file.

- [ ] Task 3: Test scenario 2 — second story sees first story's changes via fetch (AC: #3)
  - [ ] 3.1: After scenario 1 completes, merge story 1's branch into main on the bare remote (simulate auto-merge or manual merge).
  - [ ] 3.2: Call `fetch_and_sync("main", "origin", project_root=local_path)` again.
  - [ ] 3.3: Verify returned SHA is different from scenario 1's SHA (includes story 1's changes).
  - [ ] 3.4: Call `create_worktree("test-story-2", base_ref=new_sha, project_root=local_path)`.
  - [ ] 3.5: Verify story 1's file exists in story 2's worktree.

- [ ] Task 4: Test scenario 3 — configurable default branch (AC: #4)
  - [ ] 4.1: Create a `develop` branch on the bare remote with a unique commit.
  - [ ] 4.2: Call `fetch_and_sync("develop", "origin", project_root=local_path)`.
  - [ ] 4.3: Verify returned SHA matches the `develop` branch tip, not `main`.
  - [ ] 4.4: Create worktree from that SHA, verify the unique commit's file is present.

- [ ] Task 5: Test scenario 4 — fetch failure (AC: #5)
  - [ ] 5.1: Remove the remote from the local clone: `git remote remove origin`.
  - [ ] 5.2: Call `fetch_and_sync("main", "origin", project_root=local_path)`.
  - [ ] 5.3: Verify `ScmError` is raised with appropriate message.

- [ ] Task 6: Test scenario 5 — worktree from remote tip, not stale local (AC: #6)
  - [ ] 6.1: After initial clone, push a new commit directly to the bare remote (via a temporary second clone or by operating on bare repo directly).
  - [ ] 6.2: Verify local main is still at the old commit (`git log --oneline -1` in local).
  - [ ] 6.3: Call `fetch_and_sync("main", "origin", project_root=local_path)`.
  - [ ] 6.4: Verify returned SHA matches the new remote commit, not the stale local.
  - [ ] 6.5: Create worktree from that SHA, verify the new file is present.

- [ ] Task 7: Run quality gates (AC: #8, #9, #10)
  - [ ] 7.1: `ruff check .` — zero violations against FULL repository.
  - [ ] 7.2: `ruff format --check .` — zero formatting issues.
  - [ ] 7.3: `.venv/bin/python -m mypy --strict src/` — zero errors.
  - [ ] 7.4: `pytest` — all tests pass (existing + new).

## Dev Notes

### Architecture & Design Context

This story is TESTS ONLY — no production code changes. All tests go in a new file `tests/test_scm/test_scm_integration.py`. The tests validate the combined behavior of `fetch_and_sync` (Story 9.2), `create_worktree` (Epic 6), `commit_story` (Epic 6), and `push_branch` (Epic 6).

### Current State Analysis — What Already Exists

1. **`tests/test_scm/test_branch_integration.py`**: Existing integration tests for branch operations with real git. Uses `@pytest.mark.slow`, `@pytest.mark.asyncio`, and a `git_repo(tmp_path)` fixture that creates a local-only repo. This story creates a NEW file with REMOTE-aware fixtures.

2. **`tests/test_scm/test_worktree_integration.py`**: Existing integration tests for worktree operations with real git. Similar fixture pattern.

3. **`tests/conftest.py`**: Has `tmp_project` fixture. The new `bare_remote_and_clone` fixture goes in the new test file (not in conftest, to avoid polluting other tests).

4. **Existing `git_repo` fixture pattern** (from test_branch_integration.py):
   ```python
   @pytest.fixture
   async def git_repo(tmp_path):
       repo = tmp_path / "repo"
       repo.mkdir()
       subprocess.run(["git", "init", str(repo)], check=True)
       subprocess.run(["git", "-C", str(repo), "commit", "--allow-empty", "-m", "init"], check=True)
       return repo
   ```
   The new fixture extends this with a bare remote + clone pattern.

### CRITICAL: Real Git Operations

All tests in this file use REAL git commands (not mocked). This is intentional — the point is to verify the actual git behavior end-to-end. Tests are marked `@pytest.mark.slow` to allow CI to skip them in fast test runs.

### CRITICAL: Fixture Must Handle Default Branch Name

Modern git versions may use `main` or `master` as the default branch. The fixture should explicitly set the default branch: `git init -b main --bare bare.git` or `git -c init.defaultBranch=main init --bare bare.git` to avoid CI portability issues.

### CRITICAL: No PR/Merge Tests

PR creation and auto-merge require GitHub authentication and a real remote (not a bare local repo). These are NOT tested here — they were unit-tested with mocks in Stories 9.1 and 9.3. This story focuses on the git-level operations: fetch, worktree, commit, push.

### CRITICAL: Simulating "Merge into Default Branch"

For scenario 2 (second story sees first story's changes after merge), simulate the merge by operating on the bare remote. Since you can't `git merge` in a bare repo, clone it to a temp directory, merge, push back:
```bash
# Option 1: Use a temp clone
git clone bare.git temp_clone
cd temp_clone
git merge origin/arcwright-ai/test-story-1
git push origin main
rm -rf temp_clone
```

Or alternatively, fast-forward the bare repo's main ref directly:
```bash
git -C bare.git update-ref refs/heads/main <story-1-push-sha>
```

### Files Touched

| File | Changes |
|------|---------|
| `tests/test_scm/test_scm_integration.py` | New file — all 5 test scenarios + `bare_remote_and_clone` fixture |
