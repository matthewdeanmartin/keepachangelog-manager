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

## What's next

- Learn the full set of [workflows](workflows.md) including GitHub releases and JSON export
- Read the complete [CLI reference](cli.md) for every flag and option
