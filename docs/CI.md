# Generic CI

## Minimal validation gate

The simplest cross-platform gate is:

```sh
uv sync --frozen
uv run changelogmanager validate
```

Why this works well:

- `validate` exits `1` on errors
- the command is read-only unless you add `--fix`
- the same invocation works in GitHub Actions, GitLab CI, pre-push hooks, and generic shell runners

## Add commit-subject linting

If you want backfill-friendly commit history, add:

```sh
uv run changelogmanager lint-commits --strict
```

This fails when commits in the selected range are not classifiable by the chosen
schema.

## GitHub-style annotations when useful

```sh
uv run changelogmanager --error-format github validate
```

Otherwise keep the default LLVM-style diagnostics:

```text
CHANGELOG.md:5:3: error: Incompatible change type provided, MUST be one of: Added, Changed, ...
```

## Multi-component repositories

Validate every configured component:

```sh
uv run changelogmanager --config changelogmanager.toml validate --all
```

Validate only components whose changelog files changed in git:

```sh
uv run changelogmanager --config changelogmanager.toml validate --all --changed-only
```

Route commits into all configured components:

```sh
uv run changelogmanager --config changelogmanager.toml from-commits --all
```

## Machine-readable CI output

```sh
uv run changelogmanager --json validate
uv run changelogmanager --quiet validate
uv run changelogmanager --json lint-commits --all-history
```

- `--json` emits one JSON object on stdout
- `--quiet` suppresses human-friendly non-error output
- diagnostics still go to stderr

## Prefer pre-commit for early feedback

If you want to stop bad changelog edits or low-signal commit subjects before CI,
use [Pre-commit](precommit.md). That is usually a better fit than teaching the
main CI gate to rewrite files for developers.

## What this repository does in GitHub Actions

This repository currently uses:

- `.github/workflows/build_and_test.yml` for full CI on pushes to `main` and PRs
- `.github/workflows/quality_checks.yml` for PR changelog validation
- `.github/workflows/zizmor.yml` for workflow safety checks

Those files are examples of how to combine `uv`, changelog validation, and
broader quality gates in a real project.
