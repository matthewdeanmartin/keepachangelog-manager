# Generic CI

This page covers changelog validation patterns that work in any CI system. GitHub-specific release automation lives in
[GitHub automation](github.md), and GitLab-specific release jobs live in [GitLab automation](gitlab.md).

## Use `validate` as a quality gate

The simplest cross-platform gate is to fail CI when the changelog is malformed:

```sh
uv sync --frozen
uv run changelogmanager validate
```

Why this works well:

- `validate` exits `1` on errors, so the job fails automatically
- the command is read-only unless you add `--fix`
- the same invocation works on GitHub Actions, GitLab CI, local pre-push hooks, and generic shell-based CI

## GitHub-style annotations when you want them

If your CI runner understands GitHub Actions annotations, use:

```sh
uv run changelogmanager --error-format github validate
```

Otherwise keep the default LLVM-style diagnostics, which work well in terminals and many editors:

```text
CHANGELOG.md:5:3: error: Incompatible change type provided, MUST be one of: Added, Changed, ...
```

## Multi-component repositories

If your repository tracks multiple changelogs in config, validate all configured components:

```sh
uv run changelogmanager --config changelogmanager.toml validate --all
```

If you only want to validate components whose changelog files changed in git:

```sh
uv run changelogmanager --config changelogmanager.toml validate --all --changed-only
```

## Machine-readable CI output

For wrapper scripts or CI helpers that want structured output:

```sh
uv run changelogmanager --json validate
uv run changelogmanager --quiet validate
```

`--json` emits one JSON object on stdout. `--quiet` suppresses the normal human-oriented output while still preserving
diagnostics and exit codes.

## Autofix in CI

`validate --fix` exists, but it is usually better in CI as a separate opt-in job or local developer command:

```sh
uv run changelogmanager validate --fix --dry-run
```

That lets CI report what would change without silently rewriting tracked files in the main validation gate.
