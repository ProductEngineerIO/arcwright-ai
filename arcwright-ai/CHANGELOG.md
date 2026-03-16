# Changelog

All notable changes to arcwright-ai are documented in this file.

Format follows [Keep a Changelog](https://keepachangelog.com/).
Versions follow [PEP 440](https://peps.python.org/pep-0440/) via [hatch-vcs](https://github.com/ofek/hatch-vcs).

## [0.2.6] — 2026-03-16

### Added

- LangSmith Tracing section in both READMEs — documents `LANGCHAIN_TRACING_V2`, `LANGCHAIN_API_KEY`, and `LANGCHAIN_PROJECT` env vars for cloud-based run observability
- Environment Variables table in root README expanded with the three LangSmith-related vars

## [0.2.5] — 2026-03-16

### Added

- `CHANGELOG.md` (this file) covering v0.1.0 through v0.2.4

### Fixed

- `arcwright-ai-ai` typo → `arcwright-ai` in PRD (4 occurrences) and product brief (1 occurrence)
- Minimum version in `requirements.txt` examples bumped to `>=0.2.4`

### Changed

- Sprint status: epics 10 and 11 marked `done`

## [0.2.4] — 2026-03-16

### Added

- `python -m arcwright_ai` entry point (`__main__.py`) — guarantees the active venv copy is executed
- `requirements.txt` guidance in both READMEs for version-controlling the dependency

### Changed

- All documentation examples now use `python -m arcwright_ai` instead of bare `arcwright-ai` command

## [0.2.3] — 2026-03-16

### Fixed

- `dispatch --story STORY-2.7` now correctly strips the `STORY-` prefix before parsing the identifier

## [0.2.2] — 2026-03-16

### Fixed

- CLI help-text tests no longer break on terminals that emit ANSI escape codes
- SCM integration tests create bare repos with `symbolic-ref HEAD refs/heads/main` (fixes CI on platforms where default branch is `master`)
- `fetch_and_sync` handles unresolvable HEAD gracefully (detached, orphan, empty repos)

## [0.2.1] — 2026-03-16

### Fixed

- Installation docs updated with venv setup to satisfy PEP 668 (externally-managed-environment)

## [0.2.0] — 2026-03-16

### Added

- GitHub Actions CI (`ci.yml`) and Publish (`publish.yml`) at repo root with `working-directory: arcwright-ai`
- PyPI trusted publishing via OIDC
- BMAD 6.1+ prerequisite documented in both READMEs

### Changed

- Upgraded LangGraph 0.6.x → 1.x (CVE-2026-28277 & CVE-2026-27794 remediation)
- Upgraded PyJWT 2.11.0 → 2.12.1 (CVE-2026-32597 remediation)
- Dynamic versioning via hatch-vcs (git tags as single source of truth)
- BMAD framework upgraded from 6.0.3 to 6.1.0

## [0.1.0] — 2026-03-15

### Added

- Initial release — MVP feature-complete
- Sequential dispatch pipeline (`dispatch --story`, `dispatch --epic`)
- V3 reflexion + V6 invariant validation with configurable retry budgets
- Decision provenance logging to `.arcwright-ai/runs/`
- Halt-and-notify with structured failure reports and `--resume`
- Cost tracking and budget enforcement (per-story token ceiling, per-run cost cap)
- SCM integration: git worktree isolation, branch management, PR generation with auto-merge
- Role-based model registry (code-generation vs. review roles)
- CLI commands: `init`, `validate-setup`, `dispatch`, `status`, `cleanup`
- Two-tier configuration (global + project) with env var overrides
