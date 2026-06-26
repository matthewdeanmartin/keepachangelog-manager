# Quick start

This page walks you from zero to a working changelog in a few minutes.

## 1. Install

```sh
uv tool install keepachangelog-manager-fork
```

## 2. Create a changelog

In your project root:

```sh
changelogmanager create
```

This writes a minimal `CHANGELOG.md`:

```markdown
# Changelog
All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).
```

If you want config first, run:

```sh
changelogmanager config init
```

That interactive setup defaults to `pyproject.toml` and `semver`, then asks whether to enforce the preamble plus the
default component name and changelog path. If you pick `pep440` or `calver`, future `create` runs use that wording in
the generated preamble.

## Already have tagged releases?

If you are adopting the tool in an existing repository, you can backfill missing
released sections from local git history before adding new unreleased entries:

```sh
changelogmanager backfill --source local --dry-run
changelogmanager backfill --source local
```

Backfill uses local tags and can classify commit subjects between tag intervals
using Conventional Commits, gitmoji, or Keep a Changelog-flavored prefixes. If
no richer commit entries are available, each missing version gets a conservative
placeholder under `Changed`, for example `Release notes unavailable; backfilled
from tag \`v1.2.3\`.` Existing versions already present in `CHANGELOG.md` are
left alone.

## 3. Add a change

```sh
changelogmanager add --change-type added --message "Initial release"
```

Your changelog now contains:

```markdown
## [Unreleased]
### Added
- Initial release
```

## 4. Release

```sh
changelogmanager release
```

The `[Unreleased]` section is renamed to the inferred next version with today's date:

```markdown
## [0.0.1] - 2024-05-01
### Added
- Initial release
```

> **If your `pyproject.toml` also contains a `version = "..."` line**, that string must
> match the released version before you build and publish. Use `--bump-versions` to update
> it in the same step:
>
> ```sh
> changelogmanager release --bump-versions --yes
> ```
>
> Without this, the changelog and `pyproject.toml` (and any `__version__` in your source)
> will drift, and your package will be published under the wrong version number.
> See [Syncing version strings](releases.md#syncing-version-strings-with---bump-versions)
> for the full details and the `[jiggle]` extra required to enable this flag.

## 5. Validate at any time

```sh
changelogmanager validate
```

No output means no errors. Errors are printed in LLVM diagnostic format by default (compatible with many editors and CI systems).

If you want the tool to clean up common issues for you, use:

```sh
changelogmanager validate --fix
```

This can reorder released versions, lowercase change-type headings, drop empty sections, and remove duplicate entries.

## 6. Edit or remove an unreleased entry

List entries with their indices:

```sh
changelogmanager remove --list
```

Update an existing entry:

```sh
changelogmanager edit --change-type added --index 0 --message "Initial public release"
```

Remove an entry:

```sh
changelogmanager remove --change-type added --index 0
```

## 7. Prefer commit history over typing?

Seed `[Unreleased]` from git commit subjects:

```sh
changelogmanager from-commits
```

By default this starts at the last git tag, falling back to full history when no tag exists. Use `--strict` to skip
subjects that do not match the selected commit schema instead of treating them as `changed`.

## Prefer a GUI?

If you'd rather click than type, run:

```sh
changelogmanager gui
```

This opens a multi-screen Tkinter app for editing `[Unreleased]`, managing
tasks and fragments, backfilling from history, auditing commit messages,
publishing releases, and running batch component operations. See the
[Desktop GUI](gui.md) page for details.

## What's next

- Learn the full set of [workflows](workflows.md) including backfill, commit seeding, exports, validation, and config patterns
- Track future release notes with [Tasks and fragments](tasks.md)
- Read the dedicated [Releasing](releases.md) guide for `version`, `release`, and `--bump-versions`
- Read the complete [CLI reference](cli.md) for every flag and option
- Try the [Desktop GUI](gui.md) for an interactive front-end
