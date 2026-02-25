---
feature: gh-actions
status: implementing
created: 2026-02-25
updated: 2026-02-25
iteration: 0
---

## Overview

Add a GitHub Actions CI workflow that runs lint, type checking, and tests on every PR and push to main. This ensures code quality gates are enforced before merging and keeps main green. Corresponds to roadmap item #8 in the project charter.

## Requirements

- [x] Create `.github/workflows/ci.yml` with a CI workflow
- [x] Run `ruff check .` for linting
- [x] Run `mypy src/` with strict mode for type checking
- [x] Run `pytest` for tests
- [x] Test against Python 3.11, 3.12, and 3.13 matrix
- [x] Trigger on pull requests and pushes to `main`
- [x] Use `uv` for dependency installation (consistent with project tooling)

## Technical Design

### Workflow file

Single file: `.github/workflows/ci.yml`

### Job structure

One job (`ci`) with a Python version matrix:

```yaml
strategy:
  matrix:
    python-version: ["3.11", "3.12", "3.13"]
```

### Steps

1. `actions/checkout@v4`
2. Install `uv` via `astral-sh/setup-uv@v4`
3. `uv sync --dev` to install project + dev deps (uv handles Python version via `--python`)
4. `uv run ruff check .`
5. `uv run mypy src/`
6. `uv run pytest`

### Runner

`ubuntu-latest` — no macOS-specific deps, keeps CI fast and free.

### Key decisions

- **uv over pip**: Project already uses uv, and `astral-sh/setup-uv` is the standard GH Action for it. Avoids pip bootstrap overhead.
- **Single job with matrix**: Simpler than separate lint/test jobs. All three checks are fast enough to run sequentially per Python version.
- **No caching config needed**: `setup-uv` handles caching automatically.
- **No YNAB token in CI**: Tests use mocks (already the case), so no secrets needed.

## Acceptance Criteria

- [x] `ruff check .` passes in CI
- [x] `mypy src/` passes in CI (strict mode)
- [x] `pytest` passes in CI across all three Python versions
- [x] Workflow triggers on PR to any branch and push to `main`
- [ ] CI passes on the PR that introduces it

## Findings

### QA
<!-- appended by /dev-qa, tagged [iter N] -->

### Security
<!-- appended by /dev-security, tagged [iter N] -->

### User Notes
<!-- appended by /dev-ua -->
