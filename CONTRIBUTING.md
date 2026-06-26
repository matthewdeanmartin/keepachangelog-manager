# Contributing to keepachangelog-manager

Thanks for contributing.

## Development setup

This repository uses [uv](https://docs.astral.sh/uv/) for dependency management.
For Python commands in this repo, always use `uv run ...` so you execute inside
the locked project environment.

```sh
git clone https://github.com/matthewdeanmartin/keepachangelog-manager
cd keepachangelog-manager
make help
make sync
```

Common entry points:

- `make format`
- `make lint`
- `make test`
- `make validate`
- `make quality`
- `make prerelease`
- `make build`

If you need the raw commands, keep them inside `uv`:

```sh
uv run pytest
uv run changelogmanager --help
uv run changelogmanager gui
uv run python -m changelogmanager
```

## Dogfooding in this repo

This project dogfoods `keepachangelog-manager`.

- The repo has a real root `CHANGELOG.md`.
- The repo also has `[tool.changelogmanager]` config in `pyproject.toml`.
- User-facing changes should be recorded with the tool, not by hand-editing the file when the CLI can do it for you.

Useful commands:

```sh
uv run changelogmanager add --change-type changed --message "Describe the user-facing change"
uv run changelogmanager validate
uv run changelogmanager version --reference future
```

For release preparation:

```sh
uv run changelogmanager release --dry-run
uv run changelogmanager release --bump-versions --yes
```

## Working locally

The normal local loop is:

1. `make sync`
1. make your code and doc changes
1. update `CHANGELOG.md` for user-facing behavior
1. run `make quality`
1. run `make prerelease` before release-oriented changes

`make quality` runs formatting, linting, tests, Bandit, and changelog validation.
`make prerelease` adds version checks, snapshot checks, docs sync, and a build.

## Tests and changelog safety

Tests must never write to the repository's own `CHANGELOG.md`.

The suite is already guarded for this:

- `tests/conftest.py` has an autouse `isolate_cwd` fixture that changes every test into a fresh temp directory.
- Tests should rely on `tmp_path` and relative paths.
- New tests should not derive paths from `__file__` back into the repo root for changelog operations.

If a test run leaves junk entries in the root `CHANGELOG.md`, treat that as a test isolation bug and fix the working-directory or path-resolution issue.

## GitHub Actions in this repo

Current workflows live in `.github/workflows/`:

- `build_and_test.yml`: runs on pushes to `main`, pull requests, and manual dispatch; sets up Python 3.14 plus `uv`, syncs extras, runs `make format`, then `make lint bandit test validate`
- `quality_checks.yml`: pull-request validation workflow that currently runs `make validate`
- `create_draft_release.yml`: on pushes to `main`, updates the GitHub draft release from `[Unreleased]`
- `release.yml`: triggered when a GitHub Release is published; bumps `CHANGELOG.md` and version files, opens or updates the release PR, builds artifacts, and publishes to PyPI through OIDC
- `zizmor.yml`: analyzes workflow safety when `.github/**` changes

The release automation is intentionally split:

1. keep the draft release notes synced from `[Unreleased]`
1. publish the GitHub Release when ready
1. let `release.yml` create the bump branch and PR, build, and publish

If you change release behavior, update the docs in `docs/github.md`, `docs/scripting.md`, and `docs/contributing.md` alongside the workflow file.

## Before opening a PR

1. Sync your environment with `make sync`.
1. Add or update tests for changed behavior.
1. Update `CHANGELOG.md` when the change is user-facing.
1. Run `make quality`.

## Before validating a release flow

1. Run `make prerelease`.
1. Confirm `docs/CHANGELOG.md` is in sync via `make docs-sync` if needed.
1. Double-check any workflow or release-doc changes against `.github/workflows/release.yml` and `.github/workflows/create_draft_release.yml`.
