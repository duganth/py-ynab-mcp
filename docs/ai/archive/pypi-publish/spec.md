---
feature: pypi-publish
status: complete
created: 2026-02-25
updated: 2026-02-25
iteration: 2
---

## Overview

Add automated PyPI publishing via GitHub Actions so the package can be installed with `pip install py-ynab-mcp` or `uvx py-ynab-mcp`. Releases are triggered by pushing a git tag (e.g. `v0.2.0`), validated on TestPyPI first, then published to PyPI with a GitHub Release.

## Requirements

- [x] Publish workflow triggered by version tags (`v*`)
- [x] Build sdist + wheel using hatchling
- [x] Publish to TestPyPI first, then PyPI
- [x] Use Trusted Publishers (OIDC) for auth — no API token secrets
- [x] Run full CI (lint, type check, test) before publishing
- [x] Create GitHub Release with auto-generated release notes on successful publish
- [x] Version in pyproject.toml must match the git tag

## Technical Design

### Workflow: `.github/workflows/publish.yml`

Triggered on push of tags matching `v*`.

**Jobs:**

1. **`ci`** — Reuse existing CI checks (lint, type check, test across Python matrix). Either call the existing `ci.yml` as a reusable workflow or duplicate the steps. Prefer reusable workflow if `ci.yml` supports `workflow_call`.
2. **`build`** — Build sdist and wheel with `uv build`. Upload artifacts.
3. **`publish-testpypi`** — Download artifacts, publish to TestPyPI using `pypa/gh-action-pypi-publish` with Trusted Publishers OIDC. Uses `environment: testpypi` with the TestPyPI URL.
4. **`publish-pypi`** — Same as above but targeting production PyPI. Uses `environment: pypi`. Runs after TestPyPI succeeds.
5. **`github-release`** — Create a GitHub Release from the tag with auto-generated notes. Attach the built dist files.

**Job dependencies:**

```
ci → build → publish-testpypi → publish-pypi → github-release
```

### Changes to existing files

- **`.github/workflows/ci.yml`** — Add `workflow_call` trigger so the publish workflow can reuse it.
- **`pyproject.toml`** — Add `[project.urls]` with Homepage, Repository, Changelog, Bug Tracker pointing to the GitHub repo.

### Trusted Publishers setup (manual, not automated)

The user must configure Trusted Publishers on both PyPI and TestPyPI:

1. Register the package name on PyPI (and TestPyPI)
2. Add a "pending publisher" with:
   - Owner: `duganth`
   - Repository: `py-ynab-mcp`
   - Workflow: `publish.yml`
   - Environment: `pypi` (or `testpypi`)

### GitHub environments (manual)

Create two GitHub repo environments:
- `pypi` — for production PyPI publishing
- `testpypi` — for TestPyPI publishing

### Version management

Version stays in `pyproject.toml`. Release process:
1. Update version in `pyproject.toml`
2. Commit: `Release v0.2.0`
3. Tag: `git tag v0.2.0`
4. Push: `git push && git push --tags`

The workflow should validate that the tag version matches `pyproject.toml` version and fail early if they don't match.

## Acceptance Criteria

- [x] Pushing a `v*` tag runs CI, builds, publishes to TestPyPI, then PyPI
- [x] Failed CI blocks publishing
- [x] TestPyPI failure blocks PyPI publish
- [x] GitHub Release is created with auto-generated notes and dist artifacts attached
- [x] No secrets required — Trusted Publishers OIDC handles auth
- [x] Workflow fails if tag version doesn't match pyproject.toml version
- [x] `ci.yml` still works standalone on push/PR (no regression)

## Findings

### QA
<!-- appended by /dev-qa, tagged [iter N] -->
- [x] [iter 1] TestPyPI publish should use `skip-existing: true` — if publish-pypi fails after testpypi succeeds, re-running the workflow will fail at the TestPyPI step because versions can't be overwritten
- [x] [iter 1] `check-version` job uses `uv run python` which syncs all deps unnecessarily — use `python3` directly since `tomllib` is stdlib in 3.11+

### Security
<!-- appended by /dev-security, tagged [iter N] -->
_[iter 1] No findings. OIDC auth, minimal permissions, no secrets stored. Actions pinned to major versions (acceptable for well-known publishers)._

### User Notes
<!-- appended by /dev-ua -->

## Outcome

Added a tag-triggered GitHub Actions publish workflow that chains CI → version validation → build → TestPyPI → PyPI → GitHub Release, using OIDC Trusted Publishers for zero-secret auth. Also made `ci.yml` reusable via `workflow_call` and added `[project.urls]` to pyproject.toml. Successfully published v0.1.0 to PyPI on first run.
