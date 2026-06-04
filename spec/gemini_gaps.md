# Gemini Gaps: Unimplemented Features and TODOs

This document captures unimplemented features, missing commands, and other gaps identified in the `keepachangelog-manager-fork` project.

## CLI Gaps

### Backfill
The `backfill` command is partially implemented. Several sources and strategies are explicitly reserved for future phases.

- **Unimplemented Sources**:
    - `github-releases`
    - `github-prs`
    - `pypi`
- **Strategies**:
    - `--strategy merge` is implemented: it additively backfills entries into existing versions, preserving existing text, and is idempotent on re-runs.
    - `--strategy replace` is intentionally **not** supported and fast-fails. Changelog entries have no stable identity, so replacing them has no well-defined meaning in this tool. This is a deliberate design decision, not a deferred phase.
- **Reserved Arguments**:
    - `--repository`: Reserved for future phases (GitHub/GitLab/etc).
    - `--package`: Reserved for future phases (PyPI).

### Release
- `--bump-versions`: Depends on `jiggle-version` (optional extra).
- `--pyproject-only`: Linked to version bumping.

## GUI Gaps

The Tkinter GUI (`changelogmanager gui`) surfaces only a small subset of the CLI's capabilities.

### Missing Commands
The following commands are completely absent from the GUI:
- `config`
- `config init`
- `skill export`
- `remove`
- `edit`
- `to-html`
- `github-pr`
- `gitlab-release`
- `from-commits`
- `backfill`

### Missing Flags for Supported Commands
Even for commands that ARE in the GUI, many advanced flags are missing:
- `validate`: Missing `--fix`, `--all`, `--changed-only`, `--format`, `--no-format`, `--dry-run`.
- `release`: Missing `--bump-versions`, `--pyproject-only`, `--yes`.
- `to-json`: Missing `--schema-version`.
- `add`: Missing guided/interactive prompting (requires both type and message).
- **Global Flags**: The GUI does not surface `--json`, `--quiet`, `--info`, or `--verbose`.

## Interactive (Inquirer) Gaps

The "inquirer" layer provides interactive prompts in TTY mode, but it is missing for many commands:
- `create`: No guided path for picking target file or config.
- `validate`: No interactive route for `--fix`, `--all`, `--changed-only`, etc.
- `release`: No inquirer flow for override version or bump options.
- `to-json` / `to-html`: No guided export target selection.
- `from-commits` / `backfill`: No guided selection of source, schema, or strategy.

## Implementation Details & Dependencies

- **Markdown Formatting**: Autofix (`validate --fix`) supports `mdformat` but it is an optional dependency (`[format]`).
- **Version Bumping**: Supports `jiggle-version` but it is an optional dependency (`[jiggle]`).
- **Configuration**: YAML support has been completely removed in favor of TOML. Some documentation might still refer to YAML.

## Suggested Roadmap

1. ~~**Implement Local-Only Backfill Improvements**: Support merging into existing versions.~~ Done via `--strategy merge`. (`--strategy replace` is deliberately out of scope; changelog entries have no identity.)
2. **Implement Remote Backfill Sources**: Start with `github-releases` as it is high-value.
3. **Expand GUI Coverage**: Add the missing `to-html`, `remove`, `edit`, and `from-commits` commands to the GUI.
4. **Unified Interactive Layer**: Ensure all commands have a consistent Inquirer fallback when required arguments are missing in a TTY.
5. **Documentation Audit**: Clean up any remaining references to YAML or the `to-yaml` command.
