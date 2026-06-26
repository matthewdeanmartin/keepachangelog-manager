# Releasing

This page covers the local release workflow: calculating the next version, promoting `[Unreleased]`, and optionally keeping version strings in sync outside the changelog.

For publishing to GitHub or GitLab, see [GitHub automation](github.md) and [GitLab automation](gitlab.md).

## Where your version number lives

Before using `release`, decide where your project's authoritative version number lives.

**Option A — changelog is the single source of truth.**
If your build does not read a static version string from `pyproject.toml` or source files, `changelogmanager release` is enough.

**Option B — version appears in multiple places.**
If your project also stores the version in `pyproject.toml` or Python `__version__` strings, keep those files in sync with `--bump-versions`.

## Automatic version bump

`release` inspects the change types in `[Unreleased]` and bumps the version according to the configured scheme (`semver`, `pep440`, or `calver`):

| Change type present | Bump |
|---|---|
| `removed` | Major |
| `added` or `security` | Minor |
| `changed`, `deprecated`, `fixed` only | Patch or micro |

Preview the next version:

```sh
changelogmanager version --reference future
```

Release it:

```sh
changelogmanager release --yes
```

If `[Unreleased]` exists but has no entries, the command exits successfully with a skip notice.

## Override the version explicitly

```sh
changelogmanager release --override-version 2.0.0 --yes
```

A leading `v` is accepted and stripped automatically.

## Non-interactive releases

In scripts and CI, pass `--yes`:

```sh
changelogmanager release --yes
```

Without `--yes`, non-interactive runs are refused. Use `--dry-run` first if you want a preview.

## Syncing version strings with `--bump-versions` { #syncing-version-strings-with---bump-versions }

If your project stores the version outside the changelog, use `--bump-versions` to keep everything aligned in one step. This is built in — no extra to install.

Release and sync together:

```sh
changelogmanager release --bump-versions --yes
```

That command:

1. promotes `[Unreleased]` to the released version in `CHANGELOG.md`
1. updates `[project] version` in `pyproject.toml`
1. updates Python `__version__ = "..."` strings unless you opt out

Limit the bump to `pyproject.toml` only:

```sh
changelogmanager release --bump-versions --pyproject-only --yes
```

Preview without writing:

```sh
changelogmanager release --bump-versions --dry-run
```

JSON output includes the bumped files:

```sh
changelogmanager --json release --bump-versions --yes
```

```json
{
  "released": "1.3.0",
  "bumped_version": "1.3.0",
  "bumped_files": ["pyproject.toml", "mypackage/__about__.py"]
}
```

Typical build sequence:

```sh
changelogmanager release --bump-versions --yes
uv build
uv publish
```

## Querying versions

```sh
# most recently released version
changelogmanager version

# the version before that
changelogmanager version --reference previous

# what the next release would be
changelogmanager version --reference future
```
