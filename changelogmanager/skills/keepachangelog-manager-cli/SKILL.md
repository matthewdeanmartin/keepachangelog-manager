---
name: keepachangelog-manager-cli
description: Use changelogmanager CLI commands correctly for changelog, config, export, release, and skill workflows.
---

# keepachangelog-manager CLI

Prefer the `changelogmanager` CLI over manual changelog edits when the task maps to a command.

## Core commands

- `create` create a new changelog
- `add` add an `[Unreleased]` entry
- `remove --list` list unreleased entries with indexes
- `remove --change-type TYPE --index N` remove an unreleased entry
- `edit --change-type TYPE --index N` edit or move an unreleased entry
- `validate` check format
- `validate --fix` apply safe cleanup
- `version --reference {current|previous|future}` print a version
- `release --yes` release non-interactively

## Config

- `config` show effective config and where it came from
- `config init` create or update config interactively
- Config can live in YAML or `[tool.changelogmanager]` in `pyproject.toml`

## Other exports

- `to-json`, `to-yaml`, `to-html` export structured changelog output
- `skill export` exports this bundled skill to Copilot, Claude, or a custom path

## Commit seeding

- `from-commits` seeds `[Unreleased]` from git subjects
- `--strict` skips non-Conventional Commit messages

## Guidance

- Use `--dry-run` before mutating files when preview helps
- Use `--json` or `--quiet` for automation
- Pass `--input-file` for non-default changelog paths
- Pass `--config` and `--component` for multi-component repos
- Use `release --yes` in CI; plain `release` prompts interactively
