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

That interactive setup defaults to `pyproject.toml`, `Conventional Commits`, and `semver`. If you pick `pep440` or `calver`, future `create` runs use that wording in the generated preamble.

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

By default this starts at the last git tag, falling back to full history when no tag exists. Use `--strict` to skip non-Conventional Commit subjects instead of treating them as `changed`.

## Prefer a GUI?

If you'd rather click than type, run:

```sh
changelogmanager gui
```

This opens a paneled Tkinter window for the common commands. See the [Desktop GUI](gui.md) page for details.

## What's next

- Learn the full set of [workflows](workflows.md) including GitHub releases, commit seeding, exports, and automation flags
- Read the complete [CLI reference](cli.md) for every flag and option
- Try the [Desktop GUI](gui.md) for an interactive front-end
