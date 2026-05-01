# (Keep a) Changelog Manager

CLI and Python library for managing `CHANGELOG.md` files that follow the [Keep a Changelog](https://keepachangelog.com/en/1.1.0/) format.

Fork of `keepachangelog-manager-fork`.

![gif](https://raw.githubusercontent.com/matthewdeanmartin/keepachangelog-manager/main/resources/usage.gif)

## Install

```sh
uv tool install keepachangelog-manager-fork
```

The package name on PyPI is `keepachangelog-manager-fork`. The installed commands are `changelogmanager` and `keepachangelog-manager`.

## What it does

`keepachangelog-manager` helps you:

- create and validate changelogs
- add, edit, list, and remove `[Unreleased]` entries
- infer the next SemVer release from change types
- release `[Unreleased]` with an optional confirmation guard
- seed `[Unreleased]` from git history using Conventional Commit subjects
- export changelogs as JSON, YAML, or HTML
- export a bundled CLI skill for Copilot or Claude
- create or update GitHub releases
- work with multi-component repositories via config files
- script the CLI with `--dry-run`, `--quiet`, `--json`, `--info`, and `--verbose`
- use an optional Tkinter GUI for common workflows

## Commands

```text
create
version
validate
release
to-json
to-yaml
to-html
add
remove
edit
github-release
from-commits
skill export
gui
```

## Quick examples

Add an entry:

```sh
changelogmanager add --change-type added --message "Document the new release flow"
```

Edit or remove an existing `[Unreleased]` entry:

```sh
changelogmanager remove --list
changelogmanager edit --change-type added --index 0 --message "Document the guarded release flow"
changelogmanager remove --change-type added --index 0
```

Seed `[Unreleased]` from commit history:

```sh
changelogmanager from-commits
```

Validate and autofix common issues:

```sh
changelogmanager validate --fix
```

Release non-interactively:

```sh
changelogmanager release --yes
```

Export structured output:

```sh
changelogmanager to-json
changelogmanager to-yaml
changelogmanager to-html
```

Export the bundled CLI skill:

```sh
changelogmanager skill export
```

Machine-readable mode for scripts:

```sh
changelogmanager --json version --reference future
changelogmanager --quiet validate
changelogmanager --info validate
changelogmanager --verbose from-commits --dry-run
```

`--info` and `--verbose` enable stdlib runtime logging on stderr for diagnostics. `--verbose` is the more detailed level and implies `--info`. Existing validation diagnostics still use the configured LLVM or GitHub Actions annotation format.

## Configuration

Use `--config` and `--component` for multi-component repositories:

```yaml
project:
  components:
    - name: Service
      changelog: service/CHANGELOG.md
    - name: Client
      changelog: client/CHANGELOG.md
  commits:
    style: conventional
  versioning:
    scheme: semver
  validation:
    enforce_preamble: false
```

```sh
changelogmanager --config .changelogmanager.yml --component Service validate
changelogmanager config
changelogmanager config init
changelogmanager skill export
```

If `--config` is omitted, the CLI auto-detects `.changelogmanager.yml`, `.changelogmanager.yaml`, `changelogmanager.yml`, `changelogmanager.yaml`, or `[tool.changelogmanager]` in `pyproject.toml` from the current directory.

`changelogmanager config init` is the quickest way to bootstrap config. It defaults to `pyproject.toml`, `Conventional Commits`, and `semver`, and re-running it updates the active config instead of starting from scratch.

## Optional desktop GUI

```sh
changelogmanager gui
```

The GUI currently wraps the common commands `create`, `version`, `validate`, `release`, `to-json`, `add`, and `github-release`.

## Documentation

- [Quick start](docs/quickstart.md)
- [Installation](docs/installation.md)
- [Key workflows](docs/workflows.md)
- [CLI reference](docs/cli.md)
- [Desktop GUI](docs/gui.md)
