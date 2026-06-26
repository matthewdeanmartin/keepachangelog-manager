# Contributing

## Development setup

This project uses [uv](https://docs.astral.sh/uv/) for dependency management.
Inside this repository, prefer `make` targets and run raw Python commands through
`uv run`.

```sh
git clone https://github.com/matthewdeanmartin/keepachangelog-manager
cd keepachangelog-manager
make help
make sync
```

Common targets:

- `make format`
- `make lint`
- `make test`
- `make validate`
- `make quality`
- `make prerelease`
- `make build`

Raw command equivalents should stay inside `uv`:

```sh
uv run pytest
uv run changelogmanager --help
uv run changelogmanager gui
```

## Dogfooding the tool

This repository uses `keepachangelog-manager` on itself.

- The repo root has a real `CHANGELOG.md`.
- `pyproject.toml` contains `[tool.changelogmanager]` config.
- User-facing changes should be recorded with the CLI instead of ad-hoc editing when possible.

Typical local commands:

```sh
uv run changelogmanager add --change-type changed --message "Describe the behavior change"
uv run changelogmanager validate
uv run changelogmanager version --reference future
```

For release preparation:

```sh
uv run changelogmanager release --dry-run
uv run changelogmanager release --bump-versions --yes
```

## Local workflow

The usual contributor loop is:

1. `make sync`
1. make code and doc changes
1. update `CHANGELOG.md` for user-facing behavior
1. run `make quality`
1. run `make prerelease` for release-related work

`make quality` is the standard pre-PR check. `make prerelease` adds version checks,
snapshot checks, docs sync, and a build.

## Test isolation and changelog safety

Tests must never touch the repository's own `CHANGELOG.md`.

The suite enforces this with autouse fixtures in `tests/conftest.py`:

- each test runs from a fresh temporary working directory
- config caches are cleared between tests

When adding tests:

- use `tmp_path` and relative paths
- avoid deriving changelog paths from `__file__` back into the repo root
- rely on the isolated working directory unless a test explicitly needs to override it

If a test run pollutes the root `CHANGELOG.md`, fix the path-resolution or working-directory leak rather than simply reverting the file.

## GitHub Actions in this repository

Current workflows:

- `build_and_test.yml`: full CI on pushes to `main`, pull requests, and manual runs; installs Python 3.14 and `uv`, syncs extras, runs `make format`, then `make lint bandit test validate`
- `quality_checks.yml`: pull-request changelog validation workflow that currently runs `make validate`
- `create_draft_release.yml`: updates the GitHub draft release from `[Unreleased]` on pushes to `main`
- `release.yml`: runs after a GitHub Release is published; bumps the changelog and version files, opens or updates the release PR, builds distributions, and publishes to PyPI via OIDC
- `zizmor.yml`: checks workflow safety when `.github/**` changes

The release flow is:

1. merge changelog updates to `main`
1. let `create_draft_release.yml` refresh the GitHub draft release
1. publish the GitHub Release when ready
1. let `release.yml` perform the bump, build, and publish flow

For details, see [GitHub automation](github.md) and [Scripting and CI integration](scripting.md).

## Before submitting changes

1. Sync your environment with `make sync`.
1. Add or update tests for changed behavior.
1. Update `CHANGELOG.md` when the change is user-facing.
1. Run `make quality`.

## Before validating release changes

1. Run `make prerelease`.
1. Confirm docs and workflows still agree, especially `docs/github.md`, `docs/scripting.md`, `.github/workflows/create_draft_release.yml`, and `.github/workflows/release.yml`.
